# Decisions

**What was built.** FastAPI + Next.js control tower over the 18-month
dataset, the partner freight API, and the BazaarPulse scrape target, via a
one-command idempotent pipeline (`make build`) into `data/analytics.db`.
Five pillars: Service (fill rate/OTIF in eaches, worst outlets on load),
Cold Chain (excursions/100 chilled deliveries, near-expiry stock,
cold-chain returns), Money (freight ₹/case, returns % of dispatch, carrier
leakage), Price Position (Kestrel MRP vs. competitor MRP vs. observed
price, 3 columns), and Ask-anything (text-to-SQL, SQL and results shown for
transparency, read-only enforced at the DB level). Regional managers use
the same shared filter bar, not separate logins.

**Deliberately not built.** Competitor pricing covers 4 of 8 warehouse
cities (Mumbai/Bengaluru/Chennai/Delhi) — BazaarPulse has no data for the
rest. Freight cost is a warehouse×route×month aggregate, never
per-shipment — the partner API has no delivery/order join key.
**BazaarPulse's "competitors" are Kestrel's own multi-brand portfolio**, not
rival companies — Price Position is really an MAP/retailer-variance
monitor, the single most important caveat here. `/internal/`/`/admin/`
were never fetched. KP-2301 (header/line value mismatch) doesn't reproduce
in this snapshot. No auth/RBAC, no production Next build, no caching, no
alerting.

**Assumptions where the brief was ambiguous or self-contradicting.** Fill
rate is reported in **eaches**, not cases — the brief's illustrative
question says "case fill rate," but Rakesh's follow-up explicitly overrides
that. OTIF "in full" = `delivered_eaches >= ordered_eaches`, zero
tolerance. Near-expiry = ≤30 days to expiry; on-time = zero tolerance (raw
`delay_minutes` disagrees ~87% of the time — treated as noise). "Latest
complete quarter" derives from the data's own max order date (2026-06-30 →
FY2026-27 Q1), never wall-clock today. Test outlets are excluded by
code/name pattern, never by `status` (all 3 show `ACTIVE`).

**Next two weeks.** Production Next.js build behind real auth/RBAC; a
cache layer in front of the marts; charting ask-anything's results; a
second competitor-price source for the other 4 cities; a regression suite
beyond build-time assertions; threshold alerting instead of a visit.

**What breaks first in production.** Freight API chaos (429/503) rate
compounds at 10x volume. LLM cost/latency/accuracy at scale — no response
caching, no cost ceiling, shaky SQL generation on smaller local models.
BazaarPulse's per-city markup extraction is brittle (4 hand-written
parsers; any site change breaks one silently). `next dev` isn't
production-grade under load. SQLite is single-writer — fine now, not at
real scale.
