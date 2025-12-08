"""
Email classification helpers using OpenAI.

This module uses OpenAI's GPT model to classify emails into categories:
- Meeting: Emails about meetings (extracts time, location, attendees)
- Task: Emails with action items or to-dos
- Junk: Spam or unwanted emails
- Newsletter: Marketing emails, newsletters
- Other: Everything else

The classifier also extracts structured data from emails (meeting times, task due dates, etc.)
"""
from __future__ import annotations

import html
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

# Valid email categories - only these are allowed
ALLOWED_CATEGORIES = {
    EmailCategory.MEETING.value,
    EmailCategory.TASK.value,
    EmailCategory.JUNK.value,
    EmailCategory.NEWSLETTER.value,
    EmailCategory.OTHER.value,
}


class EmailClassifier:
    """
    Classifies emails using OpenAI's GPT model.
    
    This class sends email content to OpenAI and asks it to categorize the email
    and extract structured data (meeting times, task due dates, etc.).
    """
    def __init__(
        self,
        model: str = "gpt-4o-mini",  # Which OpenAI model to use (gpt-4o-mini is fast and cheap)
        rate_delay: float = 0.1,  # Delay between API calls to avoid rate limits
        batch_size: int = 25,  # How many emails to process in each batch
        max_workers: int = 5,  # How many threads to use for parallel processing
    ) -> None:
        self.model = model
        self.rate_delay = rate_delay
        self.batch_size = batch_size
        self.max_workers = max_workers
        # Get OpenAI API key from environment
        api_key = os.getenv("OPENAI_API_KEY")
        self.client: Optional[OpenAI] = OpenAI(api_key=api_key) if api_key else None
        if not api_key:
            logger.warning("OPENAI_API_KEY not set; classifier will fall back to 'other'.")

    def classify_email(self, email_row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify a single email using OpenAI.
        
        Sends the email content to OpenAI and asks it to:
        1. Categorize the email (meeting, task, junk, newsletter, other)
        2. Extract structured data (meeting times, task due dates, etc.)
        3. Find unsubscribe URLs
        
        Returns a dictionary with the classification results.
        """
        # If no OpenAI API key, just return "other" category
        if not self.client:
            return {
                "category": EmailCategory.OTHER.value,
                "confidence": 0.0,
                "notes": "OPENAI_API_KEY missing; default classification applied.",
            }

        # Get email body (limit to 4000 chars to avoid token limits)
        body = (email_row.get("body") or email_row.get("snippet") or "")[:4000]
        email_date = email_row.get("date") or ""
        
        # Build the prompt for OpenAI
        # This tells OpenAI what we want it to do and what format to return
        prompt = (
            "Classify: meeting, task, junk, newsletter, or other.\n"
            "JSON: {category, confidence (0-1), "
            "meeting{title,start_time ISO8601,end_time,location,attendees[]}, "
            "task{description,due_date ISO8601}, unsubscribe_url, notes}\n"
            "Dates: ISO8601 format YYYY-MM-DDTHH:mm:ss (no timezone = Eastern Time). Use 24-hour format.\n"
            "Meetings: Extract time from content (e.g., '8PM', '7:45PM', '6pm'). Use meeting start time, not arrival. "
            "'Tonight'/'today' = email date. 'Tomorrow' = email date +1 day. "
            "ALWAYS use the time mentioned in the email content. "
            "CRITICAL: Use 24-hour format. PM times: '6pm'/'6PM' = 18:00, '4pm'/'4PM' = 16:00, '8pm'/'8PM' = 20:00, '12pm'/'noon' = 12:00. "
            "AM times: '6am'/'6AM' = 06:00, '9am'/'9AM' = 09:00, '12am'/'midnight' = 00:00. "
            "If time has no AM/PM and is 1-11 (e.g., '6', '4'), assume PM/afternoon (18:00, 16:00). "
            "Only use email sent time if NO time is mentioned in the content. "
            "End time: +1 hour if not specified.\n"
            f"Email date: {email_date}\n"
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
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            logger.warning("OpenAI classification failed: %s", exc)
            data = {
                "category": EmailCategory.OTHER.value,
                "confidence": 0.0,
                "notes": f"classifier_error: {exc}",
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error in classification: %s", exc)
            data = {
                "category": EmailCategory.OTHER.value,
                "confidence": 0.0,
                "notes": f"classifier_error: {exc}",
            }
        return data

    def process_email(self, email_row: Dict[str, Any]) -> Dict[str, Any]:
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
            title = meeting.get("title")
            if title:
                try:
                    title = html.unescape(str(title))
                except (ValueError, TypeError):
                    pass
            location = meeting.get("location")
            if location:
                try:
                    location = html.unescape(str(location))
                except (ValueError, TypeError):
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
            headers = {}
            body = email_row.get("body") or email_row.get("snippet") or ""
            
            if raw_json_str:
                try:
                    if isinstance(raw_json_str, str):
                        raw_json = json.loads(raw_json_str)
                    else:
                        raw_json = raw_json_str
                    
                    payload = raw_json.get("payload", {})
                    
                    # Extract headers
                    for header in payload.get("headers", []):
                        name = header.get("name")
                        if name:
                            headers[name] = header.get("value", "")
                    
                    # Get body - prefer HTML for better link extraction, fallback to plain text
                    from services.gmail_sync import _extract_body
                    # Try HTML first for better link detection
                    html_body = _extract_body(payload, prefer_html=True)
                    plain_body = _extract_body(payload, prefer_html=False)
                    stored_body = email_row.get("body") or ""
                    
                    # Use the longest body available (HTML usually has more content)
                    extracted_body = html_body if html_body and len(html_body) > len(plain_body) else plain_body
                    if stored_body and len(stored_body) > len(extracted_body):
                        body = stored_body
                    elif extracted_body:
                        body = extracted_body
                    
                except (json.JSONDecodeError, KeyError, AttributeError) as e:
                    logger.debug(f"Error extracting from raw_json: {e}")
            
            # Extract unsubscribe URL from headers and body (even if body is short)
            if headers or body:
                unsubscribe_url = extract_unsubscribe_url(headers, body)
        
        # Create unsubscribe entry for ALL emails if we found a URL (not just junk/newsletter)
        # This allows unsubscribe buttons on meetings, tasks, etc.
        # Also check if one already exists to avoid duplicates
        if unsubscribe_url:
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
        start_time = time.time()
        size = batch_size or self.batch_size
        processed = 0
        failed = 0

        logger.info(f"Starting batch classification for user {user_id} (batch_size={size})")

        while True:
            batch_start = time.time()
            emails = fetch_unclassified_emails(user_id, limit=size)
            if not emails:
                break
            
            logger.info(f"Processing batch of {len(emails)} emails")
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_email = {
                    executor.submit(self.process_email, email): email
                    for email in emails
                }
                
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
                        failed += 1
            
            batch_duration = time.time() - batch_start
            logger.info(
                f"Batch completed: {processed} processed, {failed} failed, "
                f"duration {batch_duration:.2f}s ({len(emails)/batch_duration:.1f} emails/sec)"
            )
            
            if len(emails) < size:
                break
        
        total_duration = time.time() - start_time
        logger.info(
            f"Classification complete: {processed} processed, {failed} failed, "
            f"total duration {total_duration:.2f}s "
            f"({processed/total_duration:.1f} emails/sec)"
        )
        return processed
