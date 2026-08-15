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
