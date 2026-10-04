import type { ReceivingPriceSection } from "../../types/receivingAnalytics";
import { DataTable, MetricList } from "../DataTable";

function PriceHeading({ count }: { count: number | null }) {
  return (
    <div className="panel-heading">
      <div><span className="eyebrow">Product pricing</span><h2 id="price-heading">Price</h2></div>
      {count !== null && <span className="panel-count">{count} observations</span>}
    </div>
  );
}

export function PricePanel({ price }: { price: ReceivingPriceSection | null }) {
  if (!price) {
    return (
      <section className="analytics-panel" aria-labelledby="price-heading">
        <PriceHeading count={null} />
        <p className="table-empty">Enter a product ID to view price intelligence.</p>
      </section>
    );
  }
  return (
    <section className="analytics-panel" aria-labelledby="price-heading">
      <PriceHeading count={price.observation_count} />
      <MetricList items={[
        { label: "Sufficiency", value: price.sufficiency, badge: true },
        { label: "Trend", value: price.trend, badge: true },
        { label: "Confidence", value: price.confidence, format: "decimal" },
        { label: "Current price", value: price.current_price, format: "decimal" },
        { label: "Latest observed", value: price.latest_observed_price, format: "decimal" },
        { label: "Previous observed", value: price.previous_observed_price, format: "decimal" },
        { label: "Weighted average", value: price.weighted_average_price, format: "decimal" },
        { label: "Arithmetic average", value: price.arithmetic_average_price, format: "decimal" },
        { label: "Minimum price", value: price.minimum_price, format: "decimal" },
        { label: "Maximum price", value: price.maximum_price, format: "decimal" },
        { label: "Recent average", value: price.recent_average_price, format: "decimal" },
        { label: "Price change", value: price.price_change.absolute_change, format: "decimal" },
        { label: "Change percent", value: price.price_change.percentage_change, format: "percent" },
        { label: "Anomaly status", value: price.anomaly.status, badge: true },
      ]} />
      <h3 className="subheading">Observed receipts</h3>
      <DataTable columns={[
        { key: "event_date", label: "Date" }, { key: "receiving_reference", label: "Reference" },
        { key: "supplier_name", label: "Supplier" }, { key: "quantity", label: "Quantity", format: "decimal" },
        { key: "unit_price", label: "Unit price", format: "decimal" }, { key: "subtotal", label: "Subtotal", format: "decimal" },
      ]} rows={price.observations} initialRowLimit={8} />
    </section>
  );
}