import type { ReceivingPriceSection } from "../../types/receivingAnalytics";
import { DataTable, MetricList } from "../DataTable";

export function PricePanel({ price }: { price: ReceivingPriceSection | null }) {
  if (!price) return <section className="analytics-panel"><h2>Price</h2><p className="table-empty">Enter a product ID to view price intelligence.</p></section>;
  return (
    <section className="analytics-panel" aria-labelledby="price-heading">
      <div className="panel-heading">
        <div><span className="eyebrow">Product pricing</span><h2 id="price-heading">Price</h2></div>
        <span className="panel-count">{price.observation_count} observations</span>
      </div>
      <MetricList items={[
        { label: "Sufficiency", value: price.sufficiency }, { label: "Trend", value: price.trend },
        { label: "Confidence", value: price.confidence }, { label: "Current price", value: price.current_price },
        { label: "Latest observed", value: price.latest_observed_price },
        { label: "Previous observed", value: price.previous_observed_price },
        { label: "Weighted average", value: price.weighted_average_price },
        { label: "Arithmetic average", value: price.arithmetic_average_price },
        { label: "Minimum price", value: price.minimum_price }, { label: "Maximum price", value: price.maximum_price },
        { label: "Recent average", value: price.recent_average_price },
        { label: "Price change", value: price.price_change.absolute_change },
        { label: "Change percent", value: price.price_change.percentage_change },
        { label: "Anomaly status", value: price.anomaly.status },
      ]} />
      <h3 className="subheading">Observed receipts</h3>
      <DataTable columns={[
        { key: "event_date", label: "Date" }, { key: "receiving_reference", label: "Reference" },
        { key: "supplier_name", label: "Supplier" }, { key: "quantity", label: "Quantity" },
        { key: "unit_price", label: "Unit price" }, { key: "subtotal", label: "Subtotal" },
      ]} rows={price.observations} />
    </section>
  );
}