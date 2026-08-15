#!/usr/bin/env python3
"""Build mart_money and its two satellite tables in data/analytics.db.

Run: python build/marts/build_mart_money.py

mart_money (grain: warehouse x route x month) — freight cost per
delivered case:
    SUM(fact_freight.amount_inr) at warehouse x route x month
    / SUM(delivered_eaches / case_pack_at_order) at that same grain.
Delivered cases are sourced via fact_order_lines JOIN fact_deliveries
(order_id) for the delivery's actual warehouse/route/month — not
fact_orders' assigned warehouse/route, though the two agree in every
row in this data (verified, zero mismatches); fact_deliveries is used
because "delivered case" is literally about the delivery event.

**This is necessarily an aggregate ratio, not a per-shipment cost.**
The partner freight API has no delivery- or order-level key on an
invoice — only warehouse_code/route_code (see T12) — so there is no
correct way to allocate a specific invoice's cost to a specific
delivery or order. Bucketing both sides into the same warehouse x
route x month bucket is the finest grain that's actually defensible.

**Two measures from the brief don't share that grain, so they're NOT
force-fit into it** (same approach as mart_coldchain's near-expiry
column, T17) — each gets its own satellite table instead of a
misleading broadcast or a fabricated join:

mart_money_returns_by_category (grain: category x month) — returns as
% of dispatch value. Dispatch value is fact_order_lines.line_value_inr
for DELIVERED/PARTIAL orders only (CANCELLED never dispatched — same
judgment call as mart_service, T16), summed by category and the
order's month. Returns value is fact_returns.credit_note_value_inr
summed by category and the return's own month. Category has no
warehouse/route dimension in this data model (SKUs aren't
warehouse-specific), so adding warehouse/route here would just be
noise, not real granularity.

mart_money_carrier_variance (grain: carrier) — dispute rate and cost
variance by carrier. Carrier ONLY exists on fact_freight; there is no
carrier_id anywhere on fact_deliveries, fact_orders, or fact_returns
(deliveries are executed by whichever driver/vehicle, not tagged to
the invoicing carrier) — so "leakage by carrier" can only ever be a
freight-side view (dispute rate, cost variance vs. the overall mean).
Forcing a join to orders/returns to get a warehouse/route breakdown
here would silently invent a relationship the data doesn't have.

Idempotent: re-running drops and rebuilds all three tables.
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


def build_mart_money(dst: sqlite3.Connection) -> None:
    dst.execute("DROP TABLE IF EXISTS mart_money")
    dst.execute(
        """
        CREATE TABLE mart_money (
            warehouse_id INTEGER,
            warehouse_code TEXT,
            route_id INTEGER,
            route_code TEXT,
            month TEXT,
            freight_amount_inr REAL,
            delivered_cases REAL,
            freight_cost_per_delivered_case_inr REAL
        )
        """
    )
    dst.execute(
        """
        WITH freight_agg AS (
            SELECT warehouse_id, route_id, substr(invoice_date, 1, 7) AS month, SUM(amount_inr) AS freight_amount_inr
            FROM fact_freight
            GROUP BY warehouse_id, route_id, month
        ),
        delivered_cases_agg AS (
            SELECT
                d.warehouse_id,
                d.route_id,
                substr(d.actual_arrival_ts, 1, 7) AS month,
                SUM(CAST(ol.delivered_eaches AS REAL) / ol.case_pack_at_order) AS delivered_cases
            FROM fact_order_lines ol
            JOIN fact_deliveries d ON ol.order_id = d.order_id
            GROUP BY d.warehouse_id, d.route_id, month
        ),
        keys AS (
            SELECT warehouse_id, route_id, month FROM freight_agg
            UNION
            SELECT warehouse_id, route_id, month FROM delivered_cases_agg
        )
        INSERT INTO mart_money
        SELECT
            k.warehouse_id,
            w.warehouse_code,
            k.route_id,
            rt.route_code,
            k.month,
            COALESCE(f.freight_amount_inr, 0.0),
            COALESCE(dc.delivered_cases, 0.0),
            CASE WHEN COALESCE(dc.delivered_cases, 0) = 0 THEN NULL
                 ELSE f.freight_amount_inr / dc.delivered_cases END
        FROM keys k
        JOIN dim_warehouses w ON k.warehouse_id = w.warehouse_id
        JOIN dim_routes rt ON k.route_id = rt.route_id
        LEFT JOIN freight_agg f ON k.warehouse_id = f.warehouse_id AND k.route_id = f.route_id AND k.month = f.month
        LEFT JOIN delivered_cases_agg dc ON k.warehouse_id = dc.warehouse_id AND k.route_id = dc.route_id AND k.month = dc.month
        """
    )
    dst.commit()
    n = dst.execute("SELECT COUNT(*) FROM mart_money").fetchone()[0]
    print(f"  inserted {n} rows into mart_money")


def build_mart_money_returns_by_category(dst: sqlite3.Connection) -> None:
    dst.execute("DROP TABLE IF EXISTS mart_money_returns_by_category")
    dst.execute(
        """
        CREATE TABLE mart_money_returns_by_category (
            category TEXT,
            month TEXT,
            dispatch_value_inr REAL,
            returns_value_inr REAL,
            returns_pct_of_dispatch_value REAL
        )
        """
    )
    dst.execute(
        """
        WITH dispatch_agg AS (
            SELECT p.category, substr(o.order_date, 1, 7) AS month, SUM(ol.line_value_inr) AS dispatch_value_inr
            FROM fact_order_lines ol
            JOIN fact_orders o ON ol.order_id = o.order_id
            JOIN dim_products p ON ol.sku_code = p.sku_code
            WHERE o.order_status IN ('DELIVERED', 'PARTIAL')
            GROUP BY p.category, month
        ),
        returns_agg AS (
            SELECT p.category, substr(r.return_date, 1, 7) AS month, SUM(r.credit_note_value_inr) AS returns_value_inr
            FROM fact_returns r
            JOIN dim_products p ON r.sku_code = p.sku_code
            GROUP BY p.category, month
        ),
        keys AS (
            SELECT category, month FROM dispatch_agg
            UNION
            SELECT category, month FROM returns_agg
        )
        INSERT INTO mart_money_returns_by_category
        SELECT
            k.category,
            k.month,
            COALESCE(d.dispatch_value_inr, 0.0),
            COALESCE(r.returns_value_inr, 0.0),
            CASE WHEN COALESCE(d.dispatch_value_inr, 0) = 0 THEN NULL
                 ELSE 100.0 * COALESCE(r.returns_value_inr, 0.0) / d.dispatch_value_inr END
        FROM keys k
        LEFT JOIN dispatch_agg d ON k.category = d.category AND k.month = d.month
        LEFT JOIN returns_agg r ON k.category = r.category AND k.month = r.month
        """
    )
    dst.commit()
    n = dst.execute("SELECT COUNT(*) FROM mart_money_returns_by_category").fetchone()[0]
    print(f"  inserted {n} rows into mart_money_returns_by_category")


def build_mart_money_carrier_variance(dst: sqlite3.Connection) -> None:
    dst.execute("DROP TABLE IF EXISTS mart_money_carrier_variance")
    dst.execute(
        """
        CREATE TABLE mart_money_carrier_variance (
            carrier_id TEXT,
            carrier_name TEXT,
            invoice_count INTEGER,
            total_amount_inr REAL,
            avg_cost_per_invoice_inr REAL,
            dispute_count INTEGER,
            dispute_rate_pct REAL,
            cost_variance_pct_vs_overall_avg REAL
        )
        """
    )
    dst.execute(
        """
        WITH carrier_agg AS (
            SELECT
                f.carrier_id,
                c.name AS carrier_name,
                COUNT(*) AS invoice_count,
                SUM(f.amount_inr) AS total_amount_inr,
                AVG(f.amount_inr) AS avg_cost_per_invoice_inr,
                SUM(CASE WHEN f.status = 'DISPUTED' THEN 1 ELSE 0 END) AS dispute_count
            FROM fact_freight f
            JOIN dim_carriers c ON f.carrier_id = c.carrier_id
            GROUP BY f.carrier_id, c.name
        ),
        overall AS (
            SELECT SUM(amount_inr) * 1.0 / COUNT(*) AS overall_avg_cost_inr FROM fact_freight
        )
        INSERT INTO mart_money_carrier_variance
        SELECT
            ca.carrier_id,
            ca.carrier_name,
            ca.invoice_count,
            ca.total_amount_inr,
            ca.avg_cost_per_invoice_inr,
            ca.dispute_count,
            100.0 * ca.dispute_count / ca.invoice_count,
            100.0 * (ca.avg_cost_per_invoice_inr - o.overall_avg_cost_inr) / o.overall_avg_cost_inr
        FROM carrier_agg ca, overall o
        """
    )
    dst.commit()
    n = dst.execute("SELECT COUNT(*) FROM mart_money_carrier_variance").fetchone()[0]
    print(f"  inserted {n} rows into mart_money_carrier_variance")


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    row = dst.execute(
        "SELECT warehouse_id, route_id, month, freight_cost_per_delivered_case_inr FROM mart_money "
        "WHERE freight_cost_per_delivered_case_inr IS NOT NULL LIMIT 1"
    ).fetchone()
    cost = row[3] if row else None
    plausible = cost is not None and cost == cost and 0 < cost < 100_000
    check(
        f"sampled warehouse-month {row[0]}/{row[1]}/{row[2]}: freight_cost_per_delivered_case_inr is finite, positive, plausible" if row else "no rows",
        plausible,
        f"got {cost}",
    )

    row = dst.execute(
        "SELECT category, month, returns_pct_of_dispatch_value FROM mart_money_returns_by_category "
        "WHERE returns_pct_of_dispatch_value IS NOT NULL ORDER BY dispatch_value_inr DESC LIMIT 1"
    ).fetchone()
    pct = row[2] if row else None
    sane = pct is not None and 0 <= pct <= 15
    check(
        f"sampled category-month {row[0]}/{row[1]}: returns_pct_of_dispatch_value in 0-15% range" if row else "no rows",
        sane,
        f"got {pct}",
    )

    carriers = dst.execute("SELECT carrier_id, invoice_count, dispute_rate_pct, cost_variance_pct_vs_overall_avg FROM mart_money_carrier_variance").fetchall()
    check("mart_money_carrier_variance has all 5 carriers", len(carriers) == 5, f"got {len(carriers)}")
    no_div_zero = all(r[1] > 0 and r[2] == r[2] and r[3] == r[3] for r in carriers)  # r == r filters out NaN
    check("no divide-by-zero across all 5 carriers", no_div_zero, f"got {carriers}")


def main() -> int:
    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    for table in ("fact_freight", "fact_returns", "fact_orders", "fact_order_lines", "fact_deliveries", "dim_products", "dim_warehouses", "dim_routes", "dim_carriers"):
        exists = dst.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0]
        if not exists:
            print(f"ERROR: {table} not found in {ANALYTICS_DB_PATH} — run its build script first (T6/T9/T12).")
            return 1

    try:
        print(f"Building mart_money and satellite tables -> {ANALYTICS_DB_PATH}")
        build_mart_money(dst)
        build_mart_money_returns_by_category(dst)
        build_mart_money_carrier_variance(dst)
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
