"""Integration tests run the real API against the loaded PostgreSQL database
and compare it with values computed independently by pandas from the
original Excel file (no ETL code, no SQL)."""
import os
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT / "data" / "data.xlsx"
load_dotenv(ROOT / ".env")



@pytest.fixture(scope="session")
def client():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("Needs DATABASE_URL pointing at a database loaded by the ETL")
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def source():
    if not DATA_FILE.exists():
        pytest.skip("Needs data/data.xlsx")
    df = pd.read_excel(DATA_FILE, engine="calamine")
    df["revenue"] = df["Price"] * df["Quantity"]
    return df


def expected(df, start=None, end=None, outlets=(), groups=(), order_types=(), settlements=()):
    """Reference KPIs straight from the source rows, following the agreed definitions."""
    mask = pd.Series(True, index=df.index)
    if start:
        mask &= df["Order_Datetime"] >= pd.Timestamp(start)
    if end:
        mask &= df["Order_Datetime"] < pd.Timestamp(end) + timedelta(days=1)
    for column, values in [("Outlet_Name", outlets), ("Group", groups),
                           ("Order_Type", order_types), ("Settlement", settlements)]:
        if values:
            mask &= df[column].isin(values)
    rows = df[mask]
    per_bill = rows.groupby("BillNo")["revenue"].sum()
    paid = int((per_bill > 0).sum())
    revenue = int(rows["revenue"].sum())
    return {
        "rows": rows,
        "kpis": {
            "gross_revenue": revenue,
            "orders": int(rows["BillNo"].nunique()),
            "paid_orders": paid,
            "zero_value_orders": int((per_bill == 0).sum()),
            "aov": round(revenue / paid, 2) if paid else None,
            "units_sold": int(rows["Quantity"].sum()),
            "line_items": len(rows),
            "items_per_order": round(len(rows) / rows["BillNo"].nunique(), 2) if len(rows) else None,
        },
    }
