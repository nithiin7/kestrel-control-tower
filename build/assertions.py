"""Regression guards from source-data profiling (scripts/profile_source_db.py).

Hard-coded ground-truth facts about data/kestrel_ops.db that every dim/fact
build script in this pipeline was written against. build/pipeline.py runs
these first, before touching any table, and fails loudly if the source DB
has drifted — a different data snapshot, a schema change — so the pipeline
doesn't silently build on assumptions that no longer hold.

Mirrors (does not import from) scripts/profile_source_db.py's checks — that
script's job is a one-time human-readable profiling report plus the
data/ref/city_name_map.csv artifact; this module is the fast, side-effect-
free subset embedded in every pipeline run. Keep the two in sync if the
source snapshot ever changes.
"""

import re
import sqlite3

MIN_OUTLET_COUNT = 724
MIN_TEST_OUTLET_COUNT = 3

CREATED_AT_PATTERNS = {
    "ERP_WEB": re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}$"),  # DD/MM/YYYY HH:MM
    "SFA_MOBILE": re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"),  # YYYY-MM-DD HH:MM:SS
    "PARTNER_API": re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"),  # ISO8601 + Z
}

ACTUAL_ARRIVAL_PATTERNS = {
    "TELEMATICS_A": re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"),  # YYYY-MM-DD HH:MM:SS
    "TELEMATICS_B": re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2} (AM|PM)$"),  # DD-Mon-YYYY HH:MM AM/PM
}

RETURN_NEGATIVE_RATE_BAND = (0.055, 0.075)  # ~6.4% expected (KP-2402)


def check_outlets(conn: sqlite3.Connection) -> list[str]:
    failures = []

    total = conn.execute("SELECT COUNT(*) FROM outlets").fetchone()[0]
    if total < MIN_OUTLET_COUNT:
        failures.append(f"outlet count >= {MIN_OUTLET_COUNT}: got {total}")

    test_rows = conn.execute(
        """
        SELECT outlet_code FROM outlets
        WHERE outlet_code LIKE 'TST%' OR outlet_name LIKE '%TEST%'
           OR outlet_name LIKE '%DO NOT USE%' OR outlet_name LIKE '%migration%'
        """
    ).fetchall()
    if len(test_rows) < MIN_TEST_OUTLET_COUNT:
        failures.append(f"test outlet count >= {MIN_TEST_OUTLET_COUNT}: got {len(test_rows)}")

    dupes = conn.execute("SELECT outlet_code, COUNT(*) c FROM outlets GROUP BY outlet_code HAVING c > 1").fetchall()
    if dupes:
        failures.append(f"zero duplicate outlet_code: got {dupes}")

    return failures


def check_created_at_formats(conn: sqlite3.Connection) -> list[str]:
    systems = {r[0] for r in conn.execute("SELECT DISTINCT source_system FROM orders")}
    if systems != set(CREATED_AT_PATTERNS.keys()):
        return [f"orders.source_system set changed: got {sorted(systems)}, expected {sorted(CREATED_AT_PATTERNS)}"]

    failures = []
    for system, pattern in CREATED_AT_PATTERNS.items():
        rows = [r[0] for r in conn.execute("SELECT created_at FROM orders WHERE source_system = ?", (system,))]
        mismatches = [v for v in rows if not pattern.match(v or "")]
        if mismatches:
            failures.append(
                f"{system}: created_at format broke for {len(mismatches)}/{len(rows)} rows, e.g. {mismatches[:3]}"
            )
    return failures


def check_actual_arrival_formats(conn: sqlite3.Connection) -> list[str]:
    vendors = {r[0] for r in conn.execute("SELECT DISTINCT telematics_vendor FROM deliveries")}
    if vendors != set(ACTUAL_ARRIVAL_PATTERNS.keys()):
        return [
            f"deliveries.telematics_vendor set changed: got {sorted(vendors)}, expected {sorted(ACTUAL_ARRIVAL_PATTERNS)}"
        ]

    failures = []
    for vendor, pattern in ACTUAL_ARRIVAL_PATTERNS.items():
        rows = [
            r[0]
            for r in conn.execute(
                "SELECT actual_arrival FROM deliveries WHERE telematics_vendor = ? AND actual_arrival IS NOT NULL",
                (vendor,),
            )
        ]
        mismatches = [v for v in rows if not pattern.match(v or "")]
        if mismatches:
            failures.append(
                f"{vendor}: actual_arrival format broke for {len(mismatches)}/{len(rows)} rows, e.g. {mismatches[:3]}"
            )
    return failures


def check_returns_negative_rate(conn: sqlite3.Connection) -> list[str]:
    total = conn.execute("SELECT COUNT(*) FROM returns_credit_notes").fetchone()[0]
    negative = conn.execute("SELECT COUNT(*) FROM returns_credit_notes WHERE return_qty < 0").fetchone()[0]
    rate = negative / total if total else 0.0
    low, high = RETURN_NEGATIVE_RATE_BAND
    if not (low <= rate <= high):
        return [f"returns_credit_notes negative rate outside {low:.1%}-{high:.1%} band: got {rate:.2%}"]
    return []


def check_qty_uom(conn: sqlite3.Connection) -> list[str]:
    dist = dict(conn.execute("SELECT qty_uom, COUNT(*) FROM order_lines GROUP BY qty_uom").fetchall())
    failures = []
    if not {"CASE", "EACH"}.issubset(dist.keys()):
        failures.append(f"order_lines.qty_uom missing CASE/EACH: got {list(dist.keys())}")
    if None in dist:
        failures.append(f"order_lines.qty_uom has null/unknown values: got keys {list(dist.keys())}")
    return failures


def run_all(conn: sqlite3.Connection) -> list[str]:
    """Run every regression guard against the raw source DB connection.

    Returns a list of failure messages — empty means every guard held.
    """
    failures: list[str] = []
    failures += check_outlets(conn)
    failures += check_created_at_formats(conn)
    failures += check_actual_arrival_formats(conn)
    failures += check_returns_negative_rate(conn)
    failures += check_qty_uom(conn)
    return failures
