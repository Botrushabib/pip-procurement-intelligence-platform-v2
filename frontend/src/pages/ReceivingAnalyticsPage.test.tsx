import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { buildAnalyticsUrl, fetchReceivingAnalytics } from "../api/receivingAnalytics";
import App from "../App";
import { validateAnalyticsFilters } from "../components/AnalyticsFilters";
import { AnalyticsTabs } from "../components/AnalyticsTabs";
import type { AnalyticsFilters, ReceivingAnalyticsResponse } from "../types/receivingAnalytics";

const EMPTY_FILTERS: AnalyticsFilters = {
  company_id: "", warehouse_id: "", supplier_id: "", product_id: "",
  category_id: "", unit_id: "", date_from: "", date_to: "", reference: "",
};

function emptyResponse(): ReceivingAnalyticsResponse {
  return {
    summary: {
      examined_lines: 0, eligible_lines: 0, distinct_event_count: 0,
      total_quantity: 0, total_spend: 0, average_unit_price: null,
      minimum_unit_price: null, maximum_unit_price: null,
    },
    history: {
      last_receiving: null,
      receiving_frequency: {
        event_count: 0, line_count: 0, first_receiving_date: null,
        last_receiving_date: null, average_days_between_receipts: null,
      },
      monthly_totals: [],
      data_quality: {
        total_lines: 0, eligible_lines: 0, ineligible_lines: 0,
        missing_date_count: 0, missing_product_count: 0, missing_quantity_count: 0,
        missing_price_count: 0, missing_supplier_count: 0, missing_warehouse_count: 0,
      },
    },
    price: null,
    supplier: null,
    category: null,
    trend: {
      observations: [], monthly_trends: [], product_monthly_trends: [],
      supplier_monthly_trends: [], category_monthly_trends: [],
      quality: {
        examined_lines: 0, analytics_eligible_lines: 0, missing_supplier: 0,
        missing_product: 0, missing_category: 0, missing_unit: 0,
        missing_event_date: 0, missing_quantity: 0, missing_unit_price: 0,
      },
    },
    supplier_comparison: {
      request: {
        supplier_ids: null, product_id: null, category_id: null, unit_id: null,
        company_id: null, warehouse_id: null, date_from: null, date_to: null, reference: null,
      },
      sufficiency: "INSUFFICIENT_DATA", observations: [], supplier_summaries: [],
      supplier_product_comparisons: [], product_price_comparisons: [],
      data_quality: {
        examined_lines: 0, analytics_eligible_lines: 0, matched_supplier_lines: 0,
        missing_supplier_count: 0, missing_product_count: 0, missing_category_count: 0,
        missing_unit_count: 0, missing_date_count: 0, missing_price_count: 0,
        missing_quantity_count: 0,
      },
    },
  };
}

