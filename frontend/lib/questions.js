// The fixed questions behind "Ask About Your Data".
//
// Each answer is a plain function of the /api/dashboard response that is
// already on screen, so it follows the current filters and requests nothing
// new from the API. The observations are comparisons computed from that same
// result (shares, gaps, ranks). They say where the numbers differ, never why.

import { formatCount, formatHourRange, formatPercent, formatRupees, formatRupeesPrecise } from "@/lib/format";

// Settlement values that only occur on Delivery orders in this dataset.
const AGGREGATORS = ["SwiggyPay", "ZomatoPay"];
// One source value covering cash, card and coupon together.
const COMBINED = "Cash/Card/Coupon";

const pct = formatPercent;
const last = (rows) => rows[rows.length - 1];

// ---------------------------------------------------------------- outlets

function outletRevenue(data) {
  const rows = data.by_outlet; // the API returns these sorted by revenue, highest first
  const total = data.kpis.gross_revenue;
  if (!total) return { empty: "There is no gross revenue in the current selection." };
  const [top, second] = rows;

  const findings = [
    `${top.outlet} has the highest gross revenue: ${formatRupees(top.revenue)}, ${pct(top.revenue, total)} of the total.`,
  ];
  const gaps = [];
  if (second) {
    gaps.push(`${top.outlet} is ${formatRupees(top.revenue - second.revenue)} (${pct(top.revenue - second.revenue, second.revenue)}) ahead of ${second.outlet}, the next outlet.`);
  } else {
    findings.push("Only one outlet is in the current selection, so there is nothing to compare it with.");
  }
  if (rows.length > 2) {
    gaps.push(`${last(rows).outlet}, the lowest, earns ${pct(last(rows).revenue, top.revenue)} of ${top.outlet}'s gross revenue.`);
  }

  return {
    columns: ["Outlet", "Gross revenue", "Share of total"],
    rows: rows.map((r) => [r.outlet, formatRupees(r.revenue), pct(r.revenue, total)]),
    findings,
    gaps,
  };
}

function outletAov(data) {
  const rows = data.by_outlet.filter((r) => r.aov != null).sort((a, b) => b.aov - a.aov);
  if (!rows.length) return { empty: "There are no paid orders in the current selection." };
  const top = rows[0];
  const bottom = last(rows);

  const findings = [`${top.outlet} has the highest average order value: ${formatRupeesPrecise(top.aov)}.`];
  if (data.scope.line_level_filter) {
    findings.push("A menu group filter is active, so this is the average spend on the selected group per order, not the whole basket.");
  }
  const gaps = [];
  if (rows.length > 1) {
    gaps.push(`${top.outlet} is ${formatRupeesPrecise(top.aov - bottom.aov)} (${pct(top.aov - bottom.aov, bottom.aov)}) above ${bottom.outlet}, the lowest.`);
    const revenueRank = data.by_outlet.findIndex((r) => r.outlet === top.outlet) + 1;
    gaps.push(revenueRank === 1
      ? `${top.outlet} also has the highest gross revenue.`
      : `${top.outlet} ranks ${revenueRank} of ${data.by_outlet.length} outlets by gross revenue.`);
  }

  return {
    columns: ["Outlet", "Average order value", "Orders"],
    rows: rows.map((r) => [r.outlet, formatRupeesPrecise(r.aov), formatCount(r.orders)]),
    findings,
    gaps,
  };
}

// ----------------------------------------------------------- menu groups

function groupRevenue(data) {
  const rows = data.by_group; // sorted by revenue, highest first
  const total = data.kpis.gross_revenue;
  if (!total) return { empty: "There is no gross revenue in the current selection." };
  const [top, second] = rows;

  const findings = [
    `${top.group} has the highest gross revenue: ${formatRupees(top.revenue)}, ${pct(top.revenue, total)} of the total.`,
  ];
  if (rows.length > 2) {
    findings.push(`The top two groups, ${top.group} and ${second.group}, together account for ${pct(top.revenue + second.revenue, total)}.`);
  }
  const gaps = [];
  if (rows.length > 1) {
    gaps.push(`${last(rows).group}, the lowest, contributes ${pct(last(rows).revenue, total)} of gross revenue.`);
    const mostUnits = [...rows].sort((a, b) => b.units - a.units)[0];
    if (mostUnits.group !== top.group) {
      const rank = rows.findIndex((r) => r.group === mostUnits.group) + 1;
      gaps.push(`${mostUnits.group} sells the most units (${formatCount(mostUnits.units)}) but ranks ${rank} of ${rows.length} by gross revenue.`);
    }
  }

  return {
    columns: ["Menu group", "Gross revenue", "Units", "Share of total"],
    rows: rows.map((r) => [r.group, formatRupees(r.revenue), formatCount(r.units), pct(r.revenue, total)]),
    findings,
    gaps,
  };
}

