from datetime import date

import pandas as pd
import pytest

from tests.conftest import expected


def get_dashboard(client, **params):
    response = client.get("/api/dashboard", params=params)
    assert response.status_code == 200, response.text
    return response.json()


# --- Health and filters ----------------------------------------------------------

def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_filters_match_source_values(client, source):
    body = client.get("/api/filters").json()
    assert body["outlets"] == sorted(source["Outlet_Name"].unique())
    assert body["groups"] == sorted(source["Group"].unique())
    assert body["order_types"] == sorted(source["Order_Type"].unique())
    assert body["settlements"] == sorted(source["Settlement"].unique())
    assert body["min_date"] == str(source["Order_Datetime"].min().date())
    assert body["max_date"] == str(source["Order_Datetime"].max().date())
    assert "brand" not in body  # single-value column, deliberately not a filter


# --- KPIs under each filter vs. independent pandas --------------------------------

FILTER_CASES = {
    "unfiltered": {},
    "date": {"start": date(2026, 1, 1), "end": date(2026, 1, 31)},
    "single_day": {"start": date(2026, 1, 15), "end": date(2026, 1, 15)},
    "outlet": {"outlets": ("Koramangala",)},
    "two_outlets": {"outlets": ("MG Road", "Whitefield")},
    "group": {"groups": ("Drinks",)},
    "order_type": {"order_types": ("Delivery",)},
    "settlement": {"settlements": ("Dineout",)},
    "multiple": {"start": date(2025, 10, 1), "end": date(2025, 12, 31),
                 "outlets": ("Koramangala", "Indiranagar"), "groups": ("Burgers", "Sides"),
                 "order_types": ("Delivery",), "settlements": ("SwiggyPay", "ZomatoPay")},
}

PARAM_NAMES = {"outlets": "outlet", "groups": "group",
               "order_types": "order_type", "settlements": "settlement"}


def to_params(case):
    return {PARAM_NAMES.get(k, k): (list(v) if isinstance(v, tuple) else str(v))
            for k, v in case.items()}


@pytest.mark.parametrize("name", FILTER_CASES)
def test_kpis_match_pandas(client, source, name):
    case = FILTER_CASES[name]
    body = get_dashboard(client, **to_params(case))
    assert body["kpis"] == expected(source, **case)["kpis"]


@pytest.mark.parametrize("name", FILTER_CASES)
def test_breakdowns_match_pandas(client, source, name):
    case = FILTER_CASES[name]
    body = get_dashboard(client, **to_params(case))
    rows = expected(source, **case)["rows"]

    outlet_revenue = rows.groupby("Outlet_Name")["revenue"].sum()
    assert {r["outlet"]: r["revenue"] for r in body["by_outlet"]} == outlet_revenue.to_dict()

    group_revenue = rows.groupby("Group")["revenue"].sum()
    assert {r["group"]: r["revenue"] for r in body["by_group"]} == group_revenue.to_dict()

    type_orders = rows.groupby("Order_Type")["BillNo"].nunique()
    assert {r["order_type"]: r["orders"] for r in body["by_order_type"]} == type_orders.to_dict()

    channel_orders = rows.groupby(["Order_Type", "Settlement"])["BillNo"].nunique()
    assert {(r["order_type"], r["settlement"]): r["orders"] for r in body["channels"]} \
        == channel_orders.to_dict()

    hourly_orders = rows.groupby(rows["Order_Datetime"].dt.hour)["BillNo"].nunique()
    api_hourly = {r["hour"]: r["orders"] for r in body["hourly"] if r["orders"]}
    assert api_hourly == hourly_orders.to_dict()

    item_revenue = rows.groupby("Item")["revenue"].sum().sort_values(ascending=False)
    assert [(r["item"], r["revenue"]) for r in body["top_items"]] \
        == sorted(item_revenue.items(), key=lambda kv: (-kv[1], kv[0]))[:10]


# --- Specific behaviours ---------------------------------------------------------

def test_end_date_includes_the_whole_last_day(client, source):
    day = source[source["Order_Datetime"].dt.date == date(2026, 1, 15)]
    assert day["Order_Datetime"].dt.hour.max() == 23  # late orders exist that day
    body = get_dashboard(client, start="2026-01-15", end="2026-01-15")
    assert body["kpis"]["orders"] == day["BillNo"].nunique()


