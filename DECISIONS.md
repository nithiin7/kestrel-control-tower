# Decisions

**What was built.** FastAPI + Next.js control tower over the 18-month
dataset, the partner freight API, and the BazaarPulse scrape target, via a
one-command idempotent pipeline (`make build`) into `data/analytics.db`.
Five pillars: Service (fill rate/OTIF in eaches, worst outlets on load),
Cold Chain (excursions/100 chilled deliveries, near-expiry stock,
cold-chain returns), Money (freight ₹/case, returns % of dispatch, carrier
leakage), Price Position (Kestrel MRP vs. competitor MRP vs. observed
price, 3 columns), and Ask-anything (text-to-SQL, SQL and results shown for
transparency, read-only enforced at the DB level). One shared filter bar
across all pillars, not separate logins.

**Deliberately not built.** Competitor pricing covers 4 of 8 warehouse
cities (Mumbai/Bengaluru/Chennai/Delhi) — BazaarPulse has no data for the
rest. Freight cost is a warehouse×route×month aggregate, never
per-shipment — the partner API has no delivery/order join key.
**BazaarPulse's "competitors" are Kestrel's own multi-brand portfolio**, not
rival companies — Price Position is really an MAP/retailer-variance
monitor, the single most important caveat here. `/internal/`/`/admin/`
never fetched. KP-2301 doesn't reproduce in this snapshot. No auth/RBAC,
production build, caching, or alerting.

**Assumptions where the brief was ambiguous or self-contradicting.** Fill
rate is reported in **eaches**, not cases — Rakesh's follow-up overrides the
brief's "case fill rate" wording. OTIF "in full" = `delivered_eaches >=
ordered_eaches`, zero tolerance. Near-expiry = ≤30 days; on-time = zero
tolerance (raw `delay_minutes` disagrees ~87% of the time — treated as
noise). "Latest complete quarter" derives from the data's own max order
date, never wall-clock today. Test outlets excluded by code/name pattern,
never by `status`.

**QA against the brief's 8 illustrative questions** (`scripts/qa_checklist.md`).
6/8 land well; 2 are real gaps — "worst 5 outlets last month" (the
worst-outlets view is one precomputed global top-15, not per-filter) and
"top-20 SKUs vs. Mumbai competitor price" (ask-anything used an unrelated
city-wide min, not the per-SKU one). Also surfaced: **OTIF is 0% for every
region/route/month, all 18 months** — zero orders here ever clear the
zero-tolerance in-full bar, so the metric doesn't discriminate on this data.

**Next two weeks.** Real auth/RBAC and a production build; a cache layer
over the marts; a second competitor-price source; a regression suite
beyond build-time assertions; threshold alerting.

**What breaks first in production.** Freight API chaos compounds at 10x
volume. LLM cost/latency/accuracy at scale — no caching, no cost ceiling,
shaky SQL generation on smaller local models (see QA). BazaarPulse's
per-city parsers are brittle — a site change breaks one silently. `next
dev` isn't production-grade under load. SQLite is single-writer.
