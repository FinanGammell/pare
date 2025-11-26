"""Gmail integration helpers backed by google-api-python-client."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import Config
from models import get_credentials_for_user, upsert_credentials


class GmailService:
    """Interact with the Gmail API using stored OAuth credentials."""

    def __init__(self, config: type[Config] | None = None) -> None:
        self.config = config or Config

    def _build_credentials(self, credential_record: Dict[str, Any]) -> Credentials:
        expiry = credential_record.get("token_expiry")
        expiry_dt: Optional[datetime] = None
        if expiry:
            try:
                expiry_dt = datetime.fromisoformat(expiry)
            except ValueError:
                expiry_dt = None
        creds = Credentials(
            token=credential_record.get("access_token"),
            refresh_token=credential_record.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.config.GOOGLE_CLIENT_ID,
            client_secret=self.config.GOOGLE_CLIENT_SECRET,
            scopes=self.config.GOOGLE_SCOPES,
        )
        if expiry_dt:
            creds.expiry = expiry_dt
        return creds

    def _ensure_fresh_credentials(self, user_id: int) -> Optional[Credentials]:
        record = get_credentials_for_user(user_id)
        if not record:
            return None
        credentials = self._build_credentials(record)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            upsert_credentials(
                user_id=user_id,
                access_token=credentials.token,
                refresh_token=credentials.refresh_token,
                token_expiry=credentials.expiry.isoformat() if credentials.expiry else None,
            )
        return credentials

    def fetch_recent_emails(self, user_id: int, max_results: int = 10) -> List[Dict[str, Any]]:
        """Fetch the most recent Gmail messages for the authenticated user."""
        credentials = self._ensure_fresh_credentials(user_id)
        if not credentials:
            return []
        gmail = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        response = gmail.users().messages().list(userId="me", maxResults=max_results).execute()
        messages = response.get("messages", [])
        payloads: List[Dict[str, Any]] = []
        for message in messages:
            msg = gmail.users().messages().get(
                userId="me",
                id=message["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            payloads.append(
                {
                    "id": msg.get("id"),
                    "subject": headers.get("Subject"),
                    "snippet": msg.get("snippet"),
                    "from": headers.get("From"),
                    "date": headers.get("Date"),
                    "body": None,
                    "raw_json": msg,
                }
            )
        return payloads
