import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { fetchReceivingAnalytics, ReceivingAnalyticsApiError } from "../api/receivingAnalytics";
import { AnalyticsFilters, validateAnalyticsFilters } from "../components/AnalyticsFilters";
import { ANALYTICS_TABS, AnalyticsTabs, type AnalyticsTabId } from "../components/AnalyticsTabs";
import { CategoryPanel } from "../components/analytics/CategoryPanel";
import { HistoryPanel } from "../components/analytics/HistoryPanel";
import { PricePanel } from "../components/analytics/PricePanel";
import { SummaryPanel } from "../components/analytics/SummaryPanel";
import { SupplierPanel } from "../components/analytics/SupplierPanel";
import { SupplierComparisonPanel } from "../components/analytics/SupplierComparisonPanel";
import { TrendPanel } from "../components/analytics/TrendPanel";
import type {
  AnalyticsFilters as FilterValues,
  FilterErrors,
  FilterName,
  ReceivingAnalyticsResponse,
} from "../types/receivingAnalytics";

const EMPTY_FILTERS: FilterValues = {
  company_id: "", warehouse_id: "", supplier_id: "", product_id: "",
  category_id: "", unit_id: "", date_from: "", date_to: "", reference: "",
};

type LoadState =
  | { status: "loading" }
  | { status: "ready"; data: ReceivingAnalyticsResponse }
  | { status: "error"; message: string };

function AnalyticsSection({
  activeTab,
  data,
}: {
  activeTab: AnalyticsTabId;
  data: ReceivingAnalyticsResponse;
}) {
  switch (activeTab) {
    case "summary": return <SummaryPanel summary={data.summary} />;
    case "history": return <HistoryPanel history={data.history} />;
    case "price": return <PricePanel price={data.price} />;
    case "supplier": return <SupplierPanel supplier={data.supplier} />;
    case "category": return <CategoryPanel category={data.category} />;
    case "trend": return <TrendPanel trend={data.trend} />;
    case "supplier_comparison": return <SupplierComparisonPanel comparison={data.supplier_comparison} />;
  }
}

export function ReceivingAnalyticsPage() {
  const [filters, setFilters] = useState<FilterValues>(EMPTY_FILTERS);
  const [filterErrors, setFilterErrors] = useState<FilterErrors>({});
  const [activeTab, setActiveTab] = useState<AnalyticsTabId>("summary");
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const abortController = useRef<AbortController | null>(null);
  const latestRequest = useRef(0);

  async function loadAnalytics(nextFilters: FilterValues) {
    abortController.current?.abort();
    const controller = new AbortController();
    abortController.current = controller;
    const requestId = ++latestRequest.current;
    setLoadState({ status: "loading" });
    try {
      const data = await fetchReceivingAnalytics(nextFilters, controller.signal);
      if (requestId === latestRequest.current && !controller.signal.aborted) {
        setLoadState({ status: "ready", data });
      }
    } catch (error: unknown) {
      if (controller.signal.aborted || requestId !== latestRequest.current) return;
      setLoadState({
        status: "error",
        message: error instanceof ReceivingAnalyticsApiError
          ? error.message
          : "Could not reach the analytics service.",
      });
    }
  }

  useEffect(() => {
    void loadAnalytics(EMPTY_FILTERS);
    return () => {
      latestRequest.current += 1;
      abortController.current?.abort();
    };
  }, []);

  function updateFilter(name: FilterName, value: string) {
    setFilters((current) => ({ ...current, [name]: value }));
    setFilterErrors((current) => ({ ...current, [name]: undefined }));
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = validateAnalyticsFilters(filters);
    setFilterErrors(errors);
    if (Object.keys(errors).length === 0) void loadAnalytics(filters);
  }

  function resetFilters() {
    setFilters(EMPTY_FILTERS);
    setFilterErrors({});
    void loadAnalytics(EMPTY_FILTERS);
  }

  return (
    <main className="page-shell">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark">PIP</span>
          <span className="brand-name">Procurement Intelligence Platform <b>2.0</b></span>
        </div>
        <div className="header-context"><span className="status-dot" />Analytics service</div>
      </header>

      <div className="content-shell" id="main-content">
        <div className="page-heading">
          <div><p className="breadcrumb">Receiving <span>/</span> Intelligence</p><h1>Receiving Analytics</h1></div>
          <div className="read-only-label">READ ONLY</div>
        </div>

        <AnalyticsFilters
          value={filters}
          errors={filterErrors}
          onChange={updateFilter}
          onApply={applyFilters}
          onReset={resetFilters}
        />

        {loadState.status === "loading" && (
          <div className="state-message loading-state" role="status">
            <span className="loading-indicator" /><span>Loading receiving analytics...</span>
          </div>
        )}
        {loadState.status === "error" && (
          <div className="state-message error-state" role="alert">
            <strong>Analytics unavailable</strong><span>{loadState.message}</span>
          </div>
        )}
        {loadState.status === "ready" && <>
          {loadState.data.summary.examined_lines === 0 ? (
            <div className="state-message empty-state" role="status">
              <strong>No receiving records found</strong><span>No records match the current filters.</span>
            </div>
          ) : loadState.data.summary.eligible_lines === 0 ? (
            <div className="state-message empty-state" role="status">
              <strong>No analytics-eligible lines</strong><span>Records were found, but none are eligible for analytics.</span>
            </div>
          ) : null}
          <AnalyticsTabs activeTab={activeTab} onSelect={setActiveTab} />
          <div role="tabpanel" aria-labelledby={`tab-${activeTab}`}>
            <AnalyticsSection activeTab={activeTab} data={loadState.data} />
          </div>
        </>}
        <footer className="page-footer">
          <span>Receiving Analytics</span><span>{ANALYTICS_TABS.length} data views</span>
        </footer>
      </div>
    </main>
  );
}