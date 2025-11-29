"""Pare Flask application entrypoint."""
from __future__ import annotations
import os
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
# Set default port to 5001 to avoid conflict with macOS AirPlay Receiver
if "FLASK_RUN_PORT" not in os.environ:
    os.environ["FLASK_RUN_PORT"] = "5001"
if "PORT" not in os.environ:
    os.environ["PORT"] = "5001"

import json
import logging
import threading
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_cors import CORS

from config import Config
from models import (
    EmailCategory,
    clear_user_data,
    ensure_tables,
    fetch_analytics,
    fetch_category_summary,
    fetch_junk_emails,
    fetch_meetings,
    fetch_tasks,
    get_credentials_for_user,
    get_email_by_message_id,
    get_or_create_user,
    hide_email,
    init_app as init_models,
    upsert_credentials,
)
from services.classifier import EmailClassifier
from services.google_auth import GoogleAuthService
from services.gmail_sync import sync_recent_emails
from services.inbox_service import InboxService

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _validate_required_env_vars() -> None:
    """Validate that all required environment variables are set.
    
    Raises ValueError with a clear message if any are missing.
    """
    required_vars = {
        "FLASK_SECRET_KEY": os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY"),
        "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID"),
        "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET"),
        "GOOGLE_REDIRECT_URI": os.getenv("GOOGLE_REDIRECT_URI"),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
    }
    
    missing = [var for var, value in required_vars.items() if not value]
    if missing:
        # For OAuth specifically we want a hard fail if GOOGLE_REDIRECT_URI is missing.
        if "GOOGLE_REDIRECT_URI" in missing:
            raise RuntimeError(
                "Missing GOOGLE_REDIRECT_URI. OAuth cannot start. "
                "Set GOOGLE_REDIRECT_URI to either "
                "http://localhost:5001/oauth2callback (local) or "
                "https://pare.up.railway.app/oauth2callback (production)."
            )
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Please set these in your .env file or environment. "
            f"See .env.template for required variables."
        )


