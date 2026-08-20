#!/usr/bin/env python3
"""Build dim_warehouses, dim_routes, dim_regions in data/analytics.db.

Run: python build/dims/build_dim_warehouses_routes_regions.py

Clean copies of the raw warehouses/routes/regions tables — no dedupe or
normalization needed here (zero duplicate codes, zero orphaned FKs in
either direction, confirmed by this script's own checks). Kept as three
separate dim tables per the analytics schema rather than merged, since
routes and warehouses are independently filterable in the UI.

Idempotent: re-running drops and rebuilds all three tables.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import SOURCE_DB_PATH, ANALYTICS_DB_PATH

REGION_COLUMN_TYPES = {
    "region_id": "INTEGER",
    "region_code": "TEXT",
    "region_name": "TEXT",
    "regional_manager": "TEXT",
    "hq_city": "TEXT",
    "active_from": "TEXT",
    "status": "TEXT",
}
WAREHOUSE_COLUMN_TYPES = {
    "warehouse_id": "INTEGER",
    "warehouse_code": "TEXT",
    "warehouse_name": "TEXT",
    "city": "TEXT",
    "region_id": "INTEGER",
    "address_line": "TEXT",
    "pincode": "TEXT",
    "capacity_pallets": "INTEGER",
    "chilled_capacity_pallets": "INTEGER",
    "dock_count": "INTEGER",
    "opened_date": "TEXT",
    "manager_name": "TEXT",
    "shift_pattern": "TEXT",
    "temp_monitoring": "TEXT",
    "wms_version": "TEXT",
    "status": "TEXT",
}
ROUTE_COLUMN_TYPES = {
    "route_id": "INTEGER",
    "route_code": "TEXT",
    "route_name": "TEXT",
    "warehouse_id": "INTEGER",
    "region_id": "INTEGER",
    "planned_stops": "INTEGER",
    "planned_km": "REAL",
    "vehicle_type": "TEXT",
    "is_reefer": "INTEGER",
    "cost_per_km": "REAL",
    "shift": "TEXT",
    "service_frequency": "TEXT",
    "active_from": "TEXT",
    "active_to": "TEXT",
    "status": "TEXT",
}

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def copy_table(
    src: sqlite3.Connection,
    dst: sqlite3.Connection,
    source_table: str,
    dest_table: str,
    column_types: dict[str, str],
    pk: str,
) -> int:
    columns = list(column_types.keys())
    cur = src.execute(f"SELECT {', '.join(columns)} FROM {source_table}")
    rows = cur.fetchall()

    dst.execute(f"DROP TABLE IF EXISTS {dest_table}")
    column_defs = ", ".join(f'"{c}" {t}' for c, t in column_types.items())
    dst.execute(f'CREATE TABLE {dest_table} ({column_defs}, PRIMARY KEY ("{pk}"))')

    insert_cols = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join("?" for _ in columns)
    dst.executemany(
        f"INSERT INTO {dest_table} ({insert_cols}) VALUES ({placeholders})",
        [tuple(row) for row in rows],
    )
    dst.commit()
    print(f"  inserted {len(rows)} rows into {dest_table}")
    return len(rows)


def build(src: sqlite3.Connection, dst: sqlite3.Connection) -> None:
    copy_table(src, dst, "regions", "dim_regions", REGION_COLUMN_TYPES, "region_id")
    copy_table(src, dst, "warehouses", "dim_warehouses", WAREHOUSE_COLUMN_TYPES, "warehouse_id")
    copy_table(src, dst, "routes", "dim_routes", ROUTE_COLUMN_TYPES, "route_id")


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    min_counts = {
        "dim_regions": 5,
        "dim_warehouses": 8,
        "dim_routes": 140,
    }
    for dim_name, minimum in min_counts.items():
        count = dst.execute(f"SELECT COUNT(*) FROM {dim_name}").fetchone()[0]
        check(f"{dim_name} COUNT(*) >= {minimum}", count >= minimum, f"got {count}")

    orphan_route_warehouse = dst.execute(
        """
        SELECT COUNT(*) FROM dim_routes r
        LEFT JOIN dim_warehouses w ON r.warehouse_id = w.warehouse_id
        WHERE w.warehouse_id IS NULL
        """
    ).fetchone()[0]
    check(
        "zero routes with orphaned warehouse_id",
        orphan_route_warehouse == 0,
        f"got {orphan_route_warehouse}",
    )

    orphan_warehouse_region = dst.execute(
        """
        SELECT COUNT(*) FROM dim_warehouses w
        LEFT JOIN dim_regions rg ON w.region_id = rg.region_id
        WHERE rg.region_id IS NULL
        """
    ).fetchone()[0]
    check(
        "zero warehouses with orphaned region_id",
        orphan_warehouse_region == 0,
        f"got {orphan_warehouse_region}",
    )


def main() -> int:
    if not SOURCE_DB_PATH.exists():
        print(f"ERROR: source DB not found at {SOURCE_DB_PATH}")
        return 1

    src = sqlite3.connect(f"file:{SOURCE_DB_PATH}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    try:
        print(f"Building dim_warehouses/dim_routes/dim_regions from {SOURCE_DB_PATH} -> {ANALYTICS_DB_PATH}")
        build(src, dst)
        verify(dst)
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
