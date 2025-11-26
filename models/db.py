"""SQLite helpers and schema definitions for Pare."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

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
        email_id INTEGER NOT NULL,
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
        email_id INTEGER NOT NULL,
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
        email_id INTEGER NOT NULL,
        unsubscribe_url TEXT,
        status TEXT DEFAULT 'unknown',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
    )
    """,
]


def get_connection() -> sqlite3.Connection:
    """Return a cached SQLite connection stored on the Flask `g` object."""
    conn = g.get(_CONNECTION_KEY)
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        g[_CONNECTION_KEY] = conn
    return conn


def close_connection(_: Optional[BaseException] = None) -> None:
    """Close the cached SQLite connection if it exists."""
    conn = g.pop(_CONNECTION_KEY, None)
    if conn is not None:
        conn.close()


@contextmanager
def cursor() -> Iterable[sqlite3.Cursor]:
    """Context manager yielding a SQLite cursor with automatic commit."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    finally:
        cur.close()


def create_tables() -> None:
    """Create all tables defined in `DDL_STATEMENTS`. Safe to call repeatedly."""
    conn = get_connection()
    for statement in DDL_STATEMENTS:
        conn.execute(statement)
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
                user_id, gmail_message_id, sender, subject, date, body, snippet, raw_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, gmail_message_id) DO UPDATE SET
                sender=excluded.sender,
                subject=excluded.subject,
                date=excluded.date,
                body=excluded.body,
                snippet=excluded.snippet,
                raw_json=excluded.raw_json
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


def get_email_by_id(email_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM emails WHERE id = ?",
        (email_id,),
    ).fetchone()
    return dict(row) if row else None


def fetch_unclassified_emails(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM emails
        WHERE user_id = ?
          AND NOT EXISTS (
            SELECT 1 FROM classifications WHERE classifications.email_id = emails.id
          )
        ORDER BY date DESC NULLS LAST, created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


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
        WHERE emails.user_id = ?
        ORDER BY emails.date DESC NULLS LAST, emails.created_at DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_meetings(user_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    query = """
        SELECT meetings.*, emails.subject, emails.sender, emails.gmail_message_id, emails.date AS email_date
        FROM meetings
        JOIN emails ON emails.id = meetings.email_id
        WHERE emails.user_id = ?
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
        SELECT tasks.*, emails.subject, emails.sender, emails.gmail_message_id
        FROM tasks
        JOIN emails ON emails.id = tasks.email_id
        WHERE emails.user_id = ?
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
        SELECT
            emails.*,
            classifications.category,
            unsubscribe_entries.unsubscribe_url
        FROM emails
        JOIN classifications ON classifications.email_id = emails.id
        LEFT JOIN unsubscribe_entries ON unsubscribe_entries.email_id = emails.id
        WHERE emails.user_id = ?
          AND classifications.category IN ('junk', 'newsletter')
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
        "SELECT COUNT(*) AS count FROM emails WHERE user_id = ?",
        (user_id,),
    ).fetchone()["count"]
    processed_emails = conn.execute(
        """
        SELECT COUNT(DISTINCT classifications.email_id) AS count
        FROM classifications
        JOIN emails ON emails.id = classifications.email_id
        WHERE emails.user_id = ?
        """,
        (user_id,),
    ).fetchone()["count"]
    category_rows = conn.execute(
        """
        SELECT classifications.category, COUNT(*) AS count
        FROM classifications
        JOIN emails ON emails.id = classifications.email_id
        WHERE emails.user_id = ?
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
        WHERE emails.user_id = ?
        """,
        (user_id,),
    ).fetchone()["count"]
    task_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM tasks
        JOIN emails ON emails.id = tasks.email_id
        WHERE emails.user_id = ?
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
    with cursor() as cur:
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
    with cursor() as cur:
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
    with cursor() as cur:
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
