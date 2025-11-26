"""Google OAuth helpers for Pare."""
from __future__ import annotations

import json
from typing import Dict, Tuple

from flask import current_app, url_for
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_AUTH_PROVIDER_CERT_URL = "https://www.googleapis.com/oauth2/v1/certs"


class GoogleAuthService:
    """Wrap OAuth flow creation and user profile fetching."""

    def __init__(self, config) -> None:
        self.config = config

    def _get_redirect_uri(self) -> str:
        """Get OAuth redirect URI, using url_for if available, otherwise from config."""
        try:
            # Try to use url_for for dynamic redirect URI (works in Flask app context)
            with current_app.app_context():
                redirect_uri = url_for("oauth2callback", _external=True)
                return redirect_uri
        except (RuntimeError, AttributeError):
            # Fallback to config if not in app context or url_for fails
            if self.config.GOOGLE_REDIRECT_URI:
                return self.config.GOOGLE_REDIRECT_URI
            # Last resort: construct from Railway domain or localhost
            railway_domain = self.config.RAILWAY_PUBLIC_DOMAIN
            if railway_domain:
                return f"https://{railway_domain}/oauth2callback"
            return "http://localhost:5000/oauth2callback"

    def _flow(self, state: str | None = None) -> Flow:
        redirect_uri = self._get_redirect_uri()
        client_config = {
            "web": {
                "client_id": self.config.GOOGLE_CLIENT_ID,
                "project_id": "pare-email-suite",
                "auth_uri": GOOGLE_AUTH_URI,
                "token_uri": GOOGLE_TOKEN_URI,
                "auth_provider_x509_cert_url": GOOGLE_AUTH_PROVIDER_CERT_URL,
                "client_secret": self.config.GOOGLE_CLIENT_SECRET,
                "redirect_uris": [redirect_uri],
            }
        }
        flow = Flow.from_client_config(
            client_config,
            scopes=self.config.GOOGLE_SCOPES,
            state=state,
        )
        flow.redirect_uri = redirect_uri
        return flow

    def authorization_url(self) -> Tuple[str, str]:
        """Return a Google OAuth authorization URL + state."""
        flow = self._flow()
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return authorization_url, state

    def fetch_credentials(self, authorization_response: str, state: str | None):
        """Exchange the auth code for credentials using the provided state."""
        flow = self._flow(state)
        flow.fetch_token(authorization_response=authorization_response)
        return flow.credentials

    def fetch_user_profile(self, credentials) -> Dict[str, str]:
        """Retrieve the user's profile via Google OAuth2 API."""
        oauth_service = build("oauth2", "v2", credentials=credentials, cache_discovery=False)
        user_info = oauth_service.userinfo().get().execute()
        return {
            "google_user_id": user_info.get("id"),
            "email": user_info.get("email"),
            "name": user_info.get("name"),
        }
