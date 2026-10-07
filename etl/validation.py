"""Validation of the raw Excel data before anything is written to PostgreSQL.

Each check encodes an assumption confirmed during dataset inspection. If any
check fails, a DataValidationError lists every problem found and nothing is
loaded.
"""
from datetime import datetime

import pandas as pd

TEXT_COLUMNS = ["Outlet_Name", "Group", "Order_Type", "Item", "Settlement"]
REQUIRED_COLUMNS = ["BillNo", "Order_Datetime", "Price", "Quantity"] + TEXT_COLUMNS

# Attributes that must be identical on every line of the same bill.
ORDER_LEVEL_COLUMNS = ["Outlet_Name", "Order_Datetime", "Order_Type", "Settlement"]

# Format stated in the assessment brief. The provided file stores real Excel
# datetimes instead, but text in this format is accepted too.
DATETIME_TEXT_FORMAT = "%d-%m-%Y %H:%M:%S"


class DataValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("Data validation failed:\n  - " + "\n  - ".join(errors))


def _sample(values, n=5):
    # .tolist() converts numpy scalars so messages read "700002", not "np.int64(700002)"
    return pd.Series(values[:n]).tolist()


def _to_whole_numbers(series):
    """Return (Int64 series, mask of values that are not whole numbers)."""
    numeric = pd.to_numeric(series, errors="coerce")
    invalid = numeric.isna() | (numeric % 1 != 0)
    return numeric.where(~invalid).astype("Int64"), invalid


def _parse_datetimes(series):
    """Return (datetime series, mask of values that could not be parsed)."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series, series.isna()

    def parse(value):
        if isinstance(value, datetime):
            return pd.Timestamp(value)
        if isinstance(value, str):
            try:
                return pd.Timestamp(datetime.strptime(value.strip(), DATETIME_TEXT_FORMAT))
            except ValueError:
                return pd.NaT
        return pd.NaT

    parsed = pd.to_datetime(series.map(parse))
    return parsed, parsed.isna()


def validate(raw):
    """Validate the raw source frame and return a cleaned, typed copy.

    The source frame itself is never modified.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise DataValidationError([f"Missing required columns: {missing}"])

    df = raw[REQUIRED_COLUMNS].copy()
    df["_row"] = df.index + 2  # Excel row number (row 1 is the header)

    # Treat blank or whitespace-only text as missing.
    for col in TEXT_COLUMNS:
        df[col] = df[col].astype("string").str.strip().replace("", pd.NA)

    # Nulls are reported first; type checks on missing values would only add noise.
    null_counts = df[REQUIRED_COLUMNS].isna().sum()
    null_counts = null_counts[null_counts > 0]
    if not null_counts.empty:
        raise DataValidationError(
            [f"Null values in required columns: {null_counts.to_dict()}"]
        )

    errors = []

    df["BillNo"], invalid = _to_whole_numbers(df["BillNo"])
    invalid |= df["BillNo"].fillna(0) <= 0
    if invalid.any():
        errors.append(
            f"Invalid BillNo (must be a positive whole number) in {invalid.sum()} rows, "
            f"e.g. Excel rows {_sample(df.loc[invalid, '_row'])}"
        )

    df["Quantity"], invalid = _to_whole_numbers(df["Quantity"])
    invalid |= df["Quantity"].fillna(0) <= 0
    if invalid.any():
        errors.append(
            f"Invalid Quantity (must be a positive whole number) in {invalid.sum()} rows, "
            f"e.g. Excel rows {_sample(df.loc[invalid, '_row'])}"
        )

    # Prices are stored as INTEGER rupees; a fractional price would need NUMERIC.
    df["Price"], invalid = _to_whole_numbers(df["Price"])
    invalid |= df["Price"].fillna(-1) < 0
    if invalid.any():
        errors.append(
            f"Invalid Price (must be a non-negative whole number) in {invalid.sum()} rows, "
            f"e.g. Excel rows {_sample(df.loc[invalid, '_row'])}"
        )

    df["Order_Datetime"], invalid = _parse_datetimes(df["Order_Datetime"])
    if invalid.any():
        errors.append(
            f"Unparseable Order_Datetime in {invalid.sum()} rows, "
            f"e.g. Excel rows {_sample(df.loc[invalid, '_row'])}"
        )

    # The checks below group by BillNo, so they need valid values first.
    if errors:
        raise DataValidationError(errors)

    duplicated = df.duplicated(["BillNo", "Item"], keep=False)
    if duplicated.any():
        errors.append(
            f"Duplicate BillNo + Item in {duplicated.sum()} rows, "
            f"e.g. Excel rows {_sample(df.loc[duplicated, '_row'])}"
        )

    # A bill is one order, so its order-level attributes must not vary between
    # its lines. This also guarantees exactly one orders row per BillNo.
    per_bill = df.groupby("BillNo")[ORDER_LEVEL_COLUMNS].nunique()
    inconsistent = per_bill[(per_bill > 1).any(axis=1)]
    if not inconsistent.empty:
        bad_columns = inconsistent.columns[(inconsistent > 1).any()].tolist()
        errors.append(
            f"{len(inconsistent)} BillNo values have inconsistent order-level "
            f"attributes {bad_columns}, e.g. BillNo {_sample(inconsistent.index)}"
        )

    if errors:
        raise DataValidationError(errors)

    return df.drop(columns="_row")
