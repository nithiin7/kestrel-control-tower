"use client";

import { useEffect, useState } from "react";
import { getFilters, type Filters } from "@/lib/api";
import { useFilters } from "@/lib/FilterContext";

export function FilterBar() {
  const [options, setOptions] = useState<Filters | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { filters, setFilter } = useFilters();

  useEffect(() => {
    getFilters()
      .then(setOptions)
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) {
    return <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">Filters unavailable: {error}</div>;
  }

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-gray-200 bg-gray-50 px-4 py-2 text-sm">
      <select
        aria-label="Region"
        className="rounded border border-gray-300 bg-white px-2 py-1"
        value={filters.region ?? ""}
        onChange={(e) => setFilter("region", e.target.value)}
      >
        <option value="">All regions</option>
        {options?.regions.map((r) => (
          <option key={r.region_id} value={r.region_name}>
            {r.region_name}
          </option>
        ))}
      </select>

      <select
        aria-label="Warehouse"
        className="rounded border border-gray-300 bg-white px-2 py-1"
        value={filters.warehouse ?? ""}
        onChange={(e) => setFilter("warehouse", e.target.value)}
      >
        <option value="">All warehouses</option>
        {options?.warehouses.map((w) => (
          <option key={w.warehouse_id} value={w.warehouse_code}>
            {w.warehouse_code} — {w.warehouse_name}
          </option>
        ))}
      </select>

      <select
        aria-label="Route"
        className="rounded border border-gray-300 bg-white px-2 py-1"
        value={filters.route ?? ""}
        onChange={(e) => setFilter("route", e.target.value)}
      >
        <option value="">All routes</option>
        {options?.routes.map((r) => (
          <option key={r.route_id} value={r.route_code}>
            {r.route_code}
          </option>
        ))}
      </select>

      <select
        aria-label="Outlet"
        className="rounded border border-gray-300 bg-white px-2 py-1"
        value={filters.outlet ?? ""}
        onChange={(e) => setFilter("outlet", e.target.value)}
      >
        <option value="">All outlets</option>
        {options?.outlets.map((o) => (
          <option key={o.outlet_code} value={o.outlet_code}>
            {o.outlet_code} — {o.outlet_name}
          </option>
        ))}
      </select>

      <label className="flex items-center gap-1">
        From
        <input
          type="date"
          className="rounded border border-gray-300 bg-white px-2 py-1"
          value={filters.date_from ?? ""}
          onChange={(e) => setFilter("date_from", e.target.value)}
        />
      </label>

      <label className="flex items-center gap-1">
        To
        <input
          type="date"
          className="rounded border border-gray-300 bg-white px-2 py-1"
          value={filters.date_to ?? ""}
          onChange={(e) => setFilter("date_to", e.target.value)}
        />
      </label>
    </div>
  );
}
