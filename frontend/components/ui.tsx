import type { ReactNode } from "react";

export function PageHeader({ title, description }: { title: string; description?: ReactNode }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight text-gray-900">{title}</h1>
      {description && <p className="mt-1 max-w-3xl text-sm text-gray-500">{description}</p>}
    </div>
  );
}

export function Card({
  children,
  loading = false,
  className = "",
}: {
  children: ReactNode;
  loading?: boolean;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-opacity duration-150 ${
        loading ? "opacity-60" : ""
      } ${className}`}
    >
      {children}
    </section>
  );
}

export function CardHeading({ children }: { children: ReactNode }) {
  return <h2 className="mb-3 text-sm font-semibold text-gray-900">{children}</h2>;
}

export function ChartHeading({ children }: { children: ReactNode }) {
  return <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">{children}</h2>;
}

export function ErrorBanner({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">{children}</div>;
}

export function EmptyRow({ colSpan, children = "No rows match the current filters." }: { colSpan: number; children?: ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="py-8 text-center text-sm text-gray-400">
        {children}
      </td>
    </tr>
  );
}

export function Th({
  children,
  align = "left",
  className = "",
}: {
  children: ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <th
      className={`whitespace-nowrap px-3 py-2 text-xs font-semibold uppercase tracking-wide text-gray-400 ${
        align === "right" ? "text-right" : "text-left"
      } ${className}`}
    >
      {children}
    </th>
  );
}

export function Td({ children, align = "left", className = "" }: { children: ReactNode; align?: "left" | "right"; className?: string }) {
  return <td className={`whitespace-nowrap px-3 py-2 ${align === "right" ? "text-right" : "text-left"} ${className}`}>{children}</td>;
}
