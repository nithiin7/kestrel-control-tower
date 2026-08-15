#!/usr/bin/env python3
"""Profile data/kestrel_ops.db and assert the ground-truth facts the rest of
the build pipeline depends on.

Run: python scripts/profile_source_db.py

Idempotent: re-running overwrites data/ref/city_name_map.csv with the same
content and does not mutate the source DB (read-only connection).

Fails loudly (non-zero exit) if any assertion regresses — this is meant to
catch a swapped/corrupted kestrel_ops.db before the rest of the pipeline
builds on bad assumptions.
"""

import csv
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SOURCE_DB_PATH, CITY_NAME_MAP_PATH, REF_DIR

# City spellings that refer to the same place and must collapse to one
# canonical name. Gurugram and Guwahati are deliberately absent: they are
# real, distinct cities, not misspellings (KP-2288 — confirmed by inspection,
# not to be "fixed" further).
CITY_CANONICAL_OVERRIDES = {
    "Bangalore": "Bengaluru",
    "New Delhi": "Delhi",
}

CREATED_AT_PATTERNS = {
    "ERP_WEB": re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}$"),  # DD/MM/YYYY HH:MM
    "SFA_MOBILE": re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"),  # YYYY-MM-DD HH:MM:SS
    "PARTNER_API": re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    ),  # ISO8601 + Z
}

ACTUAL_ARRIVAL_PATTERNS = {
    "TELEMATICS_A": re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"),  # YYYY-MM-DD HH:MM:SS
    "TELEMATICS_B": re.compile(
        r"^\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2} (AM|PM)$"
    ),  # DD-Mon-YYYY HH:MM AM/PM
}

TEST_OUTLET_CODE_PATTERN = re.compile(r"^TST")
TEST_OUTLET_NAME_PATTERN = re.compile(r"(TEST|DO NOT USE|migration)", re.IGNORECASE)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def profile_outlets(conn: sqlite3.Connection) -> None:
    print("\n== outlets ==")
    cur = conn.execute("SELECT COUNT(*) FROM outlets")
    total = cur.fetchone()[0]
    check("outlet count == 724", total == 724, f"got {total}")

    cur = conn.execute(
        """
        SELECT outlet_code, outlet_name FROM outlets
        WHERE outlet_code LIKE 'TST%'
           OR outlet_name LIKE '%TEST%'
           OR outlet_name LIKE '%DO NOT USE%'
           OR outlet_name LIKE '%migration%'
        """
    )
    test_rows = cur.fetchall()
    check("test outlet count == 3", len(test_rows) == 3, f"got {len(test_rows)}: {test_rows}")

    cur = conn.execute(
        "SELECT outlet_code, COUNT(*) c FROM outlets GROUP BY outlet_code HAVING c > 1"
    )
    dupes = cur.fetchall()
    check("zero duplicate outlet_code", len(dupes) == 0, f"dupes: {dupes}")


def profile_city_names(conn: sqlite3.Connection) -> None:
    print("\n== city name variants (KP-2288) ==")
    cur = conn.execute("SELECT DISTINCT city FROM outlets WHERE city IS NOT NULL ORDER BY city")
    raw_cities = [row[0] for row in cur.fetchall()]

    REF_DIR.mkdir(parents=True, exist_ok=True)
    with open(CITY_NAME_MAP_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["raw_city", "canonical_city", "merged"])
        for city in raw_cities:
            canonical = CITY_CANONICAL_OVERRIDES.get(city, city)
            writer.writerow([city, canonical, "yes" if canonical != city else "no"])

    print(f"  wrote {len(raw_cities)} raw city names -> {CITY_NAME_MAP_PATH}")

    with open(CITY_NAME_MAP_PATH) as f:
        rows = list(csv.DictReader(f))
    mapping = {r["raw_city"]: r["canonical_city"] for r in rows}

    check(
        "Bangalore -> Bengaluru present",
        mapping.get("Bangalore") == "Bengaluru",
    )
    check(
        "New Delhi -> Delhi present",
        mapping.get("New Delhi") == "Delhi",
    )
    check(
        "Gurugram left distinct (not merged)",
        mapping.get("Gurugram") == "Gurugram",
    )
    check(
        "Guwahati left distinct (not merged)",
        mapping.get("Guwahati") == "Guwahati",
    )

    canonical_count = len(set(mapping.values()))
    print(f"  {len(raw_cities)} raw city spellings -> {canonical_count} canonical cities")


