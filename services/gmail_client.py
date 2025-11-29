"""Shared Gmail client and credential helpers.

This module centralizes Google OAuth credential refresh and Gmail client
construction so that higher-level services (sync, metadata fetch) do not
duplicate this logic.
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
    """Build a Credentials object from a stored credential record."""
    expiry = record.get("token_expiry")
    expiry_dt: Optional[datetime] = None
    if expiry:
        try:
            expiry_dt = datetime.fromisoformat(expiry)
        except ValueError:
            expiry_dt = None
    creds = Credentials(
        token=record.get("access_token"),
        refresh_token=record.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=Config.GOOGLE_CLIENT_ID,
        client_secret=Config.GOOGLE_CLIENT_SECRET,
        scopes=Config.GOOGLE_SCOPES,
    )
    if expiry_dt:
        creds.expiry = expiry_dt
    return creds


def _ensure_fresh_credentials(user_id: int) -> Optional[Credentials]:
    """Return fresh credentials for a user, refreshing and persisting if needed."""
    record = get_credentials_for_user(user_id)
    if not record:
        return None
    creds = _build_credentials(record)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        upsert_credentials(
            user_id=user_id,
            access_token=creds.token or "",
            refresh_token=creds.refresh_token or "",
            token_expiry=creds.expiry.isoformat() if creds.expiry else None,
        )
    return creds


def build_gmail_service(user_id: int):
    """Return a Gmail API service instance for the given user, or None if missing creds."""
    creds = _ensure_fresh_credentials(user_id)
    if not creds:
        return None
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


