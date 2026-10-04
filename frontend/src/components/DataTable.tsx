import { useMemo, useState, type ReactNode } from "react";

export type ValueFormat = "integer" | "decimal" | "percent";

export interface DataColumn<Row extends object> {
  key: keyof Row;
  label: string;
  format?: ValueFormat;
  sortable?: boolean;
  /** Custom cell renderer. Receives the already-fetched row; use for badges only. */
  render?: (row: Row) => ReactNode;
}

export interface MetricItem {
  label: string;
  value: string | number | null | undefined;
  format?: ValueFormat;
  /** Renders the (string) value as a StatusBadge instead of plain text. */
  badge?: boolean;
  /** Visual weight only; does not change the underlying value. */
  emphasis?: "headline" | "quiet";
}

const INTEGER_FORMAT = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
const DECIMAL_FORMAT = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });

function formatNumber(value: number, format?: ValueFormat): string {
  if (format === "percent") return `${DECIMAL_FORMAT.format(value)}%`;
  if (format === "integer") return INTEGER_FORMAT.format(value);
  return DECIMAL_FORMAT.format(value);
}

function formatValue(value: unknown, format?: ValueFormat): ReactNode {
  if (value === null || value === undefined || value === "") return "--";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return formatNumber(value, format);
  if (typeof value === "string") return value.replaceAll("_", " ");
  return "--";
}

/**
 * Visual-only tone mapping for status strings already returned by the API
 * (e.g. sufficiency, trend, anomaly status, price position). No new statuses
 * are introduced; unrecognized values fall back to a neutral tone.
 */
const KNOWN_STATUS_TONES: Record<string, "positive" | "warning" | "negative" | "neutral"> = {
  AVAILABLE: "positive",
  NORMAL: "positive",
  LOWEST: "positive",
  STABLE: "neutral",
  INCREASING: "neutral",
  DECREASING: "neutral",
  INSUFFICIENT_DATA: "neutral",
  UNAVAILABLE: "neutral",
  ABOVE_LOWEST: "warning",
  ABOVE_EXPECTED_RANGE: "warning",
  BELOW_EXPECTED_RANGE: "warning",
  HIGHEST: "negative",
};

export function StatusBadge({ value }: { value: string | null | undefined }) {
  if (value === null || value === undefined || value === "") {
    return <span className="status-badge tone-neutral">--</span>;
  }
  const tone = KNOWN_STATUS_TONES[value] ?? "neutral";
  return <span className={`status-badge tone-${tone}`}>{value.replaceAll("_", " ")}</span>;
}

/**
 * Directional badge for an already-computed numeric change value (e.g.
 * month-over-month quantity/spend/price change). Only reads the sign of the
 * existing number; it does not derive or calculate a new value.
 */
export function ChangeBadge({ value, format }: { value: number | null | undefined; format?: ValueFormat }) {
  if (value === null || value === undefined) return <span className="change-badge dir-flat">--</span>;
  const direction = value > 0 ? "up" : value < 0 ? "down" : "flat";
  const glyph = direction === "up" ? "\u25B2" : direction === "down" ? "\u25BC" : "\u25AC";
  return (
    <span className={`change-badge dir-${direction}`}>
      {glyph} {formatNumber(Math.abs(value), format)}
    </span>
  );
}

export function MetricList({ items }: { items: readonly MetricItem[] }) {
  return (
    <dl className="metric-list">
      {items.map((item) => (
        <div className={item.emphasis ? `metric metric-${item.emphasis}` : "metric"} key={item.label}>
          <dt>{item.label}</dt>
          <dd>
            {item.badge && typeof item.value === "string"
              ? <StatusBadge value={item.value} />
              : formatValue(item.value, item.format)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

type SortState<Row extends object> = { key: keyof Row; direction: "asc" | "desc" } | null;

function compareRows<Row extends object>(a: Row, b: Row, key: keyof Row): number {
  const left = a[key];
  const right = b[key];
  if (left === right) return 0;
  if (left === null || left === undefined) return 1;
  if (right === null || right === undefined) return -1;
  if (typeof left === "number" && typeof right === "number") return left - right;
  return String(left).localeCompare(String(right));
}

export function DataTable<Row extends object>({
  columns,
  rows,
  emptyMessage = "No rows returned by the API.",
  initialRowLimit,
}: {
  columns: readonly DataColumn<Row>[];
  rows: readonly Row[];
  emptyMessage?: string;
  /** Caps initial visible rows for long tables; a "Show all" control reveals the rest. */
  initialRowLimit?: number;
}) {
  const [sort, setSort] = useState<SortState<Row>>(null);
  const [showAll, setShowAll] = useState(false);

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    // Sorting operates on a copy; the original API-provided array is never mutated.
    return [...rows].sort((a, b) => {
      const result = compareRows(a, b, sort.key);
      return sort.direction === "asc" ? result : -result;
    });
  }, [rows, sort]);

  if (rows.length === 0) return <p className="table-empty">{emptyMessage}</p>;

  const isLimited = Boolean(initialRowLimit) && !showAll && sortedRows.length > (initialRowLimit as number);
  const visibleRows = isLimited ? sortedRows.slice(0, initialRowLimit) : sortedRows;

  function toggleSort(column: DataColumn<Row>) {
    if (column.sortable === false) return;
    setSort((current) => {
      if (!current || current.key !== column.key) return { key: column.key, direction: "asc" };
      if (current.direction === "asc") return { key: column.key, direction: "desc" };
      return null;
    });
  }

  return (
    <>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {columns.map((column) => {
                const sortable = column.sortable !== false;
                const isSorted = sort?.key === column.key;
                return (
                  <th
                    key={String(column.key)}
                    scope="col"
                    aria-sort={isSorted ? (sort?.direction === "asc" ? "ascending" : "descending") : "none"}
                  >
                    {sortable ? (
                      <button type="button" className="sort-button" onClick={() => toggleSort(column)}>
                        {column.label}
                        <span className="sort-indicator" aria-hidden="true">
                          {isSorted ? (sort?.direction === "asc" ? "\u25B2" : "\u25BC") : ""}
                        </span>
                      </button>
                    ) : column.label}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, index) => (
              <tr key={index}>
                {columns.map((column) => (
                  <td key={String(column.key)}>
                    {column.render ? column.render(row) : formatValue(row[column.key], column.format)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {initialRowLimit && sortedRows.length > initialRowLimit && (
        <div className="table-expand">
          <button type="button" className="button button-quiet" onClick={() => setShowAll((value) => !value)}>
            {showAll ? "Show fewer" : `Show all (${sortedRows.length})`}
          </button>
        </div>
      )}
    </>
  );
}