def test_group_filter_counts_only_matching_lines(client, source):
    body = get_dashboard(client, group="Drinks")
    drink_bills = source.loc[source["Group"] == "Drinks", "BillNo"].unique()
    full_bill_revenue = int(source.loc[source["BillNo"].isin(drink_bills), "revenue"].sum())
    drinks_revenue = int(source.loc[source["Group"] == "Drinks", "revenue"].sum())
    assert body["scope"]["line_level_filter"] is True
    assert body["kpis"]["orders"] == len(drink_bills)
    assert body["kpis"]["gross_revenue"] == drinks_revenue
    assert body["kpis"]["gross_revenue"] < full_bill_revenue  # not the whole basket


def test_zero_value_orders_count_as_orders_but_not_in_aov(client, source):
    body = get_dashboard(client)
    per_bill = source.groupby("BillNo")["revenue"].sum()
    kpis = body["kpis"]
    assert kpis["zero_value_orders"] == int((per_bill == 0).sum()) == 591
    assert kpis["orders"] == len(per_bill)  # zero-value bills included
    assert kpis["aov"] == round(per_bill.sum() / (per_bill > 0).sum(), 2)
    assert kpis["aov"] != round(per_bill.mean(), 2)  # would differ if they were included


def test_aov_with_many_zero_value_orders(client, source):
    # Within the Extras group, every bill whose only Extras lines are free dips
    # has zero matching revenue, so the AOV denominator differs a lot from orders.
    body = get_dashboard(client, group="Extras")
    extras = source[source["Group"] == "Extras"]
    per_bill = extras.groupby("BillNo")["revenue"].sum()
    assert body["kpis"]["zero_value_orders"] == int((per_bill == 0).sum())
    assert body["kpis"]["aov"] == round(per_bill.sum() / (per_bill > 0).sum(), 2)


@pytest.mark.parametrize("granularity, frequency", [("day", "D"), ("week", "W-SUN")])
def test_trend_matches_pandas(client, source, granularity, frequency):
    body = get_dashboard(client, granularity=granularity)
    points = body["trend"]["points"]
    period = source["Order_Datetime"].dt.to_period(frequency).dt.start_time.dt.date
    expected_revenue = source.groupby(period)["revenue"].sum()
    expected_orders = source.groupby(period)["BillNo"].nunique()
    assert body["trend"]["granularity"] == granularity
    assert {date.fromisoformat(p["period_start"]): p["revenue"] for p in points} \
        == expected_revenue.to_dict()
    assert {date.fromisoformat(p["period_start"]): p["orders"] for p in points} \
        == expected_orders.to_dict()
    assert sum(p["revenue"] for p in points) == body["kpis"]["gross_revenue"]


def test_weekly_trend_flags_partial_weeks(client):
    points = get_dashboard(client, granularity="week")["trend"]["points"]
    # Data starts Tue 2025-06-17 and ends Tue 2026-06-16.
    assert points[0]["period_start"] == "2025-06-16" and points[0]["is_partial"]
    assert points[-1]["period_start"] == "2026-06-15" and points[-1]["is_partial"]
    assert not any(p["is_partial"] for p in points[1:-1])


def test_daily_trend_zero_fills_gaps(client, source):
    # A narrow filter combination leaves some days with no orders.
    params = {"start": "2026-01-01", "end": "2026-01-31", "outlet": "MG Road",
              "group": "Desserts", "settlement": "Dineout", "granularity": "day"}
    points = get_dashboard(client, **params)["trend"]["points"]
    assert len(points) == 31
    assert any(p["orders"] == 0 for p in points)


def test_range_outside_data_returns_empty_result(client):
    body = get_dashboard(client, start="2030-01-01", end="2030-01-31")
    assert body["kpis"]["orders"] == 0
    assert body["kpis"]["gross_revenue"] == 0
    assert body["kpis"]["aov"] is None
    assert body["trend"]["points"] == []
    assert body["date_range"] is None


# --- Invalid input -----------------------------------------------------------------

@pytest.mark.parametrize("params", [
    {"outlet": "Atlantis"},
    {"group": "Pizza"},
    {"order_type": "Drive-Thru"},
    {"settlement": "Bitcoin"},
    {"outlet": ["Koramangala", "Nowhere"]},
    {"granularity": "month"},
    {"start": "15-01-2026"},
    {"start": "2026-02-30"},
    {"start": "2026-02-01", "end": "2026-01-01"},
])
def test_invalid_input_is_rejected(client, params):
    assert client.get("/api/dashboard", params=params).status_code == 422


def test_injection_attempt_is_rejected_and_harmless(client):
    response = client.get("/api/dashboard", params={"outlet": "x'; DROP TABLE orders; --"})
    assert response.status_code == 422
    assert get_dashboard(client)["kpis"]["orders"] == 110478
