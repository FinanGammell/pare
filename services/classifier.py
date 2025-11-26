"""Email classification helpers using OpenAI."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI

from models import (
    EmailCategory,
    create_classification,
    create_meeting,
    create_task,
    create_unsubscribe_entry,
    fetch_unclassified_emails,
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
        rate_delay: float = 0.5,
        batch_size: int = 25,
    ) -> None:
        self.model = model
        self.rate_delay = rate_delay
        self.batch_size = batch_size
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

        body = (email_row.get("body") or email_row.get("snippet") or "")[:6000]
        prompt = (
            "You are Pare, an email productivity assistant. "
            "Classify the email into exactly one of: meeting, task, junk, newsletter, other. "
            "Return JSON with fields: category, confidence (0-1 float), "
            "meeting (object with title, start_time ISO8601, end_time, location, attendees list) "
            "when category is meeting; task (object with description and optional due_date ISO8601) "
            "when category is task; unsubscribe_url when the email is junk or newsletter; "
            "and notes for any extra context. "
            "If information is missing, set the field to null. "
            "Here is the email:\n\n"
            f"Sender: {email_row.get('sender') or 'Unknown'}\n"
            f"Subject: {email_row.get('subject') or 'No subject'}\n"
            f"Body:\n{body}"
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
            meeting = result.get("meeting") or {}
            create_meeting(
                email_id=email_row["id"],
                title=meeting.get("title"),
                start_time=meeting.get("start_time") or meeting.get("start"),
                end_time=meeting.get("end_time"),
                location=meeting.get("location"),
                attendees_json={"attendees": meeting.get("attendees") or []},
                confidence=confidence,
            )

        if category == EmailCategory.TASK.value:
            task = result.get("task") or {}
            create_task(
                email_id=email_row["id"],
                description=task.get("description") or email_row.get("subject"),
                due_date=task.get("due_date"),
                status="pending",
                confidence=confidence,
            )

        unsubscribe_url = (
            result.get("unsubscribe_url")
            or (result.get("unsubscribe") or {}).get("url")
        )
        if unsubscribe_url and category in (
            EmailCategory.JUNK.value,
            EmailCategory.NEWSLETTER.value,
        ):
            create_unsubscribe_entry(
                email_id=email_row["id"],
                unsubscribe_url=unsubscribe_url,
                status="pending",
            )
        return result

    def process_all_unprocessed_emails(self, user_id: int, batch_size: Optional[int] = None) -> int:
        """Process all emails without classifications for the given user."""
        size = batch_size or self.batch_size
        processed = 0

        while True:
            emails = fetch_unclassified_emails(user_id, limit=size)
            if not emails:
                break
            for email in emails:
                try:
                    self.process_email(email)
                    processed += 1
                    time.sleep(self.rate_delay)
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
