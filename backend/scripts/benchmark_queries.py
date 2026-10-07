"""Run every dashboard query under EXPLAIN (ANALYZE, BUFFERS) for realistic
filter scenarios and print the median server-side execution time.

Usage (from backend/):  python -m scripts.benchmark_queries [--runs N] [--plan SCENARIO QUERY]
"""
import argparse
import json
import os
import statistics
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from app import queries as q
from app.queries import Filters

SCENARIOS = {
    "no_filters":       Filters(),
    "date_1_month":     Filters(start=date(2026, 1, 1), end=date(2026, 1, 31)),
    "date_1_week":      Filters(start=date(2026, 1, 5), end=date(2026, 1, 11)),
    "outlet":           Filters(outlets=("Koramangala",)),
    "group":            Filters(groups=("Drinks",)),
    "date_and_outlet":  Filters(start=date(2026, 1, 1), end=date(2026, 1, 31), outlets=("MG Road",)),
    "date_and_group":   Filters(start=date(2026, 1, 1), end=date(2026, 1, 31), groups=("Desserts",)),
    "multiple":         Filters(start=date(2025, 10, 1), end=date(2025, 12, 31),
                                outlets=("Koramangala", "Indiranagar"),
                                order_types=("Delivery",), settlements=("SwiggyPay",)),
}

QUERIES = {
    "order_level_week": lambda f: q.order_level_sql(f, "week"),
    "order_level_day":  lambda f: q.order_level_sql(f, "day"),
    "item_level":       lambda f: q.item_level_sql(f),
}

RUNS = 9


def explain(cur, sql, params):
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params)
    return cur.fetchone()[0][0]


def scan_types(plan):
    """Collect the scan node types used anywhere in a plan."""
    found = set()
    def walk(node):
        if "Scan" in node["Node Type"]:
            found.add(f'{node["Node Type"]}({node.get("Relation Name", "")})')
        for child in node.get("Plans", []):
            walk(child)
    walk(plan["Plan"])
    return sorted(found)


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", nargs=2, metavar=("SCENARIO", "QUERY"),
                        help="print the full text plan for one query")
    parser.add_argument("--runs", type=int, default=RUNS)
    args = parser.parse_args()
    runs = args.runs

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        if args.plan:
            sql, params = QUERIES[args.plan[1]](SCENARIOS[args.plan[0]])
            cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql, params)
            print("\n".join(row[0] for row in cur.fetchall()))
            return

        header = f"{'scenario':<17}" + "".join(f"{name:>18}" for name in QUERIES) + f"{'REQUEST':>9}"
        print(f"Median execution time in ms over {runs} runs (server-side, warm cache)")
        print("REQUEST = order_level_week + item_level (what one default dashboard request runs)")
        print(header)
        scans = {}
        for scenario, filters in SCENARIOS.items():
            medians = []
            for name, build in QUERIES.items():
                sql, params = build(filters)
                plans = [explain(cur, sql, params) for _ in range(runs)]
                medians.append(statistics.median(p["Execution Time"] for p in plans))
                scans.setdefault(scenario, set()).update(scan_types(plans[0]))
            print(f"{scenario:<17}" + "".join(f"{m:>18.1f}" for m in medians) + f"{medians[0] + medians[2]:>9.1f}")
        print("\nScan nodes used per scenario:")
        for scenario, nodes in scans.items():
            print(f"  {scenario:<17} {', '.join(sorted(nodes))}")


if __name__ == "__main__":
    main()
