"""
Pare Flask application entrypoint.

This is the main Flask application file that sets up all routes, handles OAuth authentication,
serves the React frontend, and provides API endpoints for email management.
"""
from __future__ import annotations
import os

# Allow OAuth to work over HTTP in development (not secure, but needed for local testing)
# In production, this should be HTTPS
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Set default port to 5001 to avoid conflict with macOS AirPlay Receiver
# macOS uses port 5000 for AirPlay, so we use 5001 instead
if "FLASK_RUN_PORT" not in os.environ:
    os.environ["FLASK_RUN_PORT"] = "5001"
if "PORT" not in os.environ:
    os.environ["PORT"] = "5001"

import json
import logging
import threading
from flask import Flask, current_app, flash, jsonify, redirect, request, session, url_for, send_from_directory
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
    update_meetings_with_email_dates,
    update_all_meetings_with_email_dates,
    upsert_credentials,
)
from services.classifier import EmailClassifier
from services.google_auth import fetch_credentials, fetch_user_profile
from services.gmail_sync import sync_recent_emails
from google_auth_oauthlib.flow import Flow
from services.inbox_service import get_dashboard_view, process_all_unprocessed, run_background_tick
from services.job_queue import get_job_queue
from services.jobs import ClassificationJob, GmailSyncJob

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _validate_required_env_vars() -> None:
    """
    Check that all required environment variables are set.
    
    This function makes sure we have all the secrets and API keys needed to run the app.
    Without these, OAuth won't work, we can't connect to Gmail, and AI classification won't work.
    """
    # GOOGLE_REDIRECT_URI is optional in development (has default in config)
    # Only validate it if explicitly set to ensure it's correct
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    # Common mistake: setting redirect URI to frontend URL instead of backend callback
    if redirect_uri and redirect_uri == "http://localhost:5173":
        raise RuntimeError(
            "GOOGLE_REDIRECT_URI is incorrectly set to the frontend URL. "
            "It must be the backend callback URL: http://localhost:5001/oauth2callback"
        )
    
    # List of all required environment variables and where to get them
    required_vars = {
        "FLASK_SECRET_KEY": os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY"),  # Used to encrypt session cookies
        "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID"),  # From Google Cloud Console
        "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET"),  # From Google Cloud Console
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),  # For AI email classification
    }
    
    # Find which variables are missing
    missing = [var for var, value in required_vars.items() if not value]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Please set these in your .env file or environment. "
            f"See .env.template for required variables."
        )


