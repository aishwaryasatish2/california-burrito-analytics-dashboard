import { formatCount, formatRupees, formatRupeesCompact, formatRupeesPrecise } from "@/lib/format";

export default function KpiStrip({ kpis }) {
  const items = [
    {
      label: "Gross revenue",
      value: formatRupeesCompact(kpis.gross_revenue),
      title: formatRupees(kpis.gross_revenue),
      note: `${formatRupees(kpis.gross_revenue)} at list price × quantity`,
    },
    {
      label: "Orders",
      value: formatCount(kpis.orders),
      note: kpis.zero_value_orders
        ? `Includes ${formatCount(kpis.zero_value_orders)} zero-value orders`
        : "Distinct bills",
    },
    {
      label: "Average order value",
      value: kpis.aov != null ? formatRupeesPrecise(kpis.aov) : "–",
      note: kpis.zero_value_orders
        ? `Excludes ${formatCount(kpis.zero_value_orders)} zero-revenue orders`
        : "Gross revenue ÷ orders",
    },
    {
      label: "Units sold",
      value: formatCount(kpis.units_sold),
      note: "All units, including ₹0 items",
    },
    {
      label: "Items per order",
      value: kpis.items_per_order != null ? kpis.items_per_order.toFixed(2) : "–",
      note: `${formatCount(kpis.line_items)} line items`,
    },
  ];

  return (
    <dl className="kpi-strip">
      {items.map((item) => (
        <div className="kpi" key={item.label}>
          <dt>{item.label}</dt>
          <dd className="kpi-value" title={item.title}>{item.value}</dd>
          <dd className="kpi-note">{item.note}</dd>
        </div>
      ))}
    </dl>
  );
}
