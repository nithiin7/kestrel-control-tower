# Decisions

Running log of non-obvious judgment calls made while building the pipeline.
Updated as tasks land; will be trimmed/finalized at T29.

## dim_outlets (T2)
- Dedupe/join key is `outlet_code` only — `outlet_name` has 70+ duplicate
  groups, never safe to key on.
- Test/migration outlets (KP-2377, `TST00001-3` + name patterns) excluded
  by `outlet_code`/`outlet_name` pattern, explicitly **not** by `status`
  — all three show `status=ACTIVE`, so a status filter would silently
  let them through. Excluded rows kept in `dim_outlets_excluded` for audit.
- City spelling (KP-2288) normalized via `data/ref/city_name_map.csv`:
  `Bangalore`→`Bengaluru`, `New Delhi`→`Delhi`. `Gurugram`/`Guwahati` are
  real distinct cities, deliberately left unmerged.

## dim_products (T3)
- `discontinued_flag` derived from `discontinued_date` being non-null,
  not from the `status` column — a direct read of the same underlying
  fact rather than a second, possibly-inconsistent field.

## dim_date (T5)
- Kestrel fiscal year is April–March. `get_latest_complete_fiscal_quarter()`
  anchors to the operational data's own max date (2026-06-30), never
  wall-clock today — the landing page's "latest complete quarter" tile
  and every mart's default filter must stay correct regardless of when
  the app is actually run/demoed.

## fact_orders / fact_order_lines (T6)
- `orders.created_at`: ERP_WEB and SFA_MOBILE timestamps are already
  local IST (both cluster in 06:00–20:00 business hours); PARTNER_API is
  explicit UTC (`...Z` suffix) — confirmed by its raw hour distribution
  clustering 00:00–15:00 UTC, i.e. the same business-hours window shifted
  by exactly -5:30. Only PARTNER_API gets the +5:30 conversion.
- `line_value_inr` is the money source of truth everywhere downstream,
  never `orders.order_value_gross_inr`. Checked KP-2301 (header/line
  mismatch) against this snapshot: `AVG(ABS(gross - SUM(line_value)))` =
  0.0 for all three source systems — the bug does not reproduce here.
  Line-level is still used since it's the more granular source per the
  data dictionary's general guidance, not as a "fix."
- Quantities converted to eaches via `qty_uom` + `case_pack_at_order`
  (CASE → `qty * case_pack_at_order`, EACH → `qty` as-is); raw case-grain
  columns kept alongside for audit. This is the load-bearing conversion
  for fill-rate reporting (brief requires eaches, not cases).

## fact_deliveries (T7)
- `on_time_flag` / delay are computed directly from
  `actual_arrival_ts - planned_arrival` (0 min late = on time), **not**
  from the raw `delay_minutes` column.
