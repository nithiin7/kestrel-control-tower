#!/usr/bin/env python3
"""Build fact_freight in data/analytics.db from raw_freight_invoices.

Run: python build/external/build_fact_freight.py

Joined to dim_warehouses/dim_routes via a direct string match on
warehouse_code/route_code (confirmed identical format to the source DB —
WH01-WH08, RT0001-RT0140 — no fuzzy matching needed, zero orphans either
side), and to dim_carriers via carrier_id.

Stays at invoice grain deliberately. The partner API has NO delivery- or
order-level key on a freight invoice — only warehouse_code and
route_code are ever returned, there is nothing to join a shipment or
order to. This is why "freight cost per delivered case" (mart_money)
has to be computed as a warehouse x route x month aggregate ratio
against fact_deliveries/fact_order_lines, not a per-shipment allocation
— there is no key that would make a per-shipment join correct rather
than arbitrary.

Idempotent: re-running drops and rebuilds the table.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import ANALYTICS_DB_PATH

MIN_ROW_COUNT = 41_500

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def build(dst: sqlite3.Connection) -> None:
    dst.execute("DROP TABLE IF EXISTS fact_freight")
    dst.execute(
        """
        CREATE TABLE fact_freight (
            invoice_id TEXT PRIMARY KEY,
            carrier_id TEXT,
            warehouse_id INTEGER,
            warehouse_code TEXT,
            route_id INTEGER,
            route_code TEXT,
            invoice_date TEXT,
            service_date TEXT,
            amount_inr REAL,
            currency TEXT,
            fuel_surcharge_pct REAL,
            detention_charge INTEGER,
            distance_km REAL,
            weight_kg REAL,
            temperature_controlled INTEGER,
            status TEXT,
            created_at_utc TEXT,
            created_at_ist TEXT
        )
        """
    )
    dst.execute(
        """
        INSERT INTO fact_freight
        SELECT
            r.invoice_id,
            r.carrier_id,
            w.warehouse_id,
            r.warehouse_code,
            rt.route_id,
            r.route_code,
            r.invoice_date,
            r.service_date,
            r.amount_inr,
            r.currency,
            r.fuel_surcharge_pct,
            r.detention_charge,
            r.distance_km,
            r.weight_kg,
            r.temperature_controlled,
            r.status,
            r.created_at_utc,
            r.created_at_ist
        FROM raw_freight_invoices r
        JOIN dim_warehouses w ON r.warehouse_code = w.warehouse_code
        JOIN dim_routes rt ON r.route_code = rt.route_code
        JOIN dim_carriers c ON r.carrier_id = c.carrier_id
        """
    )
    dst.commit()
    n = dst.execute("SELECT COUNT(*) FROM fact_freight").fetchone()[0]
    print(f"  inserted {n} rows into fact_freight")


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    count = dst.execute("SELECT COUNT(*) FROM fact_freight").fetchone()[0]
    check(f"fact_freight COUNT(*) >= {MIN_ROW_COUNT}", count >= MIN_ROW_COUNT, f"got {count}")

    n = dst.execute("SELECT COUNT(*) FROM fact_freight WHERE warehouse_id IS NULL").fetchone()[0]
    check("zero unresolved warehouse_id FKs", n == 0, f"got {n}")

    n = dst.execute("SELECT COUNT(*) FROM fact_freight WHERE route_id IS NULL").fetchone()[0]
    check("zero unresolved route_id FKs", n == 0, f"got {n}")

    n = dst.execute(
        "SELECT COUNT(*) FROM fact_freight WHERE carrier_id NOT IN (SELECT carrier_id FROM dim_carriers)"
    ).fetchone()[0]
    check("zero unresolved carrier_id FKs", n == 0, f"got {n}")

    row = dst.execute(
        """
        SELECT warehouse_code, substr(invoice_date, 1, 7) AS month, SUM(amount_inr) AS total
        FROM fact_freight
        GROUP BY warehouse_code, month
        ORDER BY warehouse_code, month
        LIMIT 1
        """
    ).fetchone()
    total = row[2]
    plausible = total is not None and total == total and 0 < total < 10_00_00_000  # finite, positive, < 10 crore/wh-month
    check(
        f"sampled warehouse-month {row[0]}/{row[1]}: SUM(amount_inr) is finite, positive, plausible",
        plausible,
        f"got {total}",
    )


def main() -> int:
    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    for table in ("raw_freight_invoices", "dim_warehouses", "dim_routes", "dim_carriers"):
        exists = dst.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0]
        if not exists:
            print(f"ERROR: {table} not found in {ANALYTICS_DB_PATH} — run its build script first.")
            return 1

    try:
        print(f"Building fact_freight -> {ANALYTICS_DB_PATH}")
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
