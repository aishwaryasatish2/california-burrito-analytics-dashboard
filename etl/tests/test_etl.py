import os
from datetime import datetime

import pandas as pd
import psycopg
import pytest

from etl.load import load_database, source_totals, split_orders_and_items
from etl.validation import DataValidationError, validate


def valid_rows():
    """Three bills: a two-line paid bill, a one-line paid bill, and a
    complimentary-only bill (a free dip), which must be kept."""
    t1 = datetime(2025, 8, 8, 20, 57, 34)
    t2 = datetime(2026, 6, 11, 19, 14, 28)
    t3 = datetime(2025, 7, 9, 12, 0, 0)
    common = {"Brand": "Burger Town"}
    return [
        {"BillNo": 1, "Outlet_Name": "HSR Layout", "Order_Datetime": t1, "Group": "Burgers",
         "Order_Type": "Dine-In", "Item": "Classic Veg Burger", "Price": 129, "Quantity": 2,
         "Settlement": "Cash/Card/Coupon", **common},
        {"BillNo": 1, "Outlet_Name": "HSR Layout", "Order_Datetime": t1, "Group": "Drinks",
         "Order_Type": "Dine-In", "Item": "Coke", "Price": 59, "Quantity": 1,
         "Settlement": "Cash/Card/Coupon", **common},
        {"BillNo": 2, "Outlet_Name": "Koramangala", "Order_Datetime": t2, "Group": "Combos",
         "Order_Type": "Delivery", "Item": "Veg Combo Meal", "Price": 229, "Quantity": 1,
         "Settlement": "SwiggyPay", **common},
        {"BillNo": 3, "Outlet_Name": "MG Road", "Order_Datetime": t3, "Group": "Extras",
         "Order_Type": "Takeaway", "Item": "Dip - Mayo", "Price": 0, "Quantity": 1,
         "Settlement": "Cash/Card/Coupon", **common},
    ]


def frame(rows):
    return pd.DataFrame(rows)


def assert_rejected(df, expected_message):
    with pytest.raises(DataValidationError) as error:
        validate(df)
    assert expected_message in str(error.value)


# --- Valid data ---------------------------------------------------------------

def test_valid_data_produces_expected_orders_items_and_totals():
    clean = validate(frame(valid_rows()))
    orders, items = split_orders_and_items(clean)

    assert list(orders["bill_no"]) == [1, 2, 3]
    assert len(items) == 4
    assert orders.loc[orders["bill_no"] == 2, "settlement"].item() == "SwiggyPay"

    totals = source_totals(clean)
    assert totals["line_items"] == 4
    assert totals["orders"] == 3
    assert totals["gross_revenue"] == 129 * 2 + 59 + 229  # 546
    assert totals["units_sold"] == 5
    assert totals["zero_price_lines"] == 1
    assert totals["zero_value_orders"] == 1


def test_datetime_text_in_brief_format_is_accepted():
    rows = valid_rows()
    for row in rows:
        row["Order_Datetime"] = row["Order_Datetime"].strftime("%d-%m-%Y %H:%M:%S")
    clean = validate(frame(rows))
    assert clean["Order_Datetime"].min() == pd.Timestamp(2025, 7, 9, 12, 0, 0)


def test_source_frame_is_not_modified():
    df = frame(valid_rows())
    before = df.copy()
    validate(df)
    pd.testing.assert_frame_equal(df, before)


# --- Invalid data -------------------------------------------------------------

def test_missing_required_column():
    assert_rejected(frame(valid_rows()).drop(columns="Quantity"), "Missing required columns")


def test_null_required_value():
    rows = valid_rows()
    rows[1]["Item"] = None
    assert_rejected(frame(rows), "Null values in required columns")


def test_blank_text_is_treated_as_null():
    rows = valid_rows()
    rows[0]["Outlet_Name"] = "   "
    assert_rejected(frame(rows), "Null values in required columns")


@pytest.mark.parametrize("bad_bill_no", ["ABC", 0, -5, 12.5])
def test_invalid_bill_no(bad_bill_no):
    rows = valid_rows()
    rows[2]["BillNo"] = bad_bill_no
    assert_rejected(frame(rows), "Invalid BillNo")


@pytest.mark.parametrize("bad_quantity", [0, -1, 1.5, "two"])
def test_invalid_quantity(bad_quantity):
    rows = valid_rows()
    rows[0]["Quantity"] = bad_quantity
    assert_rejected(frame(rows), "Invalid Quantity")


def test_negative_price():
    rows = valid_rows()
    rows[0]["Price"] = -129
    assert_rejected(frame(rows), "Invalid Price")


def test_fractional_price():
    rows = valid_rows()
    rows[0]["Price"] = 129.5
    assert_rejected(frame(rows), "Invalid Price")


def test_duplicate_bill_no_and_item():
    rows = valid_rows()
    rows.append(dict(rows[0]))
    assert_rejected(frame(rows), "Duplicate BillNo + Item")


@pytest.mark.parametrize("column, other_value", [
    ("Outlet_Name", "Whitefield"),
    ("Order_Type", "Takeaway"),
    ("Settlement", "Dineout"),
    ("Order_Datetime", datetime(2025, 8, 8, 21, 0, 0)),
])
def test_inconsistent_order_level_attributes(column, other_value):
    rows = valid_rows()
    rows[1][column] = other_value  # second line of bill 1 disagrees with the first
    assert_rejected(frame(rows), "inconsistent order-level attributes")


@pytest.mark.parametrize("bad_date", ["2025-13-45", "not a date", "31-02-2026 10:00:00"])
def test_invalid_date(bad_date):
    rows = valid_rows()
    rows[0]["Order_Datetime"] = bad_date
    assert_rejected(frame(rows), "Unparseable Order_Datetime")


def test_all_errors_are_reported_together():
    rows = valid_rows()
    rows[0]["Quantity"] = 0
    rows[1]["Price"] = -1
    with pytest.raises(DataValidationError) as error:
        validate(frame(rows))
    assert len(error.value.errors) == 2


# --- Database (runs only when TEST_DATABASE_URL is set) -----------------------

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@needs_db
def test_load_reconciles_and_postgres_computes_line_revenue():
    clean = validate(frame(valid_rows()))
    orders, items = split_orders_and_items(clean)
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        load_database(conn, orders, items, source_totals(clean), {})
        rows = conn.execute(
            "SELECT bill_no, item, line_revenue FROM order_items ORDER BY bill_no, item"
        ).fetchall()
    assert rows == [
        (1, "Classic Veg Burger", 258),
        (1, "Coke", 59),
        (2, "Veg Combo Meal", 229),
        (3, "Dip - Mayo", 0),
    ]


@needs_db
def test_failed_reconciliation_rolls_back_and_keeps_previous_data():
    clean = validate(frame(valid_rows()))
    orders, items = split_orders_and_items(clean)
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        load_database(conn, orders, items, source_totals(clean), {})

        wrong_totals = {**source_totals(clean), "gross_revenue": 1}
        with pytest.raises(RuntimeError, match="Reconciliation failed"):
            # Load only two orders' worth of items; it must not replace the good data.
            load_database(conn, orders, items.iloc[:2], wrong_totals, {})

        assert conn.execute("SELECT count(*) FROM order_items").fetchone()[0] == 4
