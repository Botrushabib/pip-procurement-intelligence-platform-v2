export type FilterName =
  | "company_id" | "warehouse_id" | "supplier_id" | "product_id"
  | "category_id" | "unit_id" | "date_from" | "date_to" | "reference";
export type AnalyticsFilters = Record<FilterName, string>;
export type FilterErrors = Partial<Record<FilterName, string>>;

export interface ReceivingAnalyticsSummary {
  examined_lines: number;
  eligible_lines: number;
  distinct_event_count: number;
  total_quantity: number;
  total_spend: number;
  average_unit_price: number | null;
  minimum_unit_price: number | null;
  maximum_unit_price: number | null;
}

export interface ReceivingHistorySection {
  last_receiving: {
    event_date: string; unit_price: number; quantity: number;
    supplier_id: number; supplier_name: string | null;
    warehouse_id: number; warehouse_name: string | null;
    receiving_reference: string; event_id: number; line_id: number;
  } | null;
  receiving_frequency: {
    event_count: number; line_count: number; first_receiving_date: string | null;
    last_receiving_date: string | null; average_days_between_receipts: number | null;
  };
  monthly_totals: Array<{
    year: number; month: number; event_count: number; line_count: number;
    total_quantity: number; total_subtotal: number; average_unit_price: number | null;
  }>;
  data_quality: {
    total_lines: number; eligible_lines: number; ineligible_lines: number;
    missing_date_count: number; missing_product_count: number;
    missing_quantity_count: number; missing_price_count: number;
    missing_supplier_count: number; missing_warehouse_count: number;
  };
}

export interface ReceivingAnalyticsLine {
  event_id: number; line_id: number; line_number: number; event_date: string;
  supplier_id: number; supplier_name: string | null;
  product_id: number; product_code: string | null; product_name: string | null;
  unit_id: number; unit_name: string | null;
  company_id: number; company_name: string | null;
  warehouse_id: number; warehouse_name: string | null;
  quantity: number; unit_price: number; subtotal: number;
  receiving_reference: string; source_file: string; source_sheet: string; source_row: number;
}

export interface ReceivingPriceSection {
  request: {
    product_id: number; unit_id: number | null; supplier_id: number | null;
    company_id: number | null; warehouse_id: number | null;
    date_from: string | null; date_to: string | null; reference: string | null;
    current_unit_price: number | null;
  };
  sufficiency: string;
  observations: ReceivingAnalyticsLine[];
  observation_count: number;
  current_price: number | null; current_price_source: string;
  latest_observed_price: number | null; previous_observed_price: number | null;
  weighted_average_price: number | null; arithmetic_average_price: number | null;
  minimum_price: number | null; maximum_price: number | null; price_spread: number | null;
  standard_deviation: number | null; recent_average_price: number | null; trend: string;
  price_change: {
    status: string; previous_price: number | null; current_price: number | null;
    absolute_change: number | null; percentage_change: number | null; reason: string;
  };
  anomaly: {
    status: string; current_price: number | null; reference_average: number | null;
    standard_deviation: number | null; difference: number | null;
    percentage_difference: number | null; z_score: number | null; method: string; reason: string;
  };
  confidence: string;
  data_quality: {
    examined_lines: number; analytics_eligible_lines: number; comparable_lines: number;
    missing_product_count: number; missing_date_count: number;
    missing_price_count: number; missing_unit_count: number;
  };
}

