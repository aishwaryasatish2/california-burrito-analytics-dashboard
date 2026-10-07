"""All dashboard SQL lives here. Query functions return plain rows; business
calculations (AOV, ratios, zero-filling, top-N) live in service.py.

Filter scope: every query joins order_items to orders and applies the same
WHERE clause, so all metrics describe the same set of matching line items.
With a menu-group filter, "revenue" is revenue from matching lines only, not
the whole bill.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


@dataclass(frozen=True)
class Filters:
    start: date | None = None  # inclusive
    end: date | None = None    # inclusive (converted to an exclusive bound below)
    outlets: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    order_types: tuple[str, ...] = ()
    settlements: tuple[str, ...] = ()


def build_where(filters):
    """Return (WHERE clause, params).

    Only fixed SQL fragments written in this function are ever placed in the
    query text; every user-supplied value is passed as a bound parameter.
    """
    clauses, params = [], {}
    if filters.start:
        clauses.append("o.order_datetime >= %(start)s")
        params["start"] = datetime.combine(filters.start, time.min)
    if filters.end:
        # Half-open interval: < next midnight includes the whole end day
        # without relying on 23:59:59.
        clauses.append("o.order_datetime < %(end_exclusive)s")
        params["end_exclusive"] = datetime.combine(filters.end + timedelta(days=1), time.min)
    for column, key, values in [
        ("o.outlet", "outlets", filters.outlets),
        ("i.item_group", "groups", filters.groups),
        ("o.order_type", "order_types", filters.order_types),
        ("o.settlement", "settlements", filters.settlements),
    ]:
        if values:
            clauses.append(f"{column} = ANY(%({key})s)")
            params[key] = list(values)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


# Why only two analytical queries?
# Measured with EXPLAIN ANALYZE (see scripts/benchmark_queries.py): with one
# query per chart, every query repeated the same 300K-row join + per-bill
# rollup, and the unfiltered dashboard took ~2.3 s of database time. The
# per-bill rollup is the expensive part, so it is now computed once and every
# order-level breakdown is produced from it with GROUPING SETS.

# Matching lines rolled up to one row per bill. Grouping by the orders primary
# key lets us select order-level columns without listing them in GROUP BY.
ORDER_LEVEL_SQL = """
WITH bills AS (
    SELECT o.bill_no, o.outlet, o.order_type, o.settlement,
           date_trunc(%(granularity)s, o.order_datetime)::date AS period,
           extract(hour FROM o.order_datetime)::int           AS hour,
           sum(i.line_revenue) AS revenue,
           sum(i.quantity)     AS units,
           count(*)            AS line_items
    FROM order_items i
    JOIN orders o ON o.bill_no = i.bill_no
    {where}
    GROUP BY o.bill_no
)
SELECT CASE
           WHEN GROUPING(period)     = 0 THEN 'period'
           WHEN GROUPING(outlet)     = 0 THEN 'outlet'
           WHEN GROUPING(settlement) = 0 THEN 'channel'     -- (order_type, settlement)
           WHEN GROUPING(order_type) = 0 THEN 'order_type'
           WHEN GROUPING(hour)       = 0 THEN 'hour'
           ELSE 'total'
       END AS dimension,
       period, outlet, order_type, settlement, hour,
       count(*)                            AS orders,       -- one row per bill
       count(*) FILTER (WHERE revenue > 0) AS paid_orders,  -- AOV denominator
       sum(revenue)                        AS revenue,
       sum(units)                          AS units,
       sum(line_items)                     AS line_items
FROM bills
GROUP BY GROUPING SETS (
    (), (period), (outlet), (order_type), (order_type, settlement), (hour)
)
"""

# One row per menu item. An item belongs to exactly one group, so group
# totals are sums of these rows, and because (bill_no, item) is unique,
# count(*) per item is the number of orders containing it. This replaced a
# separate group query whose COUNT(DISTINCT bill_no) sort cost ~600 ms.
ITEM_LEVEL_SQL = """
SELECT i.item_group, i.item,
       sum(i.line_revenue) AS revenue,
       sum(i.quantity)     AS units,
       count(*)            AS orders
FROM order_items i
JOIN orders o ON o.bill_no = i.bill_no
{where}
GROUP BY i.item_group, i.item
"""

FILTER_OPTIONS_SQL = """
SELECT
    (SELECT array_agg(DISTINCT outlet ORDER BY outlet)         FROM orders)      AS outlets,
    (SELECT array_agg(DISTINCT item_group ORDER BY item_group) FROM order_items) AS groups,
    (SELECT array_agg(DISTINCT order_type ORDER BY order_type) FROM orders)      AS order_types,
    (SELECT array_agg(DISTINCT settlement ORDER BY settlement) FROM orders)      AS settlements,
    (SELECT min(order_datetime)::date FROM orders)                               AS min_date,
    (SELECT max(order_datetime)::date FROM orders)                               AS max_date
"""


def order_level_sql(filters, granularity):
    where, params = build_where(filters)
    params["granularity"] = granularity  # validated to 'day' or 'week' by the API
    return ORDER_LEVEL_SQL.format(where=where), params


def item_level_sql(filters):
    where, params = build_where(filters)
    return ITEM_LEVEL_SQL.format(where=where), params


def _fetch(conn, sql, params):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def fetch_order_level(conn, filters, granularity):
    return _fetch(conn, *order_level_sql(filters, granularity))


def fetch_item_level(conn, filters):
    return _fetch(conn, *item_level_sql(filters))


def fetch_filter_options(conn):
    return _fetch(conn, FILTER_OPTIONS_SQL, {})[0]
