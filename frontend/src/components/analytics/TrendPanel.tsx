import type { ReceivingTrendSection } from "../../types/receivingAnalytics";
import { ChangeBadge, DataTable, MetricList } from "../DataTable";

export function TrendPanel({ trend }: { trend: ReceivingTrendSection }) {
  return (
    <section className="analytics-panel" aria-labelledby="trend-heading">
      <div className="panel-heading">
        <div><span className="eyebrow">Time series</span><h2 id="trend-heading">Trend</h2></div>
        <span className="panel-count">{trend.observations.length} observations</span>
      </div>
      <h3 className="subheading">Data quality</h3>
      <MetricList items={[
        { label: "Examined", value: trend.quality.examined_lines, format: "integer", emphasis: "quiet" },
        { label: "Eligible", value: trend.quality.analytics_eligible_lines, format: "integer", emphasis: "quiet" },
        { label: "Missing supplier", value: trend.quality.missing_supplier, format: "integer", emphasis: "quiet" },
        { label: "Missing product", value: trend.quality.missing_product, format: "integer", emphasis: "quiet" },
        { label: "Missing category", value: trend.quality.missing_category, format: "integer", emphasis: "quiet" },
        { label: "Missing unit", value: trend.quality.missing_unit, format: "integer", emphasis: "quiet" },
        { label: "Missing date", value: trend.quality.missing_event_date, format: "integer", emphasis: "quiet" },
        { label: "Missing quantity", value: trend.quality.missing_quantity, format: "integer", emphasis: "quiet" },
        { label: "Missing price", value: trend.quality.missing_unit_price, format: "integer", emphasis: "quiet" },
      ]} />
      <details open>
        <summary className="subheading">Monthly totals</summary>
        <DataTable columns={[
          { key: "year", label: "Year" }, { key: "month", label: "Month" },
          { key: "observation_count", label: "Lines", format: "integer" }, { key: "total_quantity", label: "Quantity", format: "decimal" },
          { key: "total_spend", label: "Spend", format: "decimal" }, { key: "weighted_average_price", label: "Weighted avg.", format: "decimal" },
          { key: "quantity_change", label: "Quantity change", render: (row) => <ChangeBadge value={row.quantity_change} format="decimal" /> },
          { key: "spend_change", label: "Spend change", render: (row) => <ChangeBadge value={row.spend_change} format="decimal" /> },
          { key: "price_change", label: "Price change", render: (row) => <ChangeBadge value={row.price_change} format="decimal" /> },
        ]} rows={trend.monthly_trends} initialRowLimit={8} />
      </details>
      <details>
        <summary className="subheading">Product and unit trends</summary>
        <DataTable columns={[
          { key: "product_id", label: "Product ID" }, { key: "unit_id", label: "Unit ID" },
          { key: "year", label: "Year" }, { key: "month", label: "Month" },
          { key: "observation_count", label: "Lines", format: "integer" }, { key: "total_quantity", label: "Quantity", format: "decimal" },
          { key: "weighted_average_price", label: "Weighted avg.", format: "decimal" },
          { key: "price_change", label: "Price change", render: (row) => <ChangeBadge value={row.price_change} format="decimal" /> },
        ]} rows={trend.product_monthly_trends} initialRowLimit={8} />
      </details>
      <details>
        <summary className="subheading">Supplier trends</summary>
        <DataTable columns={[
          { key: "supplier_id", label: "Supplier ID" }, { key: "year", label: "Year" },
          { key: "month", label: "Month" }, { key: "observation_count", label: "Lines", format: "integer" },
          { key: "distinct_products", label: "Products", format: "integer" }, { key: "total_spend", label: "Spend", format: "decimal" },
          { key: "weighted_average_price", label: "Weighted avg.", format: "decimal" },
        ]} rows={trend.supplier_monthly_trends} initialRowLimit={8} />
      </details>
      <details>
        <summary className="subheading">Category trends</summary>
        <DataTable columns={[
          { key: "category_id", label: "Category ID" }, { key: "year", label: "Year" },
          { key: "month", label: "Month" }, { key: "observation_count", label: "Lines", format: "integer" },
          { key: "distinct_products", label: "Products", format: "integer" }, { key: "distinct_suppliers", label: "Suppliers", format: "integer" },
          { key: "total_spend", label: "Spend", format: "decimal" }, { key: "weighted_average_price", label: "Weighted avg.", format: "decimal" },
        ]} rows={trend.category_monthly_trends} initialRowLimit={8} />
      </details>
    </section>
  );
}