#!/usr/bin/env python3
"""Fuzzy-match BazaarPulse listings to Kestrel SKUs.

Run: python build/external/match_bazaarpulse_skus.py

Both sides are normalized before comparison: lowercase, strip
retailer/marketing tokens ("Combo", "Pack of N", "(New)", "| Best Before
6M", "- Family Pack"), expand abbreviations that would otherwise tank a
token-based score ("Sel." -> "Select", "Inst." -> "Instant"), and strip
pack-size digits out of the name text (pack size is compared
separately, as its own gate — see below). Punctuation stripped, then
whitespace-collapsed.

Name similarity is the max of rapidfuzz's token_sort_ratio (handles
word-order/marketing-noise differences) and a plain character ratio on
the space-collapsed strings (handles "AmritValley" vs "Amrit Valley" —
a real gap found in this data: token-based scoring alone treats a
missing space as a token-count mismatch and scores it ~63, when the
strings are actually a 1-character edit apart).

Pack size agreement is a HARD GATE, not just a score component: a name
match against the wrong pack size is actively dangerous downstream
(mart_price_position compares MRP/price gaps, which are meaningless
across different pack sizes), so a candidate is only eligible to match
at all if its (value, uom) agrees exactly with the listing's parsed
pack size. Pack size is read from the structured pack_size_text column
(from build/external/parse_bazaarpulse.py) when present; title-text
parsing is a fallback for if that's ever missing (never triggers in
this snapshot, see fact_returns' identical pattern for case_pack).

Confidence threshold (NAME_MATCH_THRESHOLD, 90) is applied to the name
score of the best PACK-MATCHING candidate only. Below it — or if no
candidate shares the listing's exact pack size at all — the listing
gets sku_code=NULL but is still written to the bridge table with its
best candidate and score recorded, never silently dropped.

**Finding surfaced by this task, not a bug in the matcher**: after the
normalization above, literally 100% of the 1,134 BazaarPulse listings
have a pack-matching dim_products candidate scoring >=95 (empirical
floor across the whole table). dim_products' `brand` column has 6
values (Kestrel + Bluepeak/Hillfare/Coastline/Amrit/Marwar) — all 6 are
Kestrel's own multi-brand portfolio (see products.supplier_name), not
external competitors. So every BazaarPulse listing, regardless of which
of those 6 brands it shows, is tracking one of Kestrel's OWN SKUs sold
through a different retailer — this is an MAP/retail-price-variance
monitor, not real inter-company competitor pricing. Reframes what
"competitor observed price" in mart_price_position actually
means; see DECISIONS.md.
"""

import re
import sqlite3
import sys
from pathlib import Path

from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import ANALYTICS_DB_PATH

NAME_MATCH_THRESHOLD = 90.0

MARKETING_NOISE_RES = [
    re.compile(r"\bcombo\b"),
    re.compile(r"\bpack of \d+\b"),
    re.compile(r"\(new\)"),
    re.compile(r"\|\s*best before \d+m\b"),
    re.compile(r"-?\s*family pack\b"),
]
ABBREVIATIONS = [
    (re.compile(r"\bsel\.?\b"), "select"),
    (re.compile(r"\binst\.?\b"), "instant"),
]
PACK_SIZE_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:ml|g|kg|l)\b")
NON_WORD_RE = re.compile(r"[^\w\s]")
WHITESPACE_RE = re.compile(r"\s+")
PACK_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ml|g|kg|l)\b", re.IGNORECASE)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def normalize_name(text: str) -> str:
    t = text.lower()
    for pattern in MARKETING_NOISE_RES:
        t = pattern.sub(" ", t)
    for pattern, replacement in ABBREVIATIONS:
        t = pattern.sub(replacement, t)
    t = PACK_SIZE_TOKEN_RE.sub(" ", t)
    t = NON_WORD_RE.sub(" ", t)
    return WHITESPACE_RE.sub(" ", t).strip()


def name_similarity(a: str, b: str) -> float:
    token_sort = fuzz.token_sort_ratio(a, b)
    compact = fuzz.ratio(a.replace(" ", ""), b.replace(" ", ""))
    return max(token_sort, compact)


def parse_pack_size(pack_size_text: str | None, title_fallback: str) -> tuple[float, str] | None:
    for source in (pack_size_text, title_fallback):
        if not source:
            continue
        m = PACK_SIZE_RE.search(source)
        if m:
            return float(m.group(1)), m.group(2).upper()
    return None


def load_dim_candidates(dst: sqlite3.Connection) -> list[tuple[str, str, str, tuple[float, str]]]:
    rows = dst.execute("SELECT sku_code, product_name, pack_size_value, pack_size_uom FROM dim_products").fetchall()
    return [(sku, name, normalize_name(name), (pack_value, uom)) for sku, name, pack_value, uom in rows]


