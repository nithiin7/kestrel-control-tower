"""Read-only connection to data/analytics.db — the app never writes to it."""

import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import ANALYTICS_DB_PATH


def get_connection() -> sqlite3.Connection:
    # check_same_thread=False: each request gets its own connection (opened
    # and closed here, never shared across requests), but FastAPI's generator
    # dependencies can run a request's __enter__/__exit__ on different
    # threadpool workers, which sqlite3 forbids by default even though the
    # connection is never touched concurrently from two threads at once.
    conn = sqlite3.connect(f"file:{ANALYTICS_DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: yields a connection, closes it after the request."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
