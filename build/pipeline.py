#!/usr/bin/env python3
"""Orchestrates the full data/analytics.db build: dims -> facts -> external ingestion -> marts.

Run: python build/pipeline.py  (or `make build`)

Idempotent: every step drops-and-rebuilds its own table(s), so re-running
against the same data/kestrel_ops.db — and, for the two external sources,
the same live mock services plus the resumable data/raw_cache/ — produces
identical output.

Fails loudly and stops at the first failing step: a build/assertions.py
regression (the source data has drifted from what every downstream script
assumes, so nothing after this point should run against it) or any
individual build script's own acceptance checks failing (each script
already exits non-zero on a failed check; the runner never overrides that,
it just reports which step failed).
"""

import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from build.assertions import run_all as run_source_assertions
from config.settings import SOURCE_DB_PATH

# Dependency order: dims -> facts -> external ingestion (freight then
# BazaarPulse, each internally sequential) -> marts (which read from both
# facts and external tables).
STEPS = [
    ("dim_outlets", "build/dims/build_dim_outlets.py"),
    ("dim_products", "build/dims/build_dim_products.py"),
    ("dim_warehouses/dim_routes/dim_regions", "build/dims/build_dim_warehouses_routes_regions.py"),
    ("dim_date", "build/dims/build_dim_date.py"),
    ("fact_orders/fact_order_lines", "build/facts/build_fact_orders_and_lines.py"),
    ("fact_deliveries", "build/facts/build_fact_deliveries.py"),
    ("fact_inventory_snapshots", "build/facts/build_fact_inventory_snapshots.py"),
    ("fact_returns", "build/facts/build_fact_returns.py"),
    ("dim_carriers + fuel_surcharge_reference", "build/external/build_dim_carriers.py"),
    ("raw_freight_invoices ingest", "build/external/ingest_freight_invoices.py"),
    ("fact_freight", "build/external/build_fact_freight.py"),
    ("BazaarPulse crawl", "build/external/scrape_bazaarpulse.py"),
    ("BazaarPulse parse", "build/external/parse_bazaarpulse.py"),
    ("BazaarPulse SKU match", "build/external/match_bazaarpulse_skus.py"),
    ("mart_service", "build/marts/build_mart_service.py"),
    ("mart_coldchain", "build/marts/build_mart_coldchain.py"),
    ("mart_money", "build/marts/build_mart_money.py"),
    ("mart_price_position", "build/marts/build_mart_price_position.py"),
]


def run_source_regression_guard() -> None:
    print("== source-data regression guard (build/assertions.py) ==")
    if not SOURCE_DB_PATH.exists():
        print(f"ERROR: source DB not found at {SOURCE_DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(f"file:{SOURCE_DB_PATH}?mode=ro", uri=True)
    try:
        failures = run_source_assertions(conn)
    finally:
        conn.close()

    if failures:
        print(f"FAILED: {len(failures)} profiling assertion(s) regressed against {SOURCE_DB_PATH}:")
        for f in failures:
            print(f"  - {f}")
        print("\nEvery downstream build script assumes these hold — stopping before touching analytics.db.")
        sys.exit(1)

    print("  all guards hold\n")


def run_step(label: str, script: str) -> None:
    script_path = REPO_ROOT / script
    print(f"== {label} ({script}) ==")
    start = time.monotonic()
    result = subprocess.run([sys.executable, str(script_path)], cwd=REPO_ROOT)
    elapsed = time.monotonic() - start
    if result.returncode != 0:
        print(f"\nFAILED: {label} exited {result.returncode} after {elapsed:.1f}s ({script})")
        sys.exit(result.returncode)
    print(f"  done in {elapsed:.1f}s\n")


def main() -> int:
    pipeline_start = time.monotonic()
    run_source_regression_guard()
    for label, script in STEPS:
        run_step(label, script)

    print(f"Build complete in {time.monotonic() - pipeline_start:.1f}s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
