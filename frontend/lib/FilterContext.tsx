"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { QueryFilters } from "./api";

interface FilterContextValue {
  filters: QueryFilters;
  setFilter: (key: keyof QueryFilters, value: string) => void;
}

const FilterContext = createContext<FilterContextValue | null>(null);

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<QueryFilters>({});

  const setFilter = (key: keyof QueryFilters, value: string) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (value) {
        next[key] = value;
      } else {
        delete next[key];
      }
      return next;
    });
  };

  const value = useMemo(() => ({ filters, setFilter }), [filters]);

  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>;
}

export function useFilters(): FilterContextValue {
  const ctx = useContext(FilterContext);
  if (!ctx) {
    throw new Error("useFilters must be used within a FilterProvider");
  }
  return ctx;
}