- **New data-quality finding (not in the data dictionary's KP list):**
  raw `delay_minutes` disagrees with the computed diff on ~87% of all
  76,889 rows. Every disagreement is an exact whole-hour offset,
  symmetrically distributed -7h..+7h with mean 0 — confirmed
  vendor-independent and not a parsing artifact (`planned_arrival` is
  always on-the-hour in the source). Treated as uncorrelated noise on
  `delay_minutes`, consistent with this dataset's established pattern
  of noisy columns (e.g. KP-2402's `return_qty` sign bug) — the raw
  column is kept in `fact_deliveries` for audit but never used as
  ground truth.

## fact_returns (T9)
- `return_qty` sign bug (KP-2402) fixed unconditionally via `ABS()` —
  confirmed uncorrelated noise (~6.4% negative, uniform across every
  other field), not a conditional/reason-based fix.
- Eaches conversion uses `case_pack_at_order` looked up via
  `order_line_id`; falls back to `dim_products.case_pack` if that link
  is missing (never triggers in this snapshot — every return resolves
  cleanly — but kept as a defensive safety net, not baked in as an
  assumption).
- **Cold-chain-caused call:** only `RT06_COLD_CHAIN_BREACH` drives
  `cold_chain_caused_flag` (783 rows post-exclusion). `RT02_DAMAGE_TRANSIT`
  on a chilled SKU (814 raw rows) is a weaker, ambiguous signal — transit
  damage can be ordinary breakage/mishandling unrelated to temperature —
  so it's kept as a separate `cold_chain_secondary_signal_flag` instead
  of being folded into the primary metric.

## freight_invoices ingest (T10/T11)
- Only `amount` is converted paise→INR. `detention_charge` has the same
  suspiciously-large integer scale (0-32,000) but is nowhere documented
  as paise (only `amount` is, in the mock server's own docstring) — kept
  as returned rather than guessed at, to avoid silently introducing a
  100x error if the guess is wrong.
- Resume checkpoint is an append-only JSONL log (one line per fetched
  page), not a single JSON blob — a truncated/partial trailing line from
  a mid-write crash is detected and discarded on load, and the walk
  resumes from the last fully-written record's `next_cursor` rather than
  restarting at offset 0. Verified against a real kill -9 mid-walk plus
  manual truncation of the trailing line.

## BazaarPulse crawl (T13)
- Bengaluru/Chennai's per-city `PAGINATION.txt` (fetchable, not
  robots-disallowed) is fetched and used as the page-N URL template;
  Mumbai/Delhi have no such file, so their pager hrefs are trusted
  directly — matches the brief's description of which cities use real
  paths vs. the `?p=N` trap. Page *count* comes from the pager anchors'
  digit text either way, since that number is accurate regardless of
  whether the href itself is trustworthy.
- **New finding:** 3 of the 1,137 discovered `/product/{id}.html` links
  (387, 458, 777) 404 — dead links in the listing pages, not a crawl
  bug (confirmed: all 1,134 real files on disk were discovered, zero
  missed). T14's parser needs to skip 404s rather than treat them as a
  parse failure.

## BazaarPulse SKU matching (T15)
- Pack size agreement is a HARD GATE on a match, not just a score
  component — a name match against the wrong pack size would corrupt
  T19's price-gap-% math (comparing prices across different pack sizes
  is meaningless), so a candidate is only eligible at all if its
  (value, uom) exactly equals the listing's parsed pack size.
  Confidence threshold (90) applies to name-similarity only, among
  pack-matching candidates.
- Name similarity is `max(token_sort_ratio, ratio-on-space-collapsed-
  strings)` — token-based scoring alone scores "AmritValley" vs.
  "Amrit Valley" only ~63 (token-count mismatch from the missing
  space) despite being a 1-character edit apart; the space-collapsed
  ratio catches this and other concatenation-vs-spaced brand spelling
  differences.
- **Significant finding:** after normalization, **100% of the 1,134
  BazaarPulse listings match a real dim_products SKU** at score >=95
  (empirical floor). This is because `dim_products.brand` has 6 values
  — Kestrel plus Bluepeak/Hillfare/Coastline/Amrit/Marwar — and all 6
  are Kestrel's own multi-brand portfolio (per `products.supplier_name`
  in the source data), not external competitors. BazaarPulse is
  therefore an MAP/retail-price-variance monitor across Kestrel's own
  brand portfolio sold through different online retailers, not
  genuine inter-company competitor pricing. This reframes what
  "competitor observed price" means in mart_price_position (T19) —
  worth calling out explicitly on that page rather than labeling it
  as competitor-brand pricing.

## mart_service (T16)
- "In full" = `delivered_eaches >= ordered_eaches` per order, zero
  tolerance for partial shortfall — a judgment call; a tolerance band
  (e.g. >=95%) would also be defensible, but zero-tolerance is the
  more conservative/legible default and matches "in full" literally.
