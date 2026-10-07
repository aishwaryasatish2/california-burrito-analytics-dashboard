import { formatCount, formatRupees } from "@/lib/format";

// A table rather than a chart: item names are long, and units and orders
// belong next to revenue. The inline bar keeps the ranking visible.
export default function TopItemsTable({ items }) {
  const max = items[0]?.revenue || 1;
  return (
    <section className="panel" aria-labelledby="top-items-title">
      <h2 id="top-items-title">Top {items.length} items by gross revenue</h2>
      <div className="table-scroll">
        <table className="data-table top-items">
          <thead>
            <tr>
              <th scope="col" className="num rank">Rank</th>
              <th scope="col">Item</th>
              <th scope="col" className="hide-sm">Menu group</th>
              <th scope="col" className="revenue-col">Gross revenue</th>
              <th scope="col" className="num">Units</th>
              <th scope="col" className="num hide-sm">Orders</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={item.item}>
                <td className="num rank">{i + 1}</td>
                <th scope="row">{item.item}</th>
                <td className="hide-sm muted">{item.group}</td>
                <td className="revenue-col">
                  <div className="inline-bar">
                    <span className="inline-bar-fill" style={{ width: `${(100 * item.revenue) / max}%` }} aria-hidden="true" />
                    <span className="inline-bar-value">{formatRupees(item.revenue)}</span>
                  </div>
                </td>
                <td className="num">{formatCount(item.units)}</td>
                <td className="num hide-sm">{formatCount(item.orders)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
