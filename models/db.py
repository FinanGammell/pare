"""SQLite helpers and schema definitions for Pare."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from flask import g

from config import DB_PATH

_CONNECTION_KEY = "pare_db_conn"

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        google_user_id TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS credentials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        access_token TEXT,
        refresh_token TEXT,
        token_expiry TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        gmail_message_id TEXT NOT NULL,
        sender TEXT,
        subject TEXT,
        date TEXT,
        body TEXT,
        snippet TEXT,
        raw_json TEXT,
        hidden INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, gmail_message_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS classifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        confidence REAL DEFAULT 0.0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (email_id, category),
        FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id INTEGER NOT NULL UNIQUE,
        title TEXT,
        start_time TEXT,
        end_time TEXT,
        location TEXT,
        attendees_json TEXT,
        confidence REAL DEFAULT 0.0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id INTEGER NOT NULL UNIQUE,
        description TEXT,
        due_date TEXT,
        status TEXT DEFAULT 'pending',
        confidence REAL DEFAULT 0.0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS unsubscribe_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id INTEGER NOT NULL UNIQUE,
        unsubscribe_url TEXT,
        status TEXT DEFAULT 'unknown',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
    )
    """,
]


def _create_connection() -> sqlite3.Connection:
    """Create a new SQLite connection with proper settings for concurrency."""
    # Add timeout for concurrent access (5 seconds)
    # Enable WAL mode for better concurrency
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    # Enable WAL mode for better concurrency (allows multiple readers and one writer)
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.OperationalError:
        # WAL mode might not be available in some SQLite versions, continue without it
        pass
    return conn


def get_connection() -> sqlite3.Connection:
    """Return a cached SQLite connection stored on the Flask `g` object."""
    try:
        conn = getattr(g, _CONNECTION_KEY, None)
    except RuntimeError:
        # No Flask application context (e.g., in background thread)
        # Create a new connection for this operation
        return _create_connection()
    
    if conn is None:
        conn = _create_connection()
        setattr(g, _CONNECTION_KEY, conn)
    return conn


def close_connection(_: Optional[BaseException] = None) -> None:
    """Close the cached SQLite connection if it exists."""
    conn = getattr(g, _CONNECTION_KEY, None)
    if conn is not None:
        conn.close()
        if hasattr(g, _CONNECTION_KEY):
            delattr(g, _CONNECTION_KEY)


@contextmanager
def cursor() -> Iterator[sqlite3.Cursor]:
    """Context manager yielding a SQLite cursor with automatic commit and retry logic."""
    max_retries = 3
    retry_count = 0
    conn = None
    cur = None
    
    while retry_count < max_retries:
        try:
            conn = get_connection()
            cur = conn.cursor()
            try:
                yield cur
                conn.commit()
                break  # Success, exit retry loop
            except sqlite3.OperationalError as e:
                if cur:
                    cur.close()
                if "database is locked" in str(e).lower() and retry_count < max_retries - 1:
                    retry_count += 1
                    import time
                    time.sleep(0.1 * retry_count)  # Exponential backoff
                    continue
                else:
                    raise
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower() and retry_count < max_retries - 1:
                retry_count += 1
                import time
                time.sleep(0.1 * retry_count)  # Exponential backoff
                continue
            else:
                raise
        finally:
            if cur and retry_count >= max_retries - 1:
                try:
                    cur.close()
                except Exception:
                    pass


def remove_duplicates() -> None:
    """Remove duplicate entries from emails, meetings, tasks, and unsubscribe_entries tables."""
    conn = get_connection()
    
    # Remove duplicate emails, keeping the most recent one (by created_at or id)
    # First, delete classifications, meetings, tasks, and unsubscribe entries for duplicate emails
    conn.execute("""
        DELETE FROM classifications
        WHERE email_id IN (
            SELECT id FROM emails
            WHERE id NOT IN (
                SELECT MIN(id) 
                FROM emails 
                GROUP BY user_id, gmail_message_id
            )
        )
    """)
    
    conn.execute("""
        DELETE FROM meetings
        WHERE email_id IN (
            SELECT id FROM emails
            WHERE id NOT IN (
                SELECT MIN(id) 
                FROM emails 
                GROUP BY user_id, gmail_message_id
            )
        )
    """)
    
    conn.execute("""
        DELETE FROM tasks
        WHERE email_id IN (
            SELECT id FROM emails
            WHERE id NOT IN (
                SELECT MIN(id) 
                FROM emails 
                GROUP BY user_id, gmail_message_id
            )
        )
    """)
    
    conn.execute("""
        DELETE FROM unsubscribe_entries
        WHERE email_id IN (
            SELECT id FROM emails
            WHERE id NOT IN (
                SELECT MIN(id) 
                FROM emails 
                GROUP BY user_id, gmail_message_id
            )
        )
    """)
    
    # Now remove duplicate emails themselves, keeping the most recent one
    conn.execute("""
        DELETE FROM emails
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM emails 
            GROUP BY user_id, gmail_message_id
        )
    """)
    
    # Remove duplicate meetings, keeping the most recent one
    conn.execute("""
        DELETE FROM meetings
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM meetings 
            GROUP BY email_id
        )
    """)
    
    # Remove duplicate tasks, keeping the most recent one
    conn.execute("""
        DELETE FROM tasks
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM tasks 
            GROUP BY email_id
        )
    """)
    
    # Remove duplicate unsubscribe entries, keeping the most recent one
    conn.execute("""
        DELETE FROM unsubscribe_entries
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM unsubscribe_entries 
            GROUP BY email_id
        )
    """)
    
    conn.commit()


