"use client";

import { useState } from "react";

export interface BarDatum {
  label: string;
  value: number;
}

interface BarChartProps {
  data: BarDatum[];
  valueFormat?: (v: number) => string;
  height?: number;
}

const BAR_WIDTH = 24;
const BAND_WIDTH = 56;
const CHART_HEIGHT_DEFAULT = 180;
const BASE_MARGIN = { top: 16, right: 8, bottom: 28, left: 12 };
// Rough monospace-ish width estimate at fontSize 10 — avoids clipping wide
// labels (currency in lakhs, percentages) against the SVG's own viewport,
// which clips content outside its bounds with no scroll to recover it.
const CHAR_WIDTH_PX = 5.6;

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalized = value / magnitude;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
}

export function BarChart({ data, valueFormat = (v) => v.toFixed(1), height = CHART_HEIGHT_DEFAULT }: BarChartProps) {
  const [hovered, setHovered] = useState<number | null>(null);

  if (data.length === 0) {
    return <p className="text-sm text-gray-400">No data.</p>;
  }

  const maxValue = niceMax(Math.max(...data.map((d) => d.value)));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * maxValue);
  const longestTickLabel = Math.max(...ticks.map((t) => valueFormat(t).length));
  const MARGIN = { ...BASE_MARGIN, left: BASE_MARGIN.left + longestTickLabel * CHAR_WIDTH_PX };
  const plotHeight = height - MARGIN.top - MARGIN.bottom;
  const width = MARGIN.left + MARGIN.right + data.length * BAND_WIDTH;

  return (
    <div className="viz-root relative overflow-x-auto">
      <svg width={width} height={height} role="img" aria-label="Bar chart">
        {ticks.map((tick) => {
          const y = MARGIN.top + plotHeight - (tick / maxValue) * plotHeight;
          return (
            <g key={tick}>
              <line
                x1={MARGIN.left}
                x2={width - MARGIN.right}
                y1={y}
                y2={y}
                stroke="var(--viz-grid)"
                strokeWidth={1}
              />
              <text x={MARGIN.left - 8} y={y} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="var(--viz-text-muted)">
                {valueFormat(tick)}
              </text>
            </g>
          );
        })}

        {data.map((d, i) => {
          const barHeight = Math.max((d.value / maxValue) * plotHeight, 0);
          const x = MARGIN.left + i * BAND_WIDTH + (BAND_WIDTH - BAR_WIDTH) / 2;
          const y = MARGIN.top + plotHeight - barHeight;
          const isHovered = hovered === i;

          return (
            <g key={d.label}>
              <rect
                x={x}
                y={y}
                width={BAR_WIDTH}
                height={Math.max(barHeight, 1)}
                rx={4}
                fill="var(--viz-series-1)"
                opacity={isHovered ? 0.85 : 1}
                tabIndex={0}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered((h) => (h === i ? null : h))}
                onFocus={() => setHovered(i)}
                onBlur={() => setHovered((h) => (h === i ? null : h))}
                style={{ cursor: "pointer" }}
              >
                <title>
                  {d.label}: {valueFormat(d.value)}
                </title>
              </rect>
              <text
                x={x + BAR_WIDTH / 2}
                y={height - MARGIN.bottom + 16}
                textAnchor="middle"
                fontSize={10}
                fill="var(--viz-text-secondary)"
              >
                {d.label}
              </text>
            </g>
          );
        })}
      </svg>

      {hovered !== null && (
        <div className="pointer-events-none absolute left-2 top-0 rounded border border-gray-200 bg-white px-2 py-1 text-xs shadow">
          <span className="font-semibold text-gray-900">{valueFormat(data[hovered].value)}</span>{" "}
          <span className="text-gray-500">{data[hovered].label}</span>
        </div>
      )}
    </div>
  );
}
