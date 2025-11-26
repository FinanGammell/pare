"""Gmail synchronization helpers."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import Config
from models import create_email, get_credentials_for_user, upsert_credentials


def _build_credentials(record: Dict[str, Any]) -> Credentials:
    creds = Credentials(
        token=record.get("access_token"),
        refresh_token=record.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=Config.GOOGLE_CLIENT_ID,
        client_secret=Config.GOOGLE_CLIENT_SECRET,
        scopes=Config.GOOGLE_SCOPES,
    )
    expiry = record.get("token_expiry")
    if expiry:
        try:
            creds.expiry = datetime.fromisoformat(expiry)
        except ValueError:
            creds.expiry = None
    return creds


def _refresh_credentials(user_id: int, creds: Credentials) -> Credentials:
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        upsert_credentials(
            user_id=user_id,
            access_token=creds.token or "",
            refresh_token=creds.refresh_token or "",
            token_expiry=creds.expiry.isoformat() if creds.expiry else None,
        )
    return creds


def _decode_part(data: Optional[str]) -> str:
    if not data:
        return ""
    try:
        decoded = base64.urlsafe_b64decode(data.encode("utf-8"))
    except Exception:
        return ""
    try:
        return decoded.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_headers(payload: Dict[str, Any]) -> Dict[str, str]:
    headers = {}
    for header in payload.get("headers", []):
        name = header.get("name")
        if name:
            headers[name] = header.get("value", "")
    return headers


def _extract_body(payload: Optional[Dict[str, Any]]) -> str:
    if not payload:
        return ""
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")
    if data and (mime_type.startswith("text/plain") or not payload.get("parts")):
        return _decode_part(data)
    parts = payload.get("parts", [])
    texts: List[str] = []
    for part in parts:
        part_mime = part.get("mimeType", "")
        content = _extract_body(part)
        if part_mime.startswith("text/plain") and content:
            return content
        if content:
            texts.append(content)
    return "\n".join(texts)


def _format_internal_date(internal_date: Optional[str]) -> Optional[str]:
    if not internal_date:
        return None
    try:
        timestamp_ms = int(internal_date)
    except (TypeError, ValueError):
        return None
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return dt.isoformat()


def sync_recent_emails(user_id: int, max_results: int = 300) -> List[Dict[str, Any]]:
    """Sync recent Gmail messages into the local SQLite database."""
    record = get_credentials_for_user(user_id)
    if not record:
        return []

    creds = _build_credentials(record)
    creds = _refresh_credentials(user_id, creds)
    gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)

    response = gmail.users().messages().list(userId="me", maxResults=max_results).execute()
    messages = response.get("messages", [])

    synced: List[Dict[str, Any]] = []
    for message in messages:
        msg = gmail.users().messages().get(userId="me", id=message["id"], format="full").execute()
        payload = msg.get("payload", {})
        headers = _extract_headers(payload)
        email_payload = {
            "gmail_message_id": msg.get("id"),
            "sender": headers.get("From"),
            "subject": headers.get("Subject"),
            "date": _format_internal_date(msg.get("internalDate")),
            "snippet": msg.get("snippet"),
            "body": _extract_body(payload),
            "raw_json": msg,
        }
        create_email(
            user_id=user_id,
            gmail_message_id=email_payload["gmail_message_id"] or "",
            sender=email_payload["sender"],
            subject=email_payload["subject"],
            date=email_payload["date"],
            body=email_payload["body"],
            snippet=email_payload["snippet"],
            raw_json=email_payload["raw_json"],
        )
        synced.append(email_payload)
    return synced
