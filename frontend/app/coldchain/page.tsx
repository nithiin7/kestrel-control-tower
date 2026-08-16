"use client";

import { getColdchain, type ColdchainResponse } from "@/lib/api";
import { groupByAverage, sortByLabel } from "@/lib/aggregate";
import { useApiData } from "@/lib/useApiData";
import { useFilters } from "@/lib/FilterContext";
import { BarChart } from "@/components/charts/BarChart";
import { LineChart } from "@/components/charts/LineChart";
import { Card, CardHeading, ChartHeading, EmptyRow, ErrorBanner, PageHeader, Td, Th } from "@/components/ui";

export default function ColdchainPage() {
  const { filters } = useFilters();
  const { data, loading, error } = useApiData<ColdchainResponse>(() => getColdchain(filters), [filters]);

  const trend = data
    ? sortByLabel(groupByAverage(data.rows, (r) => r.month, (r) => r.excursions_per_100_chilled_deliveries))
    : [];

  // near_expiry_stock_value_inr is a warehouse-month snapshot broadcast onto
  // every route row in that group (same value repeated per route) — summing
  // across routes would multiply-count it, and summing across months would
  // add up a point-in-time stock value as if it were a flow. Restrict to the
  // latest month that actually has inventory-snapshot coverage (the mart's
  // trailing month or two can be delivery-only spillover with zero snapshot
  // data) and average across the (identical) route duplicates.
  const latestMonth = data
    ? data.rows
        .filter((r) => r.near_expiry_stock_value_inr > 0)
        .reduce((max, r) => (r.month > max ? r.month : max), "")
    : "";
  const byWarehouse = data
    ? groupByAverage(
        data.rows.filter((r) => r.month === latestMonth),
        (r) => r.warehouse_code,
        (r) => r.near_expiry_stock_value_inr
      )
    : [];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Cold Chain" description="Temperature excursions and near-expiry stock exposure by route and warehouse." />

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <Card loading={loading}>
        <CardHeading>Worst cold-chain routes</CardHeading>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <Th>Route</Th>
                <Th>Warehouse</Th>
                <Th>Month</Th>
                <Th align="right">Chilled deliveries</Th>
                <Th align="right">Excursions</Th>
                <Th align="right">Rate / 100</Th>
              </tr>
            </thead>
            <tbody>
              {data?.worst_routes.map((r) => (
                <tr key={`${r.route_code}-${r.month}`} className="border-b border-gray-100 hover:bg-gray-50">
                  <Td className="font-medium text-gray-900">{r.route_code}</Td>
                  <Td className="text-gray-600">{r.warehouse_code}</Td>
                  <Td className="text-gray-600">{r.month}</Td>
                  <Td align="right" className="text-gray-700">
                    {r.chilled_delivery_count}
                  </Td>
                  <Td align="right" className="text-gray-700">
                    {r.excursion_count}
                  </Td>
                  <Td align="right" className="font-semibold text-[#d03b3b]">
                    {r.excursions_per_100_chilled_deliveries.toFixed(1)}
                  </Td>
                </tr>
              ))}
              {data && data.worst_routes.length === 0 && <EmptyRow colSpan={6} />}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card loading={loading}>
          <ChartHeading>Excursion rate trend (avg / 100, by month)</ChartHeading>
          <LineChart data={trend} valueFormat={(v) => v.toFixed(1)} />
        </Card>

        <Card loading={loading}>
          <ChartHeading>Near-expiry stock value by warehouse, {latestMonth || "latest month"} (₹)</ChartHeading>
          <BarChart data={byWarehouse} valueFormat={(v) => `₹${(v / 100000).toFixed(1)}L`} />
        </Card>
      </div>
    </div>
  );
}
