"use client";

import { useEffect, useState } from "react";
import { getPricePosition, type PricePositionResponse, type PricePositionRow } from "@/lib/api";
import { groupByAverage, sortByLabel } from "@/lib/aggregate";
import { useFilters } from "@/lib/FilterContext";
import { BarChart } from "@/components/charts/BarChart";
import { LineChart } from "@/components/charts/LineChart";

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
      <h1 className="text-xl font-semibold">Price Position</h1>
      <p className="text-sm text-gray-500">
        Kestrel&apos;s MRP vs. the competitor listing&apos;s own MRP vs. what competitors are actually
        charging (observed street price) — scoped to the 4 cities BazaarPulse covers.
      </p>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
      )}

      <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm" style={{ opacity: loading ? 0.6 : 1 }}>
        <h2 className="mb-2 text-lg font-semibold">Kestrel priced highest above competitor street price</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="py-1 pr-3">SKU</th>
              <th className="py-1 pr-3">City</th>
              <th className="py-1 pr-3">Week</th>
              <th className="py-1 pr-3 text-right bg-blue-50">Kestrel MRP</th>
              <th className="py-1 pr-3 text-right bg-gray-100">Competitor MRP</th>
              <th className="py-1 pr-3 text-right bg-amber-50">Competitor observed price</th>
              <th className="py-1 text-right">Gap</th>
            </tr>
          </thead>
          <tbody>
            {mostOverpriced.map((r) => (
              <tr key={`${r.city}-${r.sku_code}-${r.week}`} className="border-b border-gray-100">
                <td className="py-1 pr-3">{r.sku_code}</td>
                <td className="py-1 pr-3">{r.city}</td>
                <td className="py-1 pr-3">{r.week}</td>
                <td className="py-1 pr-3 text-right bg-blue-50/60">₹{r.kestrel_mrp_inr.toFixed(2)}</td>
                <td className="py-1 pr-3 text-right bg-gray-50">
                  {r.competitor_mrp_inr !== null ? `₹${r.competitor_mrp_inr.toFixed(2)}` : "—"}
                </td>
                <td className="py-1 pr-3 text-right bg-amber-50/60">
                  {r.competitor_price_inr !== null ? `₹${r.competitor_price_inr.toFixed(2)}` : "—"}
                </td>
                <td className="py-1 text-right font-medium text-[#d03b3b]">+{r.gap_pct?.toFixed(1)}%</td>
              </tr>
            ))}
            {data && mostOverpriced.length === 0 && (
              <tr>
                <td colSpan={7} className="py-3 text-center text-gray-400">
                  No rows match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2" style={{ opacity: loading ? 0.6 : 1 }}>
        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-2 text-sm font-medium text-gray-500">MRP vs. street price gap trend (avg %, by week)</h2>
          <LineChart data={trend} valueFormat={(v) => `${v.toFixed(0)}%`} />
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-2 text-sm font-medium text-gray-500">Gap by city (avg %)</h2>
          <BarChart data={byCity} valueFormat={(v) => `${v.toFixed(0)}%`} />
        </section>
      </div>
    </div>
  );
}