def create_tables() -> None:
    """Create all tables defined in `DDL_STATEMENTS`. Safe to call repeatedly."""
    conn = get_connection()
    for statement in DDL_STATEMENTS:
        conn.execute(statement)
    conn.commit()
    
    # Add hidden column to emails table if it doesn't exist (migration)
    try:
        conn.execute("ALTER TABLE emails ADD COLUMN hidden INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists or table doesn't exist yet
        pass
    
    # Remove any existing duplicates before adding constraints
    try:
        remove_duplicates()
    except sqlite3.OperationalError:
        # Tables might not exist yet
        pass
    
    # Add UNIQUE constraints to existing tables if they don't exist
    try:
        # Ensure unique constraint on emails (user_id, gmail_message_id)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_emails_user_gmail_id ON emails(user_id, gmail_message_id)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_meetings_email_id ON meetings(email_id)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_email_id ON tasks(email_id)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_unsubscribe_email_id ON unsubscribe_entries(email_id)")
        conn.commit()
    except sqlite3.OperationalError:
        # Constraints might already exist or table might not exist yet
        pass


def clear_all_data() -> None:
    """Clear all data from all tables. Use with caution!"""
    conn = get_connection()
    # Delete in order to respect foreign key constraints
    conn.execute("DELETE FROM unsubscribe_entries")
    conn.execute("DELETE FROM tasks")
    conn.execute("DELETE FROM meetings")
    conn.execute("DELETE FROM classifications")
    conn.execute("DELETE FROM emails")
    conn.execute("DELETE FROM credentials")
    conn.execute("DELETE FROM users")
    conn.commit()


def clear_user_data(user_id: int) -> None:
    """Clear all data for a specific user. Use with caution!"""
    conn = get_connection()
    # Delete in order to respect foreign key constraints
    conn.execute("DELETE FROM unsubscribe_entries WHERE email_id IN (SELECT id FROM emails WHERE user_id = ?)", (user_id,))
    conn.execute("DELETE FROM tasks WHERE email_id IN (SELECT id FROM emails WHERE user_id = ?)", (user_id,))
    conn.execute("DELETE FROM meetings WHERE email_id IN (SELECT id FROM emails WHERE user_id = ?)", (user_id,))
    conn.execute("DELETE FROM classifications WHERE email_id IN (SELECT id FROM emails WHERE user_id = ?)", (user_id,))
    conn.execute("DELETE FROM emails WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM credentials WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()


def init_app(app) -> None:
    """Register teardown + first-request hooks for managing the DB."""

    @app.teardown_appcontext
    def teardown(exception):  # type: ignore[unused-ignore]
        close_connection(exception)

    # Note: Table creation is handled by ensure_tables() call in app.py
    # before_first_request is deprecated in Flask 3.0+


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def create_user(google_user_id: str, email: str) -> Dict[str, Any]:
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (google_user_id, email, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(google_user_id) DO UPDATE SET email=excluded.email
            """,
            (google_user_id, email, datetime.utcnow().isoformat()),
        )
    return get_user_by_google_id(google_user_id)  # type: ignore[return-value]


def get_user_by_google_id(google_user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE google_user_id = ?",
        (google_user_id,),
    ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_or_create_user(google_user_id: str, email: str) -> Dict[str, Any]:
    user = get_user_by_google_id(google_user_id)
    if user:
        return user
    return create_user(google_user_id, email)


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def upsert_credentials(
    user_id: int,
    access_token: str,
    refresh_token: str,
    token_expiry: Optional[str],
) -> Dict[str, Any]:
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO credentials (user_id, access_token, refresh_token, token_expiry)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                access_token=excluded.access_token,
                refresh_token=excluded.refresh_token,
                token_expiry=excluded.token_expiry
            """,
            (user_id, access_token, refresh_token, token_expiry),
        )
    return get_credentials_for_user(user_id)  # type: ignore[return-value]


def get_credentials_for_user(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM credentials WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Email + classification helpers
# ---------------------------------------------------------------------------

def create_email(
    user_id: int,
    gmail_message_id: str,
    sender: Optional[str],
    subject: Optional[str],
    date: Optional[str],
    body: Optional[str],
    snippet: Optional[str],
    raw_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload_json = json.dumps(raw_json or {})
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO emails (
                user_id, gmail_message_id, sender, subject, date, body, snippet, raw_json, hidden, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(user_id, gmail_message_id) DO UPDATE SET
                sender=excluded.sender,
                subject=excluded.subject,
                date=excluded.date,
                body=excluded.body,
                snippet=excluded.snippet,
                raw_json=excluded.raw_json,
                hidden=emails.hidden
            """,
            (
                user_id,
                gmail_message_id,
                sender,
                subject,
                date,
                body,
                snippet,
                payload_json,
                datetime.utcnow().isoformat(),
            ),
        )
    return get_email_by_message_id(user_id, gmail_message_id)  # type: ignore[return-value]


def get_email_by_message_id(user_id: int, gmail_message_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT * FROM emails
        WHERE user_id = ? AND gmail_message_id = ?
        """,
        (user_id, gmail_message_id),
    ).fetchone()
    return dict(row) if row else None


def get_all_gmail_message_ids(user_id: int) -> List[str]:
    """Get all gmail_message_ids for a user. Used for proactive duplicate prevention."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT gmail_message_id FROM emails
        WHERE user_id = ? AND gmail_message_id IS NOT NULL
        """,
        (user_id,),
    ).fetchall()
    return [row["gmail_message_id"] for row in rows if row["gmail_message_id"]]


def get_email_by_id(email_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM emails WHERE id = ?",
        (email_id,),
    ).fetchone()
    return dict(row) if row else None


def get_most_recent_email_date(user_id: int) -> Optional[str]:
    """Get the date of the most recently synced email for a user."""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT date FROM emails
        WHERE user_id = ?
        ORDER BY date DESC NULLS LAST, created_at DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    return row["date"] if row and row["date"] else None


def get_sync_stats(user_id: int) -> Dict[str, Any]:
    """Get sync statistics: total emails, processed count, unprocessed count."""
    conn = get_connection()
    total = conn.execute(
        "SELECT COUNT(*) AS count FROM emails WHERE user_id = ? AND (hidden IS NULL OR hidden = 0)",
        (user_id,),
    ).fetchone()["count"]
    
    processed = conn.execute(
        """
        SELECT COUNT(DISTINCT classifications.email_id) AS count
        FROM classifications
        JOIN emails ON emails.id = classifications.email_id
        WHERE emails.user_id = ? AND (emails.hidden IS NULL OR emails.hidden = 0)
        """,
        (user_id,),
    ).fetchone()["count"]
    
    return {
        "total_emails": total,
        "processed_emails": processed,
        "unprocessed_emails": total - processed,
    }


def fetch_unclassified_emails(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM emails
        WHERE user_id = ?
          AND (hidden IS NULL OR hidden = 0)
          AND NOT EXISTS (
            SELECT 1 FROM classifications WHERE classifications.email_id = emails.id
          )
        ORDER BY date DESC NULLS LAST, created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def hide_email(user_id: int, email_id: int) -> None:
    """Mark an email as hidden so it doesn't appear in lists."""
    conn = get_connection()
    conn.execute(
        "UPDATE emails SET hidden = 1 WHERE id = ? AND user_id = ?",
        (email_id, user_id),
    )
    conn.commit()


def create_classification(
    email_id: int,
    category: str,
    confidence: float,
) -> Dict[str, Any]:
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO classifications (email_id, category, confidence)
            VALUES (?, ?, ?)
            ON CONFLICT(email_id, category) DO UPDATE SET
                confidence=excluded.confidence,
                created_at=CURRENT_TIMESTAMP
            """,
            (email_id, category, confidence),
        )
    return get_classification_for_email(email_id, category)  # type: ignore[return-value]


def get_classification_for_email(email_id: int, category: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT * FROM classifications
        WHERE email_id = ? AND category = ?
        """,
        (email_id, category),
    ).fetchone()
    return dict(row) if row else None


def fetch_emails_with_categories(user_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT emails.id, emails.subject, emails.snippet, emails.date, classifications.category
        FROM emails
        JOIN classifications ON classifications.email_id = emails.id
        WHERE emails.user_id = ? AND (emails.hidden IS NULL OR emails.hidden = 0)
        ORDER BY emails.date DESC NULLS LAST, emails.created_at DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_meetings(user_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    query = """
        SELECT DISTINCT meetings.id, meetings.email_id, meetings.title, meetings.start_time, 
               meetings.end_time, meetings.location, meetings.attendees_json, meetings.confidence,
               emails.subject, emails.sender, emails.gmail_message_id, emails.date AS email_date
        FROM meetings
        JOIN emails ON emails.id = meetings.email_id
        WHERE emails.user_id = ? AND (emails.hidden IS NULL OR emails.hidden = 0)
        ORDER BY COALESCE(meetings.start_time, emails.date) ASC
    """
    params: List[Any] = [user_id]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(query, params).fetchall()
    meetings: List[Dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        attendees_payload = record.get("attendees_json")
        if attendees_payload:
            try:
                record["attendees_json"] = json.loads(attendees_payload)
            except json.JSONDecodeError:
                record["attendees_json"] = {}
        else:
            record["attendees_json"] = {}
        meetings.append(record)
    return meetings


def fetch_tasks(user_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    query = """
        SELECT DISTINCT tasks.id, tasks.email_id, tasks.description, tasks.due_date, 
               tasks.status, tasks.confidence, emails.subject, emails.sender, emails.gmail_message_id
        FROM tasks
        JOIN emails ON emails.id = tasks.email_id
        WHERE emails.user_id = ? AND (emails.hidden IS NULL OR emails.hidden = 0)
        ORDER BY COALESCE(tasks.due_date, emails.date) ASC
    """
    params: List[Any] = [user_id]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def fetch_junk_emails(user_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    query = """
        SELECT DISTINCT
            emails.id, emails.user_id, emails.gmail_message_id, emails.sender, 
            emails.subject, emails.date, emails.body, emails.snippet, emails.raw_json,
            emails.created_at,
            classifications.category,
            unsubscribe_entries.unsubscribe_url
        FROM emails
        JOIN classifications ON classifications.email_id = emails.id
        LEFT JOIN unsubscribe_entries ON unsubscribe_entries.email_id = emails.id
        WHERE emails.user_id = ?
          AND classifications.category IN ('junk', 'newsletter')
          AND (emails.hidden IS NULL OR emails.hidden = 0)
        ORDER BY emails.date DESC NULLS LAST, emails.created_at DESC
    """
    params: List[Any] = [user_id]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def fetch_analytics(user_id: int) -> Dict[str, Any]:
    conn = get_connection()
    total_emails = conn.execute(
        "SELECT COUNT(*) AS count FROM emails WHERE user_id = ? AND (hidden IS NULL OR hidden = 0)",
        (user_id,),
    ).fetchone()["count"]
    processed_emails = conn.execute(
        """
        SELECT COUNT(DISTINCT classifications.email_id) AS count
        FROM classifications
        JOIN emails ON emails.id = classifications.email_id
        WHERE emails.user_id = ? AND (emails.hidden IS NULL OR emails.hidden = 0)
        """,
        (user_id,),
    ).fetchone()["count"]
    category_rows = conn.execute(
        """
        SELECT classifications.category, COUNT(*) AS count
        FROM classifications
        JOIN emails ON emails.id = classifications.email_id
        WHERE emails.user_id = ? AND (emails.hidden IS NULL OR emails.hidden = 0)
        GROUP BY classifications.category
        """,
        (user_id,),
    ).fetchall()
    category_counts = {row["category"]: row["count"] for row in category_rows}
    meeting_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM meetings
        JOIN emails ON emails.id = meetings.email_id
        WHERE emails.user_id = ? AND (emails.hidden IS NULL OR emails.hidden = 0)
        """,
        (user_id,),
    ).fetchone()["count"]
    task_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM tasks
        JOIN emails ON emails.id = tasks.email_id
        WHERE emails.user_id = ? AND (emails.hidden IS NULL OR emails.hidden = 0)
        """,
        (user_id,),
    ).fetchone()["count"]
    junk_count = sum(
        count
        for category, count in category_counts.items()
        if category in ("junk", "newsletter")
    )
    return {
        "total_emails": total_emails,
        "processed_emails": processed_emails,
        "category_counts": category_counts,
        "meeting_count": meeting_count,
        "task_count": task_count,
        "junk_count": junk_count,
    }


# ---------------------------------------------------------------------------
# Meetings / Tasks / Unsubscribe helpers
# ---------------------------------------------------------------------------

def create_meeting(
    email_id: int,
    title: Optional[str],
    start_time: Optional[str],
    end_time: Optional[str],
    location: Optional[str],
    attendees_json: Optional[Dict[str, Any]],
    confidence: float,
) -> Dict[str, Any]:
    """Create or update a meeting for an email. Only one meeting per email."""
    with cursor() as cur:
        # Check if meeting already exists
        existing = cur.execute(
            "SELECT id FROM meetings WHERE email_id = ?",
            (email_id,),
        ).fetchone()
        
        if existing:
            # Update existing meeting
            cur.execute(
                """
                UPDATE meetings SET
                    title = ?,
                    start_time = ?,
                    end_time = ?,
                    location = ?,
                    attendees_json = ?,
                    confidence = ?
                WHERE email_id = ?
                """,
                (
                    title,
                    start_time,
                    end_time,
                    location,
                    json.dumps(attendees_json or {}),
                    confidence,
                    email_id,
                ),
            )
        else:
            # Insert new meeting
            cur.execute(
                """
                INSERT INTO meetings (
                    email_id, title, start_time, end_time, location, attendees_json, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email_id,
                    title,
                    start_time,
                    end_time,
                    location,
                    json.dumps(attendees_json or {}),
                    confidence,
                ),
            )
    return get_meeting_for_email(email_id)  # type: ignore[return-value]


def get_meeting_for_email(email_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM meetings WHERE email_id = ? ORDER BY id DESC LIMIT 1",
        (email_id,),
    ).fetchone()
    return dict(row) if row else None


def create_task(
    email_id: int,
    description: Optional[str],
    due_date: Optional[str],
    status: str,
    confidence: float,
) -> Dict[str, Any]:
    """Create or update a task for an email. Only one task per email."""
    with cursor() as cur:
        # Check if task already exists
        existing = cur.execute(
            "SELECT id FROM tasks WHERE email_id = ?",
            (email_id,),
        ).fetchone()
        
        if existing:
            # Update existing task (preserve status - don't overwrite user changes)
            cur.execute(
                """
                UPDATE tasks SET
                    description = ?,
                    due_date = ?,
                    confidence = ?
                WHERE email_id = ? AND status = 'pending'
                """,
                (
                    description,
                    due_date,
                    confidence,
                    email_id,
                ),
            )
        else:
            # Insert new task
            cur.execute(
                """
                INSERT INTO tasks (email_id, description, due_date, status, confidence)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    email_id,
                    description,
                    due_date,
                    status,
                    confidence,
                ),
            )
    return get_task_for_email(email_id)  # type: ignore[return-value]


def get_task_for_email(email_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM tasks WHERE email_id = ? ORDER BY id DESC LIMIT 1",
        (email_id,),
    ).fetchone()
    return dict(row) if row else None


def create_unsubscribe_entry(
    email_id: int,
    unsubscribe_url: Optional[str],
    status: str,
) -> Dict[str, Any]:
    """Create or update an unsubscribe entry for an email. Only one entry per email."""
    with cursor() as cur:
        # Check if unsubscribe entry already exists
        existing = cur.execute(
            "SELECT id FROM unsubscribe_entries WHERE email_id = ?",
            (email_id,),
        ).fetchone()
        
        if existing:
            # Update existing entry
            cur.execute(
                """
                UPDATE unsubscribe_entries SET
                    unsubscribe_url = ?,
                    status = ?
                WHERE email_id = ?
                """,
                (
                    unsubscribe_url,
                    status,
                    email_id,
                ),
            )
        else:
            # Insert new entry
            cur.execute(
                """
                INSERT INTO unsubscribe_entries (email_id, unsubscribe_url, status)
                VALUES (?, ?, ?)
                """,
                (
                    email_id,
                    unsubscribe_url,
                    status,
                ),
            )
    return get_unsubscribe_for_email(email_id)  # type: ignore[return-value]


def get_unsubscribe_for_email(email_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM unsubscribe_entries WHERE email_id = ? ORDER BY id DESC LIMIT 1",
        (email_id,),
    ).fetchone()
    return dict(row) if row else None
