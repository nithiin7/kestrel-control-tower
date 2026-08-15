export interface Datum {
  label: string;
  value: number;
}

export function groupByAverage<T>(rows: T[], keyFn: (row: T) => string, valueFn: (row: T) => number): Datum[] {
  const sums = new Map<string, { sum: number; count: number }>();
  for (const row of rows) {
    const key = keyFn(row);
    const entry = sums.get(key) ?? { sum: 0, count: 0 };
    entry.sum += valueFn(row);
    entry.count += 1;
    sums.set(key, entry);
  }
  return Array.from(sums.entries()).map(([label, { sum, count }]) => ({ label, value: sum / count }));
}

export function groupBySum<T>(rows: T[], keyFn: (row: T) => string, valueFn: (row: T) => number): Datum[] {
  const sums = new Map<string, number>();
  for (const row of rows) {
    const key = keyFn(row);
    sums.set(key, (sums.get(key) ?? 0) + valueFn(row));
  }
  return Array.from(sums.entries()).map(([label, value]) => ({ label, value }));
}

export function sortByLabel(rows: Datum[]): Datum[] {
  return [...rows].sort((a, b) => a.label.localeCompare(b.label));
}
