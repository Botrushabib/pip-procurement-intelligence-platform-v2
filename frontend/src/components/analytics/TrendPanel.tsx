import type { ReceivingTrendSection } from "../../types/receivingAnalytics";
import { DataTable, MetricList } from "../DataTable";

export function TrendPanel({ trend }: { trend: ReceivingTrendSection }) {
  return (
    <section className="analytics-panel" aria-labelledby="trend-heading">
      <div className="panel-heading">
        <div><span className="eyebrow">Time series</span><h2 id="trend-heading">Trend</h2></div>
        <span className="panel-count">{trend.observations.length} observations</span>
      </div>
      <h3 className="subheading">Data quality</h3>
      <MetricList items={[
        { label: "Examined", value: trend.quality.examined_lines },
        { label: "Eligible", value: trend.quality.analytics_eligible_lines },
        { label: "Missing supplier", value: trend.quality.missing_supplier },
        { label: "Missing product", value: trend.quality.missing_product },
        { label: "Missing category", value: trend.quality.missing_category },
        { label: "Missing unit", value: trend.quality.missing_unit },
        { label: "Missing date", value: trend.quality.missing_event_date },
        { label: "Missing quantity", value: trend.quality.missing_quantity },
        { label: "Missing price", value: trend.quality.missing_unit_price },
      ]} />
      <h3 className="subheading">Monthly totals</h3>
      <DataTable columns={[
        { key: "year", label: "Year" }, { key: "month", label: "Month" },
        { key: "observation_count", label: "Lines" }, { key: "total_quantity", label: "Quantity" },
        { key: "total_spend", label: "Spend" }, { key: "weighted_average_price", label: "Weighted avg." },
        { key: "quantity_change", label: "Quantity change" }, { key: "spend_change", label: "Spend change" },
        { key: "price_change", label: "Price change" },
      ]} rows={trend.monthly_trends} />
      <h3 className="subheading">Product and unit trends</h3>
      <DataTable columns={[
        { key: "product_id", label: "Product ID" }, { key: "unit_id", label: "Unit ID" },
        { key: "year", label: "Year" }, { key: "month", label: "Month" },
        { key: "observation_count", label: "Lines" }, { key: "total_quantity", label: "Quantity" },
        { key: "weighted_average_price", label: "Weighted avg." }, { key: "price_change", label: "Price change" },
      ]} rows={trend.product_monthly_trends} />
      <h3 className="subheading">Supplier trends</h3>
      <DataTable columns={[
        { key: "supplier_id", label: "Supplier ID" }, { key: "year", label: "Year" },
        { key: "month", label: "Month" }, { key: "observation_count", label: "Lines" },
        { key: "distinct_products", label: "Products" }, { key: "total_spend", label: "Spend" },
        { key: "weighted_average_price", label: "Weighted avg." },
      ]} rows={trend.supplier_monthly_trends} />
      <h3 className="subheading">Category trends</h3>
      <DataTable columns={[
        { key: "category_id", label: "Category ID" }, { key: "year", label: "Year" },
        { key: "month", label: "Month" }, { key: "observation_count", label: "Lines" },
        { key: "distinct_products", label: "Products" }, { key: "distinct_suppliers", label: "Suppliers" },
        { key: "total_spend", label: "Spend" }, { key: "weighted_average_price", label: "Weighted avg." },
      ]} rows={trend.category_monthly_trends} />
    </section>
  );
}