#!/usr/bin/env python3
"""Build mart_price_position in data/analytics.db.

Run: python build/marts/build_mart_price_position.py

Grain: city x category x sku_code x week. "Week" is the weekly
observation date itself from BazaarPulse's own "Observed price history"
child table (parsed by build/external/parse_bazaarpulse.py) — those dates
are already the natural weekly grain (confirmed 7-day spacing), so
they're used directly rather than re-bucketed into ISO weeks.

Only bridge_bazaarpulse_sku_match rows with a non-null sku_code (i.e.
matched at/above match_bazaarpulse_skus.py's confidence threshold) are
included — an unmatched listing has no Kestrel MRP to compare against,
so it can't produce a gap_pct at all. category comes from dim_products
(the SKU's real Kestrel category), not the BazaarPulse listing's own
breadcrumb category text.

Competitor price uses the weekly history series ("always plain
rupee-entity format regardless of city... the cleaner series for
trend/comparison"), never the noisier per-city-markup "current price"
line. Multiple retailers can list the same SKU in the same city in the
same week (375 of 1,134 matched city+sku_code combos have >1 listing,
verified) — both competitor_price_median_inr and
competitor_price_min_inr are computed across those listings;
gap_pct uses the median as the primary, more representative figure
(less skewed by one outlier retailer than the min would be).

gap_pct = (kestrel_mrp_inr - competitor_price_inr) / kestrel_mrp_inr —
positive means Kestrel is priced above the competitor observation,
negative means below.

competitor_mrp_inr is the competitor listing's OWN printed MRP
(raw_bazaarpulse_products.competitor_mrp_inr, fully populated — 1,134/1,134
matched listings), kept as its own column and never merged with
competitor_price_median_inr (the observed street price). Conflating the
two would misrepresent "Kestrel MRP vs. what competitors actually
charge" as "Kestrel MRP vs. competitor's list price" — a different,
less useful comparison. Unlike price, MRP doesn't vary week to week in
this data (it's a per-listing label, not a weekly observation), so it's
aggregated once per (city, sku_code) as the median across matched
listings and broadcast across that pair's week rows, the same
median-of-retailers approach as the observed price.

**Scoped to the 4 BazaarPulse cities only** (Mumbai, Bengaluru,
Chennai, Delhi). Kestrel has 8 warehouse cities total (dim_warehouses)
— the other 4 have zero competitor price coverage from this data
source and simply don't appear in this mart. Not a bug; there is no
BazaarPulse data for them. Worth surfacing on the price-position page
rather than leaving as a silent gap (see DECISIONS.md).

Idempotent: re-running drops and rebuilds the table.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import ANALYTICS_DB_PATH

EXPECTED_CITY_COUNT = 4

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def build(dst: sqlite3.Connection) -> None:
    dst.execute("DROP TABLE IF EXISTS mart_price_position")
    dst.execute(
        """
        CREATE TABLE mart_price_position (
            city TEXT,
            category TEXT,
            sku_code TEXT,
            week TEXT,
            kestrel_mrp_inr REAL,
            competitor_mrp_inr REAL,
            competitor_price_median_inr REAL,
            competitor_price_min_inr REAL,
            competitor_listing_count INTEGER,
            gap_pct REAL,
            gap_pct_vs_min REAL
        )
        """
    )
    dst.execute(
        """
        WITH matched AS (
            SELECT r.product_id, r.city, b.sku_code
            FROM raw_bazaarpulse_products r
            JOIN bridge_bazaarpulse_sku_match b ON r.product_id = b.product_id
            WHERE b.sku_code IS NOT NULL
        ),
        observations AS (
            SELECT m.city, p.category, m.sku_code, h.observed_date AS week, h.price_inr, p.mrp_inr AS kestrel_mrp_inr
            FROM matched m
            JOIN raw_bazaarpulse_price_history h ON m.product_id = h.product_id
            JOIN dim_products p ON m.sku_code = p.sku_code
        )
        INSERT INTO mart_price_position
        SELECT
            city,
            category,
            sku_code,
            week,
            kestrel_mrp_inr,
            NULL,  -- competitor_mrp_inr filled in below (median per city+sku_code, not per week)
            NULL,  -- median filled in below (SQLite has no built-in MEDIAN aggregate)
            MIN(price_inr) AS competitor_price_min_inr,
            COUNT(*) AS competitor_listing_count,
            NULL,
            100.0 * (kestrel_mrp_inr - MIN(price_inr)) / kestrel_mrp_inr AS gap_pct_vs_min
        FROM observations
        GROUP BY city, category, sku_code, week, kestrel_mrp_inr
        """
    )
    dst.commit()

    # competitor_mrp_inr: a per-listing label (raw_bazaarpulse_products), not a
    # weekly observation like price — median across matched listings per
    # (city, sku_code), broadcast across that pair's week rows.
    mrp_rows = dst.execute(
        """
        SELECT r.city, b.sku_code, r.competitor_mrp_inr
        FROM raw_bazaarpulse_products r
        JOIN bridge_bazaarpulse_sku_match b ON r.product_id = b.product_id
        WHERE b.sku_code IS NOT NULL
        """
    ).fetchall()
    mrp_grouped: dict[tuple[str, str], list[float]] = {}
    for city, sku_code, mrp in mrp_rows:
        mrp_grouped.setdefault((city, sku_code), []).append(mrp)

    for (city, sku_code), mrps in mrp_grouped.items():
        mrps.sort()
        n = len(mrps)
        median_mrp = mrps[n // 2] if n % 2 else (mrps[n // 2 - 1] + mrps[n // 2]) / 2
        dst.execute(
            "UPDATE mart_price_position SET competitor_mrp_inr = ? WHERE city = ? AND sku_code = ?",
            (median_mrp, city, sku_code),
        )
    dst.commit()

    # Fill in median + gap_pct in Python (no native MEDIAN() aggregate in SQLite).
    rows = dst.execute(
        """
        SELECT m.city, m.sku_code, h.observed_date, h.price_inr
        FROM (SELECT r.product_id AS product_id, r.city AS city, b.sku_code AS sku_code
              FROM raw_bazaarpulse_products r
              JOIN bridge_bazaarpulse_sku_match b ON r.product_id = b.product_id
              WHERE b.sku_code IS NOT NULL) m
        JOIN raw_bazaarpulse_price_history h ON m.product_id = h.product_id
        """
    ).fetchall()
    grouped: dict[tuple[str, str, str], list[float]] = {}
    for city, sku_code, week, price in rows:
        grouped.setdefault((city, sku_code, week), []).append(price)

    for (city, sku_code, week), prices in grouped.items():
        prices.sort()
        n = len(prices)
        median = prices[n // 2] if n % 2 else (prices[n // 2 - 1] + prices[n // 2]) / 2
        dst.execute(
            """
            UPDATE mart_price_position
            SET competitor_price_median_inr = ?,
                gap_pct = 100.0 * (kestrel_mrp_inr - ?) / kestrel_mrp_inr
            WHERE city = ? AND sku_code = ? AND week = ?
            """,
            (median, median, city, sku_code, week),
        )
    dst.commit()

    n = dst.execute("SELECT COUNT(*) FROM mart_price_position").fetchone()[0]
    print(f"  inserted {n} rows into mart_price_position")


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    rows = dst.execute(
        """
        SELECT week, kestrel_mrp_inr, competitor_price_median_inr, gap_pct
        FROM mart_price_position WHERE sku_code = 'SKU00074' AND city = 'Bengaluru'
        ORDER BY week
        """
    ).fetchall()
    check("golden path: SKU00074 (Kestrel Sel. Rusk 400G) has rows in mart_price_position", len(rows) > 0, f"got {len(rows)} rows")
    if rows:
        week, mrp, comp_price, gap_pct = rows[0]
        sane = mrp == 245.0 and comp_price is not None and gap_pct is not None and -100 < gap_pct < 100
        check(
            f"golden path {week}: gap_pct computed against Kestrel's actual MRP (245.0), sane value",
            sane,
            f"mrp={mrp} competitor_median={comp_price} gap_pct={gap_pct:.2f}",
        )

    n = dst.execute("SELECT COUNT(DISTINCT city) FROM mart_price_position").fetchone()[0]
    cities = [r[0] for r in dst.execute("SELECT DISTINCT city FROM mart_price_position").fetchall()]
    check(f"mart_price_position has exactly {EXPECTED_CITY_COUNT} distinct cities", n == EXPECTED_CITY_COUNT, f"got {sorted(cities)}")

    n = dst.execute("SELECT COUNT(*) FROM mart_price_position WHERE gap_pct IS NULL OR competitor_price_median_inr IS NULL").fetchone()[0]
    check("zero rows with unfilled median/gap_pct", n == 0, f"got {n}")

    n = dst.execute("SELECT COUNT(*) FROM mart_price_position WHERE competitor_mrp_inr IS NULL").fetchone()[0]
    check("zero rows with unfilled competitor_mrp_inr", n == 0, f"got {n}")

    n = dst.execute(
        "SELECT COUNT(*) FROM mart_price_position WHERE competitor_mrp_inr = competitor_price_median_inr"
    ).fetchone()[0]
    check(
        "competitor_mrp_inr is a distinct field from competitor_price_median_inr (not silently equal everywhere)",
        n < dst.execute("SELECT COUNT(*) FROM mart_price_position").fetchone()[0],
        f"{n} rows happen to match exactly",
    )


def main() -> int:
    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    for table in ("bridge_bazaarpulse_sku_match", "dim_products", "raw_bazaarpulse_products", "raw_bazaarpulse_price_history"):
        exists = dst.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0]
        if not exists:
            print(f"ERROR: {table} not found in {ANALYTICS_DB_PATH} — run its build script first.")
            return 1

    try:
        print(f"Building mart_price_position -> {ANALYTICS_DB_PATH}")
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
