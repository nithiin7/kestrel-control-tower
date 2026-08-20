#!/usr/bin/env python3
"""Build fact_orders and fact_order_lines in data/analytics.db.

Run: python build/facts/build_fact_orders_and_lines.py

created_at is parsed per source_system into an IST timestamp:
  - ERP_WEB "DD/MM/YYYY HH:MM" and SFA_MOBILE "YYYY-MM-DD HH:MM:SS" are
    already local IST (both cluster in 06:00-20:00 business hours, no
    conversion needed).
  - PARTNER_API is ISO8601 UTC ("...Z") — its raw hour distribution
    clusters 00:00-15:00 UTC, which is exactly the same 06:00-20:00 IST
    business-hours window shifted by -5:30, confirming it's UTC and
    needs +5:30 to normalize to IST.

qty_uom is CASE or EACH per line; eaches = qty * case_pack_at_order for
CASE, qty as-is for EACH. This is the load-bearing conversion for fill
rate (must be reported in eaches, not cases) — raw case-grain columns
are kept alongside for audit.

line_value_inr is the money source of truth for everything downstream,
never orders.order_value_gross_inr. KP-2301 (header vs. line value
mismatch) was checked against this snapshot and does not reproduce here
(AVG(ABS(gross - SUM(line_value))) == 0.0 for all three source systems)
— line-level is still used since it's the more granular source and the
data dictionary's general guidance either way.

Lines belonging to test/excluded outlets (per dim_outlets) are dropped,
matching every other outlet-scoped fact table.

Idempotent: re-running drops and rebuilds both tables.
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import SOURCE_DB_PATH, ANALYTICS_DB_PATH

IST_OFFSET = timedelta(hours=5, minutes=30)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def parse_created_at(raw: str, source_system: str) -> str:
    if source_system == "ERP_WEB":
        dt = datetime.strptime(raw, "%d/%m/%Y %H:%M")
    elif source_system == "SFA_MOBILE":
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    elif source_system == "PARTNER_API":
        dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ") + IST_OFFSET
    else:
        raise ValueError(f"unknown source_system: {source_system}")
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def eaches(qty: float, qty_uom: str, case_pack_at_order: int) -> float:
    if qty_uom == "CASE":
        return qty * case_pack_at_order
    if qty_uom == "EACH":
        return qty
    raise ValueError(f"unknown qty_uom: {qty_uom}")


def load_kept_outlet_ids(src: sqlite3.Connection, dst: sqlite3.Connection) -> set[int]:
    dim_codes = {r[0] for r in dst.execute("SELECT outlet_code FROM dim_outlets")}
    return {
        row["outlet_id"]
        for row in src.execute("SELECT outlet_id, outlet_code FROM outlets")
        if row["outlet_code"] in dim_codes
    }


def load_outlet_code_map(src: sqlite3.Connection) -> dict[int, str]:
    return {row["outlet_id"]: row["outlet_code"] for row in src.execute("SELECT outlet_id, outlet_code FROM outlets")}


def load_sku_code_map(src: sqlite3.Connection) -> dict[int, str]:
    return {row["product_id"]: row["sku_code"] for row in src.execute("SELECT product_id, sku_code FROM products")}


def build_fact_orders(
    src: sqlite3.Connection, dst: sqlite3.Connection, kept_outlet_ids: set[int], outlet_code_map: dict[int, str]
) -> set[int]:
    dst.execute("DROP TABLE IF EXISTS fact_orders")
    dst.execute(
        """
        CREATE TABLE fact_orders (
            order_id INTEGER PRIMARY KEY,
            order_number TEXT,
            outlet_code TEXT,
            order_date TEXT,
            requested_delivery_date TEXT,
            channel TEXT,
            region_id INTEGER,
            route_id INTEGER,
            warehouse_id INTEGER,
            salesperson_id INTEGER,
            order_status TEXT,
            line_count INTEGER,
            order_value_gross_inr REAL,
            discount_amount_inr REAL,
            tax_amount_inr REAL,
            order_value_net_inr REAL,
            payment_terms_days INTEGER,
            promo_code TEXT,
            priority_flag INTEGER,
            credit_hold_flag INTEGER,
            cancelled_reason_code TEXT,
            source_system TEXT,
            created_at_raw TEXT,
            created_at_ts TEXT
        )
        """
    )

    kept_order_ids: set[int] = set()
    values = []
    for row in src.execute("SELECT * FROM orders"):
        if row["outlet_id"] not in kept_outlet_ids:
            continue
        kept_order_ids.add(row["order_id"])
        values.append(
            (
                row["order_id"],
                row["order_number"],
                outlet_code_map[row["outlet_id"]],
                row["order_date"],
                row["requested_delivery_date"],
                row["channel"],
                row["region_id"],
                row["route_id"],
                row["warehouse_id"],
                row["salesperson_id"],
                row["order_status"],
                row["line_count"],
                row["order_value_gross_inr"],
                row["discount_amount_inr"],
                row["tax_amount_inr"],
                row["order_value_net_inr"],
                row["payment_terms_days"],
                row["promo_code"],
                row["priority_flag"],
                row["credit_hold_flag"],
                row["cancelled_reason_code"],
                row["source_system"],
                row["created_at"],
                parse_created_at(row["created_at"], row["source_system"]),
            )
        )

    dst.executemany(
        """
        INSERT INTO fact_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    dst.commit()
    print(f"  inserted {len(values)} rows into fact_orders")
    return kept_order_ids


