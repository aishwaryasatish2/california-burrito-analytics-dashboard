"""Time real HTTP requests against a running API (client-side wall time).

Usage (from backend/, with the API running):
    python -m scripts.benchmark_api [--base-url http://localhost:8000] [--runs 15]
"""
import argparse
import statistics
import time

import httpx

SCENARIOS = {
    "unfiltered (week)":   {},
    "unfiltered (day)":    {"granularity": "day"},
    "wide date (6 mo)":    {"start": "2025-12-01", "end": "2026-05-31"},
    "narrow date (1 wk)":  {"start": "2026-01-05", "end": "2026-01-11", "granularity": "day"},
    "outlet":              {"outlet": "Koramangala"},
    "group":               {"group": "Drinks"},
    "date + group":        {"start": "2026-01-01", "end": "2026-01-31", "group": "Desserts"},
    "multiple filters":    {"start": "2025-10-01", "end": "2025-12-31",
                            "outlet": ["Koramangala", "Indiranagar"],
                            "order_type": "Delivery", "settlement": "SwiggyPay"},
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--runs", type=int, default=15)
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=60) as client:
        started = time.perf_counter()
        client.get("/api/dashboard").raise_for_status()
        print(f"First request after start: {(time.perf_counter() - started) * 1000:.0f} ms\n")

        print(f"{'scenario':<22}{'median':>8}{'p95':>8}{'min':>8}{'db (median)':>13}{'bytes':>9}")
        for name, params in SCENARIOS.items():
            wall, db = [], []
            for _ in range(args.runs):
                started = time.perf_counter()
                response = client.get("/api/dashboard", params=params)
                wall.append((time.perf_counter() - started) * 1000)
                response.raise_for_status()
                db.append(response.json()["meta"]["query_ms"])
            p95 = statistics.quantiles(wall, n=20)[18]
            print(f"{name:<22}{statistics.median(wall):>8.0f}{p95:>8.0f}{min(wall):>8.0f}"
                  f"{statistics.median(db):>13.0f}{len(response.content):>9,}")
        print("\nAll times in ms. 'db' = time spent in the two SQL queries (from meta.query_ms).")


if __name__ == "__main__":
    main()
