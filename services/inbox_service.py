"""High-level inbox orchestration services.

This module provides a thin application-service layer between Flask routes and
our lower-level Gmail sync + classification logic + database helpers.

The goal is to keep routes thin and centralize orchestration logic here,
without changing underlying behavior.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from models import (
    fetch_analytics,
    fetch_junk_emails,
    fetch_meetings,
    fetch_tasks,
    fetch_unclassified_emails,
    get_sync_stats,
)
from services.gmail_sync import sync_and_process_emails


class InboxService:
    """Orchestrate sync + classification + dashboard data retrieval."""

    def __init__(self, classifier) -> None:
        # We depend on the EmailClassifier interface but avoid importing it here
        # to keep layering simple and prevent circular imports.
        self._classifier = classifier

    # ------------------------------------------------------------------ #
    # Dashboard helpers
    # ------------------------------------------------------------------ #
    def get_dashboard_view(
        self,
        user_id: int,
        meetings_limit: int = 4,
        tasks_limit: int = 6,
        junk_limit: int = 6,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return sync stats + dashboard data for a user.

        Returns:
            (sync_stats, analytics, meetings, tasks, junk_emails)
        """
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

    # ------------------------------------------------------------------ #
    # Background tick
    # ------------------------------------------------------------------ #
    def run_background_tick(self, user_id: int) -> None:
        """Run one non-blocking 'tick' of sync + light classification.

        This is intended to be called from a background thread and should
        never raise. It mirrors the previous behavior in `app._background_sync_and_process`.
        """
        try:
            # Sync a small batch of emails (incremental, non-blocking)
            try:
                sync_and_process_emails(user_id, max_results=50)
            except Exception:
                # Fail silently in background – logging is handled at caller level.
                return

            # Process a small batch of unprocessed emails
            try:
                unprocessed = fetch_unclassified_emails(user_id, limit=10)
                for email in unprocessed:
                    try:
                        self._classifier.process_email(email)
                    except Exception:
                        # Continue processing other emails
                        continue
            except Exception:
                # Ignore classification errors in background tick
                return
        except Exception:
            # Absolute safety net – caller may also log.
            return

    # ------------------------------------------------------------------ #
    # Manual sync / process helpers (legacy routes)
    # ------------------------------------------------------------------ #
    def process_all_unprocessed(self, user_id: int) -> int:
        """Process all currently unclassified emails for a user.

        Thin wrapper around classifier method to keep routes thin.
        """
        return self._classifier.process_all_unprocessed_emails(user_id)


