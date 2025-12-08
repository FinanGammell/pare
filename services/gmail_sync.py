"""
Gmail synchronization helpers.

This module handles syncing emails from Gmail to our local database:
- Fetching emails from Gmail API
- Decoding email content (base64, HTML entities, etc.)
- Extracting email body, headers, unsubscribe URLs
- Storing emails in the database
- Avoiding duplicates by checking existing emails
"""
from __future__ import annotations

import base64
import html
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from services.gmail_client import build_gmail_service
from models import (
    create_email,
    get_existing_message_ids,
    get_credentials_for_user,
    get_most_recent_email_date,
    get_sync_stats,
    get_user_by_id,
)

logger = logging.getLogger(__name__)


def _decode_part(data: Optional[str]) -> str:
    """
    Decode base64url-encoded email part data.
    
    Gmail API returns email content as base64url-encoded strings.
    This function decodes them and handles various character encodings.
    """
    if not data:
        return ""
    decoded = None
    try:
        # Gmail API uses base64url encoding (URL-safe base64)
        # Base64 requires padding to be a multiple of 4, so add it if needed
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        decoded = base64.urlsafe_b64decode(data.encode("utf-8"))
    except Exception:
        # Try without padding (sometimes it's already correct)
        try:
            decoded = base64.urlsafe_b64decode(data.encode("utf-8"))
        except Exception:
            return ""
    
    if decoded is None:
        return ""
    
    # Try to detect encoding from email headers or use UTF-8
    # First try UTF-8 with error handling that preserves characters
    try:
        return decoded.decode("utf-8", errors="replace")
    except Exception:
        pass
    
    # Try to detect encoding using chardet if available
    # chardet can guess the encoding by analyzing the bytes
    try:
        import chardet
        detected = chardet.detect(decoded)
        if detected and detected.get("encoding"):
            encoding = detected["encoding"]
            try:
                return decoded.decode(encoding, errors="replace")
            except Exception:
                pass
    except ImportError:
        # chardet not installed, skip this step
        pass
    
    # Fallback to latin-1 which can decode any byte sequence
    # This is a last resort - it might not be correct, but it won't crash
    try:
        return decoded.decode("latin-1", errors="replace")
    except Exception:
        return ""


