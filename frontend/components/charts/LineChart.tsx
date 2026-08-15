"use client";

import { useState, type MouseEvent } from "react";

export interface LinePoint {
  label: string;
  value: number;
}

interface LineChartProps {
  data: LinePoint[];
  valueFormat?: (v: number) => string;
  height?: number;
}

const CHART_HEIGHT_DEFAULT = 180;
const BASE_MARGIN = { top: 16, right: 16, bottom: 28, left: 12 };
// Fixed 56px/point made 18-month trends ~1000px wide inside a ~550px card —
// technically scrollable (overflow-x-auto) but the unscrolled view showed a
// stray clipped label at the cutoff, reading as a bug. Scale spacing down
// for longer series so a typical trend fits without scrolling; a sparse
// series (few points) still gets the roomier max spacing.
const TARGET_PLOT_WIDTH = 480;
const MIN_POINT_SPACING = 24;
const MAX_POINT_SPACING = 56;
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

export function LineChart({ data, valueFormat = (v) => v.toFixed(1), height = CHART_HEIGHT_DEFAULT }: LineChartProps) {
  const [hovered, setHovered] = useState<number | null>(null);

  if (data.length === 0) {
    return <p className="text-sm text-gray-400">No data.</p>;
  }

  const maxValue = niceMax(Math.max(...data.map((d) => d.value)));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * maxValue);
  const longestTickLabel = Math.max(...ticks.map((t) => valueFormat(t).length));
  // The last x-axis category label and the bold end-value label are both
  // centered/anchored at the final point, which sits at the plot's right
  // edge — give them half their own width of breathing room so they don't
  // overflow the SVG's own viewport (which clips silently, no scrollbar).
  const lastCategoryLabel = data[data.length - 1].label.length;
  const endValueLabel = valueFormat(data[data.length - 1].value).length;
  const rightLabelHalfWidth = (Math.max(lastCategoryLabel, endValueLabel) * CHAR_WIDTH_PX) / 2;
  const MARGIN = {
    ...BASE_MARGIN,
    left: BASE_MARGIN.left + longestTickLabel * CHAR_WIDTH_PX,
    right: BASE_MARGIN.right + rightLabelHalfWidth,
  };
  const plotHeight = height - MARGIN.top - MARGIN.bottom;
  const pointSpacing =
    data.length > 1
      ? Math.min(MAX_POINT_SPACING, Math.max(MIN_POINT_SPACING, TARGET_PLOT_WIDTH / (data.length - 1)))
      : MAX_POINT_SPACING;
  const width = MARGIN.left + MARGIN.right + Math.max(data.length - 1, 1) * pointSpacing;

  const xFor = (i: number) => MARGIN.left + i * pointSpacing;
  const yFor = (v: number) => MARGIN.top + plotHeight - (v / maxValue) * plotHeight;

  const linePath = data.map((d, i) => `${i === 0 ? "M" : "L"}${xFor(i)},${yFor(d.value)}`).join(" ");
  const areaPath = `${linePath} L${xFor(data.length - 1)},${MARGIN.top + plotHeight} L${xFor(0)},${MARGIN.top + plotHeight} Z`;

  const handleMove = (e: MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const idx = Math.round((x - MARGIN.left) / pointSpacing);
    setHovered(Math.min(Math.max(idx, 0), data.length - 1));
  };

  return (
    <div className="viz-root relative overflow-x-auto">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label="Line chart"
        onMouseMove={handleMove}
        onMouseLeave={() => setHovered(null)}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={MARGIN.left}
              x2={width - MARGIN.right}
              y1={yFor(tick)}
              y2={yFor(tick)}
              stroke="var(--viz-grid)"
              strokeWidth={1}
            />
            <text x={MARGIN.left - 8} y={yFor(tick)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="var(--viz-text-muted)">
              {valueFormat(tick)}
            </text>
          </g>
        ))}

        <path d={areaPath} fill="var(--viz-series-1)" opacity={0.1} stroke="none" />
        <path d={linePath} fill="none" stroke="var(--viz-series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

        {hovered !== null && (
          <line
            x1={xFor(hovered)}
            x2={xFor(hovered)}
            y1={MARGIN.top}
            y2={MARGIN.top + plotHeight}
            stroke="var(--viz-axis)"
            strokeWidth={1}
          />
        )}

        {data.map((d, i) => {
          const isEnd = i === data.length - 1;
          const isHovered = hovered === i;
          if (!isEnd && !isHovered) return null;
          return (
            <circle
              key={d.label}
              cx={xFor(i)}
              cy={yFor(d.value)}
              r={5}
              fill="var(--viz-series-1)"
              stroke="var(--viz-surface)"
              strokeWidth={2}
            />
          );
        })}

        {data.map((d, i) => (
          <text
            key={d.label}
            x={xFor(i)}
            y={height - MARGIN.bottom + 16}
            textAnchor="middle"
            fontSize={10}
            fill="var(--viz-text-secondary)"
          >
            {data.length > 8 && i % 2 === 1 ? "" : d.label}
          </text>
        ))}

        <text
          x={xFor(data.length - 1)}
          y={yFor(data[data.length - 1].value) - 10}
          textAnchor="end"
          fontSize={10}
          fontWeight={600}
          fill="var(--viz-text-primary)"
        >
          {valueFormat(data[data.length - 1].value)}
        </text>
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
