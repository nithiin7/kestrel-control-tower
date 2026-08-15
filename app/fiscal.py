"""Fiscal calendar helpers for the app layer.

Mirrors build/dims/build_dim_date.py's get_latest_complete_fiscal_quarter()
exactly (fiscal year Apr-Mar, "latest complete" anchored to the data's own
max date, not wall-clock today) without importing build-time pipeline code
into the app — the app only ever reads from the built analytics.db.
"""

from datetime import date, timedelta

QUARTER_BY_MONTH = {
    4: 1, 5: 1, 6: 1,
    7: 2, 8: 2, 9: 2,
    10: 3, 11: 3, 12: 3,
    1: 4, 2: 4, 3: 4,
}
QUARTER_END_MONTH = {1: 6, 2: 9, 3: 12, 4: 3}
QUARTER_START_MONTH = {1: 4, 2: 7, 3: 10, 4: 1}


def _fiscal_year_start_year(d: date) -> int:
    return d.year if d.month >= 4 else d.year - 1


def _fiscal_year_label(fy_start_year: int) -> str:
    return f"FY{fy_start_year}-{str(fy_start_year + 1)[-2:]}"


def _fiscal_quarter_end_date(fy_start_year: int, quarter: int) -> date:
    end_month = QUARTER_END_MONTH[quarter]
    end_year = fy_start_year + 1 if quarter == 4 else fy_start_year
    next_month_first = date(end_year, end_month, 28) + timedelta(days=4)
    return next_month_first - timedelta(days=next_month_first.day)


def _fiscal_quarter_start_date(fy_start_year: int, quarter: int) -> date:
    start_year = fy_start_year + 1 if quarter == 4 else fy_start_year
    return date(start_year, QUARTER_START_MONTH[quarter], 1)


def get_latest_complete_fiscal_quarter(max_data_date: str) -> dict:
    """Derive the latest COMPLETE fiscal quarter as of the data's max date.

    Not wall-clock today — the operational data ends 2026-06-30 regardless
    of when the app is actually run, so every "last complete quarter" view
    must anchor to the data's own max date instead.
    """
    d = date.fromisoformat(max_data_date)
    fy_start = _fiscal_year_start_year(d)
    q = QUARTER_BY_MONTH[d.month]
    q_end = _fiscal_quarter_end_date(fy_start, q)

    if d < q_end:
        if q == 1:
            fy_start, q = fy_start - 1, 4
        else:
            q -= 1

    return {
        "fiscal_year": _fiscal_year_label(fy_start),
        "fiscal_quarter": q,
        "fiscal_quarter_label": f"{_fiscal_year_label(fy_start)} Q{q}",
        "start_date": _fiscal_quarter_start_date(fy_start, q).isoformat(),
        "end_date": _fiscal_quarter_end_date(fy_start, q).isoformat(),
    }
