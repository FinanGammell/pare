"""Pare Flask application entrypoint."""
from __future__ import annotations

from flask import Flask, flash, redirect, render_template, request, session, url_for

from config import Config
from models import (
    EmailCategory,
    ensure_tables,
    fetch_analytics,
    fetch_category_summary,
    fetch_junk_emails,
    fetch_meetings,
    fetch_tasks,
    get_credentials_for_user,
    get_or_create_user,
    init_app as init_models,
    upsert_credentials,
)
from services.classifier import EmailClassifier
from services.google_auth import GoogleAuthService
from services.gmail_sync import sync_recent_emails


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    init_models(app)
    with app.app_context():
        ensure_tables()

    classifier = EmailClassifier()
    google_auth_service = GoogleAuthService(Config)

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
        """Default landing page."""
        return render_template(
            "index.html",
            message="Hello, Pare",
            user_email=session.get("user_email"),
        )

    @app.route("/dashboard")
    def dashboard():
        """Render a placeholder dashboard grouped by category."""
        user_id = _ensure_session_user()
        user_email = session.get("user_email", "demo@pare.email")
        analytics = fetch_analytics(user_id)
        meetings = fetch_meetings(user_id, limit=4)
        tasks = fetch_tasks(user_id, limit=6)
        junk_emails = fetch_junk_emails(user_id, limit=6)
        return render_template(
            "dashboard.html",
            user_email=user_email,
            analytics=analytics,
            meetings=meetings,
            tasks=tasks,
            junk_emails=junk_emails,
        )

    @app.route("/login")
    def login():
        """Kick off the Google OAuth flow."""
        authorization_url, state = google_auth_service.authorization_url()
        session["oauth_state"] = state
        return redirect(authorization_url)

    @app.route("/oauth2callback")
    def oauth2callback():
        """Handle Google's OAuth redirect and persist credentials."""
        state = request.args.get("state")
        stored_state = session.get("oauth_state")
        if not state or state != stored_state:
            return redirect(url_for("index"))

        try:
            credentials = google_auth_service.fetch_credentials(
                authorization_response=request.url,
                state=state,
            )
            profile = google_auth_service.fetch_user_profile(credentials)
        except Exception as e:
            flash(f"OAuth authentication failed: {str(e)}", "error")
            return redirect(url_for("index"))
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
        session.pop("oauth_state", None)
        session["user_id"] = user["id"]
        session["user_email"] = user["email"]

        sync_recent_emails(user_id=user["id"], max_results=50)
        classifier.process_all_unprocessed_emails(user["id"])
        return redirect(url_for("dashboard"))

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

    @app.route("/logout")
    def logout():
        """Clear the local session."""
        session.clear()
        return redirect(url_for("index"))

    @app.route("/sync")
    def sync_mailbox():
        """Manual sync trigger."""
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in with Google first.", "warning")
            return redirect(url_for("index"))
        synced_emails = sync_recent_emails(user_id=user_id, max_results=300)
        processed = classifier.process_all_unprocessed_emails(user_id)
        flash(
            f"Synced {len(synced_emails)} emails from Gmail. Processed {processed} emails with AI.",
            "success",
        )
        return redirect(url_for("dashboard"))

    @app.route("/process")
    def process_emails():
        """Run AI classification against any emails lacking metadata."""
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in with Google first.", "warning")
            return redirect(url_for("index"))
        processed = classifier.process_all_unprocessed_emails(user_id)
        if processed:
            flash(f"Processed {processed} emails with Pare AI.", "success")
        else:
            flash("No emails left to process.", "info")
        return redirect(url_for("dashboard"))

    return app


# Create app instance for Gunicorn
app = create_app()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "False").lower() == "true")