- Only `DELIVERED`/`PARTIAL` orders count toward fill_rate_eaches/
  otif_pct. `CANCELLED` orders never enter fulfillment (delivered_eaches
  is always 0, zero matching fact_deliveries rows) — counting them
  would misrepresent a demand-side cancellation as a fulfillment
  failure. `OPEN` orders are still in-flight (also zero fact_deliveries
  rows) — including them would bias whichever month is most recent.
- `mart_service_worst` excludes outlet-months with fewer than 5 orders
  — otherwise a single bad order at a low-volume outlet would dominate
  the "worst" list ahead of a high-volume outlet with a real, sustained
  problem.

## fact_inventory_snapshots (T8)
- `near_expiry_flag` threshold: `expiry_date - snapshot_date <= 30`
  days. A round number representative of a typical reorder/rotation
  cycle for short-shelf-life grocery stock — 14 or 45 would also be
  defensible; 30 was picked as the middle-of-the-road default.
  Near-expiry rate at this threshold: 14.42% (18,894/131,040).
- `on_hand_eaches` cross-checked against `on_hand_cases * case_pack`
  rather than trusted outright; zero discrepancies found in this
  snapshot (verified) — the log table is still created empty rather
  than being skipped, so a future data refresh with real discrepancies
  doesn't silently need new code.

## mart_coldchain (T17)
- **Grain mismatch, handled explicitly**: inventory has no route
  dimension (stock sits in a warehouse, not on a route), so
  `near_expiry_stock_value_inr` is a warehouse x month aggregate,
  broadcast identically across every route under that warehouse for
  that month — not a per-route allocation, since no finer key exists
  to allocate it correctly. Same shape as fact_freight's warehouse x
  route x month aggregate ratio (T12/T18). Documented on the column
  itself so it isn't read as route-attributable.
- Near-expiry stock is valued at the LAST `snapshot_date` of each
  month, not summed across that month's ~4-5 weekly snapshots — it's a
  stock level, not a flow, so summing every weekly snapshot would
  count the same physical batches multiple times.
- `fact_returns` has no warehouse_id/route_id of its own; cold-chain
  return value is attributed via `fact_orders.order_id` (the order's
  fulfillment warehouse/route) — zero orphaned `order_id`s verified,
  so this join is safe.

