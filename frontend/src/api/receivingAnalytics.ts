import type { AnalyticsFilters, ReceivingAnalyticsResponse } from "../types/receivingAnalytics";

export const RECEIVING_ANALYTICS_ENDPOINT = "/api/receiving/analytics";

const FILTER_NAMES: readonly (keyof AnalyticsFilters)[] = [
  "company_id",
  "warehouse_id",
  "supplier_id",
  "product_id",
  "category_id",
  "unit_id",
  "date_from",
  "date_to",
  "reference",
];

export class ReceivingAnalyticsApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ReceivingAnalyticsApiError";
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isAnalyticsResponse(value: unknown): value is ReceivingAnalyticsResponse {
  if (!isObject(value) || !isObject(value.summary)) return false;
  for (const key of ["history", "trend", "supplier_comparison"] as const) {
    if (!isObject(value[key])) return false;
  }
  return ["price", "supplier", "category"].every(
    (key) => value[key] === null || isObject(value[key]),
  );
}

export function buildAnalyticsUrl(filters: AnalyticsFilters): string {
  const params = new URLSearchParams();
  for (const name of FILTER_NAMES) {
    const value = filters[name].trim();
    if (value) params.set(name, value);
  }
  const query = params.toString();
  return query ? `${RECEIVING_ANALYTICS_ENDPOINT}?${query}` : RECEIVING_ANALYTICS_ENDPOINT;
}

export async function fetchReceivingAnalytics(
  filters: AnalyticsFilters,
  signal: AbortSignal,
): Promise<ReceivingAnalyticsResponse> {
  const response = await fetch(buildAnalyticsUrl(filters), {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });

  if (!response.ok) {
    throw new ReceivingAnalyticsApiError(
      response.status === 422
        ? "Check the filter values and try again."
        : "The analytics request could not be completed.",
    );
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ReceivingAnalyticsApiError("The analytics service returned unreadable data.");
  }
  if (!isAnalyticsResponse(payload)) {
    throw new ReceivingAnalyticsApiError("The analytics service returned an unexpected response.");
  }
  return payload;
}