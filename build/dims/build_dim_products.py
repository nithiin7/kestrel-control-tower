#!/usr/bin/env python3
"""Build dim_products in data/analytics.db from the raw products table.

Run: python build/dims/build_dim_products.py

1 row per sku_code (source has zero duplicate sku_code). discontinued_flag
is derived from discontinued_date being non-null/non-empty rather than
trusting the status column, since it's a direct read of the same fact
status encodes.

Idempotent: re-running drops and rebuilds the table.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import SOURCE_DB_PATH, ANALYTICS_DB_PATH

PRODUCT_COLUMN_TYPES = {
    "sku_code": "TEXT",
    "product_name": "TEXT",
    "brand": "TEXT",
    "category": "TEXT",
    "subcategory": "TEXT",
    "pack_size_value": "REAL",
    "pack_size_uom": "TEXT",
    "case_pack": "INTEGER",
    "mrp_inr": "REAL",
    "list_price_inr": "REAL",
    "gst_rate_pct": "REAL",
    "hsn_code": "TEXT",
    "shelf_life_days": "INTEGER",
    "storage_temp_band": "TEXT",
    "is_chilled": "INTEGER",
    "abc_class": "TEXT",
    "min_order_qty_cases": "INTEGER",
    "unit_weight_grams": "REAL",
    "barcode_ean13": "TEXT",
    "launch_date": "TEXT",
    "discontinued_date": "TEXT",
    "discontinued_flag": "INTEGER",
    "supplier_name": "TEXT",
    "status": "TEXT",
}
PRODUCT_COLUMNS = list(PRODUCT_COLUMN_TYPES.keys())

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def fetch_source_products(src: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = src.execute(
        """
        SELECT sku_code, product_name, brand, category, subcategory,
               pack_size_value, pack_size_uom, case_pack, mrp_inr, list_price_inr,
               gst_rate_pct, hsn_code, shelf_life_days, storage_temp_band, is_chilled,
               abc_class, min_order_qty_cases, unit_weight_grams, barcode_ean13,
               launch_date, discontinued_date, supplier_name, status
        FROM products
        """
    )
    return cur.fetchall()


def build(src: sqlite3.Connection, dst: sqlite3.Connection) -> None:
    rows = fetch_source_products(src)

    dst.execute("DROP TABLE IF EXISTS dim_products")
    column_defs = ", ".join(f'"{c}" {t}' for c, t in PRODUCT_COLUMN_TYPES.items())
    dst.execute(f"CREATE TABLE dim_products ({column_defs}, PRIMARY KEY (sku_code))")

    insert_cols = ", ".join(f'"{c}"' for c in PRODUCT_COLUMNS)
    placeholders = ", ".join("?" for _ in PRODUCT_COLUMNS)

    values = []
    for row in rows:
        discontinued_date = row["discontinued_date"]
        discontinued_flag = 1 if discontinued_date and discontinued_date.strip() else 0
        values.append(
            (
                row["sku_code"],
                row["product_name"],
                row["brand"],
                row["category"],
                row["subcategory"],
                row["pack_size_value"],
                row["pack_size_uom"],
                row["case_pack"],
                row["mrp_inr"],
                row["list_price_inr"],
                row["gst_rate_pct"],
                row["hsn_code"],
                row["shelf_life_days"],
                row["storage_temp_band"],
                row["is_chilled"],
                row["abc_class"],
                row["min_order_qty_cases"],
                row["unit_weight_grams"],
                row["barcode_ean13"],
                row["launch_date"],
                discontinued_date,
                discontinued_flag,
                row["supplier_name"],
                row["status"],
            )
        )
    dst.executemany(
        f"INSERT INTO dim_products ({insert_cols}) VALUES ({placeholders})", values
    )

    dst.commit()
    print(f"  inserted {len(values)} rows into dim_products")


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    cur = dst.execute("SELECT COUNT(*) FROM dim_products")
    count = cur.fetchone()[0]
    check("dim_products COUNT(*) == 341", count == 341, f"got {count}")

    cur = dst.execute("SELECT COUNT(*) FROM dim_products WHERE discontinued_flag = 1")
    discontinued_count = cur.fetchone()[0]
    check(
        "discontinued_flag=1 count == 24",
        discontinued_count == 24,
        f"got {discontinued_count}",
    )

    cur = dst.execute("SELECT COUNT(*) FROM dim_products WHERE case_pack IS NULL")
    null_case_pack = cur.fetchone()[0]
    check("zero null case_pack", null_case_pack == 0, f"got {null_case_pack}")

    cur = dst.execute(
        "SELECT sku_code, COUNT(*) c FROM dim_products GROUP BY sku_code HAVING c > 1"
    )
    dupes = cur.fetchall()
    check("zero duplicate sku_code in dim_products", len(dupes) == 0, f"dupes: {dupes}")


def main() -> int:
    if not SOURCE_DB_PATH.exists():
        print(f"ERROR: source DB not found at {SOURCE_DB_PATH}")
        return 1

    src = sqlite3.connect(f"file:{SOURCE_DB_PATH}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    try:
        print(f"Building dim_products from {SOURCE_DB_PATH} -> {ANALYTICS_DB_PATH}")
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
