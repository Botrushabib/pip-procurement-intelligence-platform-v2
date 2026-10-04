import type { ReactNode } from "react";

export interface DataColumn<Row extends object> {
  key: keyof Row;
  label: string;
}

export interface MetricItem {
  label: string;
  value: string | number | null | undefined;
}

function formatValue(value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") return "--";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value.replaceAll("_", " ");
  if (typeof value === "number") return String(value);
  return "--";
}

export function MetricList({ items }: { items: readonly MetricItem[] }) {
  return (
    <dl className="metric-list">
      {items.map((item) => (
        <div className="metric" key={item.label}>
          <dt>{item.label}</dt>
          <dd>{formatValue(item.value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function DataTable<Row extends object>({
  columns,
  rows,
  emptyMessage = "No rows returned by the API.",
}: {
  columns: readonly DataColumn<Row>[];
  rows: readonly Row[];
  emptyMessage?: string;
}) {
  if (rows.length === 0) return <p className="table-empty">{emptyMessage}</p>;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={String(column.key)} scope="col">{column.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => <td key={String(column.key)}>{formatValue(row[column.key])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}