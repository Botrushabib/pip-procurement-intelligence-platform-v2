import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { buildAnalyticsUrl, fetchReceivingAnalytics } from "../api/receivingAnalytics";
import App from "../App";
import { validateAnalyticsFilters } from "../components/AnalyticsFilters";
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