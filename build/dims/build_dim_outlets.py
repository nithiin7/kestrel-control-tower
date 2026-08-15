#!/usr/bin/env python3
"""Build dim_outlets in data/analytics.db from the raw outlets table.

Run: python build/dims/build_dim_outlets.py

Dedupe/join key is outlet_code exclusively — outlet_name has 70+ duplicate
groups in the source data and is never safe to key on. The 3 hardcoded test
outlets (TST00001-3) are excluded by outlet_code/name pattern, explicitly
NOT by status (all three show status=ACTIVE, is_deleted=0, so a status
filter would silently let them through). Excluded rows are kept in
dim_outlets_excluded for audit rather than being silently dropped.

City spelling is normalized via data/ref/city_name_map.csv (built by T1's
scripts/profile_source_db.py) — Bangalore/Bengaluru and Delhi/New Delhi
collapse to one canonical name each; Gurugram and Guwahati are real,
distinct cities and are left alone.

Idempotent: re-running drops and rebuilds both tables.
"""

import csv
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import SOURCE_DB_PATH, ANALYTICS_DB_PATH, CITY_NAME_MAP_PATH

TEST_OUTLET_CODE_PATTERN = re.compile(r"^TST")
TEST_OUTLET_NAME_PATTERN = re.compile(r"(TEST|DO NOT USE|migration)", re.IGNORECASE)

OUTLET_COLUMN_TYPES = {
    "outlet_code": "TEXT",
    "outlet_name": "TEXT",
    "channel": "TEXT",
    "outlet_format": "TEXT",
    "city_raw": "TEXT",
    "city": "TEXT",
    "state": "TEXT",
    "region_id": "INTEGER",
    "pincode": "TEXT",
    "latitude": "REAL",
    "longitude": "REAL",
    "route_id": "INTEGER",
    "salesperson_id": "INTEGER",
    "onboarded_date": "TEXT",
    "credit_limit_inr": "REAL",
    "credit_terms_days": "INTEGER",
    "storage_type": "TEXT",
    "chiller_available": "INTEGER",
    "avg_monthly_footfall": "INTEGER",
    "risk_flag": "TEXT",
    "status": "TEXT",
    "is_deleted": "INTEGER",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}
OUTLET_COLUMNS = list(OUTLET_COLUMN_TYPES.keys())

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def load_city_map() -> dict[str, str]:
    if not CITY_NAME_MAP_PATH.exists():
        print(f"ERROR: {CITY_NAME_MAP_PATH} not found — run scripts/profile_source_db.py first (T1).")
        sys.exit(1)
    with open(CITY_NAME_MAP_PATH) as f:
        rows = list(csv.DictReader(f))
    return {r["raw_city"]: r["canonical_city"] for r in rows}


def is_test_outlet(outlet_code: str, outlet_name: str) -> bool:
    return bool(
        TEST_OUTLET_CODE_PATTERN.match(outlet_code or "")
        or TEST_OUTLET_NAME_PATTERN.search(outlet_name or "")
    )


def exclusion_reason(outlet_code: str, outlet_name: str) -> str:
    reasons = []
    if TEST_OUTLET_CODE_PATTERN.match(outlet_code or ""):
        reasons.append("outlet_code LIKE 'TST%'")
    if TEST_OUTLET_NAME_PATTERN.search(outlet_name or ""):
        reasons.append("outlet_name matches TEST/DO NOT USE/migration")
    return "; ".join(reasons)


