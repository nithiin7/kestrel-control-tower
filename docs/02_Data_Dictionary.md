# Kestrel Provisions: Operational Database

`data/kestrel_ops.db` (SQLite 3) and `data/csv/`

18 months of history, 1 January 2025 to 30 June 2026. Roughly 820,000 rows across 13 tables.

> **Status of this document.** Partial. It was written by a business analyst who left in March and has not been maintained. Several columns below are undocumented and a few of the descriptions are known to be wrong. Where this document and the data disagree, the data wins. If something matters to your answer, verify it against the data before you rely on it.

---

## Table summary

| Table | Rows | Cols | Grain |
|---|---|---|---|
| `regions` | 5 | 7 | One row per sales region |
| `warehouses` | 8 | 16 | One row per distribution centre |
| `routes` | 140 | 15 | One row per delivery route |
| `salespeople` | 95 | 11 | One row per field sales employee |
| `outlets` | 724 | 31 | One row per retail outlet |
| `products` | 341 | 26 | One row per SKU, current state only |
| `product_price_history` | 402 | 8 | One row per SKU per price validity window |
| `promotions` | 70 | 13 | One row per trade promotion |
| `orders` | 83,671 | 23 | One row per sales order header |
| `order_lines` | 511,516 | 16 | One row per order line |
| `deliveries` | 76,889 | 21 | One row per delivery note |
| `inventory_snapshots` | 131,040 | 15 | Warehouse x SKU x batch, weekly (Mondays) |
| `returns_credit_notes` | 14,000 | 15 | One row per credit note line |

---

## `outlets`

| Column | Notes |
|---|---|
| `outlet_id` | Surrogate key. Join key for `orders`. |
| `outlet_code` | Business key. Format `OUT#####`. |
| `outlet_name` | Free text, entered by the field team. |
| `legal_name` | Sparsely populated. |
| `channel` | `GT`, `MT`, `HORECA`, `ECOM_DARKSTORE`. |
| `outlet_format` | Sub-classification within channel. |
| `city`, `state` | Entered by the field team. Not validated against a master. |
| `region_id` | FK to `regions`. |
| `route_id`, `salesperson_id` | Current assignment, not historical. |
| `credit_limit_inr`, `credit_terms_days` | Commercial terms. |
| `chiller_available` | 1 if the outlet can take chilled stock. |
| `status` | `ACTIVE`, `CLOSED`, `DELETED`. |
| `closed_date` | Populated where `status = CLOSED`. |
| `is_deleted` | Soft delete flag. The application filters on this. Direct SQL does not. |
| `risk_flag`, `last_audit_date`, `avg_monthly_footfall` | Undocumented. |

## `products`

Current state only. There is no slowly changing dimension on this table. `mrp_inr` and `list_price_inr` reflect the price as at today, not as at the order date. `product_price_history` holds the validity windows.

| Column | Notes |
|---|---|
| `sku_code` | Business key. |
| `pack_size_value`, `pack_size_uom` | Consumer pack size. `G`, `ML`, `KG`. |
| `case_pack` | Consumer units per case. |
| `mrp_inr` | Current maximum retail price. |
| `list_price_inr` | Current price to trade, per consumer unit. |
| `is_chilled`, `storage_temp_band` | Cold chain classification. |
| `discontinued_date` | Populated where `status = DISCONTINUED`. |
| `abc_class`, `min_order_qty_cases`, `hsn_code` | Undocumented. |

## `orders`

| Column | Notes |
|---|---|
| `order_status` | `DELIVERED`, `PARTIAL`, `CANCELLED`, `OPEN`. |
| `order_value_gross_inr` | Header value. *Analyst note: should tie to the sum of `order_lines.line_value_inr`. Finance have raised a mismatch twice and it was never closed out.* |
| `order_value_net_inr` | Gross less discount plus tax. |
| `source_system` | `SFA_MOBILE` (field app), `ERP_WEB` (portal), `PARTNER_API` (e-commerce). |
| `created_at` | Text. Format varies by source system. Not normalised. |
| `order_date` | Local date. |
| `promo_code` | FK to `promotions.promo_code`, nullable. |
| `credit_hold_flag`, `priority_flag` | Undocumented. |

## `order_lines`

| Column | Notes |
|---|---|
| `ordered_qty`, `allocated_qty`, `delivered_qty` | Quantities. |
| `qty_uom` | Unit in which the line was booked. **Not constant across lines.** |
| `case_pack_at_order` | Case pack captured at order time. |
| `unit_price_inr` | Price per unit of `qty_uom`. |
| `line_value_inr` | Extended value net of `line_discount_pct`. |
| `short_reason_code` | Populated where delivered is short of ordered. |

## `deliveries`

| Column | Notes |
|---|---|
| `planned_arrival`, `actual_arrival` | Text. `actual_arrival` format depends on `telematics_vendor`. |
| `telematics_vendor` | `TELEMATICS_A`, `TELEMATICS_B`. |
| `delay_minutes` | Signed. Negative means early. |
| `temperature_excursion_flag` | 1 where the reefer breached its band at any point. |
| `max_temp_celsius` | Peak temperature observed in transit. |
| `pod_captured` | Proof of delivery captured on the driver app. |
| `failure_reason_code` | Populated on significant delays. |
| `fuel_cost_inr` | Driver-entered. Not reconciled to carrier invoices. |

## `inventory_snapshots`

Weekly, taken on Mondays. Not every SKU appears at every warehouse in every week.

| Column | Notes |
|---|---|
| `on_hand_cases`, `on_hand_eaches` | Two representations of the same stock. |
| `available_cases` | On hand less allocated. |
| `days_of_cover` | Calculated upstream. Method not documented. |
| `expiry_date`, `ageing_bucket` | Batch level. |
| `damaged_cases`, `blocked_cases` | Not available for sale. |

## `returns_credit_notes`

| Column | Notes |
|---|---|
| `return_qty` | Quantity returned. Sign convention is inconsistent between upstream systems. |
| `qty_uom` | Inherited from the originating order line. |
| `return_reason_code` | `RT01` near expiry, `RT02` transit damage, `RT03` wrong SKU, `RT04` quality, `RT05` oversupply, `RT06` cold chain breach. |
| `disposition` | `SCRAP`, `RESTOCK`, `VENDOR_RECOVERY`. |
| `approval_date` | Never populated. Known defect. |

---

## Known issues log

Extracted from the analyst's handover note. It is not exhaustive and the ticket numbers no longer resolve.

- KP-2211: outlet master has duplicates following the 2025 ownership transfer programme. Not remediated.
- KP-2288: city names are free text. Several cities have more than one spelling in use.
- KP-2301: order header value does not reconcile to line values for one source system. Root cause not established.
- KP-2340: quantity unit of measure is captured per line rather than standardised. Reporting team maintain a conversion spreadsheet.
- KP-2377: test and migration outlets were never removed from production.
- KP-2402: credit note quantities appear as negative values from one upstream feed.

Anything not in this list you will have to find yourself.
