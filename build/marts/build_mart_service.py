#!/usr/bin/env python3
"""Build mart_service and mart_service_worst in data/analytics.db.

Run: python build/marts/build_mart_service.py

Grain: region x warehouse x route x outlet x month (month = order_date's
calendar month; region/warehouse/route are the order's assigned
fulfillment location, from fact_orders — not the delivery's, though
they agree 1:1 in this data since every order has at most one delivery).

Only orders with order_status IN ('DELIVERED', 'PARTIAL') are counted.
CANCELLED orders never entered fulfillment (delivered_eaches is always
0 and they have zero matching fact_deliveries rows — counting them
would misrepresent cancellations as fulfillment failures). OPEN orders
are still in-flight (also zero fact_deliveries rows, even though some
already show partial delivered_eaches) — including them would bias
whichever month is most recent, where many orders haven't reached a
final state yet. This is a judgment call (see DECISIONS.md).

fill_rate_eaches = SUM(delivered_eaches) / SUM(ordered_eaches), rolled
up from fact_order_lines.

otif_pct is computed at ORDER grain then rolled up: "on time" is
fact_deliveries.on_time_flag; "in full" is defined as
SUM(delivered_eaches) >= SUM(ordered_eaches) across an order's lines
(i.e. no partial shortfall at all, not some tolerance band) — a
judgment call worth a line in DECISIONS.md, not the only reasonable
threshold. otif_pct = 100 * (orders that are both) / (orders counted).
Every DELIVERED/PARTIAL order has exactly one fact_deliveries row in
this data (verified, zero orders with >1), so this join never
duplicates or drops rows.

mart_service_worst is pre-sorted ascending by fill_rate_eaches so the
UI needs zero drill-down. Restricted to groups with at least
MIN_ORDERS_FOR_WORST_RANKING orders — otherwise a single bad order in a
low-volume outlet-month would dominate the "worst" list ahead of a
high-volume outlet-month with a real, sustained problem. Also a
judgment call (see DECISIONS.md).

Idempotent: re-running drops and rebuilds both tables.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import ANALYTICS_DB_PATH

WORST_N = 15
MIN_ORDERS_FOR_WORST_RANKING = 5

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def build(dst: sqlite3.Connection) -> None:
    dst.execute("DROP TABLE IF EXISTS mart_service")
    dst.execute(
        """
        CREATE TABLE mart_service (
            region_id INTEGER,
            region_name TEXT,
            warehouse_id INTEGER,
            warehouse_code TEXT,
            route_id INTEGER,
            route_code TEXT,
            outlet_code TEXT,
            outlet_name TEXT,
            month TEXT,
            order_count INTEGER,
            ordered_eaches REAL,
            delivered_eaches REAL,
            fill_rate_eaches REAL,
            otif_orders INTEGER,
            otif_pct REAL
        )
        """
    )
    dst.execute(
        """
        WITH order_lines_agg AS (
            SELECT order_id, SUM(ordered_eaches) AS ordered_eaches, SUM(delivered_eaches) AS delivered_eaches
            FROM fact_order_lines
            GROUP BY order_id
        ),
        order_level AS (
            SELECT
                o.order_id,
                o.region_id,
                o.warehouse_id,
                o.route_id,
                o.outlet_code,
                substr(o.order_date, 1, 7) AS month,
                ola.ordered_eaches,
                ola.delivered_eaches,
                d.on_time_flag,
                CASE WHEN ola.delivered_eaches >= ola.ordered_eaches THEN 1 ELSE 0 END AS in_full_flag,
                CASE WHEN d.on_time_flag = 1 AND ola.delivered_eaches >= ola.ordered_eaches THEN 1 ELSE 0 END AS otif_flag
            FROM fact_orders o
            JOIN order_lines_agg ola ON o.order_id = ola.order_id
            JOIN fact_deliveries d ON o.order_id = d.order_id
            WHERE o.order_status IN ('DELIVERED', 'PARTIAL')
        )
        INSERT INTO mart_service
        SELECT
            ol.region_id,
            r.region_name,
            ol.warehouse_id,
            w.warehouse_code,
            ol.route_id,
            rt.route_code,
            ol.outlet_code,
            out.outlet_name,
            ol.month,
            COUNT(*) AS order_count,
            SUM(ol.ordered_eaches) AS ordered_eaches,
            SUM(ol.delivered_eaches) AS delivered_eaches,
            100.0 * SUM(ol.delivered_eaches) / SUM(ol.ordered_eaches) AS fill_rate_eaches,
            SUM(ol.otif_flag) AS otif_orders,
            100.0 * SUM(ol.otif_flag) / COUNT(*) AS otif_pct
        FROM order_level ol
        JOIN dim_regions r ON ol.region_id = r.region_id
        JOIN dim_warehouses w ON ol.warehouse_id = w.warehouse_id
        JOIN dim_routes rt ON ol.route_id = rt.route_id
        JOIN dim_outlets out ON ol.outlet_code = out.outlet_code
        GROUP BY ol.region_id, ol.warehouse_id, ol.route_id, ol.outlet_code, ol.month
        """
    )
    dst.commit()
    n = dst.execute("SELECT COUNT(*) FROM mart_service").fetchone()[0]
    print(f"  inserted {n} rows into mart_service")

    dst.execute("DROP TABLE IF EXISTS mart_service_worst")
    dst.execute(
        f"""
        CREATE TABLE mart_service_worst AS
        SELECT * FROM mart_service
        WHERE order_count >= {MIN_ORDERS_FOR_WORST_RANKING}
        ORDER BY fill_rate_eaches ASC
        LIMIT {WORST_N}
        """
    )
    dst.commit()
    n = dst.execute("SELECT COUNT(*) FROM mart_service_worst").fetchone()[0]
    print(f"  inserted {n} rows into mart_service_worst")


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    sample = dst.execute(
        "SELECT outlet_code, month, ordered_eaches, delivered_eaches, fill_rate_eaches FROM mart_service LIMIT 1"
    ).fetchone()
    outlet_code, month, mart_ordered, mart_delivered, mart_fill_rate = sample

    raw = dst.execute(
        """
        SELECT SUM(ola.ordered_eaches), SUM(ola.delivered_eaches)
        FROM fact_orders o
        JOIN (
            SELECT order_id, SUM(ordered_eaches) AS ordered_eaches, SUM(delivered_eaches) AS delivered_eaches
            FROM fact_order_lines GROUP BY order_id
        ) ola ON o.order_id = ola.order_id
        WHERE o.outlet_code = ? AND substr(o.order_date, 1, 7) = ? AND o.order_status IN ('DELIVERED', 'PARTIAL')
        """,
        (outlet_code, month),
    ).fetchone()
    raw_ordered, raw_delivered = raw
    raw_fill_rate = 100.0 * raw_delivered / raw_ordered

    check(
        f"hand-computed fill_rate_eaches for {outlet_code}/{month} matches mart_service",
        abs(raw_fill_rate - mart_fill_rate) < 0.001 and raw_ordered == mart_ordered and raw_delivered == mart_delivered,
        f"mart={mart_fill_rate:.4f} hand={raw_fill_rate:.4f} (ordered mart={mart_ordered} hand={raw_ordered}, delivered mart={mart_delivered} hand={raw_delivered})",
    )

    rows = [r[0] for r in dst.execute("SELECT fill_rate_eaches FROM mart_service_worst").fetchall()]
    check(
        "mart_service_worst is sorted ascending by fill_rate_eaches",
        rows == sorted(rows),
        f"got {rows}",
    )

    n = dst.execute(f"SELECT COUNT(*) FROM mart_service_worst").fetchone()[0]
    check(f"mart_service_worst has <= {WORST_N} rows", n <= WORST_N, f"got {n}")

    n = dst.execute(f"SELECT COUNT(*) FROM mart_service_worst WHERE order_count < {MIN_ORDERS_FOR_WORST_RANKING}").fetchone()[0]
    check(f"zero mart_service_worst rows below the {MIN_ORDERS_FOR_WORST_RANKING}-order noise floor", n == 0, f"got {n}")


def main() -> int:
    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    for table in ("fact_orders", "fact_order_lines", "fact_deliveries", "dim_outlets", "dim_warehouses", "dim_routes", "dim_regions"):
        exists = dst.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0]
        if not exists:
            print(f"ERROR: {table} not found in {ANALYTICS_DB_PATH} — run its build script first.")
            return 1

    try:
        print(f"Building mart_service/mart_service_worst -> {ANALYTICS_DB_PATH}")
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
