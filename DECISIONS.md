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
