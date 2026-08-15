"use client";

import { useEffect, useState } from "react";
import { getMoney, type MoneyResponse, type MoneyRow } from "@/lib/api";
import { groupByAverage, sortByLabel } from "@/lib/aggregate";
import { useFilters } from "@/lib/FilterContext";
import { BarChart } from "@/components/charts/BarChart";
import { LineChart } from "@/components/charts/LineChart";

const WORST_N = 10;

export default function MoneyPage() {
  const { filters } = useFilters();
  const [data, setData] = useState<MoneyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getMoney(filters)
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [filters]);

  const priced: MoneyRow[] = data ? data.rows.filter((r) => r.freight_cost_per_case_inr !== null) : [];
  const worstRoutes = [...priced]
    .sort((a, b) => (b.freight_cost_per_case_inr ?? 0) - (a.freight_cost_per_case_inr ?? 0))
    .slice(0, WORST_N);

  const trend = sortByLabel(groupByAverage(priced, (r) => r.month, (r) => r.freight_cost_per_case_inr as number));
  const byWarehouse = groupByAverage(priced, (r) => r.warehouse_code, (r) => r.freight_cost_per_case_inr as number);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Money</h1>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
      )}

      <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm" style={{ opacity: loading ? 0.6 : 1 }}>
        <h2 className="mb-2 text-lg font-semibold">Highest freight cost per delivered case</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="py-1 pr-3">Warehouse</th>
              <th className="py-1 pr-3">Route</th>
              <th className="py-1 pr-3">Month</th>
              <th className="py-1 pr-3 text-right">Freight amount</th>
              <th className="py-1 pr-3 text-right">Delivered cases</th>
              <th className="py-1 text-right">₹ / case</th>
            </tr>
          </thead>
          <tbody>
            {worstRoutes.map((r) => (
              <tr key={`${r.route_code}-${r.month}`} className="border-b border-gray-100">
                <td className="py-1 pr-3">{r.warehouse_code}</td>
                <td className="py-1 pr-3">{r.route_code}</td>
                <td className="py-1 pr-3">{r.month}</td>
                <td className="py-1 pr-3 text-right">₹{r.freight_amount_inr.toLocaleString("en-IN")}</td>
                <td className="py-1 pr-3 text-right">{r.delivered_cases.toFixed(1)}</td>
                <td className="py-1 text-right font-medium text-[#d03b3b]">
                  ₹{r.freight_cost_per_case_inr?.toFixed(2)}
                </td>
              </tr>
            ))}
            {data && worstRoutes.length === 0 && (
              <tr>
                <td colSpan={6} className="py-3 text-center text-gray-400">
                  No rows match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2" style={{ opacity: loading ? 0.6 : 1 }}>
        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-2 text-sm font-medium text-gray-500">Freight cost per case trend (avg ₹, by month)</h2>
          <LineChart data={trend} valueFormat={(v) => `₹${v.toFixed(0)}`} />
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-2 text-sm font-medium text-gray-500">Freight cost per case by warehouse (avg ₹)</h2>
          <BarChart data={byWarehouse} valueFormat={(v) => `₹${v.toFixed(0)}`} />
        </section>
      </div>
    </div>
  );
}