def match_one(
    bp_norm_name: str,
    bp_pack: tuple[float, str] | None,
    candidates: list[tuple[str, str, str, tuple[float, str]]],
) -> dict:
    best_pack_ok = None  # (name_score, sku_code, product_name)
    for sku, product_name, dp_norm_name, dp_pack in candidates:
        if bp_pack is None or dp_pack != bp_pack:
            continue
        score = name_similarity(bp_norm_name, dp_norm_name)
        if best_pack_ok is None or score > best_pack_ok[0]:
            best_pack_ok = (score, sku, product_name)

    if best_pack_ok is None:
        return {
            "sku_code": None,
            "matched_product_name": None,
            "match_score": None,
            "pack_size_agreement": 0,
            "match_method": "unmatched_no_pack_candidate",
        }

    score, sku, product_name = best_pack_ok
    if score >= NAME_MATCH_THRESHOLD:
        return {
            "sku_code": sku,
            "matched_product_name": product_name,
            "match_score": score,
            "pack_size_agreement": 1,
            "match_method": "matched",
        }
    return {
        "sku_code": None,
        "matched_product_name": product_name,
        "match_score": score,
        "pack_size_agreement": 1,
        "match_method": "unmatched_below_threshold",
    }


def build(dst: sqlite3.Connection) -> None:
    candidates = load_dim_candidates(dst)
    bp_rows = dst.execute("SELECT product_id, title, pack_size_text FROM raw_bazaarpulse_products").fetchall()

    dst.execute("DROP TABLE IF EXISTS bridge_bazaarpulse_sku_match")
    dst.execute(
        """
        CREATE TABLE bridge_bazaarpulse_sku_match (
            product_id TEXT PRIMARY KEY,
            sku_code TEXT,
            matched_product_name TEXT,
            match_score REAL,
            pack_size_agreement INTEGER,
            match_method TEXT
        )
        """
    )

    values = []
    for product_id, title, pack_size_text in bp_rows:
        bp_norm = normalize_name(title)
        bp_pack = parse_pack_size(pack_size_text, title)
        result = match_one(bp_norm, bp_pack, candidates)
        values.append(
            (
                product_id,
                result["sku_code"],
                result["matched_product_name"],
                result["match_score"],
                result["pack_size_agreement"],
                result["match_method"],
            )
        )

    dst.executemany("INSERT INTO bridge_bazaarpulse_sku_match VALUES (?, ?, ?, ?, ?, ?)", values)
    dst.commit()
    print(f"  inserted {len(values)} rows into bridge_bazaarpulse_sku_match")


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    row = dst.execute(
        "SELECT sku_code, matched_product_name, match_score FROM bridge_bazaarpulse_sku_match WHERE product_id = '297'"
    ).fetchone()
    check(
        "golden path: product/297.html ('Kestrel Sel. Rusk 400G') matches a Kestrel rusk SKU with high confidence",
        row is not None and row[0] is not None and row[0].startswith("SKU") and "Rusk" in (row[1] or "") and row[2] >= NAME_MATCH_THRESHOLD,
        f"got sku={row[0] if row else None} name={row[1] if row else None} score={row[2] if row else None}",
    )

    total = dst.execute("SELECT COUNT(*) FROM bridge_bazaarpulse_sku_match").fetchone()[0]
    matched = dst.execute("SELECT COUNT(*) FROM bridge_bazaarpulse_sku_match WHERE sku_code IS NOT NULL").fetchone()[0]
    unmatched = total - matched
    check("bridge_bazaarpulse_sku_match has 1 row per raw_bazaarpulse_products row", total == 1134, f"got {total}")

    match_rate = 100 * matched / total
    print(f"\n  MATCH RATE: {matched}/{total} matched ({match_rate:.1f}%), {unmatched}/{total} unmatched ({100 - match_rate:.1f}%)")
    method_counts = dst.execute(
        "SELECT match_method, COUNT(*) FROM bridge_bazaarpulse_sku_match GROUP BY match_method"
    ).fetchall()
    for method, count in method_counts:
        print(f"    {method}: {count}")

    n = dst.execute(
        "SELECT COUNT(*) FROM bridge_bazaarpulse_sku_match WHERE sku_code IS NOT NULL AND match_score < ?",
        (NAME_MATCH_THRESHOLD,),
    ).fetchone()[0]
    check("zero matched rows below the confidence threshold", n == 0, f"got {n}")

    n = dst.execute(
        "SELECT COUNT(*) FROM bridge_bazaarpulse_sku_match WHERE sku_code IS NULL AND match_score IS NULL AND match_method != 'unmatched_no_pack_candidate'"
    ).fetchone()[0]
    check("every unmatched row still records a candidate score (never silently dropped)", n == 0, f"got {n}")


def main() -> int:
    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    for table in ("raw_bazaarpulse_products", "dim_products"):
        exists = dst.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0]
        if not exists:
            print(f"ERROR: {table} not found in {ANALYTICS_DB_PATH} — run its build script first.")
            return 1

    try:
        print(f"Building bridge_bazaarpulse_sku_match -> {ANALYTICS_DB_PATH}")
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
