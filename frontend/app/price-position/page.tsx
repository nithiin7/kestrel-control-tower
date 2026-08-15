"use client";

import { useEffect, useState } from "react";
import { getPricePosition, type PricePositionResponse, type PricePositionRow } from "@/lib/api";
import { groupByAverage, sortByLabel } from "@/lib/aggregate";
import { useFilters } from "@/lib/FilterContext";
import { BarChart } from "@/components/charts/BarChart";
import { LineChart } from "@/components/charts/LineChart";
import { Card, CardHeading, ChartHeading, EmptyRow, ErrorBanner, PageHeader, Td, Th } from "@/components/ui";

const WORST_N = 10;

export default function PricePositionPage() {
  const { filters } = useFilters();
  const [data, setData] = useState<PricePositionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getPricePosition(filters)
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [filters]);

  const rows: PricePositionRow[] = data ? data.rows.filter((r) => r.gap_pct !== null) : [];
  const mostOverpriced = [...rows].sort((a, b) => (b.gap_pct ?? 0) - (a.gap_pct ?? 0)).slice(0, WORST_N);

  const trend = sortByLabel(groupByAverage(rows, (r) => r.week, (r) => r.gap_pct as number));
  const byCity = groupByAverage(rows, (r) => r.city, (r) => r.gap_pct as number);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Price Position"
        description={
          <>
            Kestrel&apos;s MRP vs. the competitor listing&apos;s own MRP vs. what competitors are actually charging
            (observed street price) — scoped to the 4 cities BazaarPulse covers.
          </>
        }
      />

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <Card loading={loading}>
        <CardHeading>Kestrel priced highest above competitor street price</CardHeading>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <Th>SKU</Th>
                <Th>City</Th>
                <Th>Week</Th>
                <Th align="right" className="bg-blue-50">
                  Kestrel MRP
                </Th>
                <Th align="right" className="bg-gray-100">
                  Competitor MRP
                </Th>
                <Th align="right" className="bg-amber-50">
                  Competitor observed price
                </Th>
                <Th align="right">Gap</Th>
              </tr>
            </thead>
            <tbody>
              {mostOverpriced.map((r) => (
                <tr key={`${r.city}-${r.sku_code}-${r.week}`} className="border-b border-gray-100 hover:bg-gray-50">
                  <Td className="font-medium text-gray-900">{r.sku_code}</Td>
                  <Td className="text-gray-600">{r.city}</Td>
                  <Td className="text-gray-600">{r.week}</Td>
                  <Td align="right" className="bg-blue-50/60 text-gray-700">
                    ₹{r.kestrel_mrp_inr.toFixed(2)}
                  </Td>
                  <Td align="right" className="bg-gray-50 text-gray-700">
                    {r.competitor_mrp_inr !== null ? `₹${r.competitor_mrp_inr.toFixed(2)}` : "—"}
                  </Td>
                  <Td align="right" className="bg-amber-50/60 text-gray-700">
                    {r.competitor_price_inr !== null ? `₹${r.competitor_price_inr.toFixed(2)}` : "—"}
                  </Td>
                  <Td align="right" className="font-semibold text-[#d03b3b]">
                    +{r.gap_pct?.toFixed(1)}%
                  </Td>
                </tr>
              ))}
              {data && mostOverpriced.length === 0 && <EmptyRow colSpan={7} />}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card loading={loading}>
          <ChartHeading>MRP vs. street price gap trend (avg %, by week)</ChartHeading>
          <LineChart data={trend} valueFormat={(v) => `${v.toFixed(0)}%`} />
        </Card>

        <Card loading={loading}>
          <ChartHeading>Gap by city (avg %)</ChartHeading>
          <BarChart data={byCity} valueFormat={(v) => `${v.toFixed(0)}%`} />
        </Card>
      </div>
    </div>
  );
}
