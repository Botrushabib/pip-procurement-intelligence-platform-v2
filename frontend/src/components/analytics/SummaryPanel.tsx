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
        { label: "Records examined", value: summary.examined_lines },
        { label: "Receiving events", value: summary.distinct_event_count },
        { label: "Total quantity", value: summary.total_quantity },
        { label: "Total spend", value: summary.total_spend },
        { label: "Average unit price", value: summary.average_unit_price },
        { label: "Minimum unit price", value: summary.minimum_unit_price },
        { label: "Maximum unit price", value: summary.maximum_unit_price },
      ]} />
    </section>
  );
}