"""Email classification helpers using OpenAI."""
from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from openai import OpenAI

from models import (
    EmailCategory,
    create_classification,
    create_meeting,
    create_task,
    create_unsubscribe_entry,
    fetch_unclassified_emails,
    get_unsubscribe_for_email,
)

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = {
    EmailCategory.MEETING.value,
    EmailCategory.TASK.value,
    EmailCategory.JUNK.value,
    EmailCategory.NEWSLETTER.value,
    EmailCategory.OTHER.value,
}


class EmailClassifier:
    """Classify emails via OpenAI and persist structured data."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        rate_delay: float = 0.1,  # Reduced from 0.5s - OpenAI handles rate limiting
        batch_size: int = 25,
        max_workers: int = 5,  # Parallel processing workers
    ) -> None:
        self.model = model
        self.rate_delay = rate_delay
        self.batch_size = batch_size
        self.max_workers = max_workers
        api_key = os.getenv("OPENAI_API_KEY")
        self.client: Optional[OpenAI] = OpenAI(api_key=api_key) if api_key else None
        if not api_key:
            logger.warning("OPENAI_API_KEY not set; classifier will fall back to 'other'.")

    # ------------------------------------------------------------------ #
    # OpenAI calls
    # ------------------------------------------------------------------ #
    def classify_email(self, email_row: Dict[str, Any]) -> Dict[str, Any]:
        """Call OpenAI to classify an email and extract structured data."""
        if not self.client:
            return {
                "category": EmailCategory.OTHER.value,
                "confidence": 0.0,
                "notes": "OPENAI_API_KEY missing; default classification applied.",
            }

        # Optimized: Reduce body size for faster processing (most important info is usually at start)
        body = (email_row.get("body") or email_row.get("snippet") or "")[:4000]
        
        # More concise prompt for faster processing
        prompt = (
            "Classify this email into exactly one: meeting, task, junk, newsletter, or other.\n"
            "Return JSON: {category, confidence (0-1), "
            "meeting{title,start_time ISO8601,end_time,location,attendees[]}, "
            "task{description,due_date ISO8601}, unsubscribe_url, notes}\n"
            "Set missing fields to null.\n\n"
            f"From: {email_row.get('sender') or 'Unknown'}\n"
            f"Subject: {email_row.get('subject') or 'No subject'}\n"
            f"Body: {body}"
        )

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You output concise JSON only."},
                    {"role": "user", "content": prompt},
                ],
            )
            content = completion.choices[0].message.content
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content)  # type: ignore[arg-type]
            data = json.loads(content or "{}")
        except (Exception, json.JSONDecodeError, KeyError, IndexError) as exc:  # noqa: BLE001
            logger.warning("OpenAI classification failed: %s", exc)
            data = {
                "category": EmailCategory.OTHER.value,
                "confidence": 0.0,
                "notes": f"classifier_error: {exc}",
            }
        return data

    # ------------------------------------------------------------------ #
    # Persistence helpers
    # ------------------------------------------------------------------ #
    def process_email(self, email_row: Dict[str, Any]) -> Dict[str, Any]:
        """Classify a single email row and persist related records."""
        result = self.classify_email(email_row)
        raw_category = (result.get("category") or EmailCategory.OTHER.value).lower()
        category = raw_category if raw_category in ALLOWED_CATEGORIES else EmailCategory.OTHER.value
        confidence = float(result.get("confidence") or 0.0)

        create_classification(
            email_id=email_row["id"],
            category=category,
            confidence=confidence,
        )

        if category == EmailCategory.MEETING.value:
            import html
            meeting = result.get("meeting") or {}
            # Decode HTML entities in meeting data
            title = meeting.get("title")
            if title:
                try:
                    title = html.unescape(str(title))
                except Exception:
                    pass
            location = meeting.get("location")
            if location:
                try:
                    location = html.unescape(str(location))
                except Exception:
                    pass
            create_meeting(
                email_id=email_row["id"],
                title=title,
                start_time=meeting.get("start_time") or meeting.get("start"),
                end_time=meeting.get("end_time"),
                location=location,
                attendees_json={"attendees": meeting.get("attendees") or []},
                confidence=confidence,
            )

        if category == EmailCategory.TASK.value:
            import html
            task = result.get("task") or {}
            # Decode HTML entities in task description
            description = task.get("description") or email_row.get("subject")
            if description:
                try:
                    description = html.unescape(str(description))
                except Exception:
                    pass
            create_task(
                email_id=email_row["id"],
                description=description,
                due_date=task.get("due_date"),
                status="pending",
                confidence=confidence,
            )

        # Extract unsubscribe URL - prefer OpenAI result, but also check email headers/body
        unsubscribe_url = (
            result.get("unsubscribe_url")
            or (result.get("unsubscribe") or {}).get("url")
        )
        
        # If OpenAI didn't find one, try extracting from email data
        if not unsubscribe_url:
            from services.gmail_sync import extract_unsubscribe_url
            import json
            
            # Try to get headers and body from raw_json
            raw_json_str = email_row.get("raw_json")
            if raw_json_str:
                try:
                    if isinstance(raw_json_str, str):
                        raw_json = json.loads(raw_json_str)
                    else:
                        raw_json = raw_json_str
                    
                    payload = raw_json.get("payload", {})
                    headers = {}
                    for header in payload.get("headers", []):
                        name = header.get("name")
                        if name:
                            headers[name] = header.get("value", "")
                    
                    body = email_row.get("body") or ""
                    unsubscribe_url = extract_unsubscribe_url(headers, body)
                except (json.JSONDecodeError, KeyError, AttributeError):
                    pass
        
        # Only create unsubscribe entry if we found a URL and email is junk/newsletter
        # Also check if one already exists to avoid duplicates
        if unsubscribe_url and category in (
            EmailCategory.JUNK.value,
            EmailCategory.NEWSLETTER.value,
        ):
            existing = get_unsubscribe_for_email(email_row["id"])
            if not existing:
                create_unsubscribe_entry(
                    email_id=email_row["id"],
                    unsubscribe_url=unsubscribe_url,
                    status="pending",
                )
        return result

    def process_all_unprocessed_emails(self, user_id: int, batch_size: Optional[int] = None) -> int:
        """Process all emails without classifications using parallel processing for speed."""
        size = batch_size or self.batch_size
        processed = 0

        while True:
            emails = fetch_unclassified_emails(user_id, limit=size)
            if not emails:
                break
            
            # Process emails in parallel for much faster processing
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all emails for processing
                future_to_email = {
                    executor.submit(self.process_email, email): email
                    for email in emails
                }
                
                # Process results as they complete
                for future in as_completed(future_to_email):
                    email = future_to_email[future]
                    try:
                        future.result()  # Wait for completion and raise any exceptions
                        processed += 1
                        # Small delay to respect rate limits (reduced from per-email to per-batch)
                        if self.rate_delay > 0:
                            time.sleep(self.rate_delay / self.max_workers)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Failed to process email %s: %s", email.get("id"), exc)
                        create_classification(
                            email_id=email["id"],
                            category=EmailCategory.OTHER.value,
                            confidence=0.0,
                        )
            
            if len(emails) < size:
                break
        return processed
