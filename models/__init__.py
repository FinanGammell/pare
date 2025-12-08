"""Model layer - re-exports from db module."""
from __future__ import annotations

from typing import Any, Dict, List

from . import db

EmailCategory = db.EmailCategory
init_app = db.init_app
ensure_tables = db.ensure_tables

# Re-export all db functions
create_user = db.create_user
get_user_by_google_id = db.get_user_by_google_id
get_user_by_id = db.get_user_by_id
get_or_create_user = db.get_or_create_user
upsert_credentials = db.upsert_credentials
get_credentials_for_user = db.get_credentials_for_user
create_email = db.create_email
create_classification = db.create_classification
get_email_by_id = db.get_email_by_id
get_email_by_message_id = db.get_email_by_message_id
get_all_gmail_message_ids = db.get_all_gmail_message_ids
get_existing_message_ids = db.get_existing_message_ids
get_most_recent_email_date = db.get_most_recent_email_date
get_sync_stats = db.get_sync_stats
fetch_unclassified_emails = db.fetch_unclassified_emails
fetch_meetings = db.fetch_meetings
fetch_tasks = db.fetch_tasks
fetch_junk_emails = db.fetch_junk_emails
fetch_analytics = db.fetch_analytics
create_meeting = db.create_meeting
create_task = db.create_task
create_unsubscribe_entry = db.create_unsubscribe_entry
get_unsubscribe_for_email = db.get_unsubscribe_for_email
update_meetings_with_email_dates = db.update_meetings_with_email_dates
update_all_meetings_with_email_dates = db.update_all_meetings_with_email_dates
hide_email = db.hide_email
clear_user_data = db.clear_user_data
remove_duplicates = db.remove_duplicates


def fetch_category_summary(user_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Return dashboard-friendly grouped emails for a user."""
    rows = db.fetch_emails_with_categories(user_id)
    summary: Dict[str, List[Dict[str, Any]]] = {
        category.value: [] for category in EmailCategory
    }
    for row in rows:
        bucket = row.get("category")
        if bucket and bucket not in summary:
            summary[bucket] = []
        if bucket:
            summary[bucket].append({
                "id": row.get("id"),
                "subject": row.get("subject"),
                "snippet": row.get("snippet"),
                "date": row.get("date"),
            })
    return summary