export interface ReceivingSupplierSection {
  request: {
    supplier_id: number; product_id: number | null; unit_id: number | null;
    company_id: number | null; warehouse_id: number | null;
    date_from: string | null; date_to: string | null; reference: string | null;
  };
  sufficiency: string;
  observations: ReceivingAnalyticsLine[];
  summary: {
    observation_count: number; distinct_event_count: number; distinct_product_count: number;
    distinct_receiving_date_count: number; total_quantity: number; total_spend: number;
    weighted_average_unit_price: number | null; arithmetic_average_unit_price: number | null;
    min_unit_price: number | null; max_unit_price: number | null; price_spread: number | null;
    first_receiving_date: string | null; latest_receiving_date: string | null;
    average_days_between_receipts: number | null;
  };
  monthly_activity: Array<{
    year: number; month: number; observation_count: number; distinct_event_count: number;
    distinct_product_count: number; total_quantity: number; total_spend: number;
    weighted_average_unit_price: number | null;
  }>;
  product_summaries: Array<{
    product_id: number; product_code: string | null; product_name: string | null;
    unit_id: number | null; unit_name: string | null; observation_count: number;
    total_quantity: number; total_spend: number; weighted_average_unit_price: number | null;
    arithmetic_average_unit_price: number | null; min_price: number | null; max_price: number | null;
    latest_price: number | null; first_receiving_date: string | null; latest_receiving_date: string | null;
  }>;
  data_quality: {
    examined_lines: number; analytics_eligible_lines: number; supplier_matched_lines: number;
    missing_supplier_count: number; missing_product_count: number; missing_date_count: number;
    missing_price_count: number; missing_quantity_count: number;
  };
}

export interface ReceivingCategorySection {
  request: {
    category_id: number; product_id: number | null; supplier_id: number | null;
    unit_id: number | null; company_id: number | null; warehouse_id: number | null;
    date_from: string | null; date_to: string | null; reference: string | null;
  };
  sufficiency: string;
  observations: Array<ReceivingAnalyticsLine & { category_id: number; category_name: string | null }>;
  summary: {
    category_id: number; category_name: string | null; observation_count: number;
    distinct_event_count: number; distinct_product_count: number; distinct_supplier_count: number;
    distinct_receiving_date_count: number; total_quantity: number; total_spend: number;
    weighted_average_unit_price: number | null; arithmetic_average_unit_price: number | null;
    min_unit_price: number | null; max_unit_price: number | null; price_spread: number | null;
    first_receiving_date: string | null; latest_receiving_date: string | null;
    average_days_between_receipts: number | null;
  };
  monthly_activity: Array<{
    year: number; month: number; observation_count: number; distinct_event_count: number;
    distinct_product_count: number; distinct_supplier_count: number; total_quantity: number;
    total_spend: number; weighted_average_unit_price: number | null;
  }>;
  product_summaries: Array<{
    product_id: number; product_code: string | null; product_name: string | null;
    unit_id: number | null; unit_name: string | null; observation_count: number;
    distinct_supplier_count: number; total_quantity: number; total_spend: number;
    weighted_average_unit_price: number | null; arithmetic_average_unit_price: number | null;
    min_price: number | null; max_price: number | null; latest_price: number | null;
    first_receiving_date: string | null; latest_receiving_date: string | null;
  }>;
  supplier_summaries: Array<{
    supplier_id: number; supplier_name: string | null; observation_count: number;
    distinct_event_count: number; distinct_product_count: number; total_quantity: number;
    total_spend: number; weighted_average_unit_price: number | null;
    arithmetic_average_unit_price: number | null; min_price: number | null; max_price: number | null;
    first_receiving_date: string | null; latest_receiving_date: string | null;
  }>;
  data_quality: {
    examined_lines: number; analytics_eligible_lines: number; category_matched_lines: number;
    missing_category_count: number; missing_product_count: number; missing_supplier_count: number;
    missing_date_count: number; missing_price_count: number; missing_quantity_count: number;
    missing_unit_count: number;
  };
}

export interface ReceivingTrendObservation {
  event_date: string; event_id: number; line_id: number; line_number: number;
  company_id: number; warehouse_id: number; supplier_id: number; product_id: number;
  category_id: number; unit_id: number; quantity: number; unit_price: number;
  subtotal: number; reference: string;
}

