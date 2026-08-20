#!/usr/bin/env python3
"""BazaarPulse parser — per-city price extraction + weekly history.

Run: python build/external/parse_bazaarpulse.py
(requires the mock site served on :8080; reads the discovered URL list
from build/external/scrape_bazaarpulse.py)

The site uses 4 different price markups, one per city, and dispatch is
done structurally (which markup is actually present on the page) rather
than by trusting the page's own "City: X" text label:
  - Mumbai:    <span class="price">&#8377;267.74</span> — plain text.
  - Bengaluru: <span class="pricing-block" data-price-paise="19731"
               data-currency="INR">Price on card</span> — the VISIBLE
               text is a decoy; the real price is only in the
               data-price-paise attribute (paise, /100 to INR).
  - Chennai:   <b class="sellingPrice">INR 229.86</b> — INR-prefixed
               text, bold tag not span.
  - Delhi:     <div class="amt"><em>Rs.</em> 88.68 <small>incl.
               taxes</small></div> — the number is a bare text node
               between two child tags; extracted from the div's direct
               NavigableString children only (not a naive
               .get_text() that would just concatenate the parent and
               children's text — which happens to work here too since
               the source already has literal whitespace around the
               number, but pulling the direct text node explicitly is
               the version that's actually correct if that source
               formatting ever changes).

competitor_mrp_inr is the competitor's OWN "MRP" field shown on the
card — explicitly not Kestrel's own dim_products.mrp_inr, hence the
verbose column name (never join price_position downstream by assuming
these are interchangeable).

last_seen_date isn't present on the product detail page itself — it's
derived as the most recent (first) row of "Observed price history",
which was spot-checked to match the listing page's own "Last seen:"
value exactly (e.g. product 297: listing says "Last seen: 2026-06-13",
history's top row is 2026-06-13).

"Observed price history" is always in plain rupee-entity format
regardless of city and is the cleaner series for trend/comparison
(vs. the noisy, differently-marked-up "current price" line) —
stored as a child table, raw_bazaarpulse_price_history.

3 of the 1,137 URLs discovered by the crawl step 404 (dead links in the listing
pages, confirmed not a crawl bug — see DECISIONS.md) — skipped with a
warning, not treated as a parse failure.

Product pages are cached under data/raw_cache/bazaarpulse/product_pages/
on first fetch (crawl-delay 1s is only paid once per page, ever) so
re-running this script after the first full run is fast and doesn't
re-hit the network.

Idempotent: re-running drops and rebuilds both tables from the (cached
or freshly fetched) HTML.
"""

import re
import sqlite3
import sys
from pathlib import Path

from bs4 import BeautifulSoup
from bs4.element import NavigableString

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from build.external.scrape_bazaarpulse import Crawler, fetch_robots
from config.settings import ANALYTICS_DB_PATH, RAW_CACHE_DIR

import httpx

DISCOVERED_URLS_PATH = RAW_CACHE_DIR / "bazaarpulse" / "discovered_product_urls.txt"
PRODUCT_PAGE_CACHE_DIR = RAW_CACHE_DIR / "bazaarpulse" / "product_pages"

PRICE_NUMBER_RE = re.compile(r"[\d,]+(?:\.\d+)?")
MUTED_LINE0_RE = re.compile(r"Retailer:\s*(.+?)\s*·\s*City:\s*(.+?)\s*·\s*Pack:\s*(.+)$")
MUTED_LINE1_RE = re.compile(r"MRP\s*₹\s*([\d,]+(?:\.\d+)?)\s*·\s*(.+)$")

# BazaarPulse's own city label -> canonical city, for dispatch/storage
# only (separate from data/ref/city_name_map.csv, which is Kestrel's
# outlet-city mapping and unrelated to this site's labels).
BAZAARPULSE_CITY_MAP = {"Delhi NCR": "Delhi"}

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def parse_price_number(text: str) -> float:
    m = PRICE_NUMBER_RE.search(text)
    if not m:
        raise ValueError(f"no numeric price found in: {text!r}")
    return float(m.group().replace(",", ""))


