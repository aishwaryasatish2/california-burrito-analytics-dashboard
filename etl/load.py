"""One-time ETL: Excel -> validate -> transform -> PostgreSQL -> reconcile.

Usage (from the repository root):
    python -m etl.load                      # uses DATABASE_URL and data/data.xlsx
    python -m etl.load --file other.xlsx --database-url postgresql://...

The whole load runs in one transaction and the reconciliation runs before the
commit, so a failed run leaves the existing database untouched.
"""
import argparse
import io
import os
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

from etl.validation import DataValidationError, validate

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = Path(__file__).resolve().parent / "sql"
DEFAULT_FILE = ROOT / "data" / "data.xlsx"


def read_excel(path):
    # python-calamine read the full file in ~5s vs ~47s for openpyxl.
    return pd.read_excel(path, engine="calamine")


def split_orders_and_items(df):
    """Split validated line-level data into orders and order_items frames."""
    orders = (
        df.drop_duplicates("BillNo")
        .loc[:, ["BillNo", "Outlet_Name", "Order_Datetime", "Order_Type", "Settlement"]]
        .rename(columns={
            "BillNo": "bill_no",
            "Outlet_Name": "outlet",
            "Order_Datetime": "order_datetime",
            "Order_Type": "order_type",
            "Settlement": "settlement",
        })
        .sort_values("bill_no")
        .reset_index(drop=True)
    )
    items = (
        df.loc[:, ["BillNo", "Item", "Group", "Price", "Quantity"]]
        .rename(columns={
            "BillNo": "bill_no",
            "Item": "item",
            "Group": "item_group",
            "Price": "price",
            "Quantity": "quantity",
        })
        .reset_index(drop=True)
    )
    return orders, items


def source_totals(df):
    """Totals computed directly from the validated line-level source data.

    This deliberately does not use the split frames, so the reconciliation
    compares the database against an independent calculation.
    """
    line_revenue = df["Price"] * df["Quantity"]
    revenue_per_bill = line_revenue.groupby(df["BillNo"]).sum()
    return {
        "line_items": int(len(df)),
        "orders": int(df["BillNo"].nunique()),
        "gross_revenue": int(line_revenue.sum()),
        "units_sold": int(df["Quantity"].sum()),
        "zero_price_lines": int((df["Price"] == 0).sum()),
        "zero_value_orders": int((revenue_per_bill == 0).sum()),
        "first_order": df["Order_Datetime"].min().to_pydatetime(),
        "last_order": df["Order_Datetime"].max().to_pydatetime(),
    }


DATABASE_TOTALS_SQL = """
SELECT
    (SELECT count(*)               FROM order_items)                  AS line_items,
    (SELECT count(*)               FROM orders)                       AS orders,
    (SELECT sum(line_revenue)      FROM order_items)                  AS gross_revenue,
    (SELECT sum(quantity)          FROM order_items)                  AS units_sold,
    (SELECT count(*) FROM order_items WHERE price = 0)                AS zero_price_lines,
    (SELECT count(*) FROM (
        SELECT bill_no FROM order_items
        GROUP BY bill_no HAVING sum(line_revenue) = 0) AS z)          AS zero_value_orders,
    (SELECT min(order_datetime)    FROM orders)                       AS first_order,
    (SELECT max(order_datetime)    FROM orders)                       AS last_order,
    (SELECT count(*) FROM orders o
      WHERE NOT EXISTS (SELECT 1 FROM order_items i
                        WHERE i.bill_no = o.bill_no))                 AS orders_without_items
"""


def database_totals(cur):
    cur.execute(DATABASE_TOTALS_SQL)
    columns = [d.name for d in cur.description]
    return dict(zip(columns, cur.fetchone()))


def reconcile(source, database):
    """Return a list of mismatches between source and database totals."""
    problems = [
        f"{key}: source={source[key]} database={database[key]}"
        for key in source
        if source[key] != database[key]
    ]
    if database["orders_without_items"] != 0:
        problems.append(f"{database['orders_without_items']} orders have no line items")
    return problems


def copy_frame(cur, table, frame):
    """Bulk-load a frame with COPY (much faster than 300K individual INSERTs)."""
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, header=False)
    # Table and column names are fixed in this module, never user input.
    columns = ", ".join(frame.columns)
    with cur.copy(f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv)") as copy:
        copy.write(buffer.getvalue())


def load_database(conn, orders, items, expected, timings):
    """Rebuild and load both tables in one transaction; commit only if reconciled."""
    with conn.transaction():
        with conn.cursor() as cur:
            started = time.perf_counter()
            cur.execute((SQL_DIR / "create_tables.sql").read_text())
            copy_frame(cur, "orders", orders)
            copy_frame(cur, "order_items", items)
            timings["copy"] = time.perf_counter() - started

            started = time.perf_counter()
            cur.execute((SQL_DIR / "add_constraints.sql").read_text())
            timings["constraints"] = time.perf_counter() - started

            started = time.perf_counter()
            cur.execute("ANALYZE orders")
            cur.execute("ANALYZE order_items")
            timings["analyze"] = time.perf_counter() - started

            started = time.perf_counter()
            actual = database_totals(cur)
            problems = reconcile(expected, actual)
            timings["reconcile"] = time.perf_counter() - started
            if problems:
                # Raising inside the transaction block rolls everything back.
                raise RuntimeError("Reconciliation failed:\n  - " + "\n  - ".join(problems))
    return actual


def run(file_path, database_url):
    timings = {}
    total_started = time.perf_counter()

    started = time.perf_counter()
    raw = read_excel(file_path)
    timings["read_excel"] = time.perf_counter() - started
    print(f"Read {len(raw):,} rows x {raw.shape[1]} columns from {file_path}")

    started = time.perf_counter()
    clean = validate(raw)
    timings["validate"] = time.perf_counter() - started
    print("Validation passed")
    for col in ["Outlet_Name", "Group", "Order_Type", "Settlement"]:
        print(f"  {col}: {sorted(clean[col].unique())}")
    if "Brand" in raw.columns:
        print(f"  Brand (not loaded): {sorted(raw['Brand'].dropna().unique())}")
    prices_per_item = clean.groupby("Item")["Price"].nunique()
    if (prices_per_item > 1).any():  # informational, not a failure
        print(f"  Note: items with more than one price: {prices_per_item[prices_per_item > 1].index.tolist()}")

    started = time.perf_counter()
    orders, items = split_orders_and_items(clean)
    expected = source_totals(clean)
    timings["transform"] = time.perf_counter() - started

    load_started = time.perf_counter()
    with psycopg.connect(database_url) as conn:
        actual = load_database(conn, orders, items, expected, timings)
    timings["database_total"] = time.perf_counter() - load_started
    timings["total"] = time.perf_counter() - total_started

    print("Reconciliation passed (database matches source):")
    for key, value in expected.items():
        print(f"  {key:<18} {value:,}" if isinstance(value, int) else f"  {key:<18} {value}")
    print("Timings (seconds):")
    for key, value in timings.items():
        print(f"  {key:<15} {value:6.2f}")
    return expected, actual, timings


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Load the Excel dataset into PostgreSQL.")
    parser.add_argument("--file", default=str(DEFAULT_FILE))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        sys.exit("DATABASE_URL is not set (use .env, the environment, or --database-url).")
    try:
        run(args.file, args.database_url)
    except DataValidationError as error:
        sys.exit(str(error))
    except RuntimeError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