def _extract_headers(payload: Dict[str, Any]) -> Dict[str, str]:
    """Extract and decode email headers, handling HTML entities and RFC 2047 encoding."""
    headers = {}
    for header in payload.get("headers", []):
        name = header.get("name")
        if name:
            value = header.get("value", "")
            # Decode RFC 2047 encoded headers (e.g., =?UTF-8?B?...?=)
            try:
                from email.header import decode_header
                decoded_parts = decode_header(value)
                decoded_value = ""
                for part, encoding in decoded_parts:
                    if isinstance(part, bytes):
                        if encoding:
                            decoded_value += part.decode(encoding, errors="replace")
                        else:
                            # Try UTF-8 first, then latin-1
                            try:
                                decoded_value += part.decode("utf-8", errors="replace")
                            except Exception:
                                decoded_value += part.decode("latin-1", errors="replace")
                    else:
                        decoded_value += part
                value = decoded_value
            except Exception:
                # If RFC 2047 decoding fails, try HTML entity decoding
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
    if not body:
        body = ""
    
    # Check List-Unsubscribe header (RFC 2369) - highest priority
    list_unsubscribe = headers.get("List-Unsubscribe") or headers.get("list-unsubscribe")
    if list_unsubscribe:
        # Parse the header - can be mailto: or http(s)://
        # Format: <mailto:...> or <https://...> or https://...
        # Can also be: <mailto:...>, <https://...>
        urls = re.findall(r'<([^>]+)>', list_unsubscribe)
        for url in urls:
            if url.startswith(('http://', 'https://')):
                return url.strip()
            elif url.startswith('mailto:'):
                # For mailto links, we can't use them directly, but we can note them
                # For now, skip mailto links
                continue
        
        # Also check for direct URLs in the header
        direct_urls = re.findall(r'https?://[^\s<>"]+', list_unsubscribe)
        if direct_urls:
            return direct_urls[0].strip()
    
    # Check List-Unsubscribe-Post header (RFC 8058)
    list_unsubscribe_post = headers.get("List-Unsubscribe-Post") or headers.get("list-unsubscribe-post")
    if list_unsubscribe_post == "List-Unsubscribe=One-Click":
        # This indicates one-click unsubscribe, but we still need the URL from List-Unsubscribe
        pass
    
    # Search body for common unsubscribe patterns
    if body:
        # Pattern 1: Links in HTML anchor tags (check first as most common)
        html_patterns = [
            r'<a[^>]+href\s*=\s*["\']([^"\']*unsubscribe[^"\']*)["\']',
            r'<a[^>]+href\s*=\s*["\']([^"\']*opt[_-]?out[^"\']*)["\']',
            r'<a[^>]+href\s*=\s*["\']([^"\']*remove[^"\']*)["\']',
            r'<a[^>]+href\s*=\s*["\']([^"\']*manage[_-]?preferences[^"\']*)["\']',
            r'href\s*=\s*["\']([^"\']*unsubscribe[^"\']*)["\']',
            r'href\s*=\s*["\']([^"\']*opt[_-]?out[^"\']*)["\']',
        ]
        
        for pattern in html_patterns:
            matches = re.findall(pattern, body, re.IGNORECASE | re.DOTALL)
            for match in matches:
                url = match if isinstance(match, str) else (match[0] if isinstance(match, tuple) and match else None)
                if url and url.strip():
                    # Decode HTML entities in URL
                    try:
                        import html
                        url = html.unescape(url.strip())
                    except Exception:
                        url = url.strip()
                    
                    # Handle relative URLs - try to construct absolute URL
                    if url.startswith(('http://', 'https://')):
                        url = url.rstrip('.,;:!?)')
                        # Validate it's a proper URL
                        if 'unsubscribe' in url.lower() or 'opt' in url.lower() or 'remove' in url.lower():
                            return url
                    elif url.startswith('/'):
                        # Relative URL - extract domain from other links in email
                        domain_match = re.search(r'https?://([^/]+)', body)
                        if domain_match:
                            domain = domain_match.group(1)
                            full_url = f"https://{domain}{url}"
                            return full_url.rstrip('.,;:!?)')
        
        # Pattern 2: Direct HTTP/HTTPS links with "unsubscribe" keywords (plain text)
        direct_patterns = [
            r'https?://[^\s<>"\'\)]+unsubscribe[^\s<>"\'\)]*',
            r'https?://[^\s<>"\'\)]+opt[_-]?out[^\s<>"\'\)]*',
            r'https?://[^\s<>"\'\)]+remove[^\s<>"\'\)]*',
            r'https?://[^\s<>"\'\)]+manage[_-]?preferences[^\s<>"\'\)]*',
            r'https?://[^\s<>"\'\)]+email[_-]?preferences[^\s<>"\'\)]*',
            r'https?://[^\s<>"\'\)]+preferences[^\s<>"\'\)]*',
        ]
        
        for pattern in direct_patterns:
            matches = re.findall(pattern, body, re.IGNORECASE)
            for url in matches:
                if url and url.strip():
                    # Clean up the URL (remove common trailing characters)
                    url = url.rstrip('.,;:!?)')
                    # Validate it contains unsubscribe keywords
                    url_lower = url.lower()
                    if any(keyword in url_lower for keyword in ['unsubscribe', 'opt', 'remove', 'preferences']):
                        return url
    
    return None


def _decode_html_entities(text: str) -> str:
    """Decode HTML entities in text."""
    if not text:
        return text
    try:
        return html.unescape(text)
    except Exception:
        return text


def extract_body_from_raw_json(raw_json_str: Optional[str]) -> Optional[str]:
    """Extract email body from raw_json if body field is empty."""
    if not raw_json_str:
        return None
    
    try:
        if isinstance(raw_json_str, str):
            import json
            raw_json = json.loads(raw_json_str)
        else:
            raw_json = raw_json_str
        
        payload = raw_json.get("payload")
        if payload:
            body = _extract_body(payload, prefer_html=False)
            if body and body.strip():
                return body
    except (json.JSONDecodeError, KeyError, AttributeError, TypeError):
        pass
    
    return None


