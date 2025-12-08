"""Inbox orchestration helpers."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from models import (
    fetch_analytics,
    fetch_junk_emails,
    fetch_meetings,
    fetch_tasks,
    fetch_unclassified_emails,
    get_sync_stats,
)
from services.job_queue import get_job_queue
from services.jobs import ClassificationJob, GmailSyncJob

logger = logging.getLogger(__name__)


def get_dashboard_view(
    user_id: int,
    meetings_limit: int = 4,
    tasks_limit: int = 6,
    junk_limit: int = 6,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return sync stats + dashboard data for a user."""
    stats = get_sync_stats(user_id)
    sync_stats = {
        "synced_count": 0,
        "new_count": 0,
        "total_emails": stats["total_emails"],
        "processed_emails": stats["processed_emails"],
        "unprocessed_emails": stats["unprocessed_emails"],
        "newly_processed": 0,
    }
    analytics = fetch_analytics(user_id)
    meetings = fetch_meetings(user_id, limit=meetings_limit)
    tasks = fetch_tasks(user_id, limit=tasks_limit)
    junk_emails = fetch_junk_emails(user_id, limit=junk_limit)
    return sync_stats, analytics, meetings, tasks, junk_emails


def run_background_tick(user_id: int, classifier) -> None:
    """Enqueue sync + classification jobs for a user."""
    try:
        job_queue = get_job_queue()
        
        # Enqueue sync job
        try:
            sync_job = GmailSyncJob.create(user_id, max_results=500)
            execute_fn = sync_job._execute_fn
            if execute_fn is None:
                raise ValueError("Sync job has no execute function")
            job_id = job_queue.enqueue(
                job_type="gmail_sync",
                user_id=user_id,
                execute_fn=execute_fn,
            )
            logger.info(f"Enqueued sync job {job_id} for user {user_id}")
        except Exception as exc:
            logger.exception(f"Failed to enqueue sync job for user {user_id}: {exc}")
            return

        # Enqueue classification job for backlog
        try:
            unprocessed = fetch_unclassified_emails(user_id, limit=100)
            if unprocessed:
                email_ids = [email["id"] for email in unprocessed]
                classification_job = ClassificationJob(classifier).create(user_id, email_ids)
                execute_fn = classification_job._execute_fn
                if execute_fn is None:
                    raise ValueError("Classification job has no execute function")
                job_id = job_queue.enqueue(
                    job_type="classification",
                    user_id=user_id,
                    execute_fn=execute_fn,
                )
                logger.info(f"Enqueued classification job {job_id} for {len(email_ids)} emails")
        except Exception as exc:
            logger.exception(f"Failed to enqueue classification job for user {user_id}: {exc}")
    except Exception:
        logger.exception(f"Error in background tick for user {user_id}")


def process_all_unprocessed(user_id: int, classifier) -> int:
    """Process all currently unclassified emails for a user."""
    return classifier.process_all_unprocessed_emails(user_id)