// ----------------------------------------------------------- order types

function orderTypes(data) {
  const rows = [...data.by_order_type].sort((a, b) => b.orders - a.orders);
  const totalOrders = data.kpis.orders;
  const totalRevenue = data.kpis.gross_revenue;
  const top = rows[0];

  const findings = [
    `${top.order_type} is the most common order type: ${formatCount(top.orders)} orders, ${pct(top.orders, totalOrders)} of the total.`,
  ];
  const gaps = [];
  if (rows.length > 1) {
    if (totalRevenue) {
      gaps.push(`${top.order_type} is ${pct(top.orders, totalOrders)} of orders but ${pct(top.revenue, totalRevenue)} of gross revenue.`);
    }
    const withAov = rows.filter((r) => r.aov != null).sort((a, b) => b.aov - a.aov);
    if (withAov.length > 1) {
      gaps.push(`${withAov[0].order_type} has the highest average order value (${formatRupeesPrecise(withAov[0].aov)}) and ${last(withAov).order_type} the lowest (${formatRupeesPrecise(last(withAov).aov)}).`);
    }
  } else {
    findings.push("Only one order type is in the current selection.");
  }

  return {
    columns: ["Order type", "Orders", "Share of orders", "Average order value"],
    rows: rows.map((r) => [r.order_type, formatCount(r.orders), pct(r.orders, totalOrders), r.aov != null ? formatRupeesPrecise(r.aov) : "–"]),
    findings,
    gaps,
  };
}

// ------------------------------------------------------------------ hours

function busiestHours(data) {
  const totalOrders = data.kpis.orders;
  const byOrders = [...data.hourly].sort((a, b) => b.orders - a.orders || a.hour - b.hour);
  const top = byOrders[0];
  const topThree = byOrders.slice(0, 3);

  const findings = [
    `Orders are busiest at ${formatHourRange(top.hour)}: ${formatCount(top.orders)} orders, ${pct(top.orders, totalOrders)} of the total.`,
  ];
  if (topThree.length === 3) {
    findings.push(`The three busiest hours together account for ${pct(topThree.reduce((sum, h) => sum + h.orders, 0), totalOrders)} of orders.`);
  }
  const gaps = [];
  const quietest = byOrders[byOrders.length - 1];
  if (quietest.hour !== top.hour) {
    gaps.push(`${formatHourRange(quietest.hour)} is the quietest hour, with ${pct(quietest.orders, top.orders)} of the busiest hour's orders.`);
  }

  return {
    columns: ["Hour", "Orders", "Share of orders"],
    rows: topThree.map((h) => [formatHourRange(h.hour), formatCount(h.orders), pct(h.orders, totalOrders)]),
    findings,
    gaps,
  };
}

// --------------------------------------------------------------- delivery

function deliverySettlement(data) {
  const rows = data.channels.filter((c) => c.order_type === "Delivery").sort((a, b) => b.orders - a.orders);
  if (!rows.length) return { empty: "There are no delivery orders in the current selection." };
  const deliveryOrders = rows.reduce((sum, r) => sum + r.orders, 0);
  const top = rows[0];

  const findings = [
    `${top.settlement} settles the most delivery orders: ${formatCount(top.orders)}, ${pct(top.orders, deliveryOrders)} of delivery.`,
    `Delivery is ${pct(deliveryOrders, data.kpis.orders)} of all orders in the current selection.`,
  ];
  const gaps = [];
  const aggregators = rows.filter((r) => AGGREGATORS.includes(r.settlement));
  if (aggregators.length) {
    const orders = aggregators.reduce((sum, r) => sum + r.orders, 0);
    gaps.push(`${aggregators.map((r) => r.settlement).join(" and ")} together settle ${pct(orders, deliveryOrders)} of delivery orders.`);
  }
  const combined = rows.find((r) => r.settlement === COMBINED);
  if (combined) {
    gaps.push(`${COMBINED} settles ${pct(combined.orders, deliveryOrders)} of delivery orders. The source records cash, card and coupon as one value, so it cannot be split further.`);
  }

  return {
    columns: ["Settlement", "Orders", "Share of delivery orders"],
    rows: rows.map((r) => [r.settlement, formatCount(r.orders), pct(r.orders, deliveryOrders)]),
    findings,
    gaps,
  };
}

export const QUESTIONS = [
  { id: "outlet-revenue", label: "Which outlet earns the most gross revenue?", answer: outletRevenue },
  { id: "outlet-aov", label: "Which outlet has the highest average order value?", answer: outletAov },
  { id: "group-revenue", label: "Which menu group earns the most gross revenue?", answer: groupRevenue },
  { id: "order-types", label: "Which order type is the most common?", answer: orderTypes },
  { id: "busiest-hours", label: "When are orders busiest?", answer: busiestHours },
  { id: "delivery-settlement", label: "How are delivery orders settled?", answer: deliverySettlement },
];
