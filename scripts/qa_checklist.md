# QA checklist — the brief's 8 illustrative questions

Run against the live system (`make serve`, backend on :8000, frontend on :3000,
`OLLAMA_MODEL=qwen3:4b` for ask-anything) on 2026-08-15, using whichever pillar
page and/or `/ask` answers each question best — never by writing fresh SQL
against `analytics.db` directly. Where a system-produced answer's plausibility
needed checking against a known fact (row counts, distributions), that
verification is noted separately from the system's own answer, exactly as
earlier build tasks hand-verified mart output against raw facts.

Score: **6 of 8 land well** (a concrete, correct-looking answer via the UI/API
as a reviewer would use it). **2 are real gaps**, documented below and fed back
into `DECISIONS.md`. Two more "answered" cases (Q2, Q5) surfaced a genuine,
systemic data finding worth flagging on their own.

---

## 1. Which five outlets had the lowest case fill rate last month, excluding closed and test outlets?

**Where asked:** Service page (`/service`, worst-outlets table) and `/api/ask`.

**Result: GAP.** `mart_service_worst` is a *globally* precomputed top-15-worst
list across all 18 months (see `build/marts/build_mart_service.py`), not
recomputed per filter. Filtering `/api/service?date_from=2026-06-01&date_to=2026-06-30`
intersects that fixed list against June and returns **1 row**, not 5 — the
Service page cannot answer "worst N for period X" for any period narrower
than its whole precomputed set.

`/api/ask` did no better: the LLM's SQL had no month filter at all (so it
picked the single worst outlet-month over the full 18-month history, not
"last month"), and its exclusion clause — `status NOT IN ('closed', 'test')`
— is a silent no-op, since `dim_outlets.status` values are uppercase
(`ACTIVE`/`CLOSED`/`DELETED`) and `'test'` isn't a status value at all (test
outlets are excluded structurally at dim-build time, not by status).
Independently verified the correct June-2026 worst 5 (`OUT00127`, `OUT00113`,
`OUT00698`, `OUT00102`, `OUT00092`, 74.4–78.2% fill) — a completely different
set from what `/api/ask` returned.

**Plausible?** No — via either surface.

---

## 2. What was OTIF by region for the last complete quarter?

**Where asked:** `/api/service?date_from=2026-04-01&date_to=2026-06-30`,
aggregated by region (the Service page charts fill rate by region but not
OTIF by region — the data is in the API response, just not charted).

**Result:** OTIF = **0.0%** for all 5 regions. Checked whether this was
specific to Q1: it isn't — `mart_service.otif_pct` is 0.0 across **all
12,933 rows**, every region/warehouse/route/outlet/month in the 18-month
dataset. Root cause (confirmed): zero of 83,411 orders have
`delivered_eaches >= ordered_eaches` (max ever achieved is 99.37%), so the
documented zero-tolerance "in full" threshold in `build_mart_service.py` is
never satisfied by this dataset. The system's answer is technically correct
per its documented definition but has zero discriminating power — every
region looks identical. Worth a DECISIONS.md line: this isn't a bug, it's the
in-full threshold interacting badly with this data's shape.

**Plausible?** Consistent and reproducible, but not a useful answer to "how
do regions compare" as posed — every region is tied at 0%.

---

## 3. Which categories drive the largest value of returns, and what is the leading reason code?

**Where asked:** `/api/ask` only — `mart_money_returns_by_category` exists
and `fact_returns.return_reason_code` exists, but neither is exposed by any
API endpoint or frontend page (Money page only covers freight cost/case).

**Result:** Answered correctly. `/ask` (both via curl and through the actual
`/ask` UI, screenshotted) returned **Staples** as the top category and
**RT01_NEAR_EXPIRY** as the leading reason code, with the natural-language
answer stating both plainly. Independently cross-checked against
`mart_money_returns_by_category` (Staples: ₹15.15L returns value, highest of
any category) and `fact_returns` reason-code counts (RT01_NEAR_EXPIRY: 4,659,
highest of any code) — both match exactly. Reproduced with a second, differently-
worded prompt; same correct answer both times.

**Plausible?** Yes, verified correct. (Note for `DECISIONS.md`: this mart has
no dedicated page — ask-anything is currently the *only* way to reach it.)

---

## 4. Temperature excursions per hundred chilled deliveries, by month.

**Where asked:** Cold Chain page (`/coldchain`) — "Excursion rate trend (avg
/ 100, by month)" line chart, backed by `/api/coldchain`.

**Result:** Renders correctly end to end (screenshotted). Values range
~2.7–3.75 per 100 chilled deliveries across all 19 months present, no
discontinuities or implausible spikes.

**Plausible?** Yes.

---

## 5. Which routes are more than two hours late on more than one delivery in ten?

