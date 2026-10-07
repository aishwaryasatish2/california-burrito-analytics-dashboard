"""Measure candidate indexes one at a time against the current database.

The baseline is whatever indexes the database has now (read from
pg_indexes and printed), not an assumed "primary keys only" state. Each
candidate that does not already exist is created, ANALYZEd, benchmarked with
scripts.benchmark_queries, and dropped again. Candidates that already exist
(e.g. order_items(item_group), which the ETL now creates) are skipped,
because they are already part of the baseline.

Usage (from backend/):
    python -m scripts.benchmark_indexes          # run the benchmark
    python -m scripts.benchmark_indexes --list   # show baseline and plan only
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# (table, column) pairs tested in Phase 2.
CANDIDATES = [
    ("orders", "order_datetime"),
    ("order_items", "item_group"),
    ("orders", "outlet"),
    ("orders", "order_type"),
    ("orders", "settlement"),
]

TEMP_INDEX = "bench_candidate_idx"


def current_indexes(conn):
    return conn.execute(
        "SELECT tablename, indexname, indexdef FROM pg_indexes "
        "WHERE tablename IN ('orders', 'order_items') ORDER BY tablename, indexname"
    ).fetchall()


def is_indexed_alone(indexes, table, column):
    """True if an existing index on `table` covers exactly this one column."""
    return any(t == table and indexdef.rstrip().endswith(f"({column})")
               for t, _, indexdef in indexes)


def analyze(conn):
    conn.execute("ANALYZE orders")
    conn.execute("ANALYZE order_items")


def benchmark(label):
    print(f"\n=== {label} ===", flush=True)
    subprocess.run([sys.executable, "-m", "scripts.benchmark_queries"], check=True)


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="print baseline and plan, run nothing")
    args = parser.parse_args()

    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        indexes = current_indexes(conn)
        names = ", ".join(name for _, name, _ in indexes)
        print(f"Baseline = current database indexes: {names}")

        plan = []
        for table, column in CANDIDATES:
            if is_indexed_alone(indexes, table, column):
                print(f"  skip {table}({column}): already in the baseline")
            else:
                plan.append((table, column))
                print(f"  test {table}({column}) on top of the baseline")
        if args.list:
            return

        conn.execute(f"DROP INDEX IF EXISTS {TEMP_INDEX}")
        benchmark(f"baseline ({names})")
        for table, column in plan:
            try:
                # Names come from the fixed CANDIDATES list above, not user input.
                conn.execute(f"CREATE INDEX {TEMP_INDEX} ON {table} ({column})")
                analyze(conn)
                benchmark(f"baseline + {table}({column})")
            finally:
                conn.execute(f"DROP INDEX IF EXISTS {TEMP_INDEX}")
                analyze(conn)


if __name__ == "__main__":
    main()
