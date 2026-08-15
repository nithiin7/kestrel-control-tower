"""Validates and executes LLM-generated SQL against a read-only connection.

Uses sqlite3's authorizer callback as a strict allowlist (SQLITE_SELECT /
SQLITE_READ / SQLITE_FUNCTION only) rather than a keyword blocklist, since
blocklists are bypassable (comments, alternate casing, unusual whitespace).
The authorizer denies everything else — INSERT/UPDATE/DELETE/DROP/ALTER/
ATTACH/PRAGMA/CREATE/etc — before SQLite executes a single byte of it.
Also enforces a row cap and a wall-clock query timeout via a progress handler.
"""

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import ANALYTICS_DB_PATH

ROW_LIMIT = 200
QUERY_TIMEOUT_SECONDS = 5.0
PROGRESS_HANDLER_INTERVAL_OPS = 1000

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
}


class UnsafeSQLError(Exception):
    pass


def _authorizer(action: int, arg1: str | None, arg2: str | None, db_name: str | None, trigger_name: str | None) -> int:
    if action in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def run_readonly_query(sql: str) -> tuple[list[str], list[dict]]:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise UnsafeSQLError("empty SQL statement")

    conn = sqlite3.connect(f"file:{ANALYTICS_DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.set_authorizer(_authorizer)

    deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, PROGRESS_HANDLER_INTERVAL_OPS)

    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows = [dict(row) for row in cursor.fetchmany(ROW_LIMIT)]
        return columns, rows
    except (sqlite3.ProgrammingError, sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
        raise UnsafeSQLError(f"rejected: {exc}") from exc
    finally:
        conn.close()