function mockResponse(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

// Populated fixture covering the fields exercised by the Stage 16B presentation
// tests (formatting, status badges, sorting, and the trend show-all control).
function populatedResponse(): ReceivingAnalyticsResponse {
  const base = emptyResponse();
  const monthlyTrends = Array.from({ length: 10 }, (_, index) => ({
    year: 2026, month: index + 1, observation_count: 5 + index,
    total_quantity: 100 + index, total_spend: 1000 + index * 10,
    weighted_average_price: 10 + index, arithmetic_average_price: 10 + index,
    minimum_price: 8, maximum_price: 12, price_spread: 4,
    distinct_receiving_dates: 3,
    quantity_change: index % 2 === 0 ? 5 : -5, quantity_change_pct: 5,
    spend_change: index % 2 === 0 ? 50 : -50, spend_change_pct: 5,
    price_change: index % 2 === 0 ? 1 : -1, price_change_pct: 5,
  }));
  return {
    ...base,
    summary: {
      examined_lines: 120, eligible_lines: 110, distinct_event_count: 20,
      total_quantity: 500, total_spend: 12345.678, average_unit_price: 24.69,
      minimum_unit_price: 5, maximum_unit_price: 50,
    },
    price: {
      request: {
        product_id: 1, unit_id: null, supplier_id: null, company_id: null, warehouse_id: null,
        date_from: null, date_to: null, reference: null, current_unit_price: null,
      },
      sufficiency: "AVAILABLE",
      observations: [],
      observation_count: 4,
      current_price: 10, current_price_source: "latest",
      latest_observed_price: 10, previous_observed_price: 9,
      weighted_average_price: 9.5, arithmetic_average_price: 9.5,
      minimum_price: 8, maximum_price: 12, price_spread: 4,
      standard_deviation: 1, recent_average_price: 9.8, trend: "INCREASING",
      price_change: {
        status: "AVAILABLE", previous_price: 9, current_price: 10,
        absolute_change: 1, percentage_change: 11.11, reason: "ok",
      },
      anomaly: {
        status: "NORMAL", current_price: 10, reference_average: 9.5,
        standard_deviation: 1, difference: 0.5, percentage_difference: 5,
        z_score: 0.5, method: "zscore", reason: "ok",
      },
      confidence: "HIGH",
      data_quality: {
        examined_lines: 10, analytics_eligible_lines: 9, comparable_lines: 8,
        missing_product_count: 0, missing_date_count: 0, missing_price_count: 0, missing_unit_count: 0,
      },
    },
    supplier: {
      request: {
        supplier_id: 1, product_id: null, unit_id: null, company_id: null, warehouse_id: null,
        date_from: null, date_to: null, reference: null,
      },
      sufficiency: "AVAILABLE",
      observations: [],
      summary: {
        observation_count: 4, distinct_event_count: 3, distinct_product_count: 2,
        distinct_receiving_date_count: 3, total_quantity: 100, total_spend: 1000,
        weighted_average_unit_price: 10, arithmetic_average_unit_price: 10,
        min_unit_price: 8, max_unit_price: 12, price_spread: 4,
        first_receiving_date: "2026-01-01", latest_receiving_date: "2026-02-01",
        average_days_between_receipts: 15,
      },
      monthly_activity: [],
      product_summaries: [],
      data_quality: {
        examined_lines: 10, analytics_eligible_lines: 9, supplier_matched_lines: 8,
        missing_supplier_count: 0, missing_product_count: 0, missing_date_count: 0,
        missing_price_count: 0, missing_quantity_count: 0,
      },
    },
    category: {
      request: {
        category_id: 1, product_id: null, supplier_id: null, unit_id: null,
        company_id: null, warehouse_id: null, date_from: null, date_to: null, reference: null,
      },
      sufficiency: "AVAILABLE",
      observations: [],
      summary: {
        category_id: 1, category_name: "Widgets", observation_count: 4,
        distinct_event_count: 3, distinct_product_count: 2, distinct_supplier_count: 2,
        distinct_receiving_date_count: 3, total_quantity: 100, total_spend: 1000,
        weighted_average_unit_price: 10, arithmetic_average_unit_price: 10,
        min_unit_price: 8, max_unit_price: 12, price_spread: 4,
        first_receiving_date: "2026-01-01", latest_receiving_date: "2026-02-01",
        average_days_between_receipts: 15,
      },
      monthly_activity: [],
      product_summaries: [],
      supplier_summaries: [],
      data_quality: {
        examined_lines: 10, analytics_eligible_lines: 9, category_matched_lines: 8,
        missing_category_count: 0, missing_product_count: 0, missing_supplier_count: 0,
        missing_date_count: 0, missing_price_count: 0, missing_quantity_count: 0, missing_unit_count: 0,
      },
    },
    trend: { ...base.trend, monthly_trends: monthlyTrends },
    supplier_comparison: {
      ...base.supplier_comparison,
      sufficiency: "AVAILABLE",
      supplier_product_comparisons: [
        {
          product_id: 1, product_code: "P1", product_name: "Product One", unit_id: 1, unit_name: "ea",
          supplier_id: 1, supplier_name: "Acme", observation_count: 3, distinct_event_count: 2,
          total_quantity: 50, total_spend: 500, weighted_average_unit_price: 10, arithmetic_average_unit_price: 10,
          min_unit_price: 9, max_unit_price: 11, price_spread: 2, latest_price: 10,
          first_receiving_date: "2026-01-01", latest_receiving_date: "2026-02-01",
          price_position: "LOWEST", price_difference_vs_lowest: 0, price_difference_percentage_vs_lowest: 0,
        },
        {
          product_id: 1, product_code: "P1", product_name: "Product One", unit_id: 1, unit_name: "ea",
          supplier_id: 2, supplier_name: "Beta", observation_count: 2, distinct_event_count: 2,
          total_quantity: 40, total_spend: 480, weighted_average_unit_price: 12, arithmetic_average_unit_price: 12,
          min_unit_price: 11, max_unit_price: 13, price_spread: 2, latest_price: 12,
          first_receiving_date: "2026-01-05", latest_receiving_date: "2026-02-05",
          price_position: "HIGHEST", price_difference_vs_lowest: 2, price_difference_percentage_vs_lowest: 20,
        },
      ],
    },
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Receiving Analytics frontend", () => {
  it("renders the app shell and all existing filter controls", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(emptyResponse())));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Receiving Analytics" })).toBeTruthy();
    for (const label of ["Company ID", "Warehouse ID", "Supplier ID", "Product ID", "Category ID", "Unit ID", "From date", "To date", "Receiving reference"]) {
      expect(screen.getByLabelText(label)).toBeTruthy();
    }
    for (const group of ["Scope", "Target", "Range"]) {
      expect(screen.getByText(group)).toBeTruthy();
    }
    expect(await screen.findByText("No receiving records found")).toBeTruthy();
  });

  it("calls only the existing GET endpoint with populated filters", async () => {
    const filters = { ...EMPTY_FILTERS, company_id: "12", date_from: "2026-01-01", reference: "REC-2" };
    const fetchMock = vi.fn().mockResolvedValue(mockResponse(emptyResponse()));
    vi.stubGlobal("fetch", fetchMock);
    const url = "/api/receiving/analytics?company_id=12&date_from=2026-01-01&reference=REC-2";
    await fetchReceivingAnalytics(filters, new AbortController().signal);
    expect(buildAnalyticsUrl(filters)).toBe(url);
    expect(fetchMock).toHaveBeenCalledWith(url, expect.objectContaining({ method: "GET" }));
  });

  it("validates positive IDs, inclusive date order, and non-blank references", () => {
    const errors = validateAnalyticsFilters({
      ...EMPTY_FILTERS,
      company_id: "0",
      product_id: "1.5",
      date_from: "2026-02-01",
      date_to: "2026-01-01",
      reference: "   ",
    });
    expect(errors.company_id).toBeTruthy();
    expect(errors.product_id).toBeTruthy();
    expect(errors.date_to).toBeTruthy();
    expect(errors.reference).toBeTruthy();
    expect(validateAnalyticsFilters({ ...EMPTY_FILTERS, company_id: "42" })).toEqual({});
  });

  it("shows loading and renders values from the successful API response", async () => {
    let resolveResponse: ((response: Response) => void) | undefined;
    const pending = new Promise<Response>((resolve) => { resolveResponse = resolve; });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));
    render(<App />);
    expect(screen.getByRole("status").textContent).toContain("Loading receiving analytics");
    const body = emptyResponse();
    body.summary = { ...body.summary, examined_lines: 1, eligible_lines: 1, total_spend: 50 };
    await act(async () => resolveResponse?.(mockResponse(body)));
    expect(await screen.findByText("50")).toBeTruthy();
  });

  it("renders all seven analytics sections", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(emptyResponse())));
    render(<App />);
    await screen.findByText("No receiving records found");
    for (const section of [
      "Summary", "History", "Price", "Supplier", "Category", "Trend", "Supplier Comparison",
    ]) {
      fireEvent.click(screen.getByRole("tab", { name: section }));
      expect(screen.getByRole("heading", { name: section })).toBeTruthy();
    }
  });

  it("formats numeric values and shows status badges for existing API values", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(populatedResponse())));
    render(<App />);
    await screen.findByRole("tabpanel");
    const expectedSpend = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(12345.678);
    expect(await screen.findByText(expectedSpend)).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "Price" }));
    expect(screen.getByText("INCREASING").className).toContain("status-badge");
    expect(screen.getByText("NORMAL").className).toContain("status-badge");

    fireEvent.click(screen.getByRole("tab", { name: "Supplier Comparison" }));
    expect(screen.getByText("LOWEST").className).toContain("status-badge");
    expect(screen.getByText("HIGHEST").className).toContain("status-badge");
  });

  it("supports client-side sorting without mutating API data", async () => {
    const body = populatedResponse();
    const originalOrder = body.supplier_comparison.supplier_product_comparisons.map((row) => row.supplier_name);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(body)));
    render(<App />);
    await screen.findByRole("tabpanel");
    fireEvent.click(screen.getByRole("tab", { name: "Supplier Comparison" }));

    const table = screen.getAllByRole("table")[0];
    expect(within(table).getAllByRole("row")[1].textContent).toContain("Acme");

    fireEvent.click(within(table).getByRole("button", { name: /Price position/ }));
    expect(within(table).getAllByRole("row")[1].textContent).toContain("Beta");

    expect(body.supplier_comparison.supplier_product_comparisons.map((row) => row.supplier_name)).toEqual(originalOrder);
  });

  it("limits long trend tables with a show all control", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(populatedResponse())));
    render(<App />);
    await screen.findByRole("tabpanel");
    fireEvent.click(screen.getByRole("tab", { name: "Trend" }));

    expect(screen.getAllByRole("row")).toHaveLength(9);
    fireEvent.click(screen.getByRole("button", { name: "Show all (10)" }));
    expect(screen.getAllByRole("row")).toHaveLength(11);
    fireEvent.click(screen.getByRole("button", { name: "Show fewer" }));
    expect(screen.getAllByRole("row")).toHaveLength(9);
  });

  it("shows a null-section indicator on the relevant tab only", () => {
    render(<AnalyticsTabs activeTab="summary" onSelect={() => {}} emptySections={["price", "supplier"]} />);
    expect(screen.getByRole("tab", { name: "Price" }).querySelector(".tab-empty-indicator")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Supplier" }).querySelector(".tab-empty-indicator")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Category" }).querySelector(".tab-empty-indicator")).toBeNull();
  });

  it("wires empty-section tab indicators into the live page when price/supplier/category are null", async () => {
    const body = emptyResponse();
    body.summary = { ...body.summary, examined_lines: 1, eligible_lines: 1 };
    // price, supplier, and category are already null from emptyResponse(); trend is not.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(body)));
    render(<App />);
    await screen.findByRole("tabpanel");
    expect(screen.getByRole("tab", { name: "Price" }).querySelector(".tab-empty-indicator")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Supplier" }).querySelector(".tab-empty-indicator")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Category" }).querySelector(".tab-empty-indicator")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Trend" }).querySelector(".tab-empty-indicator")).toBeNull();
  });

  it("shows no empty-section indicator on the live page when a section is populated", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(populatedResponse())));
    render(<App />);
    await screen.findByRole("tabpanel");
    expect(screen.getByRole("tab", { name: "Price" }).querySelector(".tab-empty-indicator")).toBeNull();
    expect(screen.getByRole("tab", { name: "Supplier" }).querySelector(".tab-empty-indicator")).toBeNull();
    expect(screen.getByRole("tab", { name: "Category" }).querySelector(".tab-empty-indicator")).toBeNull();
  });

  it("shows 'All records' in the applied-filter context when no filters are active", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(emptyResponse())));
    render(<App />);
    expect(await screen.findByText("All records")).toBeTruthy();
  });

  it("reflects active filters in the applied-filter context", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockResponse(emptyResponse()));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await screen.findByText("All records");
    fireEvent.change(screen.getByLabelText("Company ID"), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText("Receiving reference"), { target: { value: "REC-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(await screen.findByText("Company: 12 · Reference: REC-2")).toBeTruthy();
  });

  it("shows a safe API error without exposing backend details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse({ detail: "traceback secret" }, 500)));
    render(<App />);
    expect((await screen.findByRole("alert")).textContent).toContain("The analytics request could not be completed.");
    expect(screen.queryByText(/traceback secret/i)).toBeNull();
  });

  it("shows validation inline without issuing a filter request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockResponse(emptyResponse()));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    fireEvent.change(await screen.findByLabelText("Company ID"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(await screen.findByText("Enter a positive whole number.")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("aborts superseded requests and ignores a late response", async () => {
    const pending: Array<(response: Response) => void> = [];
    const signals: AbortSignal[] = [];
    const fetchMock = vi.fn((_url: RequestInfo | URL, options?: RequestInit) => {
      if (options?.signal) signals.push(options.signal as AbortSignal);
      if (fetchMock.mock.calls.length === 1) return Promise.resolve(mockResponse(emptyResponse()));
      return new Promise<Response>((resolve) => pending.push(resolve));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(await screen.findByText("No receiving records found")).toBeTruthy();
    const company = screen.getByLabelText("Company ID");
    fireEvent.change(company, { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() => expect(pending).toHaveLength(1));
    expect(signals[0]?.aborted).toBe(true);
    fireEvent.change(company, { target: { value: "11" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(signals[1]?.aborted).toBe(true);
    const stale = emptyResponse();
    stale.summary.total_spend = 11;
    await act(async () => pending[0]?.(mockResponse(stale)));
    expect(screen.getByRole("status").textContent).toContain("Loading receiving analytics");
    const latest = emptyResponse();
    latest.summary = { ...latest.summary, examined_lines: 1, eligible_lines: 1, total_spend: 33 };
    await act(async () => pending[1]?.(mockResponse(latest)));
    expect(await screen.findByText("33")).toBeTruthy();
    expect(screen.queryByText("11")).toBeNull();
  });
});