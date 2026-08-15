"use client";

import { useEffect, useState } from "react";
import { getService, type ServiceResponse } from "@/lib/api";
import { groupByAverage, sortByLabel } from "@/lib/aggregate";
import { useFilters } from "@/lib/FilterContext";
import { BarChart } from "@/components/charts/BarChart";
import { LineChart } from "@/components/charts/LineChart";

export default function ServicePage() {
  const { filters } = useFilters();
  const [data, setData] = useState<ServiceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getService(filters)
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [filters]);

  const trend = data
    ? sortByLabel(groupByAverage(data.rows, (r) => r.month, (r) => r.fill_rate_eaches))
    : [];
  const byRegion = data ? groupByAverage(data.rows, (r) => r.region_name, (r) => r.fill_rate_eaches) : [];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Service</h1>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
      )}

      <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm" style={{ opacity: loading ? 0.6 : 1 }}>
        <h2 className="mb-2 text-lg font-semibold">Worst-performing outlets</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="py-1 pr-3">Outlet</th>
              <th className="py-1 pr-3">Region</th>
              <th className="py-1 pr-3">Warehouse</th>
              <th className="py-1 pr-3">Month</th>
              <th className="py-1 pr-3 text-right">Fill rate</th>
              <th className="py-1 text-right">OTIF</th>
            </tr>
          </thead>
          <tbody>
            {data?.worst_outlets.map((o) => (
              <tr key={`${o.outlet_code}-${o.month}`} className="border-b border-gray-100">
                <td className="py-1 pr-3">{o.outlet_name}</td>
                <td className="py-1 pr-3">{o.region_name}</td>
                <td className="py-1 pr-3">{o.warehouse_code}</td>
                <td className="py-1 pr-3">{o.month}</td>
                <td className="py-1 pr-3 text-right font-medium text-[#d03b3b]">{o.fill_rate_eaches.toFixed(1)}%</td>
                <td className="py-1 text-right">{o.otif_pct.toFixed(1)}%</td>
              </tr>
            ))}
            {data && data.worst_outlets.length === 0 && (
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
          <h2 className="mb-2 text-sm font-medium text-gray-500">Fill rate trend (avg %, by month)</h2>
          <LineChart data={trend} valueFormat={(v) => `${v.toFixed(0)}%`} />
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="mb-2 text-sm font-medium text-gray-500">Fill rate by region (avg %)</h2>
          <BarChart data={byRegion} valueFormat={(v) => `${v.toFixed(0)}%`} />
        </section>
      </div>
    </div>
  );
}
