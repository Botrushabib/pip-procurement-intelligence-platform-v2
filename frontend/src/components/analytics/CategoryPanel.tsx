import type { ReceivingCategorySection } from "../../types/receivingAnalytics";
import { DataTable, MetricList } from "../DataTable";

export function CategoryPanel({ category }: { category: ReceivingCategorySection | null }) {
  if (!category) return <section className="analytics-panel"><h2>Category</h2><p className="table-empty">Enter a category ID to view category intelligence.</p></section>;
  return (
    <section className="analytics-panel" aria-labelledby="category-heading">
      <div className="panel-heading">
        <div><span className="eyebrow">Category activity</span><h2 id="category-heading">Category</h2></div>
        <span className="panel-count">{category.summary.observation_count} observations</span>
      </div>
      <MetricList items={[
        { label: "Sufficiency", value: category.sufficiency },
        { label: "Receiving events", value: category.summary.distinct_event_count },
        { label: "Distinct products", value: category.summary.distinct_product_count },
        { label: "Distinct suppliers", value: category.summary.distinct_supplier_count },
        { label: "Total quantity", value: category.summary.total_quantity },
        { label: "Total spend", value: category.summary.total_spend },
        { label: "Weighted average", value: category.summary.weighted_average_unit_price },
        { label: "Latest receipt", value: category.summary.latest_receiving_date },
      ]} />
      <h3 className="subheading">Monthly activity</h3>
      <DataTable columns={[
        { key: "year", label: "Year" }, { key: "month", label: "Month" },
        { key: "observation_count", label: "Lines" }, { key: "distinct_product_count", label: "Products" },
        { key: "distinct_supplier_count", label: "Suppliers" }, { key: "total_quantity", label: "Quantity" },
        { key: "total_spend", label: "Spend" }, { key: "weighted_average_unit_price", label: "Weighted avg." },
      ]} rows={category.monthly_activity} />
      <h3 className="subheading">Products</h3>
      <DataTable columns={[
        { key: "product_id", label: "Product ID" }, { key: "product_name", label: "Product" },
        { key: "unit_name", label: "Unit" }, { key: "observation_count", label: "Lines" },
        { key: "distinct_supplier_count", label: "Suppliers" }, { key: "total_quantity", label: "Quantity" },
        { key: "total_spend", label: "Spend" }, { key: "latest_price", label: "Latest price" },
      ]} rows={category.product_summaries} />
      <h3 className="subheading">Suppliers</h3>
      <DataTable columns={[
        { key: "supplier_id", label: "Supplier ID" }, { key: "supplier_name", label: "Supplier" },
        { key: "observation_count", label: "Lines" }, { key: "distinct_product_count", label: "Products" },
        { key: "total_quantity", label: "Quantity" }, { key: "total_spend", label: "Spend" },
        { key: "weighted_average_unit_price", label: "Weighted avg." },
      ]} rows={category.supplier_summaries} />
    </section>
  );
}