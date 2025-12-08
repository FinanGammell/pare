"""
Gmail client and credential helpers.

This module handles Gmail API authentication:
- Building credentials from stored tokens
- Refreshing expired access tokens
- Creating Gmail API service instances
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import Config
from models import get_credentials_for_user, upsert_credentials


def _build_credentials(record: Dict[str, Any]) -> Credentials:
    """
    Build a Credentials object from a stored credential record.
    
    Takes the credentials we stored in the database and converts them
    into a Google Credentials object that can be used with the Gmail API.
    """
    expiry = record.get("token_expiry")
    expiry_dt: Optional[datetime] = None
    if expiry:
        try:
            # Parse the expiry date from ISO format
            expiry_dt = datetime.fromisoformat(expiry)
        except ValueError:
            expiry_dt = None
    # Create credentials object with our stored tokens
    creds = Credentials(
        token=record.get("access_token"),  # Access token (expires in 1 hour)
        refresh_token=record.get("refresh_token"),  # Refresh token (never expires)
        token_uri="https://oauth2.googleapis.com/token",  # Where to refresh tokens
        client_id=Config.GOOGLE_CLIENT_ID,  # Our app's client ID
        client_secret=Config.GOOGLE_CLIENT_SECRET,  # Our app's client secret
        scopes=Config.GOOGLE_SCOPES,  # What permissions we have
    )
    if expiry_dt:
        creds.expiry = expiry_dt
    return creds


def _ensure_fresh_credentials(user_id: int) -> Optional[Credentials]:
    """
    Return fresh credentials for a user, refreshing and persisting if needed.
    
    Access tokens expire after 1 hour. This function checks if the token is expired
    and refreshes it using the refresh token if needed.
    """
    # Get stored credentials from database
    record = get_credentials_for_user(user_id)
    if not record:
        return None
    # Build credentials object
    creds = _build_credentials(record)
    # If expired, refresh it
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())  # Get new access token
        # Save the new token to database
        upsert_credentials(
            user_id=user_id,
            access_token=creds.token or "",
            refresh_token=creds.refresh_token or "",
            token_expiry=creds.expiry.isoformat() if creds.expiry else None,
        )
    return creds


def build_gmail_service(user_id: int):
    """
    Return a Gmail API service instance for the given user, or None if missing creds.
    
    This creates a Gmail API client that can be used to fetch emails, send emails, etc.
    """
    # Get fresh credentials (refresh if needed)
    creds = _ensure_fresh_credentials(user_id)
    if not creds:
        return None
    # Build and return Gmail API service
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