def profile_created_at(conn: sqlite3.Connection) -> None:
    print("\n== orders.created_at format per source_system ==")
    cur = conn.execute("SELECT DISTINCT source_system FROM orders ORDER BY source_system")
    systems = [row[0] for row in cur.fetchall()]
    check(
        "source_system set matches expected",
        set(systems) == set(CREATED_AT_PATTERNS.keys()),
        f"got {systems}",
    )

    for system in systems:
        pattern = CREATED_AT_PATTERNS.get(system)
        if pattern is None:
            check(f"{system}: has a known pattern", False, "no pattern defined")
            continue
        cur = conn.execute(
            "SELECT created_at FROM orders WHERE source_system = ?", (system,)
        )
        rows = [r[0] for r in cur.fetchall()]
        mismatches = [v for v in rows if not pattern.match(v or "")]
        check(
            f"{system}: created_at 100% matches expected format ({len(rows)} rows)",
            len(mismatches) == 0,
            f"{len(mismatches)} mismatches, e.g. {mismatches[:3]}",
        )


def profile_actual_arrival(conn: sqlite3.Connection) -> None:
    print("\n== deliveries.actual_arrival format per telematics_vendor ==")
    cur = conn.execute(
        "SELECT DISTINCT telematics_vendor FROM deliveries ORDER BY telematics_vendor"
    )
    vendors = [row[0] for row in cur.fetchall()]
    check(
        "telematics_vendor set matches expected",
        set(vendors) == set(ACTUAL_ARRIVAL_PATTERNS.keys()),
        f"got {vendors}",
    )

    for vendor in vendors:
        pattern = ACTUAL_ARRIVAL_PATTERNS.get(vendor)
        if pattern is None:
            check(f"{vendor}: has a known pattern", False, "no pattern defined")
            continue
        cur = conn.execute(
            "SELECT actual_arrival FROM deliveries WHERE telematics_vendor = ? "
            "AND actual_arrival IS NOT NULL",
            (vendor,),
        )
        rows = [r[0] for r in cur.fetchall()]
        mismatches = [v for v in rows if not pattern.match(v or "")]
        check(
            f"{vendor}: actual_arrival 100% matches expected format ({len(rows)} rows)",
            len(mismatches) == 0,
            f"{len(mismatches)} mismatches, e.g. {mismatches[:3]}",
        )


def profile_returns(conn: sqlite3.Connection) -> None:
    print("\n== returns_credit_notes.return_qty sign (KP-2402) ==")
    cur = conn.execute("SELECT COUNT(*) FROM returns_credit_notes")
    total = cur.fetchone()[0]
    cur = conn.execute(
        "SELECT COUNT(*) FROM returns_credit_notes WHERE return_qty < 0"
    )
    negative = cur.fetchone()[0]
    rate = negative / total if total else 0.0
    print(f"  {negative}/{total} rows negative ({rate:.2%})")
    check("negative rate within 5.5%-7.5% band (~6.4% expected)", 0.055 <= rate <= 0.075, f"got {rate:.2%}")


def profile_qty_uom(conn: sqlite3.Connection) -> None:
    print("\n== order_lines.qty_uom distribution ==")
    cur = conn.execute("SELECT qty_uom, COUNT(*) FROM order_lines GROUP BY qty_uom")
    dist = dict(cur.fetchall())
    total = sum(dist.values())
    for uom, count in sorted(dist.items()):
        print(f"  {uom}: {count} ({count/total:.1%})")
    check("qty_uom has at least CASE and EACH", {"CASE", "EACH"}.issubset(dist.keys()), f"got {list(dist.keys())}")
    check("zero null/unknown qty_uom", None not in dist, f"got keys {list(dist.keys())}")


def main() -> int:
    if not SOURCE_DB_PATH.exists():
        print(f"ERROR: source DB not found at {SOURCE_DB_PATH}")
        return 1

    conn = sqlite3.connect(f"file:{SOURCE_DB_PATH}?mode=ro", uri=True)
    try:
        print(f"Profiling {SOURCE_DB_PATH}")
        profile_outlets(conn)
        profile_city_names(conn)
        profile_created_at(conn)
        profile_actual_arrival(conn)
        profile_returns(conn)
        profile_qty_uom(conn)
    finally:
        conn.close()

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
