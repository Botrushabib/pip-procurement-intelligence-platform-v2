import type { FormEvent } from "react";
import type {
  AnalyticsFilters as FilterValues,
  FilterErrors,
  FilterName,
} from "../types/receivingAnalytics";

const FILTER_FIELDS: ReadonlyArray<{
  name: FilterName;
  label: string;
  type: "number" | "date" | "text";
}> = [
  { name: "company_id", label: "Company ID", type: "number" },
  { name: "warehouse_id", label: "Warehouse ID", type: "number" },
  { name: "supplier_id", label: "Supplier ID", type: "number" },
  { name: "product_id", label: "Product ID", type: "number" },
  { name: "category_id", label: "Category ID", type: "number" },
  { name: "unit_id", label: "Unit ID", type: "number" },
  { name: "date_from", label: "From date", type: "date" },
  { name: "date_to", label: "To date", type: "date" },
  { name: "reference", label: "Receiving reference", type: "text" },
];

// Same nine existing fields, grouped only for presentation; no field is added or removed.
const FILTER_GROUPS: ReadonlyArray<{ title: string; fields: readonly FilterName[] }> = [
  { title: "Scope", fields: ["company_id", "warehouse_id"] },
  { title: "Target", fields: ["supplier_id", "product_id", "category_id", "unit_id"] },
  { title: "Range", fields: ["date_from", "date_to", "reference"] },
];

export function validateAnalyticsFilters(filters: FilterValues): FilterErrors {
  const errors: FilterErrors = {};
  const idFields = [
    "company_id", "warehouse_id", "supplier_id", "product_id", "category_id", "unit_id",
  ] as const;

  for (const name of idFields) {
    const value = filters[name].trim();
    if (value && (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) <= 0)) {
      errors[name] = "Enter a positive whole number.";
    }
  }
  if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) {
    errors.date_to = "Choose a date on or after the from date.";
  }
  if (filters.reference && !filters.reference.trim()) {
    errors.reference = "Enter a reference or leave this field empty.";
  }
  return errors;
}

export function AnalyticsFilters({
  value,
  errors,
  onChange,
  onApply,
  onReset,
}: {
  value: FilterValues;
  errors: FilterErrors;
  onChange: (name: FilterName, nextValue: string) => void;
  onApply: (event: FormEvent<HTMLFormElement>) => void;
  onReset: () => void;
}) {
  return (
    <form className="filter-panel" noValidate onSubmit={onApply}>
      <div className="filter-heading">
        <div><span className="eyebrow">Query</span><h2>Filter receiving records</h2></div>
        <div className="filter-actions">
          <button className="button button-quiet" type="button" onClick={onReset}>Reset</button>
          <button className="button button-primary" type="submit">Apply filters</button>
        </div>
      </div>
      <div className="filter-groups">
        {FILTER_GROUPS.map((group) => (
          <fieldset className="filter-group" key={group.title}>
            <legend>{group.title}</legend>
            <div className="filter-grid">
              {group.fields.map((name) => {
                const field = FILTER_FIELDS.find((candidate) => candidate.name === name);
                if (!field) return null;
                const errorId = `${field.name}-error`;
                return (
                  <div className="filter-field" key={field.name}>
                    <label htmlFor={field.name}>{field.label}</label>
                    <input
                      id={field.name}
                      name={field.name}
                      type={field.type}
                      min={field.type === "number" ? 1 : undefined}
                      step={field.type === "number" ? 1 : undefined}
                      inputMode={field.type === "number" ? "numeric" : undefined}
                      value={value[field.name]}
                      aria-invalid={Boolean(errors[field.name])}
                      aria-describedby={errors[field.name] ? errorId : undefined}
                      onChange={(event) => onChange(field.name, event.target.value)}
                    />
                    {errors[field.name] && <span className="field-error" id={errorId}>{errors[field.name]}</span>}
                  </div>
                );
              })}
            </div>
          </fieldset>
        ))}
      </div>
    </form>
  );
}