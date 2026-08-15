# External Sources

Three external surfaces ship with this assignment. All are free, none need an account.

---

## 1. BazaarPulse: the scrape target

A static competitor price tracker. 1,137 listings across four cities and five retailers, with a detail page per listing.

**Serve it locally.**

```bash
cd bazaarpulse_site
python3 -m http.server 8080
# http://localhost:8080
```

**What is there**

| Path | Contents |
|---|---|
| `/index.html` | City index |
| `/city/{slug}/page/{n}.html` | Listing pages, Mumbai and Delhi |
| `/city/{slug}/index.html` | Listing pages, Bengaluru and Chennai |
| `/product/{id}.html` | Listing detail with observed price history |
| `/robots.txt` | Crawl policy |
| `/sitemap.txt` | Entry points |
| `/methodology.html` | How the site says it collects prices |

**Fair warning.** The site was not built for you. Markup conventions differ between cities, pagination is not uniform, some pages are unreachable, and product titles do not carry a key that maps to Kestrel SKUs. Read `/methodology.html` before you write the parser.

Treat `robots.txt` as you would on a live site.

---

## 2. Kestrel Logistics Partner API: the mock service

Carrier freight invoices. This is the only source of actual freight cost. The `fuel_cost_inr` column in `deliveries` is driver-entered and is not the billed amount.

**Run it.**

```bash
pip install fastapi uvicorn
python partner_api/server.py
# http://localhost:8088
```

**Auth.** Every `/v1/*` request needs `X-API-Key: kp_live_7f3a9c21`.

**Endpoints**

| Endpoint | Notes |
|---|---|
| `GET /v1/health` | No auth |
| `GET /v1/carriers` | Five carriers |
| `GET /v1/freight_invoices` | ~41,500 invoices, cursor paginated, 200 per page. Follow `next_cursor` until null. Supports `from` and `to` |
| `GET /v1/shipment_events?invoice_id=` | Event trail per invoice |
| `GET /v1/fuel_surcharge?month=YYYY-MM` | Monthly index |

**Behaviour to expect.** The service returns `429` with `Retry-After` on roughly one request in nine, and `503` on roughly one in twenty-five. The first page of each cursor walk is slow. Timestamps are UTC; the operational database is Asia/Kolkata. The `amount` field is in paise.

A full walk of `freight_invoices` takes a few minutes if you handle it well and does not terminate at all if you do not. Decide whether you need all of it.

---

## 3. Public APIs: optional enrichment

Two keyless public APIs, if you want to explain variance rather than only report it.

**Open-Meteo historical weather.** Daily temperature and precipitation by coordinate, back several years. Relevant to chilled product spoilage, returns, and demand.

```
https://archive-api.open-meteo.com/v1/archive
  ?latitude=19.076&longitude=72.877
  &start_date=2025-01-01&end_date=2026-06-30
  &daily=temperature_2m_max,precipitation_sum&timezone=Asia%2FKolkata
```

**Nager.Date public holidays.** Indian public holidays by year. Relevant to demand spikes and delivery failure.

```
https://date.nager.at/api/v3/PublicHolidays/2025/IN
https://date.nager.at/api/v3/PublicHolidays/2026/IN
```

Neither is required. If you use one, we will ask why, and "it was available" is not an answer.

If a public API is unreachable from your network, that is a design problem, not a blocker. Handle it the way you would in production.
