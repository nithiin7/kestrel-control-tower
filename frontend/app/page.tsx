"use client";

import { useEffect, useState } from "react";
import {
  getColdchain,
  getFilters,
  getMoney,
  getPricePosition,
  getService,
  type ColdchainRow,
  type LatestCompleteQuarter,
  type MoneyRow,
  type PricePositionRow,
  type ServiceRow,
} from "@/lib/api";

interface WorstOfWorst {
  worstOutlets: ServiceRow[];
  worstColdchainRoutes: ColdchainRow[];
  worstMoneyRoutes: MoneyRow[];
  worstPricePositions: PricePositionRow[];
}

const TOP_N = 3;

export default function Home() {
  const [quarter, setQuarter] = useState<LatestCompleteQuarter | null>(null);
  const [worst, setWorst] = useState<WorstOfWorst | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getFilters()
      .then((f) => setQuarter(f.latest_complete_quarter))
      .catch((err: Error) => setError(err.message));

    Promise.all([getService(), getColdchain(), getMoney(), getPricePosition()])
      .then(([service, coldchain, money, price]) => {
        const worstMoneyRoutes = [...money.rows]
          .filter((r) => r.freight_cost_per_case_inr !== null)
          .sort((a, b) => (b.freight_cost_per_case_inr ?? 0) - (a.freight_cost_per_case_inr ?? 0))
          .slice(0, TOP_N);

        const worstPricePositions = [...price.rows]
          .filter((r) => r.gap_pct !== null)
          .sort((a, b) => (b.gap_pct ?? 0) - (a.gap_pct ?? 0))
          .slice(0, TOP_N);

        setWorst({
          worstOutlets: service.worst_outlets.slice(0, TOP_N),
          worstColdchainRoutes: coldchain.worst_routes.slice(0, TOP_N),
          worstMoneyRoutes,
          worstPricePositions,
        });
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-medium uppercase tracking-wide text-gray-500">
          Latest complete quarter
        </h2>
        {quarter ? (
          <p className="mt-1 text-2xl font-semibold">
            {quarter.fiscal_quarter_label}{" "}
            <span className="text-base font-normal text-gray-500">
              ({quarter.start_date} – {quarter.end_date})
            </span>
          </p>
        ) : (
          <p className="mt-1 text-gray-400">Loading…</p>
        )}
      </section>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <section>
        <h2 className="mb-2 text-lg font-semibold">Worst of worst</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <WorstCard title="Lowest fill rate outlets">
            {worst?.worstOutlets.map((o) => (
              <li key={`${o.outlet_code}-${o.month}`}>
                {o.outlet_name} — {o.fill_rate_eaches.toFixed(1)}% ({o.month})
              </li>
            ))}
          </WorstCard>

          <WorstCard title="Highest cold-chain excursion rate">
            {worst?.worstColdchainRoutes.map((r) => (
              <li key={`${r.route_code}-${r.month}`}>
                {r.route_code} — {r.excursions_per_100_chilled_deliveries.toFixed(1)}/100 ({r.month})
              </li>
            ))}
          </WorstCard>

          <WorstCard title="Highest freight cost per case">
            {worst?.worstMoneyRoutes.map((r) => (
              <li key={`${r.route_code}-${r.month}`}>
                {r.route_code} — ₹{r.freight_cost_per_case_inr?.toFixed(2)} ({r.month})
              </li>
            ))}
          </WorstCard>

          <WorstCard title="Largest MRP vs. competitor gap">
            {worst?.worstPricePositions.map((r) => (
              <li key={`${r.city}-${r.sku_code}-${r.week}`}>
                {r.sku_code} in {r.city} — +{r.gap_pct?.toFixed(1)}%
              </li>
            ))}
          </WorstCard>
        </div>
      </section>
    </div>
  );
}

function WorstCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-medium text-gray-500">{title}</h3>
      <ul className="mt-2 space-y-1 text-sm">{children}</ul>
    </div>
  );
}
