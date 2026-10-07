"""Turns query rows into the dashboard response.

All business calculations live here so they are defined once:
  Gross revenue  = sum(line_revenue) of matching lines
  Orders         = bills with at least one matching line (zero-value bills included)
  AOV            = gross revenue / matching orders with revenue > 0
  Items per order = matching line items / orders
"""
import time
from datetime import date, timedelta

from app import queries
from app.queries import Filters

TOP_ITEMS_LIMIT = 10


def aov(revenue, paid_orders):
    return round(revenue / paid_orders, 2) if paid_orders else None


def _metrics(row):
    """Order-level metrics shared by every GROUPING SETS row."""
    revenue = int(row["revenue"] or 0)
    return {
        "revenue": revenue,
        "orders": int(row["orders"]),
        "units": int(row["units"] or 0),
        "aov": aov(revenue, row["paid_orders"]),
    }


def effective_date_range(filters, min_date, max_date):
    """The part of the requested range that overlaps the data (None if none)."""
    start = max(filters.start or min_date, min_date)
    end = min(filters.end or max_date, max_date)
    return (start, end) if start <= end else None


def build_trend(rows, granularity, date_range):
    """Zero-fill missing periods so gaps show as zero rather than vanishing,
    and flag weeks that are only partly inside the selected range."""
    if date_range is None:
        return []
    start, end = date_range
    by_period = {r["period"]: r for r in rows}
    if granularity == "week":
        step = timedelta(days=7)
        current = start - timedelta(days=start.weekday())  # Monday, like date_trunc('week')
    else:
        step = timedelta(days=1)
        current = start

    points = []
    while current <= end:
        row = by_period.get(current)
        period_end = current + step - timedelta(days=1)
        points.append({
            "period_start": current,
            "revenue": int(row["revenue"]) if row else 0,
            "orders": int(row["orders"]) if row else 0,
            "units": int(row["units"]) if row else 0,
            "is_partial": granularity == "week" and (current < start or period_end > end),
        })
        current += step
    return points


def build_hourly(rows):
    if not rows:
        return []
    by_hour = {r["hour"]: r for r in rows}
    return [
        {
            "hour": hour,
            "orders": int(by_hour[hour]["orders"]) if hour in by_hour else 0,
            "revenue": int(by_hour[hour]["revenue"]) if hour in by_hour else 0,
        }
        for hour in range(min(by_hour), max(by_hour) + 1)
    ]


def build_groups(item_rows):
    """Group totals are sums of item rows (each item belongs to one group)."""
    groups = {}
    for row in item_rows:
        g = groups.setdefault(row["item_group"], {"group": row["item_group"],
                                                  "revenue": 0, "units": 0, "line_items": 0})
        g["revenue"] += int(row["revenue"])
        g["units"] += int(row["units"])
        g["line_items"] += int(row["orders"])  # one line per item per bill
    return sorted(groups.values(), key=lambda g: (-g["revenue"], g["group"]))


def build_top_items(item_rows, limit=TOP_ITEMS_LIMIT):
    ranked = sorted(item_rows, key=lambda r: (-int(r["revenue"]), r["item"]))
    return [
        {"item": r["item"], "group": r["item_group"], "revenue": int(r["revenue"]),
         "units": int(r["units"]), "orders": int(r["orders"])}
        for r in ranked[:limit]
    ]


def build_dashboard(conn, filters: Filters, granularity, min_date: date, max_date: date):
    started = time.perf_counter()
    order_rows = queries.fetch_order_level(conn, filters, granularity)
    item_rows = queries.fetch_item_level(conn, filters)
    query_ms = (time.perf_counter() - started) * 1000

    by_dimension = {}
    for row in order_rows:
        by_dimension.setdefault(row["dimension"], []).append(row)

    total = by_dimension["total"][0]  # the () grouping set always returns one row
    revenue = int(total["revenue"] or 0)
    orders = int(total["orders"])
    line_items = int(total["line_items"] or 0)

    def sorted_breakdown(dimension, key):
        rows = [{key: r[key], **_metrics(r)} for r in by_dimension.get(dimension, [])]
        return sorted(rows, key=lambda r: (-r["revenue"], r[key]))

    date_range = effective_date_range(filters, min_date, max_date)
    return {
        "scope": {
            # With a group filter, metrics cover matching lines, not whole bills.
            "line_level_filter": bool(filters.groups),
            "groups": list(filters.groups),
        },
        "date_range": {"start": date_range[0], "end": date_range[1]} if date_range else None,
        "kpis": {
            "gross_revenue": revenue,
            "orders": orders,
            "paid_orders": int(total["paid_orders"]),
            "zero_value_orders": orders - int(total["paid_orders"]),
            "aov": aov(revenue, total["paid_orders"]),
            "units_sold": int(total["units"] or 0),
            "line_items": line_items,
            "items_per_order": round(line_items / orders, 2) if orders else None,
        },
        "trend": {
            "granularity": granularity,
            "points": build_trend(by_dimension.get("period", []), granularity, date_range),
        },
        "by_outlet": sorted_breakdown("outlet", "outlet"),
        "by_order_type": sorted_breakdown("order_type", "order_type"),
        "channels": sorted(
            ({"order_type": r["order_type"], "settlement": r["settlement"],
              "orders": int(r["orders"]), "revenue": int(r["revenue"])}
             for r in by_dimension.get("channel", [])),
            key=lambda r: (r["order_type"], -r["orders"]),
        ),
        "hourly": build_hourly(by_dimension.get("hour", [])),
        "by_group": build_groups(item_rows),
        "top_items": build_top_items(item_rows),
        "meta": {"query_ms": round(query_ms, 1)},
    }
