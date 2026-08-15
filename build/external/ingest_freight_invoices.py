#!/usr/bin/env python3
"""Resumable cursor-walk ingest of GET /v1/freight_invoices.

Run: python build/external/ingest_freight_invoices.py
(requires the partner API mock server running on :8088)

Cursor-walks limit=200 pages until next_cursor is JSON null, always
passing back exactly the cursor string the server returned (format is an
opaque raw-offset token like "cur_200" — never reconstructed locally).

Persists two things under data/raw_cache/freight_invoices/ so a crash
mid-walk can resume instead of restarting:
  - pages/page_{offset:08d}.json — the raw page response, one file per
    fetched page.
  - checkpoint.jsonl — one append-only line per successfully fetched
    page: {offset, next_cursor, page_size}. On startup, lines are read
    until the first JSON-decode failure (a partial line from a crash
    mid-write) and everything after that point is discarded — the walk
    resumes from the last fully-written record's next_cursor. Since the
    underlying generator is deterministic (MD5-seeded), re-fetching any
    page after a crash reproduces byte-identical data, so this is safe
    even if a page was re-fetched.

After the network walk, raw_freight_invoices in data/analytics.db is
rebuilt from ALL cached page files (not just this run's), deduped on
invoice_id as a safety net regardless of the above. amount (paise) is
converted to amount_inr (/100); created_at_utc (always UTC per the
server's docstring) is converted to created_at_ist (+5:30) — the
operational DB's timezone.

detention_charge is NOT converted — only `amount` is documented as
paise; detention_charge's unit is not specified anywhere, so it's kept
as the server returns it rather than guessed at.

Idempotent: re-running with a complete checkpoint skips the network walk
and just rebuilds the table from cache.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from build.external.freight_client import FreightAPIClient
from config.settings import ANALYTICS_DB_PATH, RAW_CACHE_DIR

import sqlite3

FREIGHT_CACHE_DIR = RAW_CACHE_DIR / "freight_invoices"
PAGES_DIR = FREIGHT_CACHE_DIR / "pages"
CHECKPOINT_PATH = FREIGHT_CACHE_DIR / "checkpoint.jsonl"

IST_OFFSET = timedelta(hours=5, minutes=30)
EXPECTED_TOTAL_INVOICES = 41_500

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def offset_of_cursor(cursor: str | None) -> int:
    return 0 if cursor is None else int(cursor.split("_")[-1])


def read_checkpoint() -> list[dict]:
    if not CHECKPOINT_PATH.exists():
        return []
    records = []
    with open(CHECKPOINT_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # Partial line from a crash mid-write — stop here, discard the rest.
                break
    return records


def append_checkpoint(record: dict) -> None:
    FREIGHT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def save_page(offset: int, page: dict) -> None:
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    (PAGES_DIR / f"page_{offset:08d}.json").write_text(json.dumps(page))


def cursor_walk(client: FreightAPIClient) -> None:
    records = read_checkpoint()
    if records:
        last = max(records, key=lambda r: r["offset"])
        cursor = last["next_cursor"]
        if cursor is None:
            print("  checkpoint shows walk already complete — skipping network walk")
            return
        print(f"  resuming walk from checkpoint: next cursor={cursor!r} ({len(records)} pages already cached)")
    else:
        cursor = None
        print("  starting fresh walk from offset 0")

    while True:
        offset = offset_of_cursor(cursor)
        page = client.freight_invoices(cursor=cursor, limit=200)
        save_page(offset, page)
        next_cursor = page["next_cursor"]
        append_checkpoint({"offset": offset, "next_cursor": next_cursor, "page_size": page["page_size"]})
        print(f"  fetched offset={offset} page_size={page['page_size']} next_cursor={next_cursor!r}")
        if next_cursor is None:
            break
        cursor = next_cursor


def load_raw_freight_invoices(dst: sqlite3.Connection) -> int:
    by_invoice_id: dict[str, dict] = {}
    for path in sorted(PAGES_DIR.glob("page_*.json")):
        page = json.loads(path.read_text())
        for inv in page["data"]:
            by_invoice_id[inv["invoice_id"]] = inv  # dedupe safety net; generator is deterministic so any copy is identical

    dst.execute("DROP TABLE IF EXISTS raw_freight_invoices")
    dst.execute(
        """
        CREATE TABLE raw_freight_invoices (
            invoice_id TEXT PRIMARY KEY,
            carrier_id TEXT,
            carrier_name TEXT,
            warehouse_code TEXT,
            route_code TEXT,
            invoice_date TEXT,
            service_date TEXT,
            amount_paise INTEGER,
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

    values = []
    for inv in by_invoice_id.values():
        created_utc = datetime.strptime(inv["created_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
        created_ist = created_utc + IST_OFFSET
        values.append(
            (
                inv["invoice_id"],
                inv["carrier_id"],
                inv["carrier_name"],
                inv["warehouse_code"],
                inv["route_code"],
                inv["invoice_date"],
                inv["service_date"],
                inv["amount"],
                round(inv["amount"] / 100, 2),
                inv["currency"],
                inv["fuel_surcharge_pct"],
                inv["detention_charge"],
                inv["distance_km"],
                inv["weight_kg"],
                1 if inv["temperature_controlled"] else 0,
                inv["status"],
                inv["created_at_utc"],
                created_ist.strftime("%Y-%m-%d %H:%M:%S"),
            )
        )

    dst.executemany(
        "INSERT INTO raw_freight_invoices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        values,
    )
    dst.commit()
    print(f"  loaded {len(values)} deduped rows into raw_freight_invoices (from {len(by_invoice_id)} cached invoices)")
    return len(values)


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    count = dst.execute("SELECT COUNT(*) FROM raw_freight_invoices").fetchone()[0]
    check(f"raw_freight_invoices COUNT(*) == {EXPECTED_TOTAL_INVOICES}", count == EXPECTED_TOTAL_INVOICES, f"got {count}")

    dupes = dst.execute(
        "SELECT COUNT(*) FROM (SELECT invoice_id, COUNT(*) c FROM raw_freight_invoices GROUP BY invoice_id HAVING c > 1)"
    ).fetchone()[0]
    check("zero duplicate invoice_id rows", dupes == 0, f"got {dupes}")

    row = dst.execute(
        "SELECT invoice_id, amount_paise, amount_inr, created_at_utc, created_at_ist FROM raw_freight_invoices LIMIT 1"
    ).fetchone()
    expected_inr = round(row[1] / 100, 2)
    check(
        f"spot-check {row[0]}: amount_inr == amount_paise / 100",
        row[2] == expected_inr,
        f"paise={row[1]} amount_inr={row[2]} expected={expected_inr}",
    )
    utc_dt = datetime.strptime(row[3], "%Y-%m-%dT%H:%M:%SZ")
    ist_dt = datetime.strptime(row[4], "%Y-%m-%d %H:%M:%S")
    check(
        f"spot-check {row[0]}: created_at_ist is UTC+5:30 from created_at_utc",
        ist_dt - utc_dt == IST_OFFSET,
        f"utc={row[3]} ist={row[4]} delta={ist_dt - utc_dt}",
    )


def main() -> int:
    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    with FreightAPIClient() as client:
        try:
            client.health()
        except Exception as e:
            print(f"ERROR: partner API not reachable at {client.base_url} — {e}")
            return 1

        try:
            print("Cursor-walking /v1/freight_invoices ...")
            cursor_walk(client)
            print(f"\nLoading raw_freight_invoices -> {ANALYTICS_DB_PATH}")
            load_raw_freight_invoices(dst)
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