def create_app() -> Flask:
    """
    Create and configure the Flask application.
    
    This function sets up the Flask app with all routes, database connections,
    CORS settings, and background job processing. It's called when the app starts.
    """
    # Check that all required environment variables are set
    try:
        _validate_required_env_vars()
    except ValueError as e:
        logger.error(str(e))
        # In production, we must have all variables - fail fast
        if os.getenv("FLASK_ENV") == "production":
            raise
    
    # Create Flask app - we don't use Flask's built-in static file serving
    # Instead, we manually serve the React build files in production
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    
    # Configure static file serving for React build in production
    # The React app is built to frontend/dist/ and we serve it from there
    from pathlib import Path
    BASE_DIR = Path(__file__).resolve().parent
    FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
    
    # Verify frontend is built in production
    # If the dist folder doesn't exist, the build process failed
    from config import is_production
    if is_production() and not FRONTEND_DIST.exists():
        logger.error("CRITICAL: Frontend dist directory does not exist in production: %s", FRONTEND_DIST)
        logger.error("This indicates the Railway build process failed to build the frontend.")
        logger.error("Check Railway build logs to see if 'npm run build' completed successfully.")
        logger.error("Ensure nixpacks.toml is being used and Railway Build Command is empty.")
    
    # Configure CORS (Cross-Origin Resource Sharing) to allow frontend to make API calls
    # In development, the frontend runs on a different port (5173) than the backend (5001)
    # CORS allows the browser to make requests across these different origins
    frontend_url = os.getenv("FRONTEND_REDIRECT_URL", "http://localhost:5173")
    cors_origins = [
        "http://localhost:5173",  # Vite dev server default
        "http://localhost:3000",  # Alternative dev port
        "http://127.0.0.1:5173",  # Alternative localhost format
    ]
    # Add production frontend URL if it's HTTPS
    if frontend_url not in cors_origins and frontend_url.startswith("https://"):
        cors_origins.append(frontend_url)
    CORS(app, supports_credentials=True, origins=cors_origins)
    
    # Initialize database connection and create tables if they don't exist
    init_models(app)
    with app.app_context():
        ensure_tables()

    import html

    @app.template_filter("unescape")
    def unescape_filter(s):
        if not s:
            return s
        try:
            return html.unescape(str(s))
        except Exception:
            return s

    # Create the AI email classifier - this uses OpenAI to categorize emails
    classifier = EmailClassifier()
    
    # Create the job queue for background processing (syncing emails, classifying them)
    # Jobs run in separate threads so they don't block web requests
    job_queue = get_job_queue(app=app)
    
    # Thread safety: prevent multiple background tasks from running for the same user
    # This avoids duplicate work and database conflicts
    _processing_lock = threading.Lock()
    _processing_active = set()  # Track active user IDs being processed

    def _background_sync_and_process(user_id: int) -> None:
        """
        Background task to sync and process emails without blocking requests.
        
        This function runs in a separate thread so it doesn't slow down web requests.
        It syncs new emails from Gmail and classifies them using AI.
        """
        # Check if already processing for this user - avoid duplicate work
        if user_id in _processing_active:
            return  # Already processing for this user

        # Thread-safe check: use a lock to prevent race conditions
        with _processing_lock:
            if user_id in _processing_active:
                return
            _processing_active.add(user_id)

        try:
            # Use app context for database operations
            # Flask needs an app context to access the database
            with app.app_context():
                try:
                    # Run the background tick: sync emails and classify them
                    run_background_tick(user_id, classifier)
                finally:
                    # Always close the database connection when done
                    # This prevents connection leaks in background threads
                    from models.db import close_connection

                    try:
                        close_connection()
                    except Exception:
                        logger.exception("Error closing background DB connection")
        except Exception:
            # Log unexpected background errors but do not crash the app
            # Background tasks should never bring down the web server
            logger.exception("Unexpected error in background sync/process tick for user %s", user_id)
        finally:
            # Always remove user from active set, even if there was an error
            with _processing_lock:
                _processing_active.discard(user_id)

    def _ensure_session_user() -> int:
        """
        Guarantee we have a user id in session (demo fallback).
        
        If there's no logged-in user, create a demo user.
        This is useful for testing and development.
        """
        user_id = session.get("user_id")
        if user_id:
            return user_id
        # Create a demo user if no one is logged in
        demo = get_or_create_user("demo-google-id", "demo@pare.email")
        session["user_id"] = demo["id"]
        session.setdefault("user_email", demo["email"])
        return demo["id"]

    @app.route("/")
    def index():
        """Default landing page - serve React frontend in production, redirect in dev."""
        from config import is_production
        
        if is_production():
            # In production, serve the React app directly
            frontend_dist = BASE_DIR / "frontend" / "dist"
            index_path = frontend_dist / "index.html"
            if index_path.exists():
                return send_from_directory(str(frontend_dist), "index.html")
            # Fallback if build doesn't exist
            return jsonify({"error": "Frontend not built"}), 500
        else:
            # In development, redirect to Vite dev server
            frontend_url = os.getenv("FRONTEND_REDIRECT_URL", "http://localhost:5173")
            return redirect(frontend_url)

    @app.route("/dashboard")
    def dashboard():
        """Serve React frontend dashboard (handled by SPA catch-all in production)."""
        from config import is_production
        
        if is_production():
            # Let the catch-all route handle it
            frontend_dist = BASE_DIR / "frontend" / "dist"
            index_path = frontend_dist / "index.html"
            if index_path.exists():
                return send_from_directory(str(frontend_dist), "index.html")
            return jsonify({"error": "Frontend not built"}), 500
        else:
            # In development, redirect to Vite dev server
            frontend_url = os.getenv("FRONTEND_REDIRECT_URL", "http://localhost:5173")
            return redirect(f"{frontend_url}/dashboard")

    @app.route("/login")
    def login():
        """
        Kick off the Google OAuth flow.
        
        When a user clicks "Login", they're redirected here. This route:
        1. Creates a Google OAuth flow with our app's credentials
        2. Generates a unique state token for security
        3. Saves the state in the session
        4. Redirects the user to Google's login page
        
        After the user logs in with Google, Google redirects them back to /oauth2callback
        """
        try:
            # Get redirect URI from config - this is where Google sends users after login
            redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI")
            if not redirect_uri:
                raise RuntimeError("GOOGLE_REDIRECT_URI not configured")
            
            # Construct Google OAuth Flow
            # This tells Google who we are and what permissions we want
            client_config = {
                "web": {
                    "client_id": current_app.config.get("GOOGLE_CLIENT_ID"),  # Our app's ID from Google Cloud Console
                    "client_secret": current_app.config.get("GOOGLE_CLIENT_SECRET"),  # Our app's secret
                    "redirect_uris": [redirect_uri],  # Where to send users after they log in
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",  # Google's login page
                    "token_uri": "https://oauth2.googleapis.com/token",  # Where to exchange codes for tokens
                }
            }
            # Scopes = what permissions we're asking for
            scopes = current_app.config.get("GOOGLE_SCOPES", [
                "openid",  # Basic user identity
                "https://www.googleapis.com/auth/userinfo.email",  # User's email address
                "https://www.googleapis.com/auth/userinfo.profile",  # User's name
                "https://www.googleapis.com/auth/gmail.readonly",  # Read Gmail (but not send/delete)
            ])
            
            # Create the OAuth flow object
            flow = Flow.from_client_config(client_config, scopes=scopes)
            # Set redirect_uri from config
            flow.redirect_uri = redirect_uri
            
            # Generate authorization URL and state
            # The state is a random token we use to verify the callback is legitimate
            # (prevents CSRF attacks)
            auth_url, state = flow.authorization_url(
                access_type="offline",  # Get a refresh token so we can refresh access tokens
                include_granted_scopes="true",  # Include any previously granted scopes
                prompt="consent",  # Always show consent screen (ensures we get refresh token)
            )
            
            # Save state in session - CRITICAL for OAuth validation
            # When Google redirects back, we check that the state matches
            # This proves the callback came from Google, not an attacker
            session.permanent = True  # Make session last longer
            session["oauth_state"] = state
            session.modified = True  # Ensure session is saved
            
            logger.info("OAuth flow started: state=%s (first 8 chars), redirect_uri=%s", 
                       state[:8] if state else None,
                       redirect_uri)
            
            # Redirect to Google OAuth URL (never redirects to /oauth2callback directly)
            # The user will see Google's login page, then Google redirects to /oauth2callback
            return redirect(auth_url)
        except Exception as e:
            logger.exception("Error in login route: %s", e)
            return (
                f"<h1>Login Error</h1><p>Failed to start OAuth flow: {str(e)}</p>",
                500,
            )

    @app.route("/oauth2callback")
    def oauth2callback():
        """
        Handle Google's OAuth redirect and persist credentials.
        
        After the user logs in with Google, Google redirects them here with:
        - code: An authorization code we exchange for an access token
        - state: The state token we sent earlier (for security)
        
        This route:
        1. Validates the state token (prevents CSRF attacks)
        2. Exchanges the code for an access token and refresh token
        3. Gets the user's profile (email, name)
        4. Saves the credentials to the database
        5. Creates a session for the user
        6. Redirects to the frontend
        
        CRITICAL: Ignores empty callback calls (no query params) to prevent
        reload loops when frontend isn't built or app reloads.
        """
        # Helper function to get query args - handles Railway reverse proxy stripping
        # Sometimes Railway's reverse proxy strips query parameters, so we need a workaround
        def get_query_arg(key: str, default=None):
            """
            Get query argument, trying request.args first, then manual parsing.
            
            This handles cases where Railway's reverse proxy might strip query parameters.
            We try Flask's normal way first, then manually parse the query string if needed.
            """
            # Try request.args first (normal Flask behavior)
            if request.args.get(key):
                return request.args.get(key)
            # If empty, try parsing query_string manually (Railway reverse proxy workaround)
            if request.query_string:
                import urllib.parse
                try:
                    # Manually parse the query string
                    parsed = urllib.parse.parse_qs(request.query_string.decode('utf-8'))
                    if key in parsed and parsed[key]:
                        logger.info(f"Found {key} in manually parsed query string")
                        return parsed[key][0]
                except Exception as e:
                    logger.error(f"Failed to parse query string for {key}: {e}")
            return default
        
        # GUARD: Ignore empty callback calls (no query params)
        # This happens when the app reloads after frontend build error or SPA prefetch
        # Without this guard, we'd get stuck in a reload loop
        if not request.args:
            current_app.logger.info("Ignoring empty /oauth2callback hit")
            return "", 204
        
        # CRITICAL DEBUG LOGGING - Log everything about the request
        # This helps debug OAuth issues in production
        logger.info("=" * 80)
        logger.info("OAUTH2CALLBACK ROUTE HIT (with query params)")
        logger.info(f"Request URL: {request.url}")
        logger.info(f"Request query_string: {request.query_string.decode('utf-8') if request.query_string else 'EMPTY'}")
        logger.info(f"Request args: {dict(request.args)}")
        logger.info(f"Session oauth_state: {session.get('oauth_state', 'NOT FOUND')}")
        logger.info("=" * 80)
        
        # Check for OAuth errors from Google (e.g., user denied access)
        # If the user clicks "Cancel" on Google's login page, Google sends an error
        error = get_query_arg("error")
        if error:
            error_description = get_query_arg("error_description", "OAuth authentication failed")
            logger.warning("OAuth error from Google: %s - %s", error, error_description)
            return (
                f"<h1>OAuth Error</h1><p>{error_description}</p><p>Please try logging in again.</p>",
                400,
            )
        
        # Get state from Google's callback - this should match what we saved earlier
        received_state = get_query_arg("state")
        # Also get code for token exchange - this is what we trade for an access token
        auth_code = get_query_arg("code")
        # Get stored state from session - this is what we saved when they clicked login
        stored_state = session.get("oauth_state")
        
        # Debug logging
        logger.info("OAuth state check: received=%s, stored=%s", received_state, stored_state)
        
        # Validate state parameter - MUST match for security
        # This prevents CSRF attacks - if the states don't match, someone might be trying to hijack the login
        if not received_state:
            logger.error("Google did not return state parameter.")
            logger.error("Request args: %s", dict(request.args))
            logger.error("Request query_string: %s", request.query_string.decode('utf-8') if request.query_string else 'EMPTY')
            return (
                "<h1>OAuth Error</h1><p>Google did not return a state parameter. "
                "This may indicate an issue with the OAuth configuration. Please try again.</p>",
                400,
            )
        
        if not stored_state:
            # Session expired or cookies blocked - user needs to log in again
            logger.error("Session does not contain oauth_state. Session keys: %s", list(session.keys()))
            return (
                "<h1>Session Error</h1><p>The OAuth session state was not found. "
                "This may happen if cookies are blocked, the session expired, or you're using multiple browser tabs. "
                "Please ensure cookies are enabled and try logging in again.</p>",
                400,
            )
        
        if received_state != stored_state:
            # States don't match - possible attack or session issue
            logger.warning("OAuth state mismatch: received=%s, stored=%s", received_state, stored_state)
            return (
                "<h1>Invalid OAuth State</h1><p>The OAuth state parameter does not match. "
                "This may happen if the session expired or you're using multiple browser tabs. "
                "Please try logging in again.</p>",
                400,
            )
        
        # State validation passed - proceed with token exchange
        # Now we can safely exchange the authorization code for an access token
        try:
            # Reconstruct full URL with query params for token exchange
            # Railway might have stripped them, so rebuild from what we have
            base_url = f"{request.scheme}://{request.host}{request.path}"
            query_parts = []
            if received_state:
                query_parts.append(f"state={received_state}")
            if auth_code:
                query_parts.append(f"code={auth_code}")
            if error:
                query_parts.append(f"error={error}")
            
            auth_response_url = f"{base_url}?{'&'.join(query_parts)}" if query_parts else request.url
            logger.info(f"Using authorization_response URL: {auth_response_url}")
            
            # Exchange the authorization code for an access token and refresh token
            # The access token lets us make API calls to Gmail
            # The refresh token lets us get new access tokens when they expire
            credentials = fetch_credentials(
                authorization_response=auth_response_url,
                state=received_state,
            )
            # Get the user's profile (email, name) using the access token
            profile = fetch_user_profile(credentials)
        except Exception as e:
            logger.exception("OAuth authentication failed: %s", e)
            return (
                f"<h1>Authentication Failed</h1><p>Failed to exchange authorization code: {str(e)}</p>"
                "<p>Please try logging in again.</p>",
                400,
            )
        
        # Create or get user and persist credentials
        # If this is a new user, create a database record for them
        # If they've logged in before, get their existing record
        user = get_or_create_user(
            profile.get("google_user_id", "missing-id"),
            profile.get("email", "unknown@pare.email"),
        )
        # Get existing credentials if any (to preserve refresh token if we already have one)
        existing = get_credentials_for_user(user["id"])
        # Keep the refresh token if we have one (it doesn't expire)
        # If we don't have one, use the new one from Google
        refresh_token = credentials.refresh_token or (existing.get("refresh_token") if existing else None)
        # Save the credentials to the database so we can use them later
        upsert_credentials(
            user_id=user["id"],
            access_token=credentials.token or "",  # Access token (expires in 1 hour)
            refresh_token=refresh_token or "",  # Refresh token (never expires, but can be revoked)
            token_expiry=credentials.expiry.isoformat() if credentials.expiry else None,  # When access token expires
        )
        
        # Clear OAuth state and set user session
        # We don't need the state anymore, and we want to mark the user as logged in
        session.pop("oauth_state", None)
        session["user_id"] = user["id"]  # Store user ID in session
        session["user_email"] = user["email"]  # Store email in session
        session.modified = True  # Mark session as modified so Flask saves it

        # Redirect to React frontend on success
        # The user is now logged in and can use the app
        frontend_redirect = os.getenv("FRONTEND_REDIRECT_URL", "http://localhost:5173")
        logger.info("OAuth login successful for user %s, redirecting to frontend", user["email"])
        return redirect(frontend_redirect)

    @app.route("/meetings")
    def meetings_view():
        """Serve React frontend meetings page (handled by SPA catch-all in production)."""
        from config import is_production
        
        if is_production():
            frontend_dist = BASE_DIR / "frontend" / "dist"
            index_path = frontend_dist / "index.html"
            if index_path.exists():
                return send_from_directory(str(frontend_dist), "index.html")
            return jsonify({"error": "Frontend not built"}), 500
        else:
            frontend_url = os.getenv("FRONTEND_REDIRECT_URL", "http://localhost:5173")
            return redirect(f"{frontend_url}/meetings")

    @app.route("/tasks")
    def tasks_view():
        """Serve React frontend tasks page (handled by SPA catch-all in production)."""
        from config import is_production
        
        if is_production():
            frontend_dist = BASE_DIR / "frontend" / "dist"
            index_path = frontend_dist / "index.html"
            if index_path.exists():
                return send_from_directory(str(frontend_dist), "index.html")
            return jsonify({"error": "Frontend not built"}), 500
        else:
            frontend_url = os.getenv("FRONTEND_REDIRECT_URL", "http://localhost:5173")
            return redirect(f"{frontend_url}/tasks")

    @app.route("/junk")
    def junk_view():
        """Serve React frontend junk page (handled by SPA catch-all in production)."""
        from config import is_production
        
        if is_production():
            frontend_dist = BASE_DIR / "frontend" / "dist"
            index_path = frontend_dist / "index.html"
            if index_path.exists():
                return send_from_directory(str(frontend_dist), "index.html")
            return jsonify({"error": "Frontend not built"}), 500
        else:
            frontend_url = os.getenv("FRONTEND_REDIRECT_URL", "http://localhost:5173")
            return redirect(f"{frontend_url}/junk")

    @app.route("/analytics")
    def analytics_view():
        """Serve React frontend analytics page (handled by SPA catch-all in production)."""
        from config import is_production
        
        if is_production():
            frontend_dist = BASE_DIR / "frontend" / "dist"
            index_path = frontend_dist / "index.html"
            if index_path.exists():
                return send_from_directory(str(frontend_dist), "index.html")
            return jsonify({"error": "Frontend not built"}), 500
        else:
            frontend_url = os.getenv("FRONTEND_REDIRECT_URL", "http://localhost:5173")
            return redirect(f"{frontend_url}/analytics")

    # ------------------------------------------------------------------ #
    # JSON API endpoints for React frontend
    # ------------------------------------------------------------------ #
    # These routes return JSON data that the React frontend uses to display information
    # They don't return HTML - just raw data

    @app.route("/api/dashboard")
    def api_dashboard():
        """
        Return dashboard payload as JSON for React frontend.
        
        This endpoint returns all the data needed to display the main dashboard:
        - Sync statistics (how many emails synced, processed, etc.)
        - Analytics (category counts, totals)
        - Recent meetings
        - Recent tasks
        - Recent junk emails
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        
        # Get all dashboard data
        sync_stats, analytics, meetings, tasks, junk_emails = get_dashboard_view(user_id)
        
        # Backfill body from raw_json if body is empty for all email lists
        # Sometimes the email body wasn't extracted during sync, so we extract it now
        from services.gmail_sync import extract_body_from_raw_json
        
        # For each meeting, if the body is missing, try to extract it from raw_json
        for meeting in meetings:
            if not meeting.get("body") or not meeting.get("body", "").strip():
                raw_json = meeting.get("raw_json")
                if raw_json:
                    extracted_body = extract_body_from_raw_json(raw_json)
                    if extracted_body:
                        meeting["body"] = extracted_body
        
        # Same for tasks
        for task in tasks:
            if not task.get("body") or not task.get("body", "").strip():
                raw_json = task.get("raw_json")
                if raw_json:
                    extracted_body = extract_body_from_raw_json(raw_json)
                    if extracted_body:
                        task["body"] = extracted_body
        
        # Same for junk emails
        for email in junk_emails:
            if not email.get("body") or not email.get("body", "").strip():
                raw_json = email.get("raw_json")
                if raw_json:
                    extracted_body = extract_body_from_raw_json(raw_json)
                    if extracted_body:
                        email["body"] = extracted_body
        
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
        # Backfill body from raw_json if body is empty
        from services.gmail_sync import extract_body_from_raw_json
        for meeting in meetings:
            if not meeting.get("body") or not meeting.get("body", "").strip():
                raw_json = meeting.get("raw_json")
                if raw_json:
                    extracted_body = extract_body_from_raw_json(raw_json)
                    if extracted_body:
                        meeting["body"] = extracted_body
        return jsonify(meetings)

    @app.route("/api/tasks")
    def api_tasks():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        tasks = fetch_tasks(user_id)
        # Backfill body from raw_json if body is empty
        from services.gmail_sync import extract_body_from_raw_json
        for task in tasks:
            if not task.get("body") or not task.get("body", "").strip():
                raw_json = task.get("raw_json")
                if raw_json:
                    extracted_body = extract_body_from_raw_json(raw_json)
                    if extracted_body:
                        task["body"] = extracted_body
        return jsonify(tasks)

    @app.route("/api/junk")
    def api_junk():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        junk_emails = fetch_junk_emails(user_id)
        # Backfill body from raw_json if body is empty
        from services.gmail_sync import extract_body_from_raw_json
        for email in junk_emails:
            if not email.get("body") or not email.get("body", "").strip():
                raw_json = email.get("raw_json")
                if raw_json:
                    extracted_body = extract_body_from_raw_json(raw_json)
                    if extracted_body:
                        email["body"] = extracted_body
        return jsonify(junk_emails)

    @app.route("/api/analytics")
    def api_analytics():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        analytics = fetch_analytics(user_id)
        summary = fetch_category_summary(user_id)
        return jsonify({"analytics": analytics, "summary": summary})

    @app.route("/api/update-meeting-dates", methods=["POST"])
    def api_update_meeting_dates():
        """Update meetings with missing or invalid start_time to use email dates."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        
        # Get update mode from request (default to conservative update)
        update_all = False
        if request.is_json and request.json:
            update_all = request.json.get("update_all", False)
        
        try:
            if update_all:
                # More aggressive: update all meetings with potentially invalid dates
                count = update_all_meetings_with_email_dates()
            else:
                # Conservative: only update meetings with clearly missing/invalid dates
                count = update_meetings_with_email_dates()
            
            return jsonify({
                "success": True,
                "meetings_updated": count,
                "message": f"Updated {count} meeting(s) with email dates"
            })
        except Exception as e:
            logger.exception("Error updating meeting dates: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/sync", methods=["POST"])
    def api_sync():
        """
        Start a background Gmail sync job. Returns immediately.
        
        This endpoint starts syncing emails from Gmail in the background.
        It doesn't wait for the sync to finish - it just queues the job and returns.
        The frontend can check the job status using /api/sync/status/<job_id>
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        
        # Get max_results from request, default to 500
        # This is how many emails to fetch from Gmail
        max_results = 500
        if request.is_json and request.json:
            max_results = request.json.get("max_results", 500)
        
        # Create and enqueue sync job
        # The job will run in a background thread so it doesn't block the web request
        job_queue = get_job_queue()
        sync_job = GmailSyncJob.create(user_id, max_results=max_results)
        if not sync_job._execute_fn:
            return jsonify({"error": "Failed to create sync job"}), 500
        job_id = job_queue.enqueue(
            job_type="gmail_sync",
            user_id=user_id,
            execute_fn=sync_job._execute_fn,
        )
        
        logger.info(f"Enqueued sync job {job_id} for user {user_id}")
        
        return jsonify({
            "status": "queued",  # Job is in the queue, not running yet
            "job_id": job_id,  # Use this to check status later
            "message": "Sync started in background",
        })

    @app.route("/api/sync/status/<job_id>")
    def api_sync_status(job_id: str):
        """Get the status of a sync job."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated"}), 401
        
        job_queue = get_job_queue()
        job = job_queue.get_job(job_id)
        
        if not job:
            return jsonify({"error": "Job not found"}), 404
        
        # Verify job belongs to user
        if job.user_id != user_id:
            return jsonify({"error": "Unauthorized"}), 403
        
        # Build response
        response = {
            "job_id": job_id,
            "status": job.status.value,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }
        
        if job.started_at:
            response["started_at"] = job.started_at.isoformat()
        if job.completed_at:
            response["completed_at"] = job.completed_at.isoformat()
        if job.progress:
            response["progress"] = job.progress
        if job.error:
            response["error"] = job.error
        if job.result:
            response["result"] = job.result
        
        return jsonify(response)

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
        processed = process_all_unprocessed(user_id, classifier)
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
        processed = process_all_unprocessed(user_id, classifier)
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

    # ------------------------------------------------------------------ #
    # Static file serving and SPA catch-all (PRODUCTION ONLY)
    # ------------------------------------------------------------------ #
    # CRITICAL: Routes are ordered so /oauth2callback is handled first
    # This catch-all must come LAST to serve React SPA for all other routes
    
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path: str):
        """
        Serve React SPA for all routes except backend API and OAuth routes.
        
        This is a catch-all route that serves the React frontend.
        In production, the React app is built to frontend/dist/ and we serve it from there.
        
        This catch-all route:
        - Serves static assets (JS, CSS, images) from frontend/dist
        - Serves index.html for SPA routes (React Router handles client-side routing)
        - Returns 204 for /oauth2callback to prevent reload loops
        - Logs warning if dist is missing (doesn't break OAuth)
        
        The route order is important: this must come LAST so it doesn't catch API routes.
        """
        dist = Path(__file__).resolve().parent / "frontend" / "dist"
        
        # If dist does not exist, do not break OAuth
        # OAuth callback should still work even if frontend isn't built
        if not dist.exists():
            current_app.logger.error("Frontend dist missing at: %s", dist)
            current_app.logger.error("Current working directory: %s", Path.cwd())
            current_app.logger.error("App file location: %s", Path(__file__).resolve().parent)
            # List what's actually in frontend directory (for debugging)
            frontend_dir = Path(__file__).resolve().parent / "frontend"
            if frontend_dir.exists():
                current_app.logger.error("Frontend directory contents: %s", list(frontend_dir.iterdir()))
            return {"error": "Frontend not built"}, 500
        
        # Never let SPA fallback hijack the OAuth callback
        # /oauth2callback must be handled by the backend route above, not this catch-all
        if path.startswith("oauth2callback"):
            return "", 204
        
        # Try to serve the requested file if it exists
        # This handles static assets like JS, CSS, images
        target = dist / path
        if path and target.exists() and target.is_file():
            return send_from_directory(str(dist), path)
        
        # Check in assets subdirectory (Vite puts assets there)
        # Vite builds the React app and puts JS/CSS files in an assets/ folder
        if path:
            assets_target = dist / "assets" / path
            if assets_target.exists() and assets_target.is_file():
                return send_from_directory(str(dist / "assets"), path)
        
        # For all other routes (including root), serve index.html (SPA fallback)
        # React Router will handle the routing on the client side
        # This is how single-page applications work - all routes serve the same HTML file
        return send_from_directory(str(dist), "index.html")

    return app


# Create app instance for Gunicorn
app = create_app()

if __name__ == "__main__":
    # Use 5001 instead of 5000 to avoid conflict with macOS AirPlay Receiver
    port = int(os.getenv("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "False").lower() == "true")
