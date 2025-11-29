"""Google OAuth helpers for Pare."""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, Tuple

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"


class GoogleAuthService:
    """Wrap OAuth flow creation and user profile fetching."""

    def __init__(self, config) -> None:
        self.config = config

    def _get_redirect_uri(self) -> str:
        """Return the OAuth redirect URI from environment only.

        The value **must** be provided via GOOGLE_REDIRECT_URI.
        """
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        if not redirect_uri:
            # This should already be validated at startup, but we keep a guard here.
            raise RuntimeError(
                "GOOGLE_REDIRECT_URI is not set. OAuth cannot start. "
                "Set GOOGLE_REDIRECT_URI to either "
                "http://localhost:5001/oauth2callback (local) or "
                "https://pare.up.railway.app/oauth2callback (production)."
            )
        return redirect_uri

    def _flow(self, state: str | None = None) -> Flow:
        """Create a unified OAuth Flow configuration using env vars only.
        
        Google Identity Platform automatically adds 'openid', so we must
        explicitly include it in our requested scopes to avoid scope mismatch errors.
        """
        redirect_uri = self._get_redirect_uri()

        # Unified OAuth Flow configuration - must match exactly across all Flow instances
        client_config = {
            "web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uris": [os.getenv("GOOGLE_REDIRECT_URI")],
                "auth_uri": GOOGLE_AUTH_URI,
                "token_uri": GOOGLE_TOKEN_URI,
            }
        }

        # CRITICAL: Must include "openid" first, as Google Identity Platform adds it automatically
        scopes = [
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/gmail.readonly",
        ]

        flow = Flow.from_client_config(
            client_config,
            scopes=scopes,
            state=state,
        )
        flow.redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        return flow

    def authorization_url(self) -> Tuple[str, str]:
        """Return a Google OAuth authorization URL + state."""
        flow = self._flow()
        # Debug logs to verify OAuth configuration
        # Get scopes from the Flow's internal oauth2session
        scopes_list = getattr(flow.oauth2session, 'scope', [])
        if isinstance(scopes_list, str):
            scopes_list = scopes_list.split()
        print("DEBUG: OAuth scopes being requested:", scopes_list)
        print("DEBUG: redirect_uri being used:", flow.redirect_uri)
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return authorization_url, state

    def fetch_credentials(self, authorization_response: str, state: str | None):
        """Exchange the auth code for credentials using the provided state.
        
        Since we now explicitly include 'openid' in our requested scopes,
        Google's response will match and no scope mismatch error will occur.
        """
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
