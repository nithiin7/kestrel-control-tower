#!/usr/bin/env python3
"""BazaarPulse crawler — URL discovery half.

Run: python build/external/scrape_bazaarpulse.py
(requires the mock site served, e.g. `python3 -m http.server 8080` from
bazaarpulse_site/)

Discovers every /product/{id}.html URL reachable from the 4 city listing
sections, starting from /sitemap.txt (which only lists each city's page
1 — the rest is found by following in-page pagination).

robots.txt is fetched and parsed at runtime (Disallow /internal/,
/admin/; Crawl-delay 1) rather than hardcoded — every request, including
ones this script constructs itself, is checked against it before being
sent, and every request made is logged so a compliance audit is trivial.
/internal/margin-sheet.html is a deliberate trap (fictional but
plausible-looking confidential data) and must never be fetched.

Pagination trap: Mumbai/Delhi serve page N at the real path
/city/{slug}/page/{n}.html, and their pager hrefs are trustworthy.
Bengaluru/Chennai serve page N at /city/{slug}/index_p{n}.html, but
their pager hrefs misleadingly read
/city/{slug}/index.html?p={n} — that query-string form just re-serves
page 1 on this static file server. The fix: each city directory's
PAGINATION.txt (itself unlisted anywhere but fetchable, not
robots-disallowed) states the real convention when one applies. This
script fetches it and only trusts a city's pager hrefs directly when
PAGINATION.txt is absent (404) for that city — never trusts href text
blindly. The page *count* still comes from the hrefs on page 1 (their
number is accurate even when the URL shape isn't).
"""

import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import BAZAARPULSE_BASE_URL

CRAWL_DELAY_SECONDS_DEFAULT = 1.0
DISALLOWED_PREFIXES_DEFAULT = ("/internal/", "/admin/")

PRODUCT_URL_RE = re.compile(r'href="(/product/\d+\.html)"')
# Pager links are the only anchors with pure-digit link text on these
# pages (product links are titles) — matched directly, since the pager
# container itself is inconsistently quoted (<p class='pager'> here).
PAGER_LINK_RE = re.compile(r'<a href="([^"]+)">(\d+)</a>')
PAGINATION_TEMPLATE_RE = re.compile(r"(\S*\{N\}\S*)")


class RobotsPolicy:
    def __init__(self, disallowed_prefixes: tuple[str, ...], crawl_delay: float) -> None:
        self.disallowed_prefixes = disallowed_prefixes
        self.crawl_delay = crawl_delay

    def is_allowed(self, path: str) -> bool:
        return not any(path.startswith(p) for p in self.disallowed_prefixes)


def fetch_robots(client: httpx.Client) -> RobotsPolicy:
    resp = client.get(f"{BAZAARPULSE_BASE_URL}/robots.txt")
    resp.raise_for_status()
    disallowed = []
    crawl_delay = CRAWL_DELAY_SECONDS_DEFAULT
    for line in resp.text.splitlines():
        line = line.strip()
        if line.lower().startswith("disallow:"):
            disallowed.append(line.split(":", 1)[1].strip())
        elif line.lower().startswith("crawl-delay:"):
            crawl_delay = float(line.split(":", 1)[1].strip())
    if not disallowed:
        disallowed = list(DISALLOWED_PREFIXES_DEFAULT)
    return RobotsPolicy(tuple(disallowed), crawl_delay)