def extract_current_price(card) -> tuple[float, str]:
    el = card.find("span", class_="price")
    if el is not None:
        return parse_price_number(el.get_text()), "mumbai_plain_text"

    el = card.find("span", class_="pricing-block")
    if el is not None:
        paise = int(el["data-price-paise"])
        return round(paise / 100, 2), "bengaluru_data_attribute"

    el = card.find("b", class_="sellingPrice")
    if el is not None:
        return parse_price_number(el.get_text()), "chennai_prefixed_text"

    el = card.find("div", class_="amt")
    if el is not None:
        direct_text = "".join(str(c) for c in el.contents if isinstance(c, NavigableString))
        return parse_price_number(direct_text), "delhi_split_text_node"

    raise ValueError("no recognized price markup found on card")


def extract_price_history(card) -> list[tuple[str, float]]:
    heading = card.find("h3", string="Observed price history")
    table = heading.find_next("table")
    rows = []
    for tr in table.find_all("tr")[1:]:  # skip header row
        tds = tr.find_all("td")
        date_text = tds[0].get_text(strip=True)
        price = parse_price_number(tds[1].get_text())
        rows.append((date_text, price))
    return rows


def parse_product_page(product_id: str, url: str, html: str) -> tuple[dict, list[tuple[str, float]]]:
    soup = BeautifulSoup(html, "lxml")
    card = soup.find("div", class_="card")

    title = card.find("h2").get_text(strip=True)

    muted_ps = card.find_all("p", class_="muted")
    retailer, city_raw, pack_size_text = MUTED_LINE0_RE.match(muted_ps[0].get_text()).groups()
    mrp_text, stock_status = MUTED_LINE1_RE.match(muted_ps[1].get_text()).groups()
    competitor_mrp_inr = float(mrp_text.replace(",", ""))

    price_inr, price_extraction_method = extract_current_price(card)
    history = extract_price_history(card)
    last_seen_date = history[0][0] if history else None

    city = BAZAARPULSE_CITY_MAP.get(city_raw, city_raw)

    product = {
        "product_id": product_id,
        "product_url": url,
        "title": title,
        "retailer": retailer,
        "city_raw": city_raw,
        "city": city,
        "pack_size_text": pack_size_text,
        "price_inr": price_inr,
        "price_extraction_method": price_extraction_method,
        "competitor_mrp_inr": competitor_mrp_inr,
        "in_stock_status": stock_status,
        "last_seen_date": last_seen_date,
    }
    return product, history


def load_discovered_urls() -> list[str]:
    return [line.strip() for line in DISCOVERED_URLS_PATH.read_text().splitlines() if line.strip()]


def fetch_cached_or_live(crawler: Crawler, path: str) -> str | None:
    product_id = path.split("/")[-1].removesuffix(".html")
    cache_path = PRODUCT_PAGE_CACHE_DIR / f"{product_id}.html"
    if cache_path.exists():
        return cache_path.read_text()

    resp = crawler.get(path)
    if resp is None:
        return None
    PRODUCT_PAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(resp.text)
    return resp.text


