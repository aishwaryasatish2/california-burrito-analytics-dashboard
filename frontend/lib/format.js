// Number and date formatting used across the dashboard (Indian conventions:
// lakh/crore for money, en-IN digit grouping for counts).

const count = new Intl.NumberFormat("en-IN");

export function formatCount(n) {
  return count.format(n);
}

export function formatRupees(n) {
  return "₹" + count.format(Math.round(n));
}

const twoDecimals = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Rupees with paise, e.g. AOV: ₹632.29, ₹1,234.50.
export function formatRupeesPrecise(n) {
  return "₹" + twoDecimals.format(n);
}

// Compact money for headline figures and axes: ₹6.95 Cr, ₹16.7 L, ₹1.05 L, ₹8,400.
// Two decimals (trailing zeros trimmed) so axis ticks like 1,05,000 aren't rounded to "1.1 L".
export function formatRupeesCompact(n) {
  const abs = Math.abs(n);
  if (abs >= 1e7) return `₹${trim(n / 1e7, 2)} Cr`;
  if (abs >= 1e5) return `₹${trim(n / 1e5, 2)} L`;
  return formatRupees(n);
}

function trim(value, digits) {
  return Number(value.toFixed(digits)).toString();
}

export function formatPercent(part, whole) {
  if (!whole) return "–";
  return `${(100 * part / whole).toFixed(1)}%`;
}

const shortDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const longDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

// API dates are plain YYYY-MM-DD; parse as UTC so the browser's timezone
// can never shift them by a day.
function parseDate(iso) {
  return new Date(`${iso}T00:00:00Z`);
}

export function formatShortDate(iso) {
  return shortDate.format(parseDate(iso));
}

export function formatLongDate(iso) {
  return longDate.format(parseDate(iso));
}

export function formatHour(hour) {
  return `${String(hour % 24).padStart(2, "0")}:00`;
}

// One-hour interval starting at `hour`; the last one is 23:00–00:00.
export function formatHourRange(hour) {
  return `${formatHour(hour)}–${formatHour(hour + 1)}`;
}
