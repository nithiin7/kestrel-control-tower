#!/usr/bin/env python3
"""Build fact_returns in data/analytics.db from returns_credit_notes.

Run: python build/facts/build_fact_returns.py

return_qty sign bug (KP-2402): ~6.4% of rows are negative, uniformly
across every other field (source system, reason code, outlet, etc.) —
confirmed uncorrelated noise, not a meaningful reversal flag. Fixed
unconditionally via ABS(), not a conditional/reason-based fix.

Eaches conversion uses case_pack_at_order looked up via order_line_id
from the raw order_lines table (matches the qty_uom on every row in this
snapshot — verified zero mismatches). Falls back to dim_products.case_pack
if the order_line_id link is missing or doesn't resolve; that fallback
never actually triggers in this snapshot (every return_id has a valid
order_line_id) but is kept as a defensive safety net rather than an
assumption baked into the join.

Cold-chain-caused call: RT06_COLD_CHAIN_BREACH is the only reason code
that unambiguously asserts a cold-chain failure, so it alone drives
cold_chain_caused_flag (806 rows). RT02_DAMAGE_TRANSIT on a chilled SKU
(814 rows) is a weaker, ambiguous signal — transit damage can be ordinary
breakage/mishandling unrelated to temperature, and folding it into the
primary flag would inflate "cold-chain-caused" with return causes that
were never asserted as temperature-related. Kept as a separate
cold_chain_secondary_signal_flag instead of merging it, so downstream
marts can choose to use it without corrupting the primary metric.

Excludes returns linked to test/excluded outlets (via dim_outlets).

Idempotent: re-running drops and rebuilds the table.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import SOURCE_DB_PATH, ANALYTICS_DB_PATH

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def eaches(qty: float, qty_uom: str, case_pack: int) -> float:
    if qty_uom == "CASE":
        return qty * case_pack
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


def load_case_pack_at_order_map(src: sqlite3.Connection) -> dict[int, int]:
    return {
        row["order_line_id"]: row["case_pack_at_order"]
        for row in src.execute("SELECT order_line_id, case_pack_at_order FROM order_lines")
    }


def load_dim_products_case_pack(dst: sqlite3.Connection) -> dict[str, int]:
    return {row["sku_code"]: row["case_pack"] for row in dst.execute("SELECT sku_code, case_pack FROM dim_products")}


def load_chilled_skus(dst: sqlite3.Connection) -> set[str]:
    return {r[0] for r in dst.execute("SELECT sku_code FROM dim_products WHERE is_chilled = 1")}


def build(
    src: sqlite3.Connection,
    dst: sqlite3.Connection,
    kept_outlet_ids: set[int],
    outlet_code_map: dict[int, str],
    sku_code_map: dict[int, str],
    case_pack_at_order_map: dict[int, int],
    dim_products_case_pack: dict[str, int],
    chilled_skus: set[str],
) -> None:
    dst.execute("DROP TABLE IF EXISTS fact_returns")
    dst.execute(
        """
        CREATE TABLE fact_returns (
            return_id INTEGER PRIMARY KEY,
            credit_note_number TEXT,
            order_id INTEGER,
            order_line_id INTEGER,
            outlet_code TEXT,
            sku_code TEXT,
            return_date TEXT,
            return_qty_raw REAL,
            qty_uom TEXT,
            return_qty_abs REAL,
            case_pack_used INTEGER,
            case_pack_source TEXT,
            return_qty_eaches REAL,
            return_reason_code TEXT,
            cold_chain_caused_flag INTEGER,
            cold_chain_secondary_signal_flag INTEGER,
            credit_note_value_inr REAL,
            approved_by TEXT,
            approval_date TEXT,
            disposition TEXT,
            status TEXT
        )
        """
    )

    values = []
    fallback_count = 0
    for row in src.execute("SELECT * FROM returns_credit_notes"):
        if row["outlet_id"] not in kept_outlet_ids:
            continue

        sku_code = sku_code_map[row["product_id"]]
        case_pack = case_pack_at_order_map.get(row["order_line_id"])
        case_pack_source = "order_line"
        if case_pack is None:
            case_pack = dim_products_case_pack[sku_code]
            case_pack_source = "dim_products_fallback"
            fallback_count += 1

        qty_abs = abs(row["return_qty"])
        reason = row["return_reason_code"]
        cold_chain_caused = 1 if reason == "RT06_COLD_CHAIN_BREACH" else 0
        cold_chain_secondary = 1 if reason == "RT02_DAMAGE_TRANSIT" and sku_code in chilled_skus else 0

        values.append(
            (
                row["return_id"],
                row["credit_note_number"],
                row["order_id"],
                row["order_line_id"],
                outlet_code_map[row["outlet_id"]],
                sku_code,
                row["return_date"],
                row["return_qty"],
                row["qty_uom"],
                qty_abs,
                case_pack,
                case_pack_source,
                eaches(qty_abs, row["qty_uom"], case_pack),
                reason,
                cold_chain_caused,
                cold_chain_secondary,
                row["credit_note_value_inr"],
                row["approved_by"],
                row["approval_date"],
                row["disposition"],
                row["status"],
            )
        )

    dst.executemany(
        """
        INSERT INTO fact_returns VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    dst.commit()
    print(f"  inserted {len(values)} rows into fact_returns")
    print(f"  case_pack fallback used for {fallback_count} rows")


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    n = dst.execute("SELECT COUNT(*) FROM fact_returns WHERE return_qty_eaches < 0").fetchone()[0]
    check("zero negative return_qty_eaches", n == 0, f"got {n}")

    cold_chain_count = dst.execute("SELECT COUNT(*) FROM fact_returns WHERE cold_chain_caused_flag = 1").fetchone()[0]
    check("cold_chain_caused_flag count is nonzero", cold_chain_count > 0, f"got {cold_chain_count}")

    n = dst.execute("SELECT COUNT(*) FROM fact_returns WHERE return_qty_eaches IS NULL").fetchone()[0]
    check("zero nulls in return_qty_eaches", n == 0, f"got {n}")

    orphan = dst.execute(
        "SELECT COUNT(*) FROM fact_returns WHERE outlet_code NOT IN (SELECT outlet_code FROM dim_outlets)"
    ).fetchone()[0]
    check("zero fact_returns rows with excluded outlet_code", orphan == 0, f"got {orphan}")


def main() -> int:
    if not SOURCE_DB_PATH.exists():
        print(f"ERROR: source DB not found at {SOURCE_DB_PATH}")
        return 1

    src = sqlite3.connect(f"file:{SOURCE_DB_PATH}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    dst = sqlite3.connect(ANALYTICS_DB_PATH)
    dst.row_factory = sqlite3.Row

    for table in ("dim_outlets", "dim_products", "dim_date"):
        exists = dst.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0]
        if not exists:
            print(f"ERROR: {table} not found in {ANALYTICS_DB_PATH} — run its build script first.")
            return 1

    try:
        print(f"Building fact_returns from {SOURCE_DB_PATH} -> {ANALYTICS_DB_PATH}")
        kept_outlet_ids = load_kept_outlet_ids(src, dst)
        outlet_code_map = load_outlet_code_map(src)
        sku_code_map = load_sku_code_map(src)
        case_pack_at_order_map = load_case_pack_at_order_map(src)
        dim_products_case_pack = load_dim_products_case_pack(dst)
        chilled_skus = load_chilled_skus(dst)

        build(
            src,
            dst,
            kept_outlet_ids,
            outlet_code_map,
            sku_code_map,
            case_pack_at_order_map,
            dim_products_case_pack,
            chilled_skus,
        )
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
