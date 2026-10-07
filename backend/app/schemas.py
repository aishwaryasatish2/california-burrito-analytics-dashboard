"""Response shapes for the API (also documented automatically at /docs)."""
from datetime import date

from pydantic import BaseModel


class FilterOptions(BaseModel):
    outlets: list[str]
    groups: list[str]
    order_types: list[str]
    settlements: list[str]
    min_date: date
    max_date: date


class Scope(BaseModel):
    line_level_filter: bool  # true when a menu-group filter is active
    groups: list[str]


class DateRange(BaseModel):
    start: date
    end: date


class Kpis(BaseModel):
    gross_revenue: int
    orders: int
    paid_orders: int
    zero_value_orders: int
    aov: float | None
    units_sold: int
    line_items: int
    items_per_order: float | None


class TrendPoint(BaseModel):
    period_start: date
    revenue: int
    orders: int
    units: int
    is_partial: bool


class Trend(BaseModel):
    granularity: str
    points: list[TrendPoint]


class OutletRow(BaseModel):
    outlet: str
    revenue: int
    orders: int
    units: int
    aov: float | None


class OrderTypeRow(BaseModel):
    order_type: str
    revenue: int
    orders: int
    units: int
    aov: float | None


class ChannelRow(BaseModel):
    order_type: str
    settlement: str
    orders: int
    revenue: int


class HourRow(BaseModel):
    hour: int
    orders: int
    revenue: int


class GroupRow(BaseModel):
    group: str
    revenue: int
    units: int
    line_items: int


class ItemRow(BaseModel):
    item: str
    group: str
    revenue: int
    units: int
    orders: int


class Meta(BaseModel):
    query_ms: float


class Dashboard(BaseModel):
    scope: Scope
    date_range: DateRange | None
    kpis: Kpis
    trend: Trend
    by_outlet: list[OutletRow]
    by_order_type: list[OrderTypeRow]
    channels: list[ChannelRow]
    hourly: list[HourRow]
    by_group: list[GroupRow]
    top_items: list[ItemRow]
    meta: Meta
