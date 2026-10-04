export const ANALYTICS_TABS = [
  { id: "summary", label: "Summary" },
  { id: "history", label: "History" },
  { id: "price", label: "Price" },
  { id: "supplier", label: "Supplier" },
  { id: "category", label: "Category" },
  { id: "trend", label: "Trend" },
  { id: "supplier_comparison", label: "Supplier Comparison" },
] as const;

export type AnalyticsTabId = (typeof ANALYTICS_TABS)[number]["id"];

export function AnalyticsTabs({
  activeTab,
  onSelect,
  emptySections = [],
}: {
  activeTab: AnalyticsTabId;
  onSelect: (tab: AnalyticsTabId) => void;
  /** Tabs whose current response section is null (no data for the applied filters). */
  emptySections?: readonly AnalyticsTabId[];
}) {
  return (
    <div className="tabs-scroll">
      <div className="analytics-tabs" role="tablist" aria-label="Receiving analytics sections">
        {ANALYTICS_TABS.map((tab) => (
          <button
            aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? "tab active" : "tab"}
            id={`tab-${tab.id}`}
            key={tab.id}
            onClick={() => onSelect(tab.id)}
            role="tab"
            type="button"
          >
            {tab.label}
            {emptySections.includes(tab.id) && (
              <span className="tab-empty-indicator" aria-hidden="true" title="No data for the current filters" />
            )}
          </button>
        ))}
      </div>
    </div>
  );
}