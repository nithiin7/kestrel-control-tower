#!/usr/bin/env python3
"""Build dim_date in data/analytics.db: one row per calendar day.

Run: python build/dims/build_dim_date.py

Covers 2025-01-01 through 2026-12-31 — the operational data window plus
headroom. Kestrel's fiscal year runs April-March, labelled "FYyyyy-yy+1"
by the calendar year its April falls in (e.g. April 2026 -> FY2026-27).
Fiscal quarters: Q1 Apr-Jun, Q2 Jul-Sep, Q3 Oct-Dec, Q4 Jan-Mar.

get_latest_complete_fiscal_quarter() is the reusable piece: it derives
"the current quarter" from the data's own max date rather than
wall-clock today, since the operational data ends 2026-06-30 and every
"last complete quarter" view (landing page Q1 tile, marts) needs to
treat that as the reference point. A quarter counts as complete only if
max_data_date lands on or after its last calendar day.

Idempotent: re-running drops and rebuilds the table.
"""

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import ANALYTICS_DB_PATH

START_DATE = date(2025, 1, 1)
END_DATE = date(2026, 12, 31)

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# month -> (fiscal_quarter, months_into_fiscal_year_that_this_quarter_starts)
QUARTER_BY_MONTH = {
    4: 1, 5: 1, 6: 1,
    7: 2, 8: 2, 9: 2,
    10: 3, 11: 3, 12: 3,
    1: 4, 2: 4, 3: 4,
}
QUARTER_END_MONTH = {1: 6, 2: 9, 3: 12, 4: 3}

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def fiscal_year_start_year(d: date) -> int:
    """Calendar year in which this date's fiscal year (Apr-Mar) began."""
    return d.year if d.month >= 4 else d.year - 1


def fiscal_year_label(fy_start_year: int) -> str:
    return f"FY{fy_start_year}-{str(fy_start_year + 1)[-2:]}"


def fiscal_quarter(d: date) -> int:
    return QUARTER_BY_MONTH[d.month]


def fiscal_quarter_label(fy_start_year: int, quarter: int) -> str:
    return f"{fiscal_year_label(fy_start_year)} Q{quarter}"


def fiscal_quarter_end_date(fy_start_year: int, quarter: int) -> date:
    """Last calendar day of the given fiscal year + quarter."""
    end_month = QUARTER_END_MONTH[quarter]
    # Q4 (Jan-Mar) falls in the calendar year after the fiscal year started.
    end_year = fy_start_year + 1 if quarter == 4 else fy_start_year
    next_month_first = date(end_year, end_month, 28) + timedelta(days=4)
    return next_month_first - timedelta(days=next_month_first.day)


def get_latest_complete_fiscal_quarter(max_data_date: str) -> dict:
    """Derive the latest COMPLETE fiscal quarter as of the data's max date.

    Not wall-clock today — every "last complete quarter" view in the app
    must anchor to this instead, since the operational data ends
    2026-06-30 regardless of when the app is actually run.
    """
    d = date.fromisoformat(max_data_date)
    fy_start = fiscal_year_start_year(d)
    q = fiscal_quarter(d)
    q_end = fiscal_quarter_end_date(fy_start, q)

    if d < q_end:
        # Current quarter isn't finished yet — step back one quarter.
        if q == 1:
            fy_start, q = fy_start - 1, 4
        else:
            q -= 1

    return {
        "fiscal_year": fiscal_year_label(fy_start),
        "fiscal_quarter": q,
        "fiscal_quarter_label": fiscal_quarter_label(fy_start, q),
    }


def build(dst: sqlite3.Connection) -> int:
    dst.execute("DROP TABLE IF EXISTS dim_date")
    dst.execute(
        """
        CREATE TABLE dim_date (
            "date" TEXT PRIMARY KEY,
            year INTEGER,
            month INTEGER,
            day INTEGER,
            day_of_week TEXT,
            fiscal_year_start_year INTEGER,
            fiscal_year TEXT,
            fiscal_quarter INTEGER,
            fiscal_quarter_label TEXT,
            is_q1 INTEGER
        )
        """
    )

    rows = []
    d = START_DATE
    while d <= END_DATE:
        fy_start = fiscal_year_start_year(d)
        q = fiscal_quarter(d)
        rows.append(
            (
                d.isoformat(),
                d.year,
                d.month,
                d.day,
                DAY_NAMES[d.weekday()],
                fy_start,
                fiscal_year_label(fy_start),
                q,
                fiscal_quarter_label(fy_start, q),
                1 if q == 1 else 0,
            )
        )
        d += timedelta(days=1)

    dst.executemany(
        """
        INSERT INTO dim_date (
            "date", year, month, day, day_of_week,
            fiscal_year_start_year, fiscal_year, fiscal_quarter,
            fiscal_quarter_label, is_q1
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    dst.commit()
    print(f"  inserted {len(rows)} rows into dim_date")
    return len(rows)


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    expected_days = (END_DATE - START_DATE).days + 1
    count = dst.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0]
    check(f"dim_date COUNT(*) == {expected_days}", count == expected_days, f"got {count}")

    def row(d: str) -> sqlite3.Row:
        return dst.execute(
            'SELECT fiscal_year, fiscal_quarter, is_q1 FROM dim_date WHERE "date" = ?', (d,)
        ).fetchone()

    r = row("2026-04-15")
    check(
        "2026-04-15 -> FY2026-27 Q1, is_q1=1",
        r is not None and r["fiscal_year"] == "FY2026-27" and r["fiscal_quarter"] == 1 and r["is_q1"] == 1,
        f"got {tuple(r) if r else None}",
    )

    r = row("2025-04-01")
    check(
        "2025-04-01 -> FY2025-26 Q1",
        r is not None and r["fiscal_year"] == "FY2025-26" and r["fiscal_quarter"] == 1,
        f"got {tuple(r) if r else None}",
    )

    latest = get_latest_complete_fiscal_quarter("2026-06-30")
    check(
        "get_latest_complete_fiscal_quarter('2026-06-30') -> FY2026-27 Q1",
        latest["fiscal_year"] == "FY2026-27" and latest["fiscal_quarter"] == 1,
        f"got {latest}",
    )


def main() -> int:
    dst = sqlite3.connect(ANALYTICS_DB_PATH)
    dst.row_factory = sqlite3.Row

    try:
        print(f"Building dim_date ({START_DATE} .. {END_DATE}) -> {ANALYTICS_DB_PATH}")
        build(dst)
        verify(dst)
    finally:
        dst.close()

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} assertion(s) did not hold:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1

    print("All assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
