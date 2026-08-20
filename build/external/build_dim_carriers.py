#!/usr/bin/env python3
"""Build dim_carriers and fuel_surcharge_reference in data/analytics.db.

Run: python build/external/build_dim_carriers.py
(requires the partner API mock server running on :8088)

dim_carriers has no source-DB equivalent — GET /v1/carriers is the only
source (5 carriers, not paginated). fuel_surcharge_reference is pulled
one GET /v1/fuel_surcharge?month=YYYY-MM call per month across the data
window (Jan 2025 - Jun 2026, 18 months). Neither endpoint is chaos-prone
(no 429/503 injected), so this script's own calls should never exercise
the freight_client retry path in practice — that path exists for the
freight invoices ingest's cursor-walk of /v1/freight_invoices, which
does see chaos.

`regions` (a list in the API response) is stored as a comma-separated
string — sqlite has no array type and nothing downstream needs to filter
within it.

Idempotent: re-running drops and rebuilds both tables.
"""

import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from build.external.freight_client import FreightAPIClient
from config.settings import ANALYTICS_DB_PATH

DATA_WINDOW_START = date(2025, 1, 1)
DATA_WINDOW_END = date(2026, 6, 30)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def months_in_window(start: date, end: date) -> list[str]:
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def build_dim_carriers(client: FreightAPIClient, dst: sqlite3.Connection) -> None:
    carriers = client.carriers()

    dst.execute("DROP TABLE IF EXISTS dim_carriers")
    dst.execute(
        """
        CREATE TABLE dim_carriers (
            carrier_id TEXT PRIMARY KEY,
            name TEXT,
            mode TEXT,
            reefer_capable INTEGER,
            sla_hours INTEGER,
            regions TEXT
        )
        """
    )
    dst.executemany(
        "INSERT INTO dim_carriers VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                c["carrier_id"],
                c["name"],
                c["mode"],
                1 if c["reefer_capable"] else 0,
                c["sla_hours"],
                ",".join(c["regions"]),
            )
            for c in carriers
        ],
    )
    dst.commit()
    print(f"  inserted {len(carriers)} rows into dim_carriers")


def build_fuel_surcharge_reference(client: FreightAPIClient, dst: sqlite3.Connection) -> None:
    months = months_in_window(DATA_WINDOW_START, DATA_WINDOW_END)

    dst.execute("DROP TABLE IF EXISTS fuel_surcharge_reference")
    dst.execute(
        """
        CREATE TABLE fuel_surcharge_reference (
            month TEXT PRIMARY KEY,
            surcharge_pct REAL,
            diesel_index REAL,
            source TEXT
        )
        """
    )
    values = []
    for month in months:
        resp = client.fuel_surcharge(month)
        values.append((resp["month"], resp["surcharge_pct"], resp["diesel_index"], resp["source"]))
    dst.executemany("INSERT INTO fuel_surcharge_reference VALUES (?, ?, ?, ?)", values)
    dst.commit()
    print(f"  inserted {len(values)} rows into fuel_surcharge_reference ({months[0]}..{months[-1]})")


def verify(client: FreightAPIClient, dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    count = dst.execute("SELECT COUNT(*) FROM dim_carriers").fetchone()[0]
    check("dim_carriers COUNT(*) == 5", count == 5, f"got {count}")

    carrier_ids = {r[0] for r in dst.execute("SELECT carrier_id FROM dim_carriers")}
    expected_ids = {f"CR-10{n}" for n in range(1, 6)}
    check(
        "dim_carriers carrier_id set == CR-101..CR-105",
        carrier_ids == expected_ids,
        f"got {sorted(carrier_ids)}",
    )

    fs_count = dst.execute("SELECT COUNT(*) FROM fuel_surcharge_reference").fetchone()[0]
    check("fuel_surcharge_reference has 18 months", fs_count == 18, f"got {fs_count}")

    # 10 runs against the live server, zero unhandled exceptions.
    run_errors = 0
    for i in range(10):
        try:
            client.health()
            client.carriers()
            client.fuel_surcharge("2025-06")
        except Exception as e:  # noqa: BLE001 — this check IS "did anything raise"
            run_errors += 1
            print(f"    run {i + 1}: exception {e!r}")
    check("10 client runs against live server, zero unhandled exceptions", run_errors == 0, f"{run_errors} failed")


def main() -> int:
    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    with FreightAPIClient() as client:
        try:
            health = client.health()
        except Exception as e:
            print(f"ERROR: partner API not reachable at {client.base_url} — {e}")
            return 1
        print(f"Partner API reachable: {health}")

        try:
            print(f"Building dim_carriers/fuel_surcharge_reference -> {ANALYTICS_DB_PATH}")
            build_dim_carriers(client, dst)
            build_fuel_surcharge_reference(client, dst)
            verify(client, dst)
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
