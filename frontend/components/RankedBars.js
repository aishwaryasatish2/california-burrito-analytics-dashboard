"use client";

import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatPercent, formatRupees, formatRupeesCompact } from "@/lib/format";
import { AXIS_TICK, COLORS } from "@/lib/theme";

const ROW_HEIGHT = 34;

// rows: [{ label, value, details: [string] }]. The API already returns them
// sorted by revenue (highest first), so they are drawn in the order given.
export default function RankedBars({ title, rows, total }) {
  const data = rows;
  const summary = data.length
    ? `${title}, highest first: ${data
        .map((r) => `${r.label} ${formatRupeesCompact(r.value)} (${formatPercent(r.value, total)})`)
        .join(", ")}.`
    : title;

  return (
    <section className="panel" aria-label={title}>
      <h2>{title}</h2>
      <div role="img" aria-label={summary}>
        <ResponsiveContainer width="100%" height={data.length * ROW_HEIGHT + 8}>
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 72, bottom: 0, left: 0 }}
                    barCategoryGap={8}>
            <XAxis type="number" hide domain={[0, "dataMax"]} />
            <YAxis type="category" dataKey="label" tick={{ ...AXIS_TICK, fill: COLORS.ink }}
                   tickLine={false} axisLine={false} width={124} />
            <Tooltip content={<BarTooltip total={total} />} cursor={{ fill: COLORS.grid, opacity: 0.6 }} />
            <Bar dataKey="value" fill={COLORS.data} isAnimationActive={false}>
              <LabelList dataKey="value" position="right" formatter={formatRupeesCompact}
                         style={{ fill: COLORS.ink, fontSize: 12 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function BarTooltip({ active, payload, total }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{row.label}</p>
      <p>{formatRupees(row.value)} gross revenue ({formatPercent(row.value, total)})</p>
      {row.details.filter(Boolean).map((d) => <p key={d}>{d}</p>)}
    </div>
  );
}
