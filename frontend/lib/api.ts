const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`API request failed: ${res.status} ${res.statusText} (${path})`);
  }
  return res.json() as Promise<T>;
}

export interface Region {
  region_id: number;
  region_code: string;
  region_name: string;
}

export interface Warehouse {
  warehouse_id: number;
  warehouse_code: string;
  warehouse_name: string;
  region_id: number;
}

export interface Route {
  route_id: number;
  route_code: string;
  warehouse_id: number;
}

export interface Outlet {
  outlet_code: string;
  outlet_name: string;
  region_id: number;
  route_id: number;
}

export interface LatestCompleteQuarter {
  fiscal_year: string;
  fiscal_quarter: number;
  fiscal_quarter_label: string;
  start_date: string;
  end_date: string;
}

export interface Filters {
  regions: Region[];
  warehouses: Warehouse[];
  routes: Route[];
  outlets: Outlet[];
  fiscal_quarters: string[];
  latest_complete_quarter: LatestCompleteQuarter | null;
}

export function getFilters(): Promise<Filters> {
  return apiFetch<Filters>("/api/meta/filters");
}

export interface QueryFilters {
  region?: string;
  warehouse?: string;
  route?: string;
  outlet?: string;
  city?: string;
  date_from?: string;
  date_to?: string;
}

function toQueryString(filters: QueryFilters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export interface ServiceRow {
  region_id: number;
  region_name: string;
  warehouse_id: number;
  warehouse_code: string;
  route_id: number;
  route_code: string;
  outlet_code: string;
  outlet_name: string;
  month: string;
  order_count: number;
  ordered_eaches: number;
  delivered_eaches: number;
  fill_rate_eaches: number;
  otif_orders: number;
  otif_pct: number;
}

export interface ServiceResponse {
  rows: ServiceRow[];
  worst_outlets: ServiceRow[];
}

export function getService(filters: QueryFilters = {}): Promise<ServiceResponse> {
  return apiFetch<ServiceResponse>(`/api/service${toQueryString(filters)}`);
}

export interface ColdchainRow {
  warehouse_id: number;
  warehouse_code: string;
  route_id: number;
  route_code: string;
  month: string;
  chilled_delivery_count: number;
  excursion_count: number;
  excursions_per_100_chilled_deliveries: number;
  near_expiry_stock_value_inr: number;
  cold_chain_return_value_inr: number;
  cold_chain_return_count: number;
}

export interface ColdchainResponse {
  rows: ColdchainRow[];
  worst_routes: ColdchainRow[];
}

export function getColdchain(filters: QueryFilters = {}): Promise<ColdchainResponse> {
  return apiFetch<ColdchainResponse>(`/api/coldchain${toQueryString(filters)}`);
}

export interface MoneyRow {
  warehouse_id: number;
  warehouse_code: string;
  route_id: number;
  route_code: string;
  month: string;
  freight_amount_inr: number;
  delivered_cases: number;
  freight_cost_per_case_inr: number | null;
}

export interface MoneyResponse {
  rows: MoneyRow[];
}

export function getMoney(filters: QueryFilters = {}): Promise<MoneyResponse> {
  return apiFetch<MoneyResponse>(`/api/money${toQueryString(filters)}`);
}

export interface PricePositionRow {
  city: string;
  category: string;
  sku_code: string;
  week: string;
  kestrel_mrp_inr: number;
  competitor_mrp_inr: number | null;
  competitor_price_inr: number | null;
  competitor_price_min_inr: number | null;
  competitor_listing_count: number;
  gap_pct: number | null;
  gap_pct_vs_min: number | null;
}

export interface PricePositionResponse {
  rows: PricePositionRow[];
}

export function getPricePosition(filters: QueryFilters = {}): Promise<PricePositionResponse> {
  return apiFetch<PricePositionResponse>(`/api/price_position${toQueryString(filters)}`);
}
