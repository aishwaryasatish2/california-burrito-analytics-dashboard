# Restaurant sales analytics dashboard

A web dashboard built from a ~300,000-row Excel export of restaurant line items:
gross revenue, orders, menu performance and order timing across 6 outlets,
with filters by date, outlet, menu group, order type and settlement.

**Live application:** _to be added after deployment_

The design decisions, and the measurements behind them, are recorded in
[`docs/decisions.md`](docs/decisions.md). The query and index work is in
[`docs/phase2-report.md`](docs/phase2-report.md).

---

## What the dashboard shows

**KPIs** (each one is labelled with its definition on screen):

| KPI | Definition |
|---|---|
| Gross revenue | sum of price × quantity (list price; no discounts, taxes or refunds in the data) |
| Orders | distinct bills (`BillNo`), including 591 complimentary-only bills |
| Average order value | gross revenue ÷ orders with revenue above ₹0 |
| Units sold | sum of quantity, including free items |
| Items per order | line items ÷ orders (the line-item count is the "total records" figure) |

**Charts and tables**, each answering one question:

- **How is revenue changing?** Weekly (or daily) gross revenue and orders, shown as two aligned charts. Partial weeks are marked.
- **Which outlets earn most?** Revenue by outlet, sorted.
- **Which menu groups earn most?** Revenue by menu group, sorted.
- **What kinds of orders are most common?** Order type mix, with the settlement channels within each type.
- **When are orders concentrated?** Orders by hour of day.
- **Which items matter most?** The top 10 items by gross revenue, with units and orders.

**Ask About Your Data** is a fixed list of six questions, not a chatbot: there
is no text input and no AI. Selecting a question shows a small result table.

1. Which outlet earns the most gross revenue?
2. Which outlet has the highest average order value?
3. Which menu group earns the most gross revenue?
4. Which order type is the most common?
5. When are orders busiest? (the three busiest hours)
6. How are delivery orders settled?

The answers are calculated in the browser from the `/api/dashboard` response
that is already on screen, so they follow the current filters and make no extra
API calls.

**Insights & Opportunities** sits beside it and lists observations for the
selected question: shares of the total, the gap between the top item and the
next or lowest one, and ranks. These are comparisons within the current
selection. They show where the numbers differ, not why, and they do not suggest
causes or actions.

**Filters:** date range, outlet, menu group, order type and settlement. All
except the dates are multi-select. Filters are kept in the URL, so a view can
be bookmarked or shared.

When a menu group filter is active, a note explains the change of scope: the
metrics then cover only the matching lines, not whole bills.

**Theme:** green for all chart data, red as a restrained accent (the rule above
the KPIs and the selected question), sand for the filter bar and the insights
panel, black text on a white page. No gradients. Text and control borders were
checked against WCAG contrast minimums (details in `docs/decisions.md`).

## Architecture

```
data/data.xlsx ──(one-time ETL: etl/load.py)──► PostgreSQL
                                                    │  SQL aggregation
                                              FastAPI (backend/)
                                                    │  JSON aggregates only (3–37 kB)
                                          Next.js + Recharts (frontend/)
```

```
etl/        load.py (read, transform, load, reconcile), validation.py, sql/, tests/
backend/    app/main.py (HTTP), service.py (calculations), queries.py (SQL),
            schemas.py, db.py (connection pool); tests/; scripts/ (benchmarks)
frontend/   app/, components/ (one per dashboard section), lib/ (API client,
            filters/URL state, formatting, questions); tests/ui_check.py
docs/       decisions.md, phase2-report.md
```

The Excel file is read once by the ETL, never by the API. The browser only
receives aggregated results, never raw rows.

## Dataset and data handling

From inspecting the file:

- **Rows and coverage:** 300,000 line-item rows, one sheet, covering 17 Jun 2025 to 16 Jun 2026 (365 days, every day present).
- **Bills:** 110,478 bills. `BillNo` is globally unique, and a bill has 1–6 lines.
- **Order-level fields:** outlet, timestamp, order type and settlement are identical on every line of a bill, so they belong to the order rather than to each line.
- **Dimensions:** 6 outlets, 7 menu groups, 45 items, 3 order types, 4 settlement values. Each item has a single fixed price.
- **Free items:** 8,611 lines have price ₹0, and all of them are BBQ or Mayo dips. 591 bills contain only those dips. Both are kept.
- **Brand:** a single value for every row, so it is not loaded or filtered.
- **Data quality:** no nulls, no duplicate rows and no duplicate items within a bill.

