"use client";

import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";

import { formatCount, formatPercent } from "@/lib/format";
import { COLORS } from "@/lib/theme";

const SLICE_COLORS = [COLORS.data, COLORS.dataMid, COLORS.dataLight];

export default function OrderTypePanel({ orderTypes, channels }) {
  const types = [...orderTypes].sort((a, b) => b.orders - a.orders);
  const totalOrders = types.reduce((sum, t) => sum + t.orders, 0);
  const summary = `Donut chart of ${formatCount(totalOrders)} orders by order type: ${types
    .map((t) => `${t.order_type} ${formatCount(t.orders)} (${formatPercent(t.orders, totalOrders)})`).join(", ")}.`;

  return (
    <section className="panel" aria-labelledby="order-type-title">
      <h2 id="order-type-title">Order type</h2>
      <div className="donut-layout">
        <div role="img" aria-label={summary}>
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie data={types} dataKey="orders" nameKey="order_type" innerRadius="62%" outerRadius="94%"
                   startAngle={90} endAngle={-270} stroke={COLORS.background} strokeWidth={2}
                   isAnimationActive={false}>
                {types.map((t, i) => <Cell key={t.order_type} fill={SLICE_COLORS[i % SLICE_COLORS.length]} />)}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>
        <table className="legend-table">
          <caption className="visually-hidden">Orders by order type</caption>
          <thead>
            <tr><th scope="col">Order type</th><th scope="col" className="num">Orders</th><th scope="col" className="num">Share</th></tr>
          </thead>
          <tbody>
            {types.map((t, i) => (
              <tr key={t.order_type}>
                <th scope="row">
                  <span className="swatch" style={{ background: SLICE_COLORS[i % SLICE_COLORS.length] }} aria-hidden="true" />
                  {t.order_type}
                </th>
                <td className="num">{formatCount(t.orders)}</td>
                <td className="num">{formatPercent(t.orders, totalOrders)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Channel / settlement within each order type</h3>
      <div className="table-scroll">
        <table className="data-table channel-table">
          <thead>
            <tr>
              <th scope="col">Order type</th>
              <th scope="col">Settlement</th>
              <th scope="col" className="num">Orders</th>
              <th scope="col" className="num">Share of type</th>
            </tr>
          </thead>
          <tbody>
            {types.map((t) =>
              channels
                .filter((c) => c.order_type === t.order_type)
                .sort((a, b) => b.orders - a.orders)
                .map((c, i) => (
                  <tr key={`${c.order_type}-${c.settlement}`} className={i === 0 ? "group-start" : undefined}>
                    <td>{i === 0 ? c.order_type : ""}</td>
                    <td>{c.settlement}</td>
                    <td className="num">{formatCount(c.orders)}</td>
                    <td className="num">{formatPercent(c.orders, t.orders)}</td>
                  </tr>
                ))
            )}
          </tbody>
        </table>
      </div>
      <p className="chart-note">
        Settlement is recorded per order in the source data. &ldquo;Cash/Card/Coupon&rdquo; is a single
        combined value there, so it cannot be split into separate payment methods.
      </p>
    </section>
  );
}
