import type { ReceivingSupplierComparisonSection } from "../../types/receivingAnalytics";
import { DataTable, StatusBadge } from "../DataTable";

export function SupplierComparisonPanel({ comparison }: { comparison: ReceivingSupplierComparisonSection }) {
  return (
    <section className="analytics-panel" aria-labelledby="comparison-heading">
      <div className="panel-heading">
        <div><span className="eyebrow">Supplier pricing</span><h2 id="comparison-heading">Supplier Comparison</h2></div>
        <span className="panel-count">{comparison.supplier_summaries.length} suppliers</span>
      </div>
      <h3 className="subheading">Supplier summaries</h3>
      <DataTable columns={[
        { key: "supplier_id", label: "Supplier ID" }, { key: "supplier_name", label: "Supplier" },
        { key: "observation_count", label: "Lines", format: "integer" }, { key: "distinct_product_count", label: "Products", format: "integer" },
        { key: "total_quantity", label: "Quantity", format: "decimal" }, { key: "total_spend", label: "Spend", format: "decimal" },
        { key: "weighted_average_unit_price", label: "Weighted avg.", format: "decimal" },
      ]} rows={comparison.supplier_summaries} initialRowLimit={8} />
      <h3 className="subheading">Supplier by product</h3>
      <DataTable columns={[
        { key: "product_id", label: "Product ID" }, { key: "product_name", label: "Product" },
        { key: "unit_name", label: "Unit" }, { key: "supplier_id", label: "Supplier ID" },
        { key: "supplier_name", label: "Supplier" }, { key: "observation_count", label: "Lines", format: "integer" },
        { key: "weighted_average_unit_price", label: "Weighted avg.", format: "decimal" },
        { key: "price_position", label: "Price position", render: (row) => <StatusBadge value={row.price_position} /> },
        { key: "price_difference_vs_lowest", label: "Difference vs. lowest", format: "decimal" },
      ]} rows={comparison.supplier_product_comparisons} initialRowLimit={8} />
      <h3 className="subheading">Product price ranges</h3>
      <DataTable columns={[
        { key: "product_id", label: "Product ID" }, { key: "product_name", label: "Product" },
        { key: "unit_name", label: "Unit" }, { key: "supplier_count", label: "Suppliers", format: "integer" },
        { key: "lowest_weighted_average_price", label: "Lowest avg.", format: "decimal" },
        { key: "lowest_price_supplier_name", label: "Lowest supplier" },
        { key: "highest_weighted_average_price", label: "Highest avg.", format: "decimal" },
        { key: "highest_price_supplier_name", label: "Highest supplier" },
        { key: "price_spread", label: "Spread", format: "decimal" },
      ]} rows={comparison.product_price_comparisons} initialRowLimit={8} />
    </section>
  );
}