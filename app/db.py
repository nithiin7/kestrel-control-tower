"""Read-only connection to data/analytics.db — the app never writes to it."""

import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import ANALYTICS_DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{ANALYTICS_DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: yields a connection, closes it after the request."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
