import type { ReceivingCategorySection } from "../../types/receivingAnalytics";
import { DataTable, MetricList } from "../DataTable";

function CategoryHeading({ count }: { count: number | null }) {
  return (
    <div className="panel-heading">
      <div><span className="eyebrow">Category activity</span><h2 id="category-heading">Category</h2></div>
      {count !== null && <span className="panel-count">{count} observations</span>}
    </div>
  );
}

export function CategoryPanel({ category }: { category: ReceivingCategorySection | null }) {
  if (!category) {
    return (
      <section className="analytics-panel" aria-labelledby="category-heading">
        <CategoryHeading count={null} />
        <p className="table-empty">Enter a category ID to view category intelligence.</p>
      </section>
    );
  }
  return (
    <section className="analytics-panel" aria-labelledby="category-heading">
      <CategoryHeading count={category.summary.observation_count} />
      <MetricList items={[
        { label: "Sufficiency", value: category.sufficiency, badge: true },
        { label: "Receiving events", value: category.summary.distinct_event_count, format: "integer" },
        { label: "Distinct products", value: category.summary.distinct_product_count, format: "integer" },
        { label: "Distinct suppliers", value: category.summary.distinct_supplier_count, format: "integer" },
        { label: "Total quantity", value: category.summary.total_quantity, format: "decimal" },
        { label: "Total spend", value: category.summary.total_spend, format: "decimal" },
        { label: "Weighted average", value: category.summary.weighted_average_unit_price, format: "decimal" },
        { label: "Latest receipt", value: category.summary.latest_receiving_date },
      ]} />
      <h3 className="subheading">Monthly activity</h3>
      <DataTable columns={[
        { key: "year", label: "Year" }, { key: "month", label: "Month" },
        { key: "observation_count", label: "Lines", format: "integer" }, { key: "distinct_product_count", label: "Products", format: "integer" },
        { key: "distinct_supplier_count", label: "Suppliers", format: "integer" }, { key: "total_quantity", label: "Quantity", format: "decimal" },
        { key: "total_spend", label: "Spend", format: "decimal" }, { key: "weighted_average_unit_price", label: "Weighted avg.", format: "decimal" },
      ]} rows={category.monthly_activity} initialRowLimit={8} />
      <h3 className="subheading">Products</h3>
      <DataTable columns={[
        { key: "product_id", label: "Product ID" }, { key: "product_name", label: "Product" },
        { key: "unit_name", label: "Unit" }, { key: "observation_count", label: "Lines", format: "integer" },
        { key: "distinct_supplier_count", label: "Suppliers", format: "integer" }, { key: "total_quantity", label: "Quantity", format: "decimal" },
        { key: "total_spend", label: "Spend", format: "decimal" }, { key: "latest_price", label: "Latest price", format: "decimal" },
      ]} rows={category.product_summaries} initialRowLimit={8} />
      <h3 className="subheading">Suppliers</h3>
      <DataTable columns={[
        { key: "supplier_id", label: "Supplier ID" }, { key: "supplier_name", label: "Supplier" },
        { key: "observation_count", label: "Lines", format: "integer" }, { key: "distinct_product_count", label: "Products", format: "integer" },
        { key: "total_quantity", label: "Quantity", format: "decimal" }, { key: "total_spend", label: "Spend", format: "decimal" },
        { key: "weighted_average_unit_price", label: "Weighted avg.", format: "decimal" },
      ]} rows={category.supplier_summaries} initialRowLimit={8} />
    </section>
  );
}