def build(crawler: Crawler, dst: sqlite3.Connection) -> tuple[int, int]:
    urls = load_discovered_urls()
    print(f"  {len(urls)} URLs to parse (cached pages under {PRODUCT_PAGE_CACHE_DIR} are reused, not re-fetched)")

    products = []
    history_rows = []
    skipped_404 = 0

    for i, path in enumerate(urls):
        product_id = path.split("/")[-1].removesuffix(".html")
        html = fetch_cached_or_live(crawler, path)
        if html is None:
            print(f"  [{i + 1}/{len(urls)}] {path} -> 404, skipping")
            skipped_404 += 1
            continue
        product, history = parse_product_page(product_id, path, html)
        products.append(product)
        for observed_date, price in history:
            history_rows.append((product_id, observed_date, price))
        if (i + 1) % 100 == 0:
            print(f"  [{i + 1}/{len(urls)}] parsed...")

    dst.execute("DROP TABLE IF EXISTS raw_bazaarpulse_products")
    dst.execute(
        """
        CREATE TABLE raw_bazaarpulse_products (
            product_id TEXT PRIMARY KEY,
            product_url TEXT,
            title TEXT,
            retailer TEXT,
            city_raw TEXT,
            city TEXT,
            pack_size_text TEXT,
            price_inr REAL,
            price_extraction_method TEXT,
            competitor_mrp_inr REAL,
            in_stock_status TEXT,
            last_seen_date TEXT
        )
        """
    )
    dst.executemany(
        """
        INSERT INTO raw_bazaarpulse_products VALUES
        (:product_id, :product_url, :title, :retailer, :city_raw, :city,
         :pack_size_text, :price_inr, :price_extraction_method,
         :competitor_mrp_inr, :in_stock_status, :last_seen_date)
        """,
        products,
    )

    dst.execute("DROP TABLE IF EXISTS raw_bazaarpulse_price_history")
    dst.execute(
        """
        CREATE TABLE raw_bazaarpulse_price_history (
            product_id TEXT,
            observed_date TEXT,
            price_inr REAL,
            FOREIGN KEY (product_id) REFERENCES raw_bazaarpulse_products(product_id)
        )
        """
    )
    dst.executemany("INSERT INTO raw_bazaarpulse_price_history VALUES (?, ?, ?)", history_rows)

    dst.commit()
    print(f"  inserted {len(products)} rows into raw_bazaarpulse_products ({skipped_404} 404s skipped)")
    print(f"  inserted {len(history_rows)} rows into raw_bazaarpulse_price_history")
    return len(products), skipped_404


def verify(dst: sqlite3.Connection) -> None:
    print("\n== acceptance checks ==")

    row = dst.execute("SELECT price_inr FROM raw_bazaarpulse_products WHERE product_id = '1'").fetchone()
    check("product/1.html (Mumbai) price_inr == 267.74", row is not None and row[0] == 267.74, f"got {row}")

    row = dst.execute(
        "SELECT price_inr, price_extraction_method FROM raw_bazaarpulse_products WHERE product_id = '297'"
    ).fetchone()
    check(
        "product/297.html (Bengaluru, Kestrel Rusk) price_inr == 197.31 via data-price-paise",
        row is not None and row[0] == 197.31 and row[1] == "bengaluru_data_attribute",
        f"got {row}",
    )

    row = dst.execute("SELECT price_inr FROM raw_bazaarpulse_products WHERE product_id = '845'").fetchone()
    check("Chennai sample (product/845.html) parses to a numeric float", row is not None and isinstance(row[0], float), f"got {row}")

    row = dst.execute("SELECT price_inr FROM raw_bazaarpulse_products WHERE product_id = '589'").fetchone()
    check("Delhi sample (product/589.html) price_inr == 88.68", row is not None and row[0] == 88.68, f"got {row}")

    n = dst.execute("SELECT COUNT(*) FROM raw_bazaarpulse_products WHERE price_inr IS NULL").fetchone()[0]
    check("zero null price_inr rows", n == 0, f"got {n}")

    bad_history_counts = dst.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT product_id, COUNT(*) c FROM raw_bazaarpulse_price_history
            GROUP BY product_id HAVING c != 6
        )
        """
    ).fetchone()[0]
    check("every product has exactly 6 price-history rows", bad_history_counts == 0, f"{bad_history_counts} products with != 6 rows")

    method_counts = dst.execute(
        "SELECT price_extraction_method, COUNT(*) FROM raw_bazaarpulse_products GROUP BY price_extraction_method"
    ).fetchall()
    check("all 4 city markups represented", len(method_counts) == 4, f"got {method_counts}")


def main() -> int:
    if not DISCOVERED_URLS_PATH.exists():
        print(f"ERROR: {DISCOVERED_URLS_PATH} not found — run build/external/scrape_bazaarpulse.py first.")
        return 1

    dst = sqlite3.connect(ANALYTICS_DB_PATH)

    with httpx.Client(timeout=10.0) as client:
        robots = fetch_robots(client)
        crawler = Crawler(client, robots)

        try:
            print(f"Parsing BazaarPulse product pages -> {ANALYTICS_DB_PATH}")
            build(crawler, dst)
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