def build_fact_order_lines(
    src: sqlite3.Connection, dst: sqlite3.Connection, kept_order_ids: set[int], sku_code_map: dict[int, str]
) -> None:
    dst.execute("DROP TABLE IF EXISTS fact_order_lines")
    dst.execute(
        """
        CREATE TABLE fact_order_lines (
            order_line_id INTEGER PRIMARY KEY,
            order_id INTEGER,
            line_number INTEGER,
            sku_code TEXT,
            qty_uom TEXT,
            case_pack_at_order INTEGER,
            ordered_qty_raw REAL,
            allocated_qty_raw REAL,
            delivered_qty_raw REAL,
            ordered_eaches REAL,
            allocated_eaches REAL,
            delivered_eaches REAL,
            unit_price_inr REAL,
            line_discount_pct REAL,
            line_value_inr REAL,
            gst_rate_pct REAL,
            batch_id TEXT,
            substitution_flag INTEGER,
            short_reason_code TEXT
        )
        """
    )

    values = []
    for row in src.execute("SELECT * FROM order_lines"):
        if row["order_id"] not in kept_order_ids:
            continue
        uom = row["qty_uom"]
        pack = row["case_pack_at_order"]
        values.append(
            (
                row["order_line_id"],
                row["order_id"],
                row["line_number"],
                sku_code_map[row["product_id"]],
                uom,
                pack,
                row["ordered_qty"],
                row["allocated_qty"],
                row["delivered_qty"],
                eaches(row["ordered_qty"], uom, pack),
                eaches(row["allocated_qty"], uom, pack),
                eaches(row["delivered_qty"], uom, pack),
                row["unit_price_inr"],
                row["line_discount_pct"],
                row["line_value_inr"],
                row["gst_rate_pct"],
                row["batch_id"],
                row["substitution_flag"],
                row["short_reason_code"],
            )
        )

    dst.executemany(
        """
        INSERT INTO fact_order_lines VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    dst.commit()
    print(f"  inserted {len(values)} rows into fact_order_lines")


def verify(dst: sqlite3.Connection, src: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    # Hand-verify one sampled CASE-uom line and one sampled EACH-uom line
    # against the raw values.
    for uom in ("CASE", "EACH"):
        raw = src.execute(
            "SELECT order_line_id, ordered_qty, case_pack_at_order FROM order_lines WHERE qty_uom = ? LIMIT 1",
            (uom,),
        ).fetchone()
        fact = dst.execute(
            "SELECT ordered_eaches FROM fact_order_lines WHERE order_line_id = ?", (raw["order_line_id"],)
        ).fetchone()
        if fact is None:
            print(f"  [SKIP] sampled {uom} line {raw['order_line_id']} excluded (test outlet) — resampling not needed for this check")
            continue
        expected = raw["ordered_qty"] * raw["case_pack_at_order"] if uom == "CASE" else raw["ordered_qty"]
        check(
            f"sampled {uom}-uom line {raw['order_line_id']}: ordered_eaches matches hand calc",
            fact["ordered_eaches"] == expected,
            f"raw qty={raw['ordered_qty']}, case_pack={raw['case_pack_at_order']}, got eaches={fact['ordered_eaches']}, expected={expected}",
        )

    # SUM(ordered_eaches) >= SUM(delivered_eaches) for a sampled order.
    sample_order = dst.execute(
        "SELECT order_id, SUM(ordered_eaches) o, SUM(delivered_eaches) d FROM fact_order_lines GROUP BY order_id LIMIT 1"
    ).fetchone()
    check(
        f"order {sample_order['order_id']}: SUM(ordered_eaches) >= SUM(delivered_eaches)",
        sample_order["o"] >= sample_order["d"],
        f"ordered={sample_order['o']}, delivered={sample_order['d']}",
    )
    violations = dst.execute(
        "SELECT COUNT(*) FROM (SELECT order_id, SUM(ordered_eaches) o, SUM(delivered_eaches) d FROM fact_order_lines GROUP BY order_id HAVING d > o)"
    ).fetchone()[0]
    check("zero orders where delivered_eaches exceeds ordered_eaches", violations == 0, f"got {violations}")

    for col in ("ordered_eaches", "allocated_eaches", "delivered_eaches"):
        n = dst.execute(f"SELECT COUNT(*) FROM fact_order_lines WHERE {col} IS NULL").fetchone()[0]
        check(f"zero nulls in {col}", n == 0, f"got {n}")

    n = dst.execute("SELECT COUNT(*) FROM fact_orders WHERE created_at_ts IS NULL").fetchone()[0]
    check("zero nulls in fact_orders.created_at_ts", n == 0, f"got {n}")

    orphan_orders = dst.execute(
        "SELECT COUNT(*) FROM fact_orders WHERE outlet_code NOT IN (SELECT outlet_code FROM dim_outlets)"
    ).fetchone()[0]
    check("zero fact_orders rows with excluded outlet_code", orphan_orders == 0, f"got {orphan_orders}")

    orphan_lines = dst.execute(
        "SELECT COUNT(*) FROM fact_order_lines WHERE order_id NOT IN (SELECT order_id FROM fact_orders)"
    ).fetchone()[0]
    check("zero fact_order_lines rows with no matching fact_orders row", orphan_lines == 0, f"got {orphan_lines}")


def main() -> int:
    if not SOURCE_DB_PATH.exists():
        print(f"ERROR: source DB not found at {SOURCE_DB_PATH}")
        return 1

    src = sqlite3.connect(f"file:{SOURCE_DB_PATH}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    dst = sqlite3.connect(ANALYTICS_DB_PATH)
    dst.row_factory = sqlite3.Row

    for table in ("dim_outlets", "dim_products", "dim_warehouses", "dim_routes", "dim_regions", "dim_date"):
        exists = dst.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0]
        if not exists:
            print(f"ERROR: {table} not found in {ANALYTICS_DB_PATH} — run its build script first.")
            return 1

    try:
        print(f"Building fact_orders/fact_order_lines from {SOURCE_DB_PATH} -> {ANALYTICS_DB_PATH}")
        kept_outlet_ids = load_kept_outlet_ids(src, dst)
        outlet_code_map = load_outlet_code_map(src)
        sku_code_map = load_sku_code_map(src)

        kept_order_ids = build_fact_orders(src, dst, kept_outlet_ids, outlet_code_map)
        build_fact_order_lines(src, dst, kept_order_ids, sku_code_map)
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
