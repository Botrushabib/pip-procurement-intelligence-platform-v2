import type { ReceivingSupplierComparisonSection } from "../../types/receivingAnalytics";
import { DataTable } from "../DataTable";

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
        { key: "observation_count", label: "Lines" }, { key: "distinct_product_count", label: "Products" },
        { key: "total_quantity", label: "Quantity" }, { key: "total_spend", label: "Spend" },
        { key: "weighted_average_unit_price", label: "Weighted avg." },
      ]} rows={comparison.supplier_summaries} />
      <h3 className="subheading">Supplier by product</h3>
      <DataTable columns={[
        { key: "product_id", label: "Product ID" }, { key: "product_name", label: "Product" },
        { key: "unit_name", label: "Unit" }, { key: "supplier_id", label: "Supplier ID" },
        { key: "supplier_name", label: "Supplier" }, { key: "observation_count", label: "Lines" },
        { key: "weighted_average_unit_price", label: "Weighted avg." },
        { key: "price_position", label: "Price position" },
        { key: "price_difference_vs_lowest", label: "Difference vs. lowest" },
      ]} rows={comparison.supplier_product_comparisons} />
      <h3 className="subheading">Product price ranges</h3>
      <DataTable columns={[
        { key: "product_id", label: "Product ID" }, { key: "product_name", label: "Product" },
        { key: "unit_name", label: "Unit" }, { key: "supplier_count", label: "Suppliers" },
        { key: "lowest_weighted_average_price", label: "Lowest avg." },
        { key: "lowest_price_supplier_name", label: "Lowest supplier" },
        { key: "highest_weighted_average_price", label: "Highest avg." },
        { key: "highest_price_supplier_name", label: "Highest supplier" },
        { key: "price_spread", label: "Spread" },
      ]} rows={comparison.product_price_comparisons} />
    </section>
  );
}