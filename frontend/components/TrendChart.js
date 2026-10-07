"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatCount, formatLongDate, formatRupees, formatRupeesCompact, formatShortDate } from "@/lib/format";
import { AXIS_TICK, COLORS } from "@/lib/theme";

const SYNC_ID = "trend";

export default function TrendChart({ trend, granularity, onGranularityChange, dataRange }) {
  const points = trend.points;
  const weekly = granularity === "week";
  const hasPartial = points.some((p) => p.is_partial);

  // Weekly: small markers, hollow for partial weeks. Daily (~365 points): no markers.
  const renderDot = (props) => {
    const { cx, cy, index, payload } = props;
    if (!weekly || cx == null || cy == null) return <g key={index} />;
    return payload.is_partial
      ? <circle key={index} cx={cx} cy={cy} r={4} fill={COLORS.background} stroke={COLORS.data} strokeWidth={1.5} />
      : <circle key={index} cx={cx} cy={cy} r={2} fill={COLORS.data} />;
  };

  const summary = describeTrend(points, weekly);

  return (
    <section className="panel" aria-labelledby="trend-title">
      <div className="panel-header">
        <h2 id="trend-title">Revenue and orders over time</h2>
        <div className="segmented" role="group" aria-label="Time granularity">
          {[["week", "Weekly"], ["day", "Daily"]].map(([value, label]) => (
            <button key={value} type="button" aria-pressed={granularity === value}
                    onClick={() => onGranularityChange(value)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      <div role="img" aria-label={summary}>
        <p className="chart-label">Gross revenue</p>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={points} syncId={SYNC_ID} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={COLORS.grid} vertical={false} />
            <XAxis dataKey="period_start" hide />
            {/* Zero baseline: weekly revenue is very stable, and a truncated axis would
                exaggerate small wobbles. */}
            <YAxis domain={[0, "auto"]} tickFormatter={formatRupeesCompact} tick={AXIS_TICK} axisLine={false} tickLine={false} width={72} />
            <Tooltip content={<TrendTooltip weekly={weekly} />} cursor={{ stroke: COLORS.muted, strokeDasharray: "3 3" }} />
            <Line type="linear" dataKey="revenue" stroke={COLORS.data} strokeWidth={1.75}
                  dot={renderDot} activeDot={{ r: 4 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>

        <p className="chart-label">Orders</p>
        <ResponsiveContainer width="100%" height={150}>
          <LineChart data={points} syncId={SYNC_ID} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={COLORS.grid} vertical={false} />
            <XAxis dataKey="period_start" tickFormatter={formatShortDate} tick={AXIS_TICK}
                   tickLine={false} axisLine={{ stroke: COLORS.grid }} minTickGap={28} />
            <YAxis domain={[0, "auto"]} tickFormatter={formatCount} tick={AXIS_TICK} axisLine={false} tickLine={false} width={72} />
            {/* Hover is synced with the revenue chart, whose tooltip shows both values. */}
            <Tooltip content={() => null} cursor={{ stroke: COLORS.muted, strokeDasharray: "3 3" }} />
            <Line type="linear" dataKey="orders" stroke={COLORS.dataMid} strokeWidth={1.75}
                  dot={renderDot} activeDot={{ r: 4 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {weekly && hasPartial && (
        <p className="chart-note">
          <span className="hollow-marker" aria-hidden="true" /> Partial week: only some of its days fall
          inside the selected dates
          {dataRange ? ` (the data runs from ${formatLongDate(dataRange.min_date)} to ${formatLongDate(dataRange.max_date)})` : ""},
          so its totals are not comparable with full weeks. Weeks start on Monday.
        </p>
      )}
    </section>
  );
}

function TrendTooltip({ active, payload, weekly }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">
        {weekly ? `Week of ${formatLongDate(point.period_start)}` : formatLongDate(point.period_start)}
      </p>
      {point.is_partial && <p className="tooltip-flag">Partial week</p>}
      <p>{formatRupees(point.revenue)} gross revenue</p>
      <p>{formatCount(point.orders)} orders</p>
    </div>
  );
}

// Text alternative: range and average over full periods, so partial weeks
// don't distort the figures read out to screen-reader users.
function describeTrend(points, weekly) {
  const unit = weekly ? "week" : "day";
  const full = points.filter((p) => !p.is_partial);
  if (!points.length) return `Line charts of gross revenue and orders per ${unit}: no data.`;
  const basis = full.length ? full : points;
  const revenues = basis.map((p) => p.revenue);
  const orders = basis.map((p) => p.orders);
  const average = Math.round(revenues.reduce((a, b) => a + b, 0) / revenues.length);
  const partialNote = full.length < points.length
    ? ` ${points.length - full.length} partial ${points.length - full.length > 1 ? "weeks are" : "week is"} excluded from these figures.`
    : "";
  return `Line charts of gross revenue and orders per ${unit}, ${formatLongDate(points[0].period_start)} to `
    + `${formatLongDate(points[points.length - 1].period_start)}. Across ${basis.length} ${full.length ? "full " : ""}${unit}s, `
    + `gross revenue ranged from ${formatRupeesCompact(Math.min(...revenues))} to ${formatRupeesCompact(Math.max(...revenues))} `
    + `(average ${formatRupeesCompact(average)}), and orders from ${formatCount(Math.min(...orders))} to ${formatCount(Math.max(...orders))}.`
    + partialNote;
}
