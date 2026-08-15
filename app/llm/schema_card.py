"""Compact schema description of data/analytics.db for LLM prompts.

Only clean dim/fact/mart/bridge tables are included — raw_* staging tables
are excluded so the model never targets scrape/ingest artifacts directly.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import ANALYTICS_DB_PATH


def build_schema_card() -> str:
    conn = sqlite3.connect(f"file:{ANALYTICS_DB_PATH}?mode=ro", uri=True)
    try:
        table_names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'raw\\_%' ESCAPE '\\' ORDER BY name"
            )
        ]

        lines = []
        for table in table_names:
            columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
            col_desc = ", ".join(f"{col[1]} {col[2]}" for col in columns)
            lines.append(f"{table}({col_desc})")

        return "\n".join(lines)
    finally:
        conn.close()
