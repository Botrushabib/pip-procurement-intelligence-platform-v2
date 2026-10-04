import type { ReceivingAnalyticsSummary } from "../../types/receivingAnalytics";
import { MetricList } from "../DataTable";

export function SummaryPanel({ summary }: { summary: ReceivingAnalyticsSummary }) {
  return (
    <section className="analytics-panel" aria-labelledby="summary-heading">
      <div className="panel-heading">
        <div><span className="eyebrow">Overview</span><h2 id="summary-heading">Summary</h2></div>
        <span className="panel-count">{summary.eligible_lines} eligible lines</span>
      </div>
      <MetricList items={[
        { label: "Total spend", value: summary.total_spend, format: "decimal", emphasis: "headline" },
        { label: "Total quantity", value: summary.total_quantity, format: "decimal", emphasis: "headline" },
        { label: "Average unit price", value: summary.average_unit_price, format: "decimal", emphasis: "headline" },
        { label: "Receiving events", value: summary.distinct_event_count, format: "integer", emphasis: "headline" },
      ]} />
      <h3 className="subheading">Data quality</h3>
      <MetricList items={[
        { label: "Records examined", value: summary.examined_lines, format: "integer", emphasis: "quiet" },
        { label: "Eligible lines", value: summary.eligible_lines, format: "integer", emphasis: "quiet" },
        { label: "Minimum unit price", value: summary.minimum_unit_price, format: "decimal", emphasis: "quiet" },
        { label: "Maximum unit price", value: summary.maximum_unit_price, format: "decimal", emphasis: "quiet" },
      ]} />
    </section>
  );
}