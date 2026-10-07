// Filter state is mirrored in the URL. Parameter names match the API exactly, so
// the page's query string can be passed to /api/dashboard unchanged.

export const MULTI_FILTERS = ["outlet", "group", "order_type", "settlement"];
export const DEFAULT_GRANULARITY = "week";

export function readFilters(searchParams) {
  const filters = {
    start: searchParams.get("start") || "",
    end: searchParams.get("end") || "",
    granularity: searchParams.get("granularity") === "day" ? "day" : DEFAULT_GRANULARITY,
  };
  for (const key of MULTI_FILTERS) {
    filters[key] = searchParams.getAll(key);
  }
  return filters;
}

// Defaults are left out so the plain URL means "everything, weekly".
export function toQueryString(filters) {
  const params = new URLSearchParams();
  if (filters.start) params.set("start", filters.start);
  if (filters.end) params.set("end", filters.end);
  for (const key of MULTI_FILTERS) {
    for (const value of [...filters[key]].sort()) params.append(key, value);
  }
  if (filters.granularity !== DEFAULT_GRANULARITY) params.set("granularity", filters.granularity);
  return params.toString();
}

export function hasActiveFilters(filters) {
  return Boolean(filters.start || filters.end || MULTI_FILTERS.some((k) => filters[k].length));
}

export function dateRangeError(filters) {
  if (filters.start && filters.end && filters.start > filters.end) {
    return "The start date is after the end date.";
  }
  return null;
}

const OPTION_KEYS = { outlet: "outlets", group: "groups", order_type: "order_types", settlement: "settlements" };

function isValidDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value; // rejects 2026-02-30
}

// Drop URL values that don't exist in the data (e.g. a hand-edited or stale
// link), so they never show as selected or reach the API.
export function sanitizeFilters(filters, options) {
  const clean = { ...filters };
  for (const key of MULTI_FILTERS) {
    const allowed = options[OPTION_KEYS[key]];
    clean[key] = [...new Set(filters[key])].filter((v) => allowed.includes(v));
  }
  for (const key of ["start", "end"]) {
    if (clean[key] && !isValidDate(clean[key])) clean[key] = "";
  }
  return clean;
}
