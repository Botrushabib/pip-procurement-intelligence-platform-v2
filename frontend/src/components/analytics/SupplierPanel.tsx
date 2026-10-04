import type { ReceivingSupplierSection } from "../../types/receivingAnalytics";
import { DataTable, MetricList } from "../DataTable";

export function SupplierPanel({ supplier }: { supplier: ReceivingSupplierSection | null }) {
  if (!supplier) return <section className="analytics-panel"><h2>Supplier</h2><p className="table-empty">Enter a supplier ID to view supplier intelligence.</p></section>;
  return (
    <section className="analytics-panel" aria-labelledby="supplier-heading">
      <div className="panel-heading">
        <div><span className="eyebrow">Supplier activity</span><h2 id="supplier-heading">Supplier</h2></div>
        <span className="panel-count">{supplier.summary.observation_count} observations</span>
      </div>
      <MetricList items={[
        { label: "Sufficiency", value: supplier.sufficiency },
        { label: "Receiving events", value: supplier.summary.distinct_event_count },
        { label: "Distinct products", value: supplier.summary.distinct_product_count },
        { label: "Total quantity", value: supplier.summary.total_quantity },
        { label: "Total spend", value: supplier.summary.total_spend },
        { label: "Weighted average", value: supplier.summary.weighted_average_unit_price },
        { label: "Minimum price", value: supplier.summary.min_unit_price },
        { label: "Maximum price", value: supplier.summary.max_unit_price },
        { label: "Latest receipt", value: supplier.summary.latest_receiving_date },
      ]} />
      <h3 className="subheading">Monthly activity</h3>
      <DataTable columns={[
        { key: "year", label: "Year" }, { key: "month", label: "Month" },
        { key: "observation_count", label: "Lines" }, { key: "distinct_event_count", label: "Events" },
        { key: "distinct_product_count", label: "Products" }, { key: "total_quantity", label: "Quantity" },
        { key: "total_spend", label: "Spend" }, { key: "weighted_average_unit_price", label: "Weighted avg." },
      ]} rows={supplier.monthly_activity} />
      <h3 className="subheading">Products</h3>
      <DataTable columns={[
        { key: "product_id", label: "Product ID" }, { key: "product_name", label: "Product" },
        { key: "unit_name", label: "Unit" }, { key: "observation_count", label: "Lines" },
        { key: "total_quantity", label: "Quantity" }, { key: "total_spend", label: "Spend" },
        { key: "latest_price", label: "Latest price" },
      ]} rows={supplier.product_summaries} />
    </section>
  );
}