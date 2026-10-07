"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatCount, formatHourRange, formatPercent, formatRupees } from "@/lib/format";
import { AXIS_TICK, COLORS } from "@/lib/theme";

export default function HourlyChart({ hourly, totalOrders }) {
  const busiest = hourly.reduce((best, h) => (h.orders > (best?.orders ?? -1) ? h : best), null);
  const quietest = hourly.reduce((low, h) => (h.orders < (low?.orders ?? Infinity) ? h : low), null);
  const caption = busiest
    ? `Busiest hour: ${formatHourRange(busiest.hour)}, with ${formatCount(busiest.orders)} orders (${formatPercent(busiest.orders, totalOrders)} of orders).`
    : "";
  const summary = busiest
    ? `Bar chart of orders by hour of day, ${formatHourRange(hourly[0].hour)} to ${formatHourRange(hourly[hourly.length - 1].hour)}. `
      + `${caption} Quietest hour: ${formatHourRange(quietest.hour)}, with ${formatCount(quietest.orders)} orders.`
    : "Bar chart of orders by hour of day.";

  return (
    <section className="panel" aria-labelledby="hourly-title">
      <h2 id="hourly-title">Orders by hour of day</h2>
      <p className="panel-caption">{caption}</p>
      <div role="img" aria-label={summary}>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={hourly} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={3}>
            <CartesianGrid stroke={COLORS.grid} vertical={false} />
            <XAxis dataKey="hour" tickFormatter={(h) => String(h).padStart(2, "0")} tick={AXIS_TICK}
                   tickLine={false} axisLine={{ stroke: COLORS.grid }} interval={0} />
            <YAxis tickFormatter={formatCount} tick={AXIS_TICK} axisLine={false} tickLine={false} width={56} />
            <Tooltip content={<HourTooltip totalOrders={totalOrders} />} cursor={{ fill: COLORS.grid, opacity: 0.6 }} />
            <Bar dataKey="orders" fill={COLORS.data} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="chart-note">Hour the order was placed (24-hour clock).</p>
    </section>
  );
}

function HourTooltip({ active, payload, totalOrders }) {
  if (!active || !payload?.length) return null;
  const h = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{formatHourRange(h.hour)}</p>
      <p>{formatCount(h.orders)} orders ({formatPercent(h.orders, totalOrders)})</p>
      <p>{formatRupees(h.revenue)} gross revenue</p>
    </div>
  );
}
