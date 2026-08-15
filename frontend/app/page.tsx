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
import { Card, ErrorBanner } from "@/components/ui";

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
    <div className="flex flex-col gap-8">
      <Card className="p-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">Latest complete quarter</p>
        {quarter ? (
          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-3xl font-semibold tracking-tight text-gray-900">{quarter.fiscal_quarter_label}</span>
            <span className="text-sm text-gray-500">
              {quarter.start_date} – {quarter.end_date}
            </span>
          </div>
        ) : (
          <div className="mt-3 h-8 w-48 animate-pulse rounded bg-gray-100" />
        )}
      </Card>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <section>
        <h2 className="mb-3 text-base font-semibold text-gray-900">Worst of worst</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <WorstCard title="Lowest fill rate outlets">
            {worst?.worstOutlets.map((o, i) => (
              <RankRow
                key={`${o.outlet_code}-${o.month}`}
                rank={i + 1}
                label={o.outlet_name}
                sub={o.month}
                value={`${o.fill_rate_eaches.toFixed(1)}%`}
              />
            ))}
          </WorstCard>

          <WorstCard title="Highest cold-chain excursion rate">
            {worst?.worstColdchainRoutes.map((r, i) => (
              <RankRow
                key={`${r.route_code}-${r.month}`}
                rank={i + 1}
                label={r.route_code}
                sub={r.month}
                value={`${r.excursions_per_100_chilled_deliveries.toFixed(1)}/100`}
              />
            ))}
          </WorstCard>

          <WorstCard title="Highest freight cost per case">
            {worst?.worstMoneyRoutes.map((r, i) => (
              <RankRow
                key={`${r.route_code}-${r.month}`}
                rank={i + 1}
                label={r.route_code}
                sub={r.month}
                value={`₹${r.freight_cost_per_case_inr?.toFixed(2)}`}
              />
            ))}
          </WorstCard>

          <WorstCard title="Largest MRP vs. competitor gap">
            {worst?.worstPricePositions.map((r, i) => (
              <RankRow
                key={`${r.city}-${r.sku_code}-${r.week}`}
                rank={i + 1}
                label={`${r.sku_code} · ${r.city}`}
                sub={r.week}
                value={`+${r.gap_pct?.toFixed(1)}%`}
              />
            ))}
          </WorstCard>
        </div>
      </section>
    </div>
  );
}

function WorstCard({ title, children }: { title: string; children: React.ReactNode }) {
  const hasContent = Array.isArray(children) ? children.length > 0 : Boolean(children);
  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
      <div className="h-1 bg-[#d03b3b]" />
      <div className="p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400">{title}</h3>
        <ul className="mt-3 flex flex-col gap-2.5 text-sm">
          {hasContent ? children : <SkeletonRows />}
        </ul>
      </div>
    </div>
  );
}

function RankRow({ rank, label, sub, value }: { rank: number; label: string; sub: string; value: string }) {
  return (
    <li className="flex items-center gap-3">
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-gray-100 text-[10px] font-semibold text-gray-500">
        {rank}
      </span>
      <span className="min-w-0 flex-1 truncate text-gray-700">{label}</span>
      <span className="shrink-0 text-right">
        <span className="block font-semibold text-[#d03b3b]">{value}</span>
        <span className="block text-[10px] text-gray-400">{sub}</span>
      </span>
    </li>
  );
}

function SkeletonRows() {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <li key={i} className="h-5 animate-pulse rounded bg-gray-100" />
      ))}
    </>
  );
}
