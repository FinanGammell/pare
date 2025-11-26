"""SQLite model layer entrypoints for Pare."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from . import db


class EmailCategory(str, Enum):
    """Supported AI-driven email categories."""

    MEETING = "meeting"
    TASK = "task"
    JUNK = "junk"
    NEWSLETTER = "newsletter"
    OTHER = "other"


def init_app(app) -> None:
    """Expose DB initialization to the Flask app factory."""
    db.init_app(app)


def ensure_tables() -> None:
    """Create tables immediately (useful for CLI + tests)."""
    db.create_tables()

# Convenience re-exports -----------------------------------------------------
create_user = db.create_user
get_user_by_google_id = db.get_user_by_google_id
get_user_by_id = db.get_user_by_id
get_or_create_user = db.get_or_create_user
upsert_credentials = db.upsert_credentials
get_credentials_for_user = db.get_credentials_for_user
create_email = db.create_email
create_classification = db.create_classification
get_email_by_id = db.get_email_by_id
fetch_unclassified_emails = db.fetch_unclassified_emails
fetch_meetings = db.fetch_meetings
fetch_tasks = db.fetch_tasks
fetch_junk_emails = db.fetch_junk_emails
fetch_analytics = db.fetch_analytics
create_meeting = db.create_meeting
create_task = db.create_task
create_unsubscribe_entry = db.create_unsubscribe_entry


def fetch_category_summary(user_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Return dashboard-friendly grouped emails for a user."""
    rows = db.fetch_emails_with_categories(user_id)
    summary: Dict[str, List[Dict[str, Any]]] = {
        category.value: [] for category in EmailCategory
    }
    for row in rows:
        bucket = row.get("category")
        if bucket not in summary:
            summary[bucket] = []
        summary[bucket].append(
            {
                "id": row.get("id"),
                "subject": row.get("subject"),
                "snippet": row.get("snippet"),
                "date": row.get("date"),
            }
        )
    return summary


__all__ = [
    "EmailCategory",
    "init_app",
    "ensure_tables",
    "create_user",
    "get_user_by_google_id",
    "get_user_by_id",
    "get_or_create_user",
    "upsert_credentials",
    "get_credentials_for_user",
    "create_email",
    "create_classification",
    "get_email_by_id",
    "fetch_unclassified_emails",
    "fetch_meetings",
    "fetch_tasks",
    "fetch_junk_emails",
    "fetch_analytics",
    "create_meeting",
    "create_task",
    "create_unsubscribe_entry",
    "fetch_category_summary",
]
