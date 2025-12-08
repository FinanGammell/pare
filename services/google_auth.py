"""
Google OAuth helpers.

This module handles Google OAuth authentication:
- Creating OAuth flows
- Generating authorization URLs
- Exchanging authorization codes for access tokens
- Fetching user profiles
"""
from __future__ import annotations

import os
from typing import Dict, Tuple

from flask import current_app
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# Google OAuth endpoints
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"  # Where to exchange codes for tokens
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"  # Google's login page


def _get_redirect_uri() -> str:
    """
    Get redirect URI from Flask config or environment variable.
    
    The redirect URI is where Google sends users after they log in.
    It MUST be the backend URL (not the frontend), because the backend handles OAuth.
    
    Common mistake: setting this to the frontend URL (localhost:5173) instead of backend (localhost:5001).
    """
    try:
        # Try to get from Flask config first (preferred)
        redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI")
        if redirect_uri:
            # Validate it's not the frontend URL
            # The frontend can't handle OAuth callbacks - only the backend can
            if redirect_uri == "http://localhost:5173" or redirect_uri.startswith("http://localhost:5173/"):
                raise RuntimeError(
                    "GOOGLE_REDIRECT_URI cannot be the frontend URL (localhost:5173). "
                    "It must be the backend callback URL: http://localhost:5001/oauth2callback"
                )
            return redirect_uri
    except RuntimeError as e:
        # Re-raise RuntimeError (our validation error)
        if "frontend URL" in str(e):
            raise
        # Not in Flask app context, fall back to env var
        pass
    
    # Fall back to environment variable if not in Flask context
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if redirect_uri:
        # Validate it's not the frontend URL
        if redirect_uri == "http://localhost:5173" or redirect_uri.startswith("http://localhost:5173/"):
            raise RuntimeError(
                "GOOGLE_REDIRECT_URI is incorrectly set to the frontend URL. "
                "It must be the backend callback URL: http://localhost:5001/oauth2callback. "
                "Either unset GOOGLE_REDIRECT_URI to use the default, or set it to the correct backend URL."
            )
        return redirect_uri
    
    # No redirect URI set - this is OK in development (config will provide default)
    # But we need to raise an error here since we're not in app context
    raise RuntimeError(
        "GOOGLE_REDIRECT_URI is not set. OAuth cannot start. "
        "Set GOOGLE_REDIRECT_URI to either "
        "http://localhost:5001/oauth2callback (local) or "
        "https://pare.up.railway.app/oauth2callback (production)."
    )


def _create_oauth_flow(state: str | None = None) -> Flow:
    redirect_uri = _get_redirect_uri()
    client_config = {
        "web": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uris": [redirect_uri],
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
        }
    }
    scopes = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/gmail.readonly",
    ]
    flow = Flow.from_client_config(client_config, scopes=scopes, state=state)
    flow.redirect_uri = redirect_uri
    return flow


def authorization_url() -> Tuple[str, str]:
    """Return a Google OAuth authorization URL + state."""
    flow = _create_oauth_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return authorization_url, state


def fetch_credentials(authorization_response: str, state: str | None):
    """
    Exchange the auth code for credentials using the provided state.
    
    After the user logs in, Google redirects them back with an authorization code.
    This function exchanges that code for an access token and refresh token.
    
    The access token lets us make API calls to Gmail.
    The refresh token lets us get new access tokens when they expire.
    """
    flow = _create_oauth_flow(state)
    # Exchange the authorization code for tokens
    flow.fetch_token(authorization_response=authorization_response)
    return flow.credentials


def fetch_user_profile(credentials) -> Dict[str, str]:
    """
    Retrieve the user's profile via Google OAuth2 API.
    
    Uses the access token to get the user's basic info (email, name, Google user ID).
    This is how we know who logged in.
    """
    # Build the OAuth2 API service
    oauth_service = build("oauth2", "v2", credentials=credentials, cache_discovery=False)
    # Get user info
    user_info = oauth_service.userinfo().get().execute()
    return {
        "google_user_id": user_info.get("id"),  # Google's unique ID for this user
        "email": user_info.get("email"),  # User's email address
        "name": user_info.get("name"),  # User's display name
    }