**Where asked:** `/api/ask` only — no mart or endpoint exposes a per-route
delay-threshold breach rate (`mart_coldchain`/`mart_service` don't carry
`computed_delay_minutes`).

**Result:** `/ask` returned **all 140 routes**. Surprising enough to
independently verify: confirmed **0 of 140 routes** fall at or below the 10%
threshold — every route has ≥27% of its deliveries delayed >120 minutes
(fleet-wide: 44.2% of all 76,649 deliveries). This is consistent with Q2's
finding — on-time performance is a systemic, fleet-wide problem in this
dataset, not concentrated in a handful of bad routes. The answer is correct
but not very actionable as phrased (it doesn't discriminate between routes).

**Plausible?** Yes, verified correct, though the honest answer here is "this
question doesn't discriminate on this data" more than a route list would
suggest.

---

## 6. For our top twenty SKUs by value, how does our MRP compare with the lowest observed competitor price in Mumbai?

**Where asked:** Price Position page (`/price-position`, filtered to
Mumbai) and `/api/ask`.

**Result: GAP.** The Price Position page/mart has no order-value ranking at
all (`mart_price_position` doesn't carry SKU order value) — it can show
Mumbai's rows sorted by gap%, not "top 20 by value."

`/api/ask`'s generated SQL was actively wrong: it computed top-20 SKUs by
order value correctly, but for "lowest observed competitor price in Mumbai"
it used `MIN(competitor_price_min_inr)` across *all* Mumbai SKU-weeks (₹15.15
— some unrelated low-priced product) rather than the per-SKU minimum, then
applied that single global number to all 20 SKUs. Its own natural-language
summary ("MRP is 25–31x higher than the lowest competitor price") is
therefore comparing unrelated products. Independently verified: e.g.
`SKU00144`'s actual Mumbai competitor price is ₹332–414, not ₹15.15.

**Plausible?** No — the pillar page can't do it, and ask-anything's answer is
confidently wrong.

---

## 7. Freight cost per delivered case, by warehouse, for the last quarter.

**Where asked:** Money page (`/money`, "Freight cost per case by warehouse"
bar chart), filtered to FY2026-27 Q1 via the date filter, backed by
`/api/money`.

**Result:** `/api/money?date_from=2026-04-01&date_to=2026-06-30` returns
plausible, differentiated values across all 8 warehouses (₹54.52–₹82.64/case).
Chart renders correctly (screenshotted, unfiltered view shown but same code
path as the filtered one — filter interaction with the date picker was
already verified in T26).

**Plausible?** Yes.

---

## 8. Which outlets ordered a discontinued SKU after its discontinuation date?

**Where asked:** `/api/ask` only — no pillar page covers this (it's an
event-level question, not an aggregate).

**Result: GAP (partial).** First phrasing failed: the LLM's SQL joined
`fact_orders` directly on `sku_code` (which only exists at
`fact_order_lines` grain), a plain SQL error — but `sql_guard.py` catches
*any* `sqlite3.OperationalError` and reports it as `{"error":
"unsafe_sql_rejected", ...}`, the same UI state used for genuinely blocked
writes. A reviewer would read this as "the system refused this for safety,"
when it's actually just a schema bug in the generated SQL — worth a
DECISIONS.md line, since it's a real mislabeling, not a security issue.

A rephrased question succeeded, but hit the 200-row `ROW_LIMIT` and
undercounted: the natural-language answer claimed "50 unique outlet codes,"
counted only from the truncated 200 rows. Independently verified the true
scope is **9,054 outlet×SKU combinations across 721 distinct outlets** (i.e.
nearly every outlet in the network, at some point in 18 months, ordered one
of the ~24 discontinued SKUs after its discontinuation date) — the
row-limited answer materially understates this.

**Plausible?** Partially — the second attempt's *rows* were correct as far as
they went, but the summary count was wrong, and the first attempt's error
state was misleading.

---

## Summary for DECISIONS.md

- **Real gaps (2/8):** Q1 (worst-N-for-a-period isn't supported by the
  precomputed global worst-list design) and Q6 (ask-anything's SQL silently
  substituted an unrelated global value for a per-SKU one).
- **Answered but exposes real findings (2/8):** Q2 and Q5 both show OTIF/
  on-time performance is a systemic 0%/fleet-wide problem in this dataset,
  not a differentiator between regions/routes — a genuine data characteristic
  worth flagging, not a bug.
- **Ask-anything-only, but correct (2/8):** Q3 and Q5 (returns-by-category
  and route delay-breach both lack a dedicated mart endpoint/page).
- **Row-limit/error-labeling issues surfaced (Q8):** truncated results are
  silently under-reported by the NL synthesis step, and generic SQL errors
  are shown in the same UI state as safety rejections.