export interface ReceivingTrendValues {
  year: number; month: number; observation_count: number;
  total_quantity: number; total_spend: number;
  weighted_average_price: number | null; arithmetic_average_price: number | null;
  minimum_price: number | null; maximum_price: number | null; price_spread: number | null;
  distinct_receiving_dates: number; quantity_change: number | null; quantity_change_pct: number | null;
  spend_change: number | null; spend_change_pct: number | null;
  price_change: number | null; price_change_pct: number | null;
}

export interface ReceivingTrendSection {
  observations: ReceivingTrendObservation[];
  monthly_trends: ReceivingTrendValues[];
  product_monthly_trends: Array<ReceivingTrendValues & { product_id: number; unit_id: number }>;
  supplier_monthly_trends: Array<ReceivingTrendValues & { supplier_id: number; distinct_products: number }>;
  category_monthly_trends: Array<ReceivingTrendValues & {
    category_id: number; distinct_products: number; distinct_suppliers: number;
  }>;
  quality: {
    examined_lines: number; analytics_eligible_lines: number;
    missing_supplier: number; missing_product: number; missing_category: number;
    missing_unit: number; missing_event_date: number; missing_quantity: number; missing_unit_price: number;
  };
}

export interface ReceivingSupplierComparisonSection {
  request: {
    supplier_ids: number[] | null; product_id: number | null; category_id: number | null;
    unit_id: number | null; company_id: number | null; warehouse_id: number | null;
    date_from: string | null; date_to: string | null; reference: string | null;
  };
  sufficiency: string;
  observations: Array<ReceivingAnalyticsLine & { category_id: number | null; category_name: string | null }>;
  supplier_summaries: Array<{
    supplier_id: number; supplier_name: string | null; observation_count: number;
    distinct_event_count: number; distinct_product_count: number; distinct_category_count: number;
    distinct_receiving_date_count: number; total_quantity: number; total_spend: number;
    weighted_average_unit_price: number | null; arithmetic_average_unit_price: number | null;
    min_unit_price: number | null; max_unit_price: number | null; price_spread: number | null;
    first_receiving_date: string | null; latest_receiving_date: string | null;
    average_days_between_receipts: number | null;
  }>;
  supplier_product_comparisons: Array<{
    product_id: number; product_code: string | null; product_name: string | null;
    unit_id: number | null; unit_name: string | null; supplier_id: number; supplier_name: string | null;
    observation_count: number; distinct_event_count: number; total_quantity: number; total_spend: number;
    weighted_average_unit_price: number | null; arithmetic_average_unit_price: number | null;
    min_unit_price: number | null; max_unit_price: number | null; price_spread: number | null;
    latest_price: number | null; first_receiving_date: string | null; latest_receiving_date: string | null;
    price_position: string | null; price_difference_vs_lowest: number | null;
    price_difference_percentage_vs_lowest: number | null;
  }>;
  product_price_comparisons: Array<{
    product_id: number; product_code: string | null; product_name: string | null;
    unit_id: number | null; unit_name: string | null; supplier_count: number;
    lowest_weighted_average_price: number | null; highest_weighted_average_price: number | null;
    price_spread: number | null; lowest_price_supplier_id: number | null;
    lowest_price_supplier_name: string | null; highest_price_supplier_id: number | null;
    highest_price_supplier_name: string | null;
  }>;
  data_quality: {
    examined_lines: number; analytics_eligible_lines: number; matched_supplier_lines: number;
    missing_supplier_count: number; missing_product_count: number; missing_category_count: number;
    missing_unit_count: number; missing_date_count: number; missing_price_count: number;
    missing_quantity_count: number;
  };
}

export interface ReceivingAnalyticsResponse {
  summary: ReceivingAnalyticsSummary;
  history: ReceivingHistorySection;
  price: ReceivingPriceSection | null;
  supplier: ReceivingSupplierSection | null;
  category: ReceivingCategorySection | null;
  trend: ReceivingTrendSection;
  supplier_comparison: ReceivingSupplierComparisonSection;
}