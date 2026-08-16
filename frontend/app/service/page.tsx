"use client";

import { getService, type ServiceResponse } from "@/lib/api";
import { groupByAverage, sortByLabel } from "@/lib/aggregate";
import { useApiData } from "@/lib/useApiData";
import { useFilters } from "@/lib/FilterContext";
import { BarChart } from "@/components/charts/BarChart";
import { LineChart } from "@/components/charts/LineChart";
import { Card, CardHeading, ChartHeading, EmptyRow, ErrorBanner, PageHeader, Td, Th } from "@/components/ui";

export default function ServicePage() {
  const { filters } = useFilters();
  const { data, loading, error } = useApiData<ServiceResponse>(() => getService(filters), [filters]);

  const trend = data
    ? sortByLabel(groupByAverage(data.rows, (r) => r.month, (r) => r.fill_rate_eaches))
    : [];
  const byRegion = data ? groupByAverage(data.rows, (r) => r.region_name, (r) => r.fill_rate_eaches) : [];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Service" description="Order fulfillment and on-time-in-full performance by outlet." />

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <Card loading={loading}>
        <CardHeading>Worst-performing outlets</CardHeading>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <Th>Outlet</Th>
                <Th>Region</Th>
                <Th>Warehouse</Th>
                <Th>Month</Th>
                <Th align="right">Fill rate</Th>
                <Th align="right">OTIF</Th>
              </tr>
            </thead>
            <tbody>
              {data?.worst_outlets.map((o) => (
                <tr key={`${o.outlet_code}-${o.month}`} className="border-b border-gray-100 hover:bg-gray-50">
                  <Td className="font-medium text-gray-900">{o.outlet_name}</Td>
                  <Td className="text-gray-600">{o.region_name}</Td>
                  <Td className="text-gray-600">{o.warehouse_code}</Td>
                  <Td className="text-gray-600">{o.month}</Td>
                  <Td align="right" className="font-semibold text-[#d03b3b]">
                    {o.fill_rate_eaches.toFixed(1)}%
                  </Td>
                  <Td align="right" className="text-gray-700">
                    {o.otif_pct.toFixed(1)}%
                  </Td>
                </tr>
              ))}
              {data && data.worst_outlets.length === 0 && <EmptyRow colSpan={6} />}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card loading={loading}>
          <ChartHeading>Fill rate trend (avg %, by month)</ChartHeading>
          <LineChart data={trend} valueFormat={(v) => `${v.toFixed(0)}%`} />
        </Card>

        <Card loading={loading}>
          <ChartHeading>Fill rate by region (avg %)</ChartHeading>
          <BarChart data={byRegion} valueFormat={(v) => `${v.toFixed(0)}%`} />
        </Card>
      </div>
    </div>
  );
}
