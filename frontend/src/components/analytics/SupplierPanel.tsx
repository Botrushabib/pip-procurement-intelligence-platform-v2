import type { ReceivingSupplierSection } from "../../types/receivingAnalytics";
import { DataTable, MetricList } from "../DataTable";

function SupplierHeading({ count }: { count: number | null }) {
  return (
    <div className="panel-heading">
      <div><span className="eyebrow">Supplier activity</span><h2 id="supplier-heading">Supplier</h2></div>
      {count !== null && <span className="panel-count">{count} observations</span>}
    </div>
  );
}

export function SupplierPanel({ supplier }: { supplier: ReceivingSupplierSection | null }) {
  if (!supplier) {
    return (
      <section className="analytics-panel" aria-labelledby="supplier-heading">
        <SupplierHeading count={null} />
        <p className="table-empty">Enter a supplier ID to view supplier intelligence.</p>
      </section>
    );
  }
  return (
    <section className="analytics-panel" aria-labelledby="supplier-heading">
      <SupplierHeading count={supplier.summary.observation_count} />
      <MetricList items={[
        { label: "Sufficiency", value: supplier.sufficiency, badge: true },
        { label: "Receiving events", value: supplier.summary.distinct_event_count, format: "integer" },
        { label: "Distinct products", value: supplier.summary.distinct_product_count, format: "integer" },
        { label: "Total quantity", value: supplier.summary.total_quantity, format: "decimal" },
        { label: "Total spend", value: supplier.summary.total_spend, format: "decimal" },
        { label: "Weighted average", value: supplier.summary.weighted_average_unit_price, format: "decimal" },
        { label: "Minimum price", value: supplier.summary.min_unit_price, format: "decimal" },
        { label: "Maximum price", value: supplier.summary.max_unit_price, format: "decimal" },
        { label: "Latest receipt", value: supplier.summary.latest_receiving_date },
      ]} />
      <h3 className="subheading">Monthly activity</h3>
      <DataTable columns={[
        { key: "year", label: "Year" }, { key: "month", label: "Month" },
        { key: "observation_count", label: "Lines", format: "integer" }, { key: "distinct_event_count", label: "Events", format: "integer" },
        { key: "distinct_product_count", label: "Products", format: "integer" }, { key: "total_quantity", label: "Quantity", format: "decimal" },
        { key: "total_spend", label: "Spend", format: "decimal" }, { key: "weighted_average_unit_price", label: "Weighted avg.", format: "decimal" },
      ]} rows={supplier.monthly_activity} initialRowLimit={8} />
      <h3 className="subheading">Products</h3>
      <DataTable columns={[
        { key: "product_id", label: "Product ID" }, { key: "product_name", label: "Product" },
        { key: "unit_name", label: "Unit" }, { key: "observation_count", label: "Lines", format: "integer" },
        { key: "total_quantity", label: "Quantity", format: "decimal" }, { key: "total_spend", label: "Spend", format: "decimal" },
        { key: "latest_price", label: "Latest price", format: "decimal" },
      ]} rows={supplier.product_summaries} initialRowLimit={8} />
    </section>
  );
}