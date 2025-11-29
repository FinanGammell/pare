"""Gmail integration helpers backed by google-api-python-client.

This module provides a higher-level wrapper around the shared gmail_client
helpers for use cases that only need lightweight metadata about recent
emails. The main sync path lives in `services.gmail_sync`.
"""
from __future__ import annotations

from typing import Dict, List

from services.gmail_client import build_gmail_service


class GmailService:
    """Interact with the Gmail API using stored OAuth credentials."""

    def fetch_recent_emails(self, user_id: int, max_results: int = 10) -> List[Dict[str, object]]:
        """Fetch the most recent Gmail messages for the authenticated user.

        This is a lightweight helper that returns basic metadata and is
        separate from the full sync pipeline in `gmail_sync`.
        """
        gmail = build_gmail_service(user_id)
        if not gmail:
            return []

        response = gmail.users().messages().list(userId="me", maxResults=max_results).execute()
        messages = response.get("messages", [])
        payloads: List[Dict[str, object]] = []
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