## PostgreSQL schema

```sql
orders      (bill_no INTEGER PRIMARY KEY, outlet TEXT, order_datetime TIMESTAMP,
             order_type TEXT, settlement TEXT)

order_items (bill_no INTEGER REFERENCES orders, item TEXT, item_group TEXT,
             price INTEGER CHECK (price >= 0), quantity INTEGER CHECK (quantity > 0),
             line_revenue INTEGER GENERATED ALWAYS AS (price * quantity) STORED,
             PRIMARY KEY (bill_no, item))

INDEX order_items (item_group)   -- the only index kept after measurement
```

The full definitions are in `etl/sql/`.

## ETL (`etl/load.py`)

1. Read the Excel file with **python-calamine**: 5.4 s for the full file, against 47.4 s with openpyxl, with identical output.
2. Validate it. The run fails clearly, writing nothing, if any of these checks fail:
   - columns, nulls, and number formats (BillNo, quantity, price);
   - dates that cannot be parsed;
   - duplicate bill + item pairs;
   - order fields that differ between lines of the same bill.
3. Split the data into `orders` and `order_items`.
4. In **one transaction**:
   - recreate the tables and bulk-load them with `COPY`;
   - add keys and the index;
   - run `ANALYZE`;
   - **reconcile** the database totals against totals computed independently from the source rows.
5. Commit only if the reconciliation passes; otherwise roll back and leave the previous data untouched.

A full run takes about 8–10 s locally. About 5 s of that is reading the Excel file.

## API (FastAPI)

| Endpoint | Returns |
|---|---|
| `GET /api/health` | API and database status |
| `GET /api/filters` | filter options and the data's date range (loaded once at startup) |
| `GET /api/dashboard` | KPIs, trend, every breakdown, top items, all in one response |

`/api/dashboard` accepts `start` and `end` (`YYYY-MM-DD`, both inclusive),
`outlet`, `group`, `order_type` and `settlement` (each repeatable), and
`granularity=day|week`.

Inputs are validated: unknown values return 422. All values are passed to SQL
as bound parameters. Interactive docs are served at `/docs`.

## Performance

These numbers were measured locally (1-CPU sandbox), not on the hosted setup.

- **Query design.** At first there was one SQL query per chart, and each one repeated the same 300K-row join. Rolling the lines up per bill once, and producing all order-level breakdowns from that with `GROUPING SETS`, cut an unfiltered request from **~2,101 ms to ~578 ms** of database time.
- **Indexes.** Each candidate index was measured on its own. Only `order_items(item_group)` was kept: date + menu group went from 136 to 47 ms. Indexes on `order_datetime` and `outlet` were rejected because they made date + outlet queries about 2.3× slower.
- **Prepared statements.** With psycopg's automatic prepared statements, a 6-month date range measured ~340 ms in one benchmark run and ~597 ms in the next, as PostgreSQL switched to a generic plan. They are turned off, and that range now measures ~325 ms. Trade-off: 1-week ranges became about 45 ms slower.
- **Caching.** None so far. Filter options are loaded once at startup, because that query costs about 300 ms and the data is static. A response cache will be considered only if the hosted timings need it.

Final API response times (median of 15 requests, two runs):

| Request | Median (ms) |
|---|---|
| Unfiltered, weekly | 488–490 |
| Unfiltered, daily | 491–498 |
| 6-month date range | 325–326 |
| One outlet | 255–257 |
| One menu group | 246–249 |
| 1-week date range | 116–122 |
| Date + menu group | 51 |
| Several filters | 85 |

## Assumptions and limitations

