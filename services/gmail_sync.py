"""Gmail synchronization helpers."""
from __future__ import annotations

import base64
import html
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.gmail_client import build_gmail_service
from models import (
    create_email,
    get_all_gmail_message_ids,
    get_credentials_for_user,
    get_most_recent_email_date,
    get_sync_stats,
)


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
    """Extract and decode email headers, handling HTML entities."""
    headers = {}
    for header in payload.get("headers", []):
        name = header.get("name")
        if name:
            value = header.get("value", "")
            # Decode HTML entities in header values
            try:
                value = html.unescape(value)
            except Exception:
                pass
            headers[name] = value
    return headers


def extract_unsubscribe_url(headers: Dict[str, str], body: str) -> Optional[str]:
    """
    Extract unsubscribe URL from email headers and body.
    Checks List-Unsubscribe header first, then searches body for common patterns.
    """
    # Check List-Unsubscribe header (RFC 2369)
    list_unsubscribe = headers.get("List-Unsubscribe") or headers.get("list-unsubscribe")
    if list_unsubscribe:
        # Parse the header - can be mailto: or http(s)://
        # Format: <mailto:...> or <https://...> or https://...
        # Can also be: <mailto:...>, <https://...>
        urls = re.findall(r'<([^>]+)>', list_unsubscribe)
        for url in urls:
            if url.startswith(('http://', 'https://')):
                return url
            elif url.startswith('mailto:'):
                # For mailto links, we can't use them directly, but we can note them
                # For now, skip mailto links
                continue
        
        # Also check for direct URLs in the header
        direct_urls = re.findall(r'https?://[^\s<>"]+', list_unsubscribe)
        if direct_urls:
            return direct_urls[0]
    
    # Check List-Unsubscribe-Post header (RFC 8058)
    list_unsubscribe_post = headers.get("List-Unsubscribe-Post") or headers.get("list-unsubscribe-post")
    if list_unsubscribe_post == "List-Unsubscribe=One-Click":
        # This indicates one-click unsubscribe, but we still need the URL from List-Unsubscribe
        pass
    
    # Search body for common unsubscribe patterns
    if body:
        # Pattern 1: Direct HTTP/HTTPS links with "unsubscribe" keywords
        direct_patterns = [
            r'https?://[^\s<>"\'\)]+unsubscribe[^\s<>"\'\)]*',
            r'https?://[^\s<>"\'\)]+opt[_-]?out[^\s<>"\'\)]*',
            r'https?://[^\s<>"\'\)]+remove[^\s<>"\'\)]*',
        ]
        
        for pattern in direct_patterns:
            matches = re.findall(pattern, body, re.IGNORECASE)
            for url in matches:
                if url:
                    # Clean up the URL (remove common trailing characters)
                    url = url.rstrip('.,;:!?)')
                    return url
        
        # Pattern 2: Links in HTML anchor tags
        html_patterns = [
            r'<a[^>]+href=["\']([^"\']*unsubscribe[^"\']*)["\']',
            r'<a[^>]+href=["\']([^"\']*opt[_-]?out[^"\']*)["\']',
            r'<a[^>]+href=["\']([^"\']*remove[^"\']*)["\']',
        ]
        
        for pattern in html_patterns:
            matches = re.findall(pattern, body, re.IGNORECASE)
            for match in matches:
                url = match if isinstance(match, str) else (match[0] if isinstance(match, tuple) and match else None)
                if url:
                    # Handle relative URLs (though we prefer absolute)
                    if url.startswith(('http://', 'https://')):
                        url = url.rstrip('.,;:!?)')
                        return url
                    # For relative URLs, we'd need the email's base URL, so skip for now
    
    return None


def _decode_html_entities(text: str) -> str:
    """Decode HTML entities in text."""
    if not text:
        return text
    try:
        return html.unescape(text)
    except Exception:
        return text


