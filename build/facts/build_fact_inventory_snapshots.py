#!/usr/bin/env python3
"""Build fact_inventory_snapshots in data/analytics.db.

Run: python build/facts/build_fact_inventory_snapshots.py

Grain: warehouse x SKU x batch x week, 1 row per raw inventory_snapshots
row (no dedup/exclusion needed — inventory isn't outlet-scoped, zero
nulls/orphans in the source).

near_expiry_flag threshold: expiry_date - snapshot_date <= 30 days.
Picked as a round, conservative number representative of a typical
reorder/rotation cycle for short-shelf-life grocery stock; a different
number (e.g. 14 or 45) would also be defensible — judgment call, see
DECISIONS.md.

on_hand_eaches is cross-checked against on_hand_cases * case_pack
(case_pack from dim_products) rather than trusting either column
outright. Discrepancies are logged to
fact_inventory_snapshots_discrepancies instead of silently preferring
one side — the table is created either way, even if it ends up empty
(zero discrepancies found in this snapshot, verified).

Idempotent: re-running drops and rebuilds both tables.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import SOURCE_DB_PATH, ANALYTICS_DB_PATH

NEAR_EXPIRY_THRESHOLD_DAYS = 30
EXPECTED_ROW_COUNT = 131_040

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def load_sku_and_case_pack_map(src: sqlite3.Connection) -> dict[int, tuple[str, int]]:
    return {
        row["product_id"]: (row["sku_code"], row["case_pack"])
        for row in src.execute("SELECT product_id, sku_code, case_pack FROM products")
    }


def build(src: sqlite3.Connection, dst: sqlite3.Connection) -> None:
    sku_case_pack_map = load_sku_and_case_pack_map(src)

    dst.execute("DROP TABLE IF EXISTS fact_inventory_snapshots")
    dst.execute(
        """
        CREATE TABLE fact_inventory_snapshots (
            snapshot_id INTEGER PRIMARY KEY,
            snapshot_date TEXT,
            warehouse_id INTEGER,
            sku_code TEXT,
            batch_id TEXT,
            on_hand_cases INTEGER,
            on_hand_eaches INTEGER,
            allocated_cases INTEGER,
            available_cases INTEGER,
            days_of_cover REAL,
            expiry_date TEXT,
            days_to_expiry INTEGER,
            near_expiry_flag INTEGER,
            ageing_bucket TEXT,
            damaged_cases INTEGER,
            blocked_cases INTEGER,
            storage_temp_celsius REAL
        )
        """
    )
    dst.execute("DROP TABLE IF EXISTS fact_inventory_snapshots_discrepancies")
    dst.execute(
        """
        CREATE TABLE fact_inventory_snapshots_discrepancies (
            snapshot_id INTEGER,
            sku_code TEXT,
            on_hand_cases INTEGER,
            case_pack INTEGER,
            expected_eaches INTEGER,
            actual_eaches INTEGER
        )
        """
    )

    rows = []
    discrepancies = []
    for row in src.execute("SELECT * FROM inventory_snapshots"):
        sku_code, case_pack = sku_case_pack_map[row["product_id"]]
        expected_eaches = row["on_hand_cases"] * case_pack
        if expected_eaches != row["on_hand_eaches"]:
            discrepancies.append(
                (row["snapshot_id"], sku_code, row["on_hand_cases"], case_pack, expected_eaches, row["on_hand_eaches"])
            )

        rows.append(
            (
                row["snapshot_id"],
                row["snapshot_date"],
                row["warehouse_id"],
                sku_code,
                row["batch_id"],
                row["on_hand_cases"],
                row["on_hand_eaches"],
                row["allocated_cases"],
                row["available_cases"],
                row["days_of_cover"],
                row["expiry_date"],
                None,  # days_to_expiry, filled below
                None,  # near_expiry_flag, filled below
                row["ageing_bucket"],
                row["damaged_cases"],
                row["blocked_cases"],
                row["storage_temp_celsius"],
            )
        )

    dst.executemany(
        "INSERT INTO fact_inventory_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    # days_to_expiry / near_expiry_flag computed in SQL (julianday handles the date math cleanly).
    dst.execute(
        """
        UPDATE fact_inventory_snapshots
        SET days_to_expiry = CAST(julianday(expiry_date) - julianday(snapshot_date) AS INTEGER),
            near_expiry_flag = CASE
                WHEN julianday(expiry_date) - julianday(snapshot_date) <= ? THEN 1 ELSE 0
            END
        """,
        (NEAR_EXPIRY_THRESHOLD_DAYS,),
    )

    dst.executemany(
        "INSERT INTO fact_inventory_snapshots_discrepancies VALUES (?, ?, ?, ?, ?, ?)",
        discrepancies,
    )

    dst.commit()
    print(f"  inserted {len(rows)} rows into fact_inventory_snapshots")
    print(f"  logged {len(discrepancies)} rows into fact_inventory_snapshots_discrepancies")


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    count = dst.execute("SELECT COUNT(*) FROM fact_inventory_snapshots").fetchone()[0]
    check(f"fact_inventory_snapshots COUNT(*) == {EXPECTED_ROW_COUNT}", count == EXPECTED_ROW_COUNT, f"got {count}")

    near_expiry = dst.execute("SELECT COUNT(*) FROM fact_inventory_snapshots WHERE near_expiry_flag = 1").fetchone()[0]
    rate = 100 * near_expiry / count
    check(f"near_expiry_flag rate is nonzero (threshold <= {NEAR_EXPIRY_THRESHOLD_DAYS} days)", near_expiry > 0, f"{near_expiry}/{count} = {rate:.2f}%")
    print(f"  near-expiry rate: {rate:.2f}%")

    n = dst.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='fact_inventory_snapshots_discrepancies'"
    ).fetchone()[0]
    check("discrepancy log table exists", n == 1, f"got {n}")
    d_count = dst.execute("SELECT COUNT(*) FROM fact_inventory_snapshots_discrepancies").fetchone()[0]
    print(f"  discrepancy log row count: {d_count}")


def main() -> int:
    if not SOURCE_DB_PATH.exists():
        print(f"ERROR: source DB not found at {SOURCE_DB_PATH}")
        return 1

    src = sqlite3.connect(f"file:{SOURCE_DB_PATH}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    for table in ("dim_products", "dim_warehouses", "dim_date"):
        exists = dst.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0]
        if not exists:
            print(f"ERROR: {table} not found in {ANALYTICS_DB_PATH} — run its build script first (T3/T4/T5).")
            return 1

    try:
        print(f"Building fact_inventory_snapshots from {SOURCE_DB_PATH} -> {ANALYTICS_DB_PATH}")
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