def _extract_body(payload: Optional[Dict[str, Any]], prefer_html: bool = False) -> str:
    """
    Extract email body content. If prefer_html is True, returns HTML if available,
    otherwise returns plain text.
    
    Handles:
    - Single part messages
    - Multi-part messages
    - Nested multipart structures (multipart/alternative, multipart/mixed, etc.)
    """
    if not payload:
        return ""
    
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")
    
    # Single part message (no nested parts)
    if data and not payload.get("parts"):
        if mime_type.startswith("text/html") or mime_type.startswith("text/plain"):
            content = _decode_part(data)
            # Decode HTML entities in plain text (not HTML, as HTML may contain valid entities)
            if mime_type.startswith("text/plain"):
                content = _decode_html_entities(content)
            return content
    
    # Multi-part message - recursively extract from all parts
    parts = payload.get("parts", [])
    if not parts:
        return ""
    
    html_content = None
    text_content = None
    
    # Process all parts recursively
    for part in parts:
        part_mime = part.get("mimeType", "")
        
        # If this part is itself multipart, recurse into it
        if part_mime.startswith("multipart/"):
            nested_content = _extract_body(part, prefer_html)
            if nested_content:
                # If we got HTML from nested multipart and prefer HTML, use it
                if prefer_html and not html_content:
                    html_content = nested_content
                # If we got text from nested multipart and don't have text yet, use it
                elif not text_content:
                    text_content = nested_content
            continue
        
        # Extract content from this part
        part_body = part.get("body", {})
        part_data = part_body.get("data")
        
        if part_data:
            content = _decode_part(part_data)
            
            if part_mime.startswith("text/html"):
                if not html_content:  # Take first HTML part found
                    html_content = content
            elif part_mime.startswith("text/plain"):
                if not text_content:  # Take first plain text part found
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

    # Get user's email to filter out self-sent emails
    user = get_user_by_id(user_id)
    user_email = user.get("email") if user else None
    
    list_params = {
        "userId": "me",
        "maxResults": max_results,
    }
    
    # Exclude emails sent by the user (only show incoming emails)
    # Note: Temporarily disabled to debug - Gmail From header format may differ from stored email
    # if user_email:
    #     list_params["q"] = f"-from:{user_email}"
    
    response = gmail.users().messages().list(**list_params).execute()
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


