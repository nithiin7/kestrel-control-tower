# Decisions

**What was built** — FastAPI + Next.js control tower, one shared filter bar
across every page. `make build` → `data/analytics.db`; `make serve` runs the app.
- Service, Cold Chain, Money, Price Position — fill rate/OTIF (eaches),
  cold-chain excursions & near-expiry stock, freight ₹/case & returns %,
  and Kestrel MRP vs. competitor MRP vs. observed price (3 columns) — each
  with a worst-performer list on load
- Ask-anything — text-to-SQL, SQL/results shown, read-only enforced at the DB level

**Deliberately not built**
- Competitor pricing covers 4/8 cities; freight cost is a
  warehouse×route×month aggregate, not per-shipment; `/internal/`/`/admin/`
  never fetched; KP-2301 doesn't reproduce here
- **BazaarPulse's "competitors" are Kestrel's own multi-brand portfolio, not
  rivals** — the single most important caveat here. Also: no auth/RBAC,
  production build, caching, or alerting

**Assumptions** (brief was ambiguous or self-contradicting)
- Fill rate in **eaches**, not cases (overrides the brief); OTIF "in full" =
  `delivered_eaches >= ordered_eaches`, zero tolerance; near-expiry = ≤30 days
- On-time = zero tolerance (raw `delay_minutes` is noise); "latest complete
  quarter" derives from the data's own max order date; test outlets
  excluded by code/name pattern, never by `status`

**QA results** (`scripts/qa_checklist.md`, all 8 brief questions)
- 6/8 answered correctly and verified; 2 gaps — "worst 5 outlets last month"
  (worst-list is global, not per-filter) and "top-20 SKUs vs. Mumbai price"
  (ask-anything used a city-wide min, not per-SKU)
- Finding: **OTIF is 0% for every region/month, all 18 months** — no order
  ever clears the zero-tolerance in-full bar, so the metric doesn't discriminate here

**Next two weeks** — auth/RBAC + production build; cache layer over the marts;
second competitor-price source; regression suite beyond build-time assertions; threshold alerting.

**What breaks first in production** — freight API chaos at 10x volume; LLM
cost/latency/accuracy (no caching/cost ceiling, shaky small-model SQL);
BazaarPulse's 4 parsers break silently on site changes; the Next.js dev
server isn't production-grade; SQLite is single-writer.
