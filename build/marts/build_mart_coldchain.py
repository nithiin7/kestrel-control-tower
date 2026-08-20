#!/usr/bin/env python3
"""Build mart_coldchain in data/analytics.db.

Run: python build/marts/build_mart_coldchain.py

Grain: warehouse x route x month.

excursions_per_100_chilled_deliveries: denominator is deliveries whose
order carries at least one chilled SKU (fact_order_lines joined to
dim_products.is_chilled), joined to fact_deliveries by order_id. Month
is the delivery's actual_arrival_ts month — this metric is genuinely
warehouse x route x month, since fact_deliveries carries both FKs
directly.

near_expiry_stock_value_inr: fact_inventory_snapshots.near_expiry_flag
rows x dim_products.list_price_inr, valued at the LAST snapshot_date of
each warehouse's month (not summed across that month's ~4-5 weekly
snapshots — inventory is a stock/level, not a flow, so summing every
weekly snapshot would count the same physical batches multiple times).

**Grain mismatch, handled explicitly, not silently**: inventory has no
route dimension (stock sits in a warehouse, not on a route) — this
column is a warehouse x month aggregate, broadcast identically across
every route under that warehouse for that month. It is NOT a
per-route allocation; treat it as "this warehouse's near-expiry
exposure," not "this route's." Same pattern as fact_freight's
warehouse x route x month aggregate ratio (fact_freight/mart_money) —
no finer key exists to allocate it correctly, so it isn't invented.

cold_chain_return_value_inr: fact_returns (cold_chain_caused_flag=1)
joined to fact_orders by order_id to pick up warehouse_id/route_id
(fact_returns doesn't carry them directly — zero orphans verified, this
join is safe). Month is the return's own return_date.

Grain rows come from the UNION of (warehouse, route, month) keys that
actually appear in the excursion and returns data — not a full
warehouse x route x month x n_months cross join, which would produce
mostly-empty rows for route-months with zero activity.

Idempotent: re-running drops and rebuilds the table.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import ANALYTICS_DB_PATH

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def build(dst: sqlite3.Connection) -> None:
    dst.execute("DROP TABLE IF EXISTS mart_coldchain")
    dst.execute(
        """
        CREATE TABLE mart_coldchain (
            warehouse_id INTEGER,
            warehouse_code TEXT,
            route_id INTEGER,
            route_code TEXT,
            month TEXT,
            chilled_delivery_count INTEGER,
            excursion_count INTEGER,
            excursions_per_100_chilled_deliveries REAL,
            near_expiry_stock_value_inr REAL,
            cold_chain_return_value_inr REAL,
            cold_chain_return_count INTEGER
        )
        """
    )
    dst.execute(
        """
        WITH chilled_orders AS (
            SELECT DISTINCT ol.order_id
            FROM fact_order_lines ol
            JOIN dim_products p ON ol.sku_code = p.sku_code
            WHERE p.is_chilled = 1
        ),
        excursion_agg AS (
            SELECT
                d.warehouse_id,
                d.route_id,
                substr(d.actual_arrival_ts, 1, 7) AS month,
                COUNT(*) AS chilled_delivery_count,
                SUM(d.temperature_excursion_flag) AS excursion_count
            FROM fact_deliveries d
            JOIN chilled_orders co ON d.order_id = co.order_id
            GROUP BY d.warehouse_id, d.route_id, month
        ),
        returns_agg AS (
            SELECT
                o.warehouse_id,
                o.route_id,
                substr(r.return_date, 1, 7) AS month,
                SUM(r.credit_note_value_inr) AS cold_chain_return_value_inr,
                COUNT(*) AS cold_chain_return_count
            FROM fact_returns r
            JOIN fact_orders o ON r.order_id = o.order_id
            WHERE r.cold_chain_caused_flag = 1
            GROUP BY o.warehouse_id, o.route_id, month
        ),
        last_snapshot_date AS (
            SELECT warehouse_id, substr(snapshot_date, 1, 7) AS month, MAX(snapshot_date) AS last_date
            FROM fact_inventory_snapshots
            GROUP BY warehouse_id, month
        ),
        near_expiry_agg AS (
            SELECT s.warehouse_id, s.month, SUM(i.on_hand_eaches * p.list_price_inr) AS near_expiry_stock_value_inr
            FROM last_snapshot_date s
            JOIN fact_inventory_snapshots i ON i.warehouse_id = s.warehouse_id AND i.snapshot_date = s.last_date
            JOIN dim_products p ON i.sku_code = p.sku_code
            WHERE i.near_expiry_flag = 1
            GROUP BY s.warehouse_id, s.month
        ),
        keys AS (
            SELECT warehouse_id, route_id, month FROM excursion_agg
            UNION
            SELECT warehouse_id, route_id, month FROM returns_agg
        )
        INSERT INTO mart_coldchain
        SELECT
            k.warehouse_id,
            w.warehouse_code,
            k.route_id,
            rt.route_code,
            k.month,
            COALESCE(e.chilled_delivery_count, 0),
            COALESCE(e.excursion_count, 0),
            CASE WHEN COALESCE(e.chilled_delivery_count, 0) = 0 THEN NULL
                 ELSE 100.0 * e.excursion_count / e.chilled_delivery_count END,
            COALESCE(ne.near_expiry_stock_value_inr, 0.0),
            COALESCE(ra.cold_chain_return_value_inr, 0.0),
            COALESCE(ra.cold_chain_return_count, 0)
        FROM keys k
        JOIN dim_warehouses w ON k.warehouse_id = w.warehouse_id
        JOIN dim_routes rt ON k.route_id = rt.route_id
        LEFT JOIN excursion_agg e ON k.warehouse_id = e.warehouse_id AND k.route_id = e.route_id AND k.month = e.month
        LEFT JOIN returns_agg ra ON k.warehouse_id = ra.warehouse_id AND k.route_id = ra.route_id AND k.month = ra.month
        LEFT JOIN near_expiry_agg ne ON k.warehouse_id = ne.warehouse_id AND k.month = ne.month
        """
    )
    dst.commit()
    n = dst.execute("SELECT COUNT(*) FROM mart_coldchain").fetchone()[0]
    print(f"  inserted {n} rows into mart_coldchain")


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    sample = dst.execute(
        """
        SELECT warehouse_id, route_id, month, chilled_delivery_count, excursion_count, excursions_per_100_chilled_deliveries
        FROM mart_coldchain
        WHERE chilled_delivery_count > 0
        LIMIT 1
        """
    ).fetchone()
    warehouse_id, route_id, month, mart_count, mart_excursions, mart_rate = sample

    raw = dst.execute(
        """
        SELECT COUNT(*), SUM(d.temperature_excursion_flag)
        FROM fact_deliveries d
        WHERE d.warehouse_id = ? AND d.route_id = ? AND substr(d.actual_arrival_ts, 1, 7) = ?
          AND d.order_id IN (
              SELECT DISTINCT ol.order_id FROM fact_order_lines ol
              JOIN dim_products p ON ol.sku_code = p.sku_code WHERE p.is_chilled = 1
          )
        """,
        (warehouse_id, route_id, month),
    ).fetchone()
    raw_count, raw_excursions = raw
    raw_rate = 100.0 * raw_excursions / raw_count

    check(
        f"hand-verified excursion rate for warehouse={warehouse_id}/route={route_id}/{month}",
        raw_count == mart_count and raw_excursions == mart_excursions and abs(raw_rate - mart_rate) < 0.001,
        f"mart=({mart_count},{mart_excursions},{mart_rate:.3f}) hand=({raw_count},{raw_excursions},{raw_rate:.3f})",
    )

    total_near_expiry = dst.execute(
        "SELECT SUM(near_expiry_stock_value_inr) FROM (SELECT DISTINCT warehouse_id, month, near_expiry_stock_value_inr FROM mart_coldchain)"
    ).fetchone()[0]
    check(
        "near-expiry stock value is nonzero and finite",
        total_near_expiry is not None and total_near_expiry == total_near_expiry and total_near_expiry > 0,
        f"got {total_near_expiry}",
    )


def main() -> int:
    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    for table in ("fact_deliveries", "fact_inventory_snapshots", "fact_returns", "fact_orders", "fact_order_lines", "dim_products", "dim_warehouses", "dim_routes"):
        exists = dst.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0]
        if not exists:
            print(f"ERROR: {table} not found in {ANALYTICS_DB_PATH} — run its build script first.")
            return 1

    try:
        print(f"Building mart_coldchain -> {ANALYTICS_DB_PATH}")
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