## mart_money (T18)
- **Two of the three brief-listed measures don't share the warehouse x
  route x month grain, so they're split into satellite tables** instead
  of being force-fit or broadcast: `mart_money_returns_by_category`
  (category x month — SKUs aren't warehouse-specific, so a
  warehouse/route dimension here would just be noise) and
  `mart_money_carrier_variance` (carrier only — carrier exists
  exclusively on fact_freight, with no link into deliveries, orders, or
  returns; forcing a warehouse/route breakdown would invent a
  relationship the data doesn't have). Same reasoning as mart_coldchain's
  near-expiry column (T17), applied twice more in one mart.
- Freight cost per delivered case uses `fact_deliveries` (not
  `fact_orders`) for the warehouse/route/month on the case side, since
  "delivered case" is literally about the delivery event — the two
  agree in every row in this data (zero mismatches verified) so the
  choice doesn't change any numbers here, but it's the more defensible
  reading of "delivered."
- Returns land at ~0.05% of dispatch value overall (well inside the
  0-15% sanity band, just at the low end) — cross-checked against raw
  `SUM(credit_note_value_inr)` / `SUM(line_value_inr)`, not a bug:
  13,686 returns average ~₹684 each vs. 460,515 order lines averaging
  ~₹39,881 each.

## mart_price_position (T19)
- **4 of Kestrel's 8 warehouse cities have zero rows in this mart** —
  BazaarPulse only covers Mumbai/Bengaluru/Chennai/Delhi, so the other
  4 (wherever they are) simply have no competitor price data. Not a
  gap to "fix"; there is no source for it. Should be surfaced
  explicitly on the price-position page (e.g. "no coverage" state for
  the other 4 cities) rather than left as a silent absence.
- Both `competitor_price_median_inr` and `competitor_price_min_inr`
  are computed (375 of 1,134 matched city+SKU combos have more than
  one retailer listing) — `gap_pct` uses the median as primary since
  it's less skewed by one outlier retailer than the min would be;
  `gap_pct_vs_min` is kept alongside for reference.
- "Week" is BazaarPulse's own weekly observation date used directly
  (confirmed 7-day spacing in the raw history), not re-bucketed into
  ISO weeks — avoids introducing a second, redundant week-numbering
  scheme.
- Median has no native SQLite aggregate, so it's computed in Python
  after the SQL grouping pass rather than reached for a window-function
  workaround — simpler and just as correct at this data volume (6,317
  rows).

## /api/ask text-to-SQL (T23)
- SQL safety uses SQLite's `set_authorizer` callback as an allowlist
  (only `SQLITE_SELECT`/`SQLITE_READ`/`SQLITE_FUNCTION` return `SQLITE_OK`,
  everything else — `DROP`, `PRAGMA`, `ATTACH`, `INSERT`/`UPDATE`/`DELETE`,
  even comment- or string-literal-disguised attempts — is denied before a
  single byte executes), not a keyword blocklist, per the task's explicit
  "blocklists are bypassable" requirement. `cursor.execute()` (never
  `executescript`) also rejects multi-statement payloads outright
  (`SELECT 1; DROP TABLE x;` fails with "one statement at a time" before
  the authorizer is even reached). Verified against 9 hand-written attack
  strings and one live prompt-injection attempt ("ignore previous
  instructions... write DROP TABLE") — all rejected with `{"error":
  "unsafe_sql_rejected"}`, table row counts unchanged.
- A wall-clock query timeout uses `set_progress_handler`, and the row cap
  is enforced via `fetchmany(200)` after execution rather than rewriting
  the LLM's SQL to inject a `LIMIT` clause — simpler and works regardless
  of whether the model already added its own limit.
- Local Ollama models are meaningfully slower than the Anthropic API for
  this workload — a 4B "thinking" model took ~40-80s per call on this
  machine's CPU, well past the original 60s timeout, so
  `OllamaProvider`'s timeout was raised to 180s. Verified end-to-end with
  `qwen3:4b` (no `llama3.1` pulled locally): valid SQL, plausible result
  rows, and a natural-language summary all returned correctly, just slow.
- LLM SQL *safety* is guaranteed by the validator; SQL *correctness*
  isn't and can't be — e.g. the local model's answer to the brief's
  outlet-fill-rate question used `status NOT IN ('closed', 'test')`
  (wrong case, and 'test' isn't a real status value) which is a
  silent no-op filter rather than an error. Test outlets are already
  excluded upstream in `dim_outlets` (T2), so this particular case was
  harmless, but it's a reminder that natural-language answers should be
  read as "a plausible attempt," not a verified fact, especially with
  smaller local models.

## Frontend scaffold + serve.sh (T24)
- Found and fixed a real bug in `app/db.py` while testing the landing
  page's parallel fetches (filters + 4 pillar endpoints firing at once):
  `sqlite3.ProgrammingError: SQLite objects created in a thread can only
  be used in that same thread`. FastAPI's generator dependencies can run
  a request's setup and teardown on different threadpool workers even
  though the connection is only ever touched by one thread at a time —
  fixed with `check_same_thread=False` on the read-only connection. This
  affected every existing endpoint (T20-T23), not just this task; only
  surfaced now because this is the first place several endpoints get hit
  concurrently.
- `app/fiscal.py` duplicates `get_latest_complete_fiscal_quarter()` from
  `build/dims/build_dim_date.py` rather than importing it, since the app
  is only supposed to read the built `analytics.db`, never import
  build-time pipeline code. `/api/meta/filters` now computes it from
  `MAX(fact_orders.order_date)` and returns it as `latest_complete_quarter`
  — verified it resolves to FY2026-27 Q1 (2026-04-01 – 2026-06-30) for
  the Q1 tile, not wall-clock today.
- `Nav.tsx` uses plain `<a>` tags instead of `next/link`'s typed `Link`
  for the four pillar-page links that don't exist until T25/T26 — Next's
  typed-routes feature rejects `Link` hrefs that don't resolve to a real
  page at build time. Worth swapping to `Link` once those pages land.
- The landing page's "worst of worst" row surfaced a real small-sample
  issue in T21's `/api/coldchain`: `worst_routes` has no minimum-volume
  floor (unlike `mart_service_worst`'s `MIN_ORDERS_FOR_WORST_RANKING`),
  so a route with exactly 1 chilled delivery that had an excursion shows
  as "100% excursion rate" and dominates the ranking. The underlying
  data is correct (verified against raw mart rows), just statistically
  noisy — worth a minimum-delivery floor if `/api/coldchain`'s worst
  ranking gets revisited.
- Verified the Ctrl+C acceptance test properly: a real terminal's Ctrl+C
  sends SIGINT to the whole foreground process group (confirmed clean
  shutdown, zero orphans via `ps`/`lsof`), not just to the `make`
  process — signaling `make` alone does *not* cascade, since `make`
  doesn't forward signals to children by default. `serve.sh`'s trap is
  what makes the group-signal case work by explicitly killing its two
  recorded child PIDs rather than relying on `make` to propagate.

## Service + cold-chain pages (T25)
- Charts are hand-rolled SVG (`components/charts/BarChart.tsx`,
  `LineChart.tsx`) rather than a charting library — no library was
  already in the project, and the dataviz skill's mark specs (2px
  lines, 4px rounded bar ends, hairline gridlines, hover tooltips,
  single-hue magnitude) are simple enough to implement directly.
  Followed the skill's procedure: form → color (validated the light
  palette's blue/red pair via `validate_palette.js`, all checks pass)
  → marks → hover layer → accessibility pass → render-and-look. Charts
  are light-mode only, matching the rest of the app (Nav/FilterBar have
  no dark-mode styling yet either) rather than introducing dark-mode
  divergence just for charts.
- Caught a real correctness bug while building the cold-chain page's
  "near-expiry stock value by warehouse" chart: `near_expiry_stock_value_inr`
  is a warehouse-month snapshot broadcast onto every route row in
  `mart_coldchain` (same value repeated per route, confirmed via direct
  query). Naively summing it by warehouse multiply-counted the same
  figure once per route *and* once per month — inflating a real ~₹4
  crore/warehouse figure into a nonsensical ~₹2,000 crore. Fixed by
  restricting to a single month (the latest with actual snapshot
  coverage — the mart's trailing month or two is delivery-spillover
  with zero inventory data) and averaging across the identical route
  duplicates rather than summing.
- Two SVG label-clipping bugs, both from fixed pixel margins that
  didn't scale with label content: y-axis ticks with wide formatted
  values (e.g. `₹200000.0L`) were cut off against a fixed 44px left
  margin, and a fixed 56px/point line-chart spacing made 18-month
  trends ~1000px wide inside a ~550px card — technically scrollable,
  but the unscrolled view showed a stray clipped label at the cutoff,
  reading as broken rather than "scroll for more." Fixed by sizing
  margins from actual label-string length and scaling point spacing
  down for longer series (with a floor) so a typical trend fits without
  scrolling. Caught by actually screenshotting the rendered charts
  (the skill's final "render it and look at it" step) — `tsc`/`next
  build` were clean the whole time since neither bug is a type error.

## Money + price-position pages (T26)
- Found and fixed a real gap in T19's `mart_price_position`:
  `raw_bazaarpulse_products.competitor_mrp_inr` (the competitor
  listing's own printed MRP) is fully populated — 1,134/1,134 matched
  listings, all 5 retailers — but was never carried through the mart,
  which only surfaced the observed street price. The brief's own ask
  ("Kestrel MRP vs. what competitors are actually charging") and this
  task's explicit "do not merge these" instruction both assume a real
  third field exists, so rather than fake it or collapse to two
  columns, extended `build_mart_price_position.py` to add
  `competitor_mrp_inr` (median across matched listings per city+SKU,
  broadcast across that pair's week rows — MRP is a per-listing label,
  not a weekly observation like price) and exposed it through
  `/api/price_position`. Rebuilt `analytics.db`; all prior acceptance
  checks plus two new ones (zero unfilled `competitor_mrp_inr`, not
  silently identical to the observed-price column) pass. Sanity-checked
  the values: competitor MRP is often exactly equal to Kestrel's own
  MRP (expected — T15's earlier finding that BazaarPulse's "competitors"
  are reselling Kestrel's own portfolio, not rival brands), and
  competitor MRP exceeds observed price in ~81% of rows, consistent
  with retailers typically discounting off list price.
- The price-position table visually distinguishes the three price
  columns with light background tints (blue/gray/amber) in addition to
  distinct text headers, so "Kestrel MRP / Competitor MRP / Competitor
  observed price" don't read as one undifferentiated block of numbers —
  a light table-only treatment, not a dataviz mark, so it doesn't
  interact with the categorical palette rules.
- The money and price-position pages surface "worst" tables the API
  doesn't provide directly (unlike service/coldchain's `worst_outlets`/
  `worst_routes`) — sorted client-side by highest freight cost per case
  and largest MRP-vs-street gap respectively, matching the brief's
  "worst performers immediately, not after four clicks" for all four
  pillars, not just the two with a backend-provided ranking.
- A ~55-point weekly trend (price-position, unfiltered) exposed that
  `LineChart`'s point-spacing floor (24px, set in T25) still overflowed
  its card — 1,392px in a 582px container. Lowered the floor to 3px:
  there's no readability reason to protect a minimum pixel gap between
  points (hover already snaps to the nearest point regardless of
  spacing), unlike the label-width floor, which is a real constraint.

## Ask-anything page (T27)
- Found and fixed a real robustness gap in T23's `/api/ask`: the local
  Ollama model (`qwen3:4b`) routinely ignored the "output ONLY the SQL
  statement" instruction and wrapped the query in explanatory prose
  before *and* after a fenced code block — a shape T23's
  `_strip_code_fences` never handled (it only stripped a fence if the
  *entire* response was one, so a wrapped response fell through as raw
  prose and got correctly-but-uselessly rejected as invalid SQL syntax).
  Replaced it with `_extract_sql`, which searches for a fenced block
  anywhere in the response via regex and falls back to the raw text
  only if no fence is found. Verified against both a real prose-wrapped
  Ollama response (previously failed, now extracts cleanly) and the
  T23 destructive-prompt-injection regression test (still correctly
  rejected, table untouched) — the extraction change doesn't loosen
  the safety validator at all, it only widens what counts as "found the
  SQL" before that validator ever sees it.
- Manually exercised both acceptance-test legs end-to-end through the
  UI (not just curl): a real question against local Ollama rendered a
  natural-language answer, the SQL in a `<details>` block, and a 5-row
  result table, zero console errors; then restarting the backend with
  `OLLAMA_BASE_URL` pointed at an unreachable port (rather than
  disrupting the user's actual running Ollama instance) reproduced the
  "neither provider available" state cleanly — rendered as a calm blue
  informational box, not styled as an error, with zero console errors.
- Swapped `Nav.tsx` from plain `<a>` tags back to `next/link`'s typed
  `Link` now that all five pillar pages exist (T24 had deferred this
  exact swap in a comment, since Next's typed-routes feature rejects
  `Link` hrefs that don't resolve to a real page at build time) —
  verified every nav link now does a client-side transition with zero
  console errors.