def create_app() -> Flask:
    # Validate required environment variables at startup
    try:
        _validate_required_env_vars()
    except ValueError as e:
        logger.error(str(e))
        # In production, we might want to fail fast, but for development
        # we'll log the error and continue (some routes may work without all vars)
        if os.getenv("FLASK_ENV") == "production":
            raise
    
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    # Enable CORS for React frontend
    # Get frontend URL from environment or use defaults
    frontend_url = os.getenv("FRONTEND_REDIRECT_URL", "http://localhost:5173")
    cors_origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]
    # Add production frontend URL if different from localhost
    if frontend_url not in cors_origins and frontend_url.startswith("https://"):
        cors_origins.append(frontend_url)
    CORS(app, supports_credentials=True, origins=cors_origins)
    init_models(app)
    with app.app_context():
        ensure_tables()  # This will also remove duplicates and add constraints

    # Add Jinja2 filter to decode HTML entities
    import html

    @app.template_filter("unescape")
    def unescape_filter(s):
        """Decode HTML entities in template strings."""
        if not s:
            return s
        try:
            return html.unescape(str(s))
        except Exception:
            return s

    classifier = EmailClassifier()
    google_auth_service = GoogleAuthService(Config)
    inbox_service = InboxService(classifier)

    # Background processing lock to prevent multiple threads from processing simultaneously
    _processing_lock = threading.Lock()
    _processing_active = set()  # Track active user IDs being processed

    def _background_sync_and_process(user_id: int) -> None:
        """Background task to sync and process emails without blocking requests."""
        # Check if already processing for this user
        if user_id in _processing_active:
            return  # Already processing for this user

        with _processing_lock:
            if user_id in _processing_active:
                return
            _processing_active.add(user_id)

        try:
            # Use app context for database operations
            with app.app_context():
                try:
                    inbox_service.run_background_tick(user_id)
                finally:
                    # Ensure database connection is closed for this thread
                    from models.db import close_connection

                    try:
                        close_connection()
                    except Exception:
                        logger.exception("Error closing background DB connection")
        except Exception:
            # Log unexpected background errors but do not crash the app
            logger.exception("Unexpected error in background sync/process tick for user %s", user_id)
        finally:
            with _processing_lock:
                _processing_active.discard(user_id)

    def _ensure_session_user() -> int:
        """Guarantee we have a user id in session (demo fallback)."""
        user_id = session.get("user_id")
        if user_id:
            return user_id
        demo = get_or_create_user("demo-google-id", "demo@pare.email")
        session["user_id"] = demo["id"]
        session.setdefault("user_email", demo["email"])
        return demo["id"]

    @app.route("/")
    def index():
        """Default landing page - redirect to dashboard if logged in, otherwise show landing page."""
        user_id = session.get("user_id")
        if user_id:
            return redirect(url_for("dashboard"))
        return render_template(
            "index.html",
            message="Hello, Pare",
            user_email=session.get("user_email"),
        )

    @app.route("/dashboard")
    def dashboard():
        """Render dashboard immediately, process emails in background."""
        user_id = _ensure_session_user()
        user_email = session.get("user_email", "demo@pare.email")

        # Get current stats and dashboard data (fast, no processing)
        sync_stats, analytics, meetings, tasks, junk_emails = inbox_service.get_dashboard_view(user_id)

        # Trigger background processing (non-blocking, won't block page load)
        # Only start if not already processing for this user
        if user_id not in _processing_active:
            thread = threading.Thread(
                target=_background_sync_and_process,
                args=(user_id,),
                daemon=True,
            )
            thread.start()

        return render_template(
            "dashboard.html",
            user_email=user_email,
            analytics=analytics,
            meetings=meetings,
            tasks=tasks,
            junk_emails=junk_emails,
            sync_stats=sync_stats,
        )

    @app.route("/login")
    def login():
        """Kick off the Google OAuth flow."""
        try:
            authorization_url, state = google_auth_service.authorization_url()
            session["oauth_state"] = state
            return redirect(authorization_url)
        except Exception as e:
            logger.exception("Error in login route: %s", e)
            flash(f"Login failed: {str(e)}", "error")
            return redirect(url_for("index"))

    @app.route("/oauth2callback")
    def oauth2callback():
        """Handle Google's OAuth redirect and persist credentials.
        
        After successful authentication, redirects to the React frontend.
        Session is preserved via cookies (CORS with credentials).
        """
        # Get frontend redirect URL from environment
        frontend_redirect = os.getenv("FRONTEND_REDIRECT_URL", "http://localhost:5173")
        
        # Check for access denied
        error = request.args.get("error")
        if error:
            error_description = request.args.get("error_description", "Access denied")
            logger.warning("OAuth error: %s - %s", error, error_description)
            # Redirect to frontend with error parameter
            return redirect(f"{frontend_redirect}?error={error}&error_description={error_description}")
        
        # Validate state parameter
        state = request.args.get("state")
        stored_state = session.get("oauth_state")
        if not state or state != stored_state:
            logger.warning("OAuth state mismatch or missing state parameter")
            # Redirect to frontend with error parameter
            return redirect(f"{frontend_redirect}?error=invalid_state&error_description=Invalid OAuth state. Please try logging in again.")

        try:
            credentials = google_auth_service.fetch_credentials(
                authorization_response=request.url,
                state=state,
            )
            profile = google_auth_service.fetch_user_profile(credentials)
        except Exception as e:
            logger.exception("OAuth authentication failed: %s", e)
            # Redirect to frontend with error parameter
            return redirect(f"{frontend_redirect}?error=auth_failed&error_description={str(e)}")
        
        # Create or get user and persist credentials
        user = get_or_create_user(
            profile.get("google_user_id", "missing-id"),
            profile.get("email", "unknown@pare.email"),
        )
        existing = get_credentials_for_user(user["id"])
        refresh_token = credentials.refresh_token or (existing.get("refresh_token") if existing else None)
        upsert_credentials(
            user_id=user["id"],
            access_token=credentials.token or "",
            refresh_token=refresh_token or "",
            token_expiry=credentials.expiry.isoformat() if credentials.expiry else None,
        )
        
        # Set session (preserved via cookies for frontend)
        session.pop("oauth_state", None)
        session["user_id"] = user["id"]
        session["user_email"] = user["email"]
        
        # Redirect to React frontend - session cookie will be sent automatically
        logger.info("OAuth login successful for user %s, redirecting to frontend", user["email"])
        return redirect(frontend_redirect)

    @app.route("/meetings")
    def meetings_view():
        """Display meeting insights extracted from emails."""
        user_id = _ensure_session_user()
        meetings = fetch_meetings(user_id)
        return render_template(
            "meetings.html",
            user_email=session.get("user_email"),
            meetings=meetings,
        )

    @app.route("/tasks")
    def tasks_view():
        """Display detected tasks."""
        user_id = _ensure_session_user()
        tasks = fetch_tasks(user_id)
        return render_template(
            "tasks.html",
            user_email=session.get("user_email"),
            tasks=tasks,
        )

    @app.route("/junk")
    def junk_view():
        """Show newsletters and junk mail."""
        user_id = _ensure_session_user()
        junk_emails = fetch_junk_emails(user_id)
        return render_template(
            "junk.html",
            user_email=session.get("user_email"),
            junk_emails=junk_emails,
        )

    @app.route("/analytics")
    def analytics_view():
        """Display Pare analytics for the inbox."""
        user_id = _ensure_session_user()
        analytics = fetch_analytics(user_id)
        summary = fetch_category_summary(user_id)
        return render_template(
            "analytics.html",
            user_email=session.get("user_email"),
            analytics=analytics,
            summary=summary,
        )

    # ------------------------------------------------------------------ #
    # JSON API endpoints for React frontend
    # ------------------------------------------------------------------ #

    @app.route("/api/dashboard")
    def api_dashboard():
        """Return dashboard payload as JSON for React frontend."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        
        sync_stats, analytics, meetings, tasks, junk_emails = inbox_service.get_dashboard_view(user_id)
        # meetings/tasks/junk_emails are already shaped similarly to templates; they can be
        # consumed directly by the React app.
        return jsonify(
            {
                "sync_stats": sync_stats,
                "analytics": analytics,
                "meetings": meetings,
                "tasks": tasks,
                "junk_emails": junk_emails,
            }
        )

    @app.route("/api/meetings")
    def api_meetings():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        meetings = fetch_meetings(user_id)
        return jsonify(meetings)

    @app.route("/api/tasks")
    def api_tasks():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        tasks = fetch_tasks(user_id)
        return jsonify(tasks)

    @app.route("/api/junk")
    def api_junk():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        junk_emails = fetch_junk_emails(user_id)
        return jsonify(junk_emails)

    @app.route("/api/analytics")
    def api_analytics():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        analytics = fetch_analytics(user_id)
        summary = fetch_category_summary(user_id)
        return jsonify({"analytics": analytics, "summary": summary})

    @app.route("/logout")
    def logout():
        """Clear the local session."""
        session.clear()
        return redirect(url_for("index"))

    @app.route("/hide-email/<int:email_id>", methods=["POST"])
    def hide_email_route(email_id: int):
        """Hide an email so it doesn't appear in lists."""
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in first.", "warning")
            return redirect(url_for("index"))
        
        hide_email(user_id, email_id)
        # Return to the page that made the request, or dashboard
        referer = request.headers.get("Referer")
        if referer:
            # Extract path from referer
            try:
                from urllib.parse import urlparse
                parsed = urlparse(referer)
                if parsed.path:
                    return redirect(parsed.path)
            except Exception:
                pass
        return redirect(url_for("dashboard"))

    @app.route("/api/hide-email/<int:email_id>", methods=["POST"])
    def api_hide_email(email_id: int):
        """Hide an email via API (for React frontend)."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        
        try:
            hide_email(user_id, email_id)
            return jsonify({"success": True, "message": "Email hidden"})
        except Exception as e:
            logger.exception("Error hiding email %s: %s", email_id, e)
            return jsonify({"error": str(e)}), 500

    @app.route("/clear-data", methods=["POST"])
    def clear_data():
        """Clear all data for the current user. Use with caution!"""
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in first.", "warning")
            return redirect(url_for("index"))
        
        clear_user_data(user_id)
        session.clear()
        flash("All data cleared. Please log in again.", "success")
        return redirect(url_for("index"))
    
    @app.route("/remove-duplicates", methods=["POST"])
    def remove_duplicates_route():
        """Remove duplicate emails and related data."""
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in first.", "warning")
            return redirect(url_for("index"))
        
        try:
            from models import remove_duplicates
            remove_duplicates()
            flash("Duplicates removed successfully.", "success")
        except Exception as e:
            flash(f"Error removing duplicates: {str(e)}", "error")
        return redirect(url_for("dashboard"))

    @app.route("/sync")
    def sync_mailbox():
        """Manual sync trigger (legacy)."""
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in with Google first.", "warning")
            return redirect(url_for("index"))
        synced_emails = sync_recent_emails(user_id=user_id, max_results=300)
        processed = inbox_service.process_all_unprocessed(user_id)
        flash(
            f"Synced {len(synced_emails)} emails from Gmail. Processed {processed} emails with AI.",
            "success",
        )
        return redirect(url_for("dashboard"))

    @app.route("/process")
    def process_emails():
        """Run AI classification against any emails lacking metadata (legacy)."""
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in with Google first.", "warning")
            return redirect(url_for("index"))
        processed = inbox_service.process_all_unprocessed(user_id)
        if processed:
            flash(f"Processed {processed} emails with Pare AI.", "success")
        else:
            flash("No emails left to process.", "info")
        return redirect(url_for("dashboard"))

    @app.route("/open_email/<gmail_message_id>")
    def open_email(gmail_message_id: str):
        """Redirect to Gmail thread view for a specific email."""
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in with Google first.", "warning")
            return redirect(url_for("index"))
        
        email = get_email_by_message_id(user_id, gmail_message_id)
        if not email:
            flash("Email not found.", "error")
            return redirect(url_for("dashboard"))
        
        # Extract threadId from raw_json
        thread_id = None
        raw_json_str = email.get("raw_json")
        if raw_json_str:
            try:
                if isinstance(raw_json_str, str):
                    raw_json = json.loads(raw_json_str)
                else:
                    raw_json = raw_json_str
                thread_id = raw_json.get("threadId")
            except (json.JSONDecodeError, AttributeError):
                pass
        
        # Use thread ID if available, otherwise fall back to message ID search
        if thread_id:
            gmail_url = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"
        else:
            # Fallback: search for the message ID
            gmail_url = f"https://mail.google.com/mail/u/0/#search/rfc822msgid%3A{gmail_message_id}"
        
        return redirect(gmail_url)

    return app


# Create app instance for Gunicorn
app = create_app()

if __name__ == "__main__":
    # Use 5001 instead of 5000 to avoid conflict with macOS AirPlay Receiver
    port = int(os.getenv("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "False").lower() == "true")
