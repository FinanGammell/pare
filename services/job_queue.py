"""
Background job queue system for async processing.

This module provides a thread-based job queue for processing Gmail sync
and email classification tasks without blocking request handlers.

When a user clicks "Sync", we don't want to make them wait for all emails to sync.
Instead, we queue a job that runs in the background, and the frontend can check
the job status to see when it's done.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job execution status."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class Job:
    """Represents a background job."""

    job_id: str
    job_type: str
    user_id: int
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Store execute function separately (not in dataclass fields)."""
        self._execute_fn: Optional[Callable[[], Dict[str, Any]]] = None

    def set_execute_fn(self, fn: Callable[[], Dict[str, Any]]) -> None:
        """Set the execute function for this job."""
        self._execute_fn = fn

    def execute(self) -> Dict[str, Any]:
        """Execute the job and return results."""
        if not self._execute_fn:
            raise ValueError(f"Job {self.job_id} has no execute function")
        return self._execute_fn()


class JobQueue:
    """
    Thread-based job queue for background processing.
    
    This class manages a queue of jobs that run in background threads.
    Jobs can be things like "sync Gmail" or "classify emails".
    The queue processes jobs one at a time (or a few at a time with multiple workers).
    """

    def __init__(self, max_workers: int = 2) -> None:
        """
        Initialize the job queue.

        Args:
            max_workers: Maximum number of concurrent worker threads
                         (how many jobs can run at the same time)
        """
        self._jobs: Dict[str, Job] = {}  # All jobs by ID
        self._lock = threading.Lock()  # Thread safety lock
        self._queue: list[Job] = []  # Queue of jobs waiting to run
        self._max_workers = max_workers
        self._active_workers = 0  # How many workers are currently running jobs
        self._shutdown = False  # Flag to stop workers
        self._worker_threads: list[threading.Thread] = []  # List of worker threads
        self._app: Optional[Any] = None  # Flask app instance for app context

        # Start worker threads
        # These threads continuously check the queue for new jobs
        for i in range(max_workers):
            thread = threading.Thread(
                target=self._worker_loop,  # Function that runs in the thread
                name=f"JobQueue-Worker-{i}",
                daemon=True,  # Thread dies when main program exits
            )
            thread.start()
            self._worker_threads.append(thread)

        logger.info(f"JobQueue initialized with {max_workers} workers")

    def enqueue(
        self,
        job_type: str,
        user_id: int,
        execute_fn: Callable[[], Dict[str, Any]],
        job_id: Optional[str] = None,
    ) -> str:
        """Enqueue a new job.

        Args:
            job_type: Type identifier for the job (e.g., "gmail_sync", "classification")
            user_id: User ID associated with the job
            execute_fn: Function to execute when job runs
            job_id: Optional custom job ID (auto-generated if not provided)

        Returns:
            Job ID string
        """
        if job_id is None:
            job_id = str(uuid.uuid4())

        job = Job(
            job_id=job_id,
            job_type=job_type,
            user_id=user_id,
        )
        job.set_execute_fn(execute_fn)

        with self._lock:
            self._jobs[job_id] = job
            self._queue.append(job)

        logger.info(f"Enqueued job {job_id} (type: {job_type}, user: {user_id})")
        return job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job status and details.

        Args:
            job_id: Job ID to look up

        Returns:
            Job object or None if not found
        """
        with self._lock:
            return self._jobs.get(job_id)

    def _worker_loop(self) -> None:
        """Worker thread main loop."""
        while not self._shutdown:
            job = None
            try:
                # Get next job from queue
                with self._lock:
                    if self._queue:
                        job = self._queue.pop(0)
                        self._active_workers += 1

                if job:
                    self._execute_job(job)
                else:
                    # No jobs available, sleep briefly
                    time.sleep(0.1)

            except Exception:
                logger.exception("Error in worker thread")
            finally:
                if job:
                    with self._lock:
                        self._active_workers -= 1

    def _execute_job(self, job: Job) -> None:
        """Execute a job and update its status."""
        logger.info(f"Starting job {job.job_id} (type: {job.job_type})")
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()

        try:
            # Jobs need Flask app context for database operations
            # We'll pass the app instance when creating the queue
            if hasattr(self, '_app') and self._app:
                with self._app.app_context():
                    result = job.execute()
                    # Close DB connection after job completes
                    try:
                        from models.db import close_connection
                        close_connection()
                    except Exception:
                        pass
            else:
                # Fallback: try to get current app context
                try:
                    from flask import current_app
                    with current_app.app_context():
                        result = job.execute()
                except RuntimeError:
                    # No app context available, execute directly
                    # (This may fail for DB operations)
                    result = job.execute()
            
            job.status = JobStatus.COMPLETE
            job.completed_at = datetime.utcnow()
            job.result = result
            logger.info(
                f"Completed job {job.job_id} in "
                f"{(job.completed_at - job.started_at).total_seconds():.2f}s"
            )
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            job.error = str(exc)
            logger.exception(f"Job {job.job_id} failed: {exc}")

    def shutdown(self) -> None:
        """Shutdown the job queue and wait for workers to finish."""
        self._shutdown = True
        for thread in self._worker_threads:
            thread.join(timeout=5.0)


# Global job queue instance
_global_queue: Optional[JobQueue] = None


def get_job_queue(app=None) -> JobQueue:
    """Get or create the global job queue instance.
    
    Args:
        app: Optional Flask app instance to use for app context in jobs
    """
    global _global_queue
    if _global_queue is None:
        _global_queue = JobQueue(max_workers=2)
    if app and not hasattr(_global_queue, '_app'):
        _global_queue._app = app
    return _global_queue