- **Revenue:** it is **gross** list-price revenue. The data has no discount, tax, refund or cost fields, so there are no net revenue or margin figures.
- **No customer metrics:** there is no customer identifier, so retention and repeat-customer analysis are not possible.
- **Settlement:** "Cash/Card/Coupon" is one combined value in the source, so it cannot be split into payment methods. The field is shown as a channel.
- **Timestamps:** they have no timezone and are treated as local time (IST).
- **Partial periods:** the first and last weeks are partial and are marked as such. There is no monthly chart, because June 2025 and June 2026 are both half-months.
- **Group-filter scope:** with a menu group filter, AOV is the average spend on that group per order, not the full basket value.
- **Branding:** the dashboard is labelled "California Burrito" for the assessment. The dataset's own Brand value is "Burger Town".
- **Questions and insights:** only the six fixed questions are supported, and they use the data already loaded for the current filters. Insights are comparisons, not explanations of causes, and they make no recommendations.
- **Colours:** the palette is an interpretation of red, green, sand, white and black, not official California Burrito brand values.
- **After re-running the ETL:** restart the API, because filter options are loaded at startup.

## Running locally

Tested with Python 3.12, Node 22 and PostgreSQL 16.

```bash
# 1. Database and configuration
createdb dashboard                      # and optionally: createdb dashboard_test
cp .env.example .env                    # set DATABASE_URL
cp frontend/.env.example frontend/.env.local

# 2. Python dependencies (ETL + API + tests)
python -m venv .venv && source .venv/bin/activate
pip install -r etl/requirements.txt -r backend/requirements-dev.txt

# 3. Load the data (place the assessment file at data/data.xlsx; it is gitignored)
python -m etl.load

# 4. API, from backend/  ->  http://localhost:8000  (docs at /docs)
cd backend && python -m uvicorn app.main:app --reload --port 8000

# 5. Frontend, from frontend/ in another terminal  ->  http://localhost:3000
cd frontend && npm install && npm run dev
```

**Environment variables:**

| Variable | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | ETL, API | PostgreSQL connection |
| `CORS_ORIGINS` | API | allowed frontend origins (comma-separated); default `http://localhost:3000` |
| `DB_POOL_MAX_SIZE` | API | connection pool size; default 5 |
| `NEXT_PUBLIC_API_URL` | frontend | API base URL; default `http://localhost:8000` |
| `TEST_DATABASE_URL` | ETL tests | separate database for the two ETL database tests |

## Testing

| Suite | Command | Result |
|---|---|---|
| ETL validation and loading | `TEST_DATABASE_URL=... python -m pytest` (repository root) | 27 passed |
| API vs. source data | `python -m pytest` (in `backend/`) | 39 passed |
| Browser checks | `python tests/ui_check.py` (in `frontend/`) | 86 passed |

- **API tests:** they recompute the expected values with pandas directly from the Excel file, with no ETL code and no SQL, so the database is never used to check itself. As a check on the tests themselves, deliberately breaking AOV, the end-date boundary and the group filter made 8, 7 and 6 tests fail.
- **Browser checks:**
  - they compare every on-screen KPI with the API;
  - they check each Ask About Your Data result, and the main figures in its insights, against values recomputed in Python from the raw API response;
  - they also cover the filters, URL state, Reset, date boundaries, the empty, loading and error states, keyboard use, the theme colours, and layouts at 1280, 820 and 390 px.
- **Requirements for each suite:**
  - the two ETL database tests need `TEST_DATABASE_URL` set (they are skipped otherwise);
  - the API tests need `DATABASE_URL` pointing at a database loaded by the ETL, and also need `data/data.xlsx`;
  - the browser checks need the API and the built frontend running, plus `pip install playwright && playwright install chromium`.
- **Benchmarks:** they can be re-run from `backend/` with `python -m scripts.benchmark_queries`, `python -m scripts.benchmark_indexes` and `python -m scripts.benchmark_api`.

## Deployment

Planned setup; not yet deployed.

| Part | Platform | Settings |
|---|---|---|
| Database | hosted PostgreSQL | load it once from a local machine: `python -m etl.load --database-url "<hosted URL>"` (most hosts need `sslmode=require` in the URL) |
| API | Render (web service) | root `backend`; build `pip install -r requirements.txt`; start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`; set `DATABASE_URL` and `CORS_ORIGINS=<Vercel URL>` |
| Frontend | Vercel | root `frontend`; set `NEXT_PUBLIC_API_URL=<Render URL>` |

The Excel file is not deployed; only the loaded database is.

On Render's free tier the API sleeps when idle, so the first request after a
pause is slow. The timings above are local, and will be re-measured once the
hosted setup is running.
