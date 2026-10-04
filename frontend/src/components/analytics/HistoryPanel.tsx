import type { ReceivingHistorySection } from "../../types/receivingAnalytics";
import { DataTable, MetricList } from "../DataTable";

export function HistoryPanel({ history }: { history: ReceivingHistorySection }) {
  const frequency = history.receiving_frequency;
  const quality = history.data_quality;
  return (
    <section className="analytics-panel" aria-labelledby="history-heading">
      <div className="panel-heading">
        <div><span className="eyebrow">Receiving activity</span><h2 id="history-heading">History</h2></div>
        <span className="panel-count">{frequency.event_count} events</span>
      </div>
      <h3 className="subheading">Frequency</h3>
      <MetricList items={[
        { label: "Lines", value: frequency.line_count, format: "integer" },
        { label: "First receipt", value: frequency.first_receiving_date },
        { label: "Latest receipt", value: frequency.last_receiving_date },
        { label: "Average days between", value: frequency.average_days_between_receipts, format: "decimal" },
      ]} />
      <h3 className="subheading">Latest receiving</h3>
      {history.last_receiving ? <MetricList items={[
        { label: "Date", value: history.last_receiving.event_date },
        { label: "Reference", value: history.last_receiving.receiving_reference },
        { label: "Supplier", value: history.last_receiving.supplier_name ?? history.last_receiving.supplier_id },
        { label: "Warehouse", value: history.last_receiving.warehouse_name ?? history.last_receiving.warehouse_id },
        { label: "Quantity", value: history.last_receiving.quantity, format: "decimal" },
        { label: "Unit price", value: history.last_receiving.unit_price, format: "decimal" },
      ]} /> : <p className="table-empty">No latest receiving record.</p>}
      <h3 className="subheading">Monthly totals</h3>
      <DataTable columns={[
        { key: "year", label: "Year" }, { key: "month", label: "Month" },
        { key: "event_count", label: "Events", format: "integer" }, { key: "line_count", label: "Lines", format: "integer" },
        { key: "total_quantity", label: "Quantity", format: "decimal" }, { key: "total_subtotal", label: "Spend", format: "decimal" },
        { key: "average_unit_price", label: "Avg. unit price", format: "decimal" },
      ]} rows={history.monthly_totals} initialRowLimit={8} />
      <h3 className="subheading">Data quality</h3>
      <MetricList items={[
        { label: "Lines", value: quality.total_lines, format: "integer", emphasis: "quiet" },
        { label: "Eligible", value: quality.eligible_lines, format: "integer", emphasis: "quiet" },
        { label: "Ineligible", value: quality.ineligible_lines, format: "integer", emphasis: "quiet" },
        { label: "Missing dates", value: quality.missing_date_count, format: "integer", emphasis: "quiet" },
        { label: "Missing products", value: quality.missing_product_count, format: "integer", emphasis: "quiet" },
        { label: "Missing quantities", value: quality.missing_quantity_count, format: "integer", emphasis: "quiet" },
        { label: "Missing prices", value: quality.missing_price_count, format: "integer", emphasis: "quiet" },
        { label: "Missing suppliers", value: quality.missing_supplier_count, format: "integer", emphasis: "quiet" },
        { label: "Missing warehouses", value: quality.missing_warehouse_count, format: "integer", emphasis: "quiet" },
      ]} />
    </section>
  );
}