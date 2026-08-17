"""Minimal SQLite storage: submissions and run traces, each as a JSON blob.
No ORM — this is a portfolio-scale app and a couple of tables with JSON
columns is simpler to read than a mapped schema would be."""
import json
import sqlite3
from contextlib import contextmanager
from typing import List, Optional

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    trace TEXT NOT NULL
);
"""


def init_db(path: str = DB_PATH) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn(path: str = DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_submission(conn: sqlite3.Connection, submission: dict) -> None:
    conn.execute(
        "INSERT INTO submissions (id, data) VALUES (?, ?) "
        "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
        (submission["submission_id"], json.dumps(submission)),
    )


def get_submission(conn: sqlite3.Connection, submission_id: str) -> Optional[dict]:
    row = conn.execute("SELECT data FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def list_submissions(conn: sqlite3.Connection) -> List[dict]:
    rows = conn.execute("SELECT data FROM submissions").fetchall()
    return [json.loads(r["data"]) for r in rows]


def save_run(conn: sqlite3.Connection, run_trace: dict) -> None:
    conn.execute(
        "INSERT INTO runs (id, submission_id, created_at, trace) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET trace = excluded.trace",
        (run_trace["run_id"], run_trace["submission_id"], run_trace["created_at"], json.dumps(run_trace)),
    )


def get_run(conn: sqlite3.Connection, run_id: str) -> Optional[dict]:
    row = conn.execute("SELECT trace FROM runs WHERE id = ?", (run_id,)).fetchone()
    return json.loads(row["trace"]) if row else None


def list_runs(conn: sqlite3.Connection, submission_id: Optional[str] = None) -> List[dict]:
    if submission_id:
        rows = conn.execute(
            "SELECT trace FROM runs WHERE submission_id = ? ORDER BY created_at DESC", (submission_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT trace FROM runs ORDER BY created_at DESC").fetchall()
    return [json.loads(r["trace"]) for r in rows]


def latest_run_for_submission(conn: sqlite3.Connection, submission_id: str) -> Optional[dict]:
    runs = list_runs(conn, submission_id)
    return runs[0] if runs else None
