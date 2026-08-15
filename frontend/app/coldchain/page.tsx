"use client";

import { useEffect, useState } from "react";
import { getColdchain, type ColdchainResponse } from "@/lib/api";
import { groupByAverage, sortByLabel } from "@/lib/aggregate";
import { useFilters } from "@/lib/FilterContext";
import { BarChart } from "@/components/charts/BarChart";
import { LineChart } from "@/components/charts/LineChart";

export default function ColdchainPage() {
  const { filters } = useFilters();
  const [data, setData] = useState<ColdchainResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getColdchain(filters)
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [filters]);

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
      <h1 className="text-xl font-semibold">Cold Chain</h1>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
      )}

      <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm" style={{ opacity: loading ? 0.6 : 1 }}>
        <h2 className="mb-2 text-lg font-semibold">Worst cold-chain routes</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="py-1 pr-3">Route</th>
              <th className="py-1 pr-3">Warehouse</th>
              <th className="py-1 pr-3">Month</th>
              <th className="py-1 pr-3 text-right">Chilled deliveries</th>
              <th className="py-1 pr-3 text-right">Excursions</th>
              <th className="py-1 text-right">Rate / 100</th>
            </tr>
          </thead>
          <tbody>
            {data?.worst_routes.map((r) => (
              <tr key={`${r.route_code}-${r.month}`} className="border-b border-gray-100">
                <td className="py-1 pr-3">{r.route_code}</td>
                <td className="py-1 pr-3">{r.warehouse_code}</td>
                <td className="py-1 pr-3">{r.month}</td>
                <td className="py-1 pr-3 text-right">{r.chilled_delivery_count}</td>
                <td className="py-1 pr-3 text-right">{r.excursion_count}</td>
                <td className="py-1 text-right font-medium text-[#d03b3b]">
                  {r.excursions_per_100_chilled_deliveries.toFixed(1)}
                </td>
              </tr>
            ))}
            {data && data.worst_routes.length === 0 && (
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
          <h2 className="mb-2 text-sm font-medium text-gray-500">Excursion rate trend (avg / 100, by month)</h2>
          <LineChart data={trend} valueFormat={(v) => v.toFixed(1)} />
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-2 text-sm font-medium text-gray-500">
            Near-expiry stock value by warehouse, {latestMonth || "latest month"} (₹)
          </h2>
          <BarChart data={byWarehouse} valueFormat={(v) => `₹${(v / 100000).toFixed(1)}L`} />
        </section>
      </div>
    </div>
  );
}
