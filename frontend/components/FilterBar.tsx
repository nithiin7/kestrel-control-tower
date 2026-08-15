"use client";

import { useEffect, useState, type ReactNode } from "react";
import { getFilters, type Filters } from "@/lib/api";
import { useFilters } from "@/lib/FilterContext";

const inputClass =
  "h-9 rounded-lg border border-gray-300 bg-white px-2.5 text-sm text-gray-900 shadow-sm outline-none transition-colors focus:border-[#2a78d6] focus:ring-2 focus:ring-[#2a78d6]/20";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-wide text-gray-400">{label}</span>
      {children}
    </label>
  );
}

export function FilterBar() {
  const [options, setOptions] = useState<Filters | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { filters, setFilter, resetFilters } = useFilters();

  useEffect(() => {
    getFilters()
      .then(setOptions)
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) {
    return (
      <div className="border-b border-red-200 bg-red-50 px-6 py-2 text-sm text-red-700">Filters unavailable: {error}</div>
    );
  }

  const activeCount = Object.keys(filters).length;

  return (
    <div className="sticky top-14.25 z-10 border-b border-gray-200 bg-gray-50/90 backdrop-blur supports-backdrop-filter:bg-gray-50/70">
      <div className="mx-auto flex max-w-7xl flex-wrap items-end gap-3 px-6 py-3">
        <Field label="Region">
          <select
            aria-label="Region"
            className={inputClass}
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
        </Field>

        <Field label="Warehouse">
          <select
            aria-label="Warehouse"
            className={inputClass}
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
        </Field>

        <Field label="Route">
          <select
            aria-label="Route"
            className={inputClass}
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
        </Field>

        <Field label="Outlet">
          <select
            aria-label="Outlet"
            className={inputClass}
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
        </Field>

        <Field label="From">
          <input
            type="date"
            className={inputClass}
            value={filters.date_from ?? ""}
            onChange={(e) => setFilter("date_from", e.target.value)}
          />
        </Field>

        <Field label="To">
          <input
            type="date"
            className={inputClass}
            value={filters.date_to ?? ""}
            onChange={(e) => setFilter("date_to", e.target.value)}
          />
        </Field>

        {activeCount > 0 && (
          <button
            type="button"
            onClick={resetFilters}
            className="h-9 rounded-lg px-3 text-sm font-medium text-gray-500 transition-colors hover:bg-gray-200 hover:text-gray-900"
          >
            Clear filters
          </button>
        )}
      </div>
    </div>
  );
}