def fetch_source_outlets(src: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = src.execute(
        """
        SELECT outlet_code, outlet_name, channel, outlet_format, city, state,
               region_id, pincode, latitude, longitude, route_id, salesperson_id,
               onboarded_date, credit_limit_inr, credit_terms_days, storage_type,
               chiller_available, avg_monthly_footfall, risk_flag, status,
               is_deleted, created_at, updated_at
        FROM outlets
        """
    )
    return cur.fetchall()


def build(src: sqlite3.Connection, dst: sqlite3.Connection, city_map: dict[str, str]) -> None:
    rows = fetch_source_outlets(src)

    # Defensive dedupe on outlet_code — source has none per T1, but this
    # protects the build if that ever regresses (keep the first occurrence).
    seen: set[str] = set()
    deduped = []
    for row in rows:
        code = row["outlet_code"]
        if code in seen:
            continue
        seen.add(code)
        deduped.append(row)

    kept = []
    excluded = []
    for row in deduped:
        code, name = row["outlet_code"], row["outlet_name"]
        if is_test_outlet(code, name):
            excluded.append((row, exclusion_reason(code, name)))
        else:
            kept.append(row)

    dst.execute("DROP TABLE IF EXISTS dim_outlets")
    dst.execute("DROP TABLE IF EXISTS dim_outlets_excluded")

    column_defs = ", ".join(f'"{c}" {t}' for c, t in OUTLET_COLUMN_TYPES.items())
    dst.execute(f"CREATE TABLE dim_outlets ({column_defs}, PRIMARY KEY (outlet_code))")
    dst.execute(f"CREATE TABLE dim_outlets_excluded ({column_defs}, exclusion_reason TEXT)")

    insert_cols = ", ".join(f'"{c}"' for c in OUTLET_COLUMNS)
    placeholders = ", ".join("?" for _ in OUTLET_COLUMNS)

    kept_values = []
    for row in kept:
        city_raw = row["city"]
        city_canonical = city_map.get(city_raw, city_raw)
        kept_values.append(
            (
                row["outlet_code"],
                row["outlet_name"],
                row["channel"],
                row["outlet_format"],
                city_raw,
                city_canonical,
                row["state"],
                row["region_id"],
                row["pincode"],
                row["latitude"],
                row["longitude"],
                row["route_id"],
                row["salesperson_id"],
                row["onboarded_date"],
                row["credit_limit_inr"],
                row["credit_terms_days"],
                row["storage_type"],
                row["chiller_available"],
                row["avg_monthly_footfall"],
                row["risk_flag"],
                row["status"],
                row["is_deleted"],
                row["created_at"],
                row["updated_at"],
            )
        )
    dst.executemany(
        f"INSERT INTO dim_outlets ({insert_cols}) VALUES ({placeholders})", kept_values
    )

    excluded_values = []
    for row, reason in excluded:
        city_raw = row["city"]
        city_canonical = city_map.get(city_raw, city_raw)
        excluded_values.append(
            (
                row["outlet_code"],
                row["outlet_name"],
                row["channel"],
                row["outlet_format"],
                city_raw,
                city_canonical,
                row["state"],
                row["region_id"],
                row["pincode"],
                row["latitude"],
                row["longitude"],
                row["route_id"],
                row["salesperson_id"],
                row["onboarded_date"],
                row["credit_limit_inr"],
                row["credit_terms_days"],
                row["storage_type"],
                row["chiller_available"],
                row["avg_monthly_footfall"],
                row["risk_flag"],
                row["status"],
                row["is_deleted"],
                row["created_at"],
                row["updated_at"],
                reason,
            )
        )
    dst.executemany(
        f"INSERT INTO dim_outlets_excluded ({insert_cols}, exclusion_reason) "
        f"VALUES ({placeholders}, ?)",
        excluded_values,
    )

    dst.commit()
    print(f"  inserted {len(kept_values)} rows into dim_outlets")
    print(f"  inserted {len(excluded_values)} rows into dim_outlets_excluded")


def verify(dst: sqlite3.Connection, src: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    cur = dst.execute("SELECT COUNT(*) FROM dim_outlets")
    count = cur.fetchone()[0]
    check("dim_outlets COUNT(*) == 721", count == 721, f"got {count}")

    cur = dst.execute("SELECT COUNT(*) FROM dim_outlets WHERE outlet_code LIKE 'TST%'")
    tst_count = cur.fetchone()[0]
    check("zero TST% rows in dim_outlets", tst_count == 0, f"got {tst_count}")

    cur = dst.execute("SELECT COUNT(*) FROM dim_outlets_excluded")
    excluded_count = cur.fetchone()[0]
    check("dim_outlets_excluded has exactly 3 rows", excluded_count == 3, f"got {excluded_count}")

    cur = dst.execute("SELECT COUNT(DISTINCT city) FROM dim_outlets")
    dim_city_count = cur.fetchone()[0]
    cur = src.execute("SELECT COUNT(DISTINCT city) FROM outlets")
    raw_city_count = cur.fetchone()[0]
    check(
        "distinct city count in dim_outlets < raw outlets",
        dim_city_count < raw_city_count,
        f"dim={dim_city_count}, raw={raw_city_count}",
    )

    cur = dst.execute("SELECT COUNT(*) FROM dim_outlets WHERE city IN ('Gurugram', 'Guwahati')")
    distinct_kept = cur.fetchone()[0]
    check(
        "Gurugram and Guwahati still present as distinct cities",
        distinct_kept > 0,
        f"got {distinct_kept} rows",
    )

    cur = dst.execute("SELECT COUNT(*) FROM dim_outlets WHERE city = 'Bangalore'")
    check("no residual 'Bangalore' spelling in dim_outlets", cur.fetchone()[0] == 0)

    cur = dst.execute("SELECT COUNT(*) FROM dim_outlets WHERE city = 'New Delhi'")
    check("no residual 'New Delhi' spelling in dim_outlets", cur.fetchone()[0] == 0)

    cur = dst.execute(
        "SELECT outlet_code, COUNT(*) c FROM dim_outlets GROUP BY outlet_code HAVING c > 1"
    )
    dupes = cur.fetchall()
    check("zero duplicate outlet_code in dim_outlets", len(dupes) == 0, f"dupes: {dupes}")


def main() -> int:
    if not SOURCE_DB_PATH.exists():
        print(f"ERROR: source DB not found at {SOURCE_DB_PATH}")
        return 1

    city_map = load_city_map()

    src = sqlite3.connect(f"file:{SOURCE_DB_PATH}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    try:
        print(f"Building dim_outlets from {SOURCE_DB_PATH} -> {ANALYTICS_DB_PATH}")
        build(src, dst, city_map)
        verify(dst, src)
    finally:
        src.close()
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