def _extract_body(payload: Optional[Dict[str, Any]], prefer_html: bool = False) -> str:
    """
    Extract email body content. If prefer_html is True, returns HTML if available,
    otherwise returns plain text.
    """
    if not payload:
        return ""
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")
    
    # Single part message
    if data and not payload.get("parts"):
        if mime_type.startswith("text/html") or mime_type.startswith("text/plain"):
            content = _decode_part(data)
            # Decode HTML entities in plain text (not HTML, as HTML may contain valid entities)
            if mime_type.startswith("text/plain"):
                content = _decode_html_entities(content)
            return content
    
    # Multi-part message
    parts = payload.get("parts", [])
    html_content = None
    text_content = None
    
    for part in parts:
        part_mime = part.get("mimeType", "")
        content = _extract_body(part, prefer_html)
        
        if part_mime.startswith("text/html"):
            html_content = content
        elif part_mime.startswith("text/plain") and not text_content:
            # Decode HTML entities in plain text
            text_content = _decode_html_entities(content)
    
    # Return HTML if preferred and available, otherwise text
    if prefer_html and html_content:
        return html_content
    return text_content or html_content or ""


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
    gmail = build_gmail_service(user_id)
    if not gmail:
        return []

    response = gmail.users().messages().list(userId="me", maxResults=max_results).execute()
    messages = response.get("messages", [])

    synced: List[Dict[str, Any]] = []
    for message in messages:
        msg = gmail.users().messages().get(userId="me", id=message["id"], format="full").execute()
        payload = msg.get("payload", {})
        headers = _extract_headers(payload)
        snippet = msg.get("snippet")
        if snippet:
            snippet = _decode_html_entities(snippet)
        
        email_payload = {
            "gmail_message_id": msg.get("id"),
            "sender": headers.get("From"),
            "subject": headers.get("Subject"),
            "date": _format_internal_date(msg.get("internalDate")),
            "snippet": snippet,
            "body": _extract_body(payload, prefer_html=False),  # Store plain text for body
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


def sync_and_process_emails(user_id: int, max_results: int = 1000) -> Dict[str, Any]:
    """
    Proactively sync only new emails that haven't been processed yet.
    Uses Gmail query parameters to filter out already-processed emails.
    """
    # Get stats before sync
    stats_before = get_sync_stats(user_id)
    total_before = stats_before["total_emails"]
    
    record = get_credentials_for_user(user_id)
    if not record:
        return {
            "synced_count": 0,
            "new_count": 0,
            "total_emails": total_before,
            "processed_emails": stats_before["processed_emails"],
            "unprocessed_emails": stats_before["unprocessed_emails"],
        }

    gmail = build_gmail_service(user_id)
    if not gmail:
        return {
            "synced_count": 0,
            "new_count": 0,
            "total_emails": total_before,
            "processed_emails": stats_before["processed_emails"],
            "unprocessed_emails": stats_before["unprocessed_emails"],
        }

    # PROACTIVE APPROACH: Get the most recent email date we've already synced
    # Only fetch emails newer than that date (or all emails if this is first sync)
    most_recent_date = get_most_recent_email_date(user_id)
    
    # Build Gmail query to only fetch emails we haven't seen yet
    # If we have a most recent date, only fetch emails after that date
    query_params = {}
    if most_recent_date:
        try:
            # Convert ISO date to Gmail query format (after:YYYY/MM/DD)
            # Gmail uses YYYY/MM/DD format for date queries
            dt = datetime.fromisoformat(most_recent_date.replace('Z', '+00:00'))
            # Use the date (not time) to ensure we get all emails from that day onwards
            # Subtract 1 day to account for timezone differences and ensure we don't miss any
            from datetime import timedelta
            dt = dt - timedelta(days=1)
            date_str = dt.strftime("%Y/%m/%d")
            query_params["q"] = f"after:{date_str}"
        except Exception:
            # If date parsing fails, fetch all emails (fallback)
            pass
    
    # Fetch only new emails using the query
    # This prevents fetching emails we've already processed
    list_params = {
        "userId": "me",
        "maxResults": max_results,
    }
    if "q" in query_params:
        list_params["q"] = query_params["q"]
    
    response = gmail.users().messages().list(**list_params).execute()
    messages = response.get("messages", [])
    
    # Get all existing gmail_message_ids for this user to filter out any remaining duplicates
    # (This is a safety net in case query filtering isn't perfect)
    existing_ids = set(get_all_gmail_message_ids(user_id))
    
    # Process only truly new emails
    from models import create_unsubscribe_entry
    
    new_emails_processed = 0
    for message in messages:
        gmail_message_id = message.get("id")
        if not gmail_message_id:
            continue
        
        # Proactive check: Skip if we already have this email
        if gmail_message_id in existing_ids:
            continue
        
        # Fetch and process the email
        msg = gmail.users().messages().get(userId="me", id=gmail_message_id, format="full").execute()
        payload = msg.get("payload", {})
        headers = _extract_headers(payload)
        body = _extract_body(payload, prefer_html=False)  # Store plain text for body
        
        # Extract unsubscribe URL from headers and body (prefer HTML body for better link extraction)
        html_body = _extract_body(payload, prefer_html=True)
        unsubscribe_url = extract_unsubscribe_url(headers, html_body or body)
        
        snippet = msg.get("snippet")
        if snippet:
            snippet = _decode_html_entities(snippet)
        
        email_record = create_email(
            user_id=user_id,
            gmail_message_id=gmail_message_id,
            sender=headers.get("From"),
            subject=headers.get("Subject"),
            date=_format_internal_date(msg.get("internalDate")),
            body=body,
            snippet=snippet,
            raw_json=msg,
        )
        
        # Add to existing_ids set to prevent processing duplicates in the same batch
        if email_record:
            existing_ids.add(gmail_message_id)
            new_emails_processed += 1
        
        # Store unsubscribe URL if found (check if one already exists to avoid duplicates)
        if unsubscribe_url and email_record:
            from models import get_unsubscribe_for_email
            existing = get_unsubscribe_for_email(email_record["id"])
            if not existing:
                create_unsubscribe_entry(
                    email_id=email_record["id"],
                    unsubscribe_url=unsubscribe_url,
                    status="pending",
                )
    
    # Get stats after sync to determine how many were new
    stats_after = get_sync_stats(user_id)
    total_after = stats_after["total_emails"]
    new_count = total_after - total_before
    
    return {
        "synced_count": len(messages),
        "new_count": new_count,
        "total_emails": total_after,
        "processed_emails": stats_after["processed_emails"],
        "unprocessed_emails": stats_after["unprocessed_emails"],
    }
