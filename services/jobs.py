"""Job implementations for Gmail sync and email classification."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from services.classifier import EmailClassifier
from services.gmail_sync import sync_and_process_emails
from services.job_queue import Job, get_job_queue

logger = logging.getLogger(__name__)


class GmailSyncJob:
    """Job for syncing Gmail emails."""

    @staticmethod
    def create(user_id: int, max_results: int = 500) -> Job:
        """Create a Gmail sync job.

        Args:
            user_id: User ID to sync emails for
            max_results: Maximum number of emails to fetch

        Returns:
            Job instance
        """
        def execute() -> Dict[str, Any]:
            """Execute the sync job."""
            logger.info(f"Starting Gmail sync job for user {user_id} (max_results={max_results})")
            result = sync_and_process_emails(user_id, max_results=max_results)
            logger.info(
                f"Gmail sync job completed: {result.get('new_count', 0)} new emails, "
                f"{result.get('skipped_count', 0)} skipped"
            )
            return result

        job = Job(
            job_id="",  # Will be set by queue
            job_type="gmail_sync",
            user_id=user_id,
        )
        job.set_execute_fn(execute)
        return job


class ClassificationJob:
    """Job for classifying emails."""

    def __init__(self, classifier: EmailClassifier) -> None:
        """Initialize classification job.

        Args:
            classifier: EmailClassifier instance to use
        """
        self._classifier = classifier

    def create(self, user_id: int, email_ids: List[int]) -> Job:
        """Create a classification job.

        Args:
            user_id: User ID
            email_ids: List of email IDs to classify

        Returns:
            Job instance
        """
        def execute() -> Dict[str, Any]:
            """Execute the classification job."""
            logger.info(
                f"Starting classification job for user {user_id}: "
                f"{len(email_ids)} emails"
            )
            
            from models import get_email_by_id
            
            processed = 0
            failed = 0
            
            for email_id in email_ids:
                try:
                    email = get_email_by_id(email_id)
                    if not email:
                        logger.warning(f"Email {email_id} not found")
                        failed += 1
                        continue
                    
                    self._classifier.process_email(email)
                    processed += 1
                except Exception as exc:
                    logger.exception(f"Failed to classify email {email_id}: {exc}")
                    failed += 1
            
            result = {
                "processed": processed,
                "failed": failed,
                "total": len(email_ids),
            }
            logger.info(
                f"Classification job completed: {processed} processed, {failed} failed"
            )
            return result

        job = Job(
            job_id="",  # Will be set by queue
            job_type="classification",
            user_id=user_id,
        )
        job.set_execute_fn(execute)
        return job

