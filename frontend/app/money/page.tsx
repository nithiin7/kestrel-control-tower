"use client";

import { getMoney, type MoneyResponse, type MoneyRow } from "@/lib/api";
import { groupByAverage, sortByLabel, topNByValue } from "@/lib/aggregate";
import { useApiData } from "@/lib/useApiData";
import { useFilters } from "@/lib/FilterContext";
import { BarChart } from "@/components/charts/BarChart";
import { LineChart } from "@/components/charts/LineChart";
import { Card, CardHeading, ChartHeading, EmptyRow, ErrorBanner, PageHeader, Td, Th } from "@/components/ui";

const WORST_N = 10;

export default function MoneyPage() {
  const { filters } = useFilters();
  const { data, loading, error } = useApiData<MoneyResponse>(() => getMoney(filters), [filters]);

  const priced: MoneyRow[] = data ? data.rows.filter((r) => r.freight_cost_per_case_inr !== null) : [];
  const worstRoutes = topNByValue(priced, (r) => r.freight_cost_per_case_inr, WORST_N);

  const trend = sortByLabel(groupByAverage(priced, (r) => r.month, (r) => r.freight_cost_per_case_inr as number));
  const byWarehouse = groupByAverage(priced, (r) => r.warehouse_code, (r) => r.freight_cost_per_case_inr as number);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Money" description="Freight cost per delivered case by route and warehouse." />

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <Card loading={loading}>
        <CardHeading>Highest freight cost per delivered case</CardHeading>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <Th>Warehouse</Th>
                <Th>Route</Th>
                <Th>Month</Th>
                <Th align="right">Freight amount</Th>
                <Th align="right">Delivered cases</Th>
                <Th align="right">₹ / case</Th>
              </tr>
            </thead>
            <tbody>
              {worstRoutes.map((r) => (
                <tr key={`${r.route_code}-${r.month}`} className="border-b border-gray-100 hover:bg-gray-50">
                  <Td className="font-medium text-gray-900">{r.warehouse_code}</Td>
                  <Td className="text-gray-600">{r.route_code}</Td>
                  <Td className="text-gray-600">{r.month}</Td>
                  <Td align="right" className="text-gray-700">
                    ₹{r.freight_amount_inr.toLocaleString("en-IN")}
                  </Td>
                  <Td align="right" className="text-gray-700">
                    {r.delivered_cases.toFixed(1)}
                  </Td>
                  <Td align="right" className="font-semibold text-[#d03b3b]">
                    ₹{r.freight_cost_per_case_inr?.toFixed(2)}
                  </Td>
                </tr>
              ))}
              {data && worstRoutes.length === 0 && <EmptyRow colSpan={6} />}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card loading={loading}>
          <ChartHeading>Freight cost per case trend (avg ₹, by month)</ChartHeading>
          <LineChart data={trend} valueFormat={(v) => `₹${v.toFixed(0)}`} />
        </Card>

        <Card loading={loading}>
          <ChartHeading>Freight cost per case by warehouse (avg ₹)</ChartHeading>
          <BarChart data={byWarehouse} valueFormat={(v) => `₹${v.toFixed(0)}`} />
        </Card>
      </div>
    </div>
  );
}