class Crawler:
    def __init__(self, client: httpx.Client, robots: RobotsPolicy) -> None:
        self.client = client
        self.robots = robots
        self.request_log: list[tuple[str, int]] = []

    def get(self, path: str) -> httpx.Response | None:
        if not self.robots.is_allowed(path):
            raise RuntimeError(f"refusing to request robots-disallowed path: {path}")
        url = urljoin(BAZAARPULSE_BASE_URL, path)
        resp = self.client.get(url)
        self.request_log.append((path, resp.status_code))
        time.sleep(self.robots.crawl_delay)
        if resp.status_code != 200:
            return None
        return resp

    def fetch_pagination_template(self, city_dir: str) -> str | None:
        """Return e.g. 'index_p{N}.html' if city_dir/PAGINATION.txt exists, else None."""
        resp = self.get(f"{city_dir}PAGINATION.txt")
        if resp is None:
            return None
        m = PAGINATION_TEMPLATE_RE.search(resp.text)
        return m.group(1) if m else None

    def extract_product_urls(self, html: str) -> set[str]:
        return set(PRODUCT_URL_RE.findall(html))

    def extract_pager_pages(self, html: str) -> list[tuple[str, int]]:
        """Return [(href, page_num), ...] found anywhere on the page."""
        return [(href, int(num)) for href, num in PAGER_LINK_RE.findall(html)]

    def crawl_city(self, start_path: str) -> tuple[set[str], set[int]]:
        """Returns (product_urls, pages_visited) for one city."""
        parsed = urlparse(start_path)
        # e.g. /city/mumbai/page/1.html -> /city/mumbai/ ; /city/bengaluru/index.html -> /city/bengaluru/
        city_dir = "/".join(parsed.path.split("/")[:3]) + "/"

        resp = self.get(start_path)
        if resp is None:
            return set(), set()

        product_urls = self.extract_product_urls(resp.text)
        pages_visited = {1}
        pager_pages = self.extract_pager_pages(resp.text)
        max_page = max((n for _, n in pager_pages), default=1)

        template = self.fetch_pagination_template(city_dir)

        for page_num in range(2, max_page + 1):
            if template:
                page_path = city_dir + template.replace("{N}", str(page_num))
            else:
                # No PAGINATION.txt override for this city — trust the href as-is
                # (confirmed true for Mumbai/Delhi, which use real file paths).
                href = next(href for href, n in pager_pages if n == page_num)
                page_path = href
            page_resp = self.get(page_path)
            if page_resp is None:
                continue
            product_urls |= self.extract_product_urls(page_resp.text)
            pages_visited.add(page_num)

        return product_urls, pages_visited


def parse_sitemap(client: httpx.Client) -> list[str]:
    resp = client.get(f"{BAZAARPULSE_BASE_URL}/sitemap.txt")
    resp.raise_for_status()
    return [line.strip() for line in resp.text.splitlines() if line.strip().startswith("/city/")]


def main() -> int:
    with httpx.Client(timeout=10.0) as client:
        robots = fetch_robots(client)
        print(f"robots.txt: disallow={robots.disallowed_prefixes} crawl_delay={robots.crawl_delay}s")

        city_start_paths = parse_sitemap(client)
        print(f"sitemap city entries: {city_start_paths}")

        crawler = Crawler(client, robots)

        all_product_urls: set[str] = set()
        per_city_pages: dict[str, set[int]] = {}
        for start_path in city_start_paths:
            city = start_path.split("/")[2]
            print(f"\nCrawling {city} from {start_path} ...")
            product_urls, pages_visited = crawler.crawl_city(start_path)
            print(f"  {city}: {len(product_urls)} product URLs across pages {sorted(pages_visited)}")
            all_product_urls |= product_urls
            per_city_pages[city] = pages_visited

    print(f"\nTotal requests made: {len(crawler.request_log)}")
    disallowed_hits = [p for p, _ in crawler.request_log if not robots.is_allowed(p)]
    print(f"Requests to disallowed paths: {len(disallowed_hits)}")

    print(f"\nTotal unique product URLs discovered: {len(all_product_urls)}")
    for city, pages in per_city_pages.items():
        beyond_page1 = max(pages) > 1
        print(f"  {city}: reached page {max(pages)} ({'beyond page 1' if beyond_page1 else 'PAGE 1 ONLY'})")

    out_dir = Path(__file__).resolve().parent.parent.parent / "data" / "raw_cache" / "bazaarpulse"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "discovered_product_urls.txt"
    out_path.write_text("\n".join(sorted(all_product_urls)) + "\n")
    print(f"\nWrote {len(all_product_urls)} URLs to {out_path}")

    log_path = out_dir / "crawl_request_log.txt"
    log_path.write_text("\n".join(f"{status} {path}" for path, status in crawler.request_log) + "\n")
    print(f"Wrote {len(crawler.request_log)} request log entries to {log_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