def sync_and_process_emails(user_id: int, max_results: int = 500) -> Dict[str, Any]:
    """
    Proactively sync only new emails using batched Gmail API calls.
    
    This is the main sync function that:
    1. Lists recent emails from Gmail
    2. Checks which ones we already have (avoids duplicates)
    3. Fetches new emails in batches (Gmail API supports up to 100 per batch)
    4. Stores them in the database
    5. Extracts unsubscribe URLs
    
    This function uses Gmail's batch HTTP request API to fetch multiple emails
    in a single request, dramatically improving performance.
    
    Returns:
        Dict with sync statistics including new_count, skipped_count, timestamps
    """
    start_time = time.time()
    
    # Get stats before sync
    stats_before = get_sync_stats(user_id)
    total_before = stats_before["total_emails"]
    
    record = get_credentials_for_user(user_id)
    if not record:
        logger.warning(f"User {user_id} has no credentials")
        return {
            "synced_count": 0,
            "new_count": 0,
            "skipped_count": 0,
            "total_emails": total_before,
            "processed_emails": stats_before["processed_emails"],
            "unprocessed_emails": stats_before["unprocessed_emails"],
            "duration_seconds": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }

    gmail = build_gmail_service(user_id)
    if not gmail:
        logger.warning(f"Failed to build Gmail service for user {user_id}")
        return {
            "synced_count": 0,
            "new_count": 0,
            "skipped_count": 0,
            "total_emails": total_before,
            "processed_emails": stats_before["processed_emails"],
            "unprocessed_emails": stats_before["unprocessed_emails"],
            "duration_seconds": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # Step 1: List message IDs (1 API call)
    list_start = time.time()
    most_recent_date = get_most_recent_email_date(user_id)
    
    # Get user's email to filter out self-sent emails
    user = get_user_by_id(user_id)
    user_email = user.get("email") if user else None
    
    query_parts = []
    if most_recent_date:
        try:
            dt = datetime.fromisoformat(most_recent_date.replace('Z', '+00:00'))
            dt = dt - timedelta(days=1)
            date_str = dt.strftime("%Y/%m/%d")
            query_parts.append(f"after:{date_str}")
        except Exception:
            pass
    
    # Exclude emails sent by the user (only show incoming emails)
    if user_email:
        # Gmail query syntax: -from:email@example.com excludes emails from that address
        # Use quotes to handle special characters in email addresses
        query_parts.append(f'-from:"{user_email}"')
        logger.info(f"Filtering out emails from user: {user_email}")
    
    list_params = {
        "userId": "me",
        "maxResults": max_results,
    }
    if query_parts:
        list_params["q"] = " ".join(query_parts)
        logger.info(f"Gmail query: {list_params['q']}")
    
    response = gmail.users().messages().list(**list_params).execute()
    messages = response.get("messages", [])
    message_ids = [msg["id"] for msg in messages if msg.get("id")]
    list_duration = time.time() - list_start
    logger.info(f"Listed {len(message_ids)} messages in {list_duration:.2f}s")
    
    if not message_ids:
        return {
            "synced_count": 0,
            "new_count": 0,
            "skipped_count": 0,
            "total_emails": total_before,
            "processed_emails": stats_before["processed_emails"],
            "unprocessed_emails": stats_before["unprocessed_emails"],
            "duration_seconds": time.time() - start_time,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    # Step 2: Efficient duplicate check (1 DB query with IN clause)
    dup_check_start = time.time()
    existing_ids = set(get_existing_message_ids(user_id, message_ids))
    new_ids = [mid for mid in message_ids if mid not in existing_ids]
    dup_check_duration = time.time() - dup_check_start
    skipped_count = len(message_ids) - len(new_ids)
    logger.info(
        f"Duplicate check: {len(new_ids)} new, {skipped_count} skipped "
        f"in {dup_check_duration:.2f}s"
    )
    
    if not new_ids:
        return {
            "synced_count": len(message_ids),
            "new_count": 0,
            "skipped_count": skipped_count,
            "total_emails": total_before,
            "processed_emails": stats_before["processed_emails"],
            "unprocessed_emails": stats_before["unprocessed_emails"],
            "duration_seconds": time.time() - start_time,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    # Step 3: Batch fetch new emails (Gmail batchGet - up to 100 per request)
    batch_start = time.time()
    batch_size = 100  # Gmail API limit per batch request
    new_emails_processed = 0
    from models import create_unsubscribe_entry, get_unsubscribe_for_email
    
    for i in range(0, len(new_ids), batch_size):
        batch_ids = new_ids[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(new_ids) + batch_size - 1) // batch_size
        
        logger.info(f"Fetching batch {batch_num}/{total_batches} ({len(batch_ids)} emails)")
        
        # Create batch request
        batch_request = gmail.new_batch_http_request()
        batch_results: Dict[str, Any] = {}
        
        def batch_callback(request_id: str, response: Any, exception: Optional[Exception]) -> None:
            """Callback for batch request responses."""
            if exception:
                logger.error(f"Batch request error for {request_id}: {exception}")
                batch_results[request_id] = None
            else:
                batch_results[request_id] = response
        
        # Add all messages in this batch to the batch request
        for msg_id in batch_ids:
            batch_request.add(
                gmail.users().messages().get(userId="me", id=msg_id, format="full"),
                callback=batch_callback,
                request_id=msg_id,
            )
        
        # Execute batch request (this will call callbacks for each response)
        try:
            batch_request.execute()
        except Exception as exc:
            logger.exception(f"Batch request execution failed: {exc}")
            # Continue with whatever we got
        
        # Process batch results
        for msg_id in batch_ids:
            msg = batch_results.get(msg_id)
            if not msg:
                logger.warning(f"Failed to fetch message {msg_id}")
                continue
            
            payload = msg.get("payload", {})
            headers = _extract_headers(payload)
            body = _extract_body(payload, prefer_html=False)
            html_body = _extract_body(payload, prefer_html=True)
            unsubscribe_url = extract_unsubscribe_url(headers, html_body or body)
            
            snippet = msg.get("snippet")
            if snippet:
                snippet = _decode_html_entities(snippet)
            
            email_record = create_email(
                user_id=user_id,
                gmail_message_id=msg_id,
                sender=headers.get("From"),
                subject=headers.get("Subject"),
                date=_format_internal_date(msg.get("internalDate")),
                body=body,
                snippet=snippet,
                raw_json=msg,
            )
            
            if email_record:
                new_emails_processed += 1
                
                # Store unsubscribe URL if found
                if unsubscribe_url:
                    existing = get_unsubscribe_for_email(email_record["id"])
                    if not existing:
                        create_unsubscribe_entry(
                            email_id=email_record["id"],
                            unsubscribe_url=unsubscribe_url,
                            status="pending",
                        )
        
        logger.info(f"Processed batch {batch_num}/{total_batches}")
    
    batch_duration = time.time() - batch_start
    total_duration = time.time() - start_time
    
    # Get stats after sync
    stats_after = get_sync_stats(user_id)
    total_after = stats_after["total_emails"]
    new_count = total_after - total_before
    
    logger.info(
        f"Sync complete: {new_emails_processed} new emails, {skipped_count} skipped, "
        f"total duration {total_duration:.2f}s (list: {list_duration:.2f}s, "
        f"dup_check: {dup_check_duration:.2f}s, batch: {batch_duration:.2f}s)"
    )
    
    return {
        "synced_count": len(message_ids),
        "new_count": new_count,
        "skipped_count": skipped_count,
        "total_emails": total_after,
        "processed_emails": stats_after["processed_emails"],
        "unprocessed_emails": stats_after["unprocessed_emails"],
        "duration_seconds": total_duration,
        "timestamp": datetime.utcnow().isoformat(),
    }
