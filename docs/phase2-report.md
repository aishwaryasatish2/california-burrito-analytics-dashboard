# Phase 2 — Query design and performance

This document records how the backend query layer was designed and why, using
the measurements actually taken. Nothing here is estimated.

**Measurement environment.** Local PostgreSQL 16.15, a sandbox where `nproc`
reports 1 CPU, default PostgreSQL settings (`work_mem` 4 MB), warm cache.
Absolute numbers will differ on the hosted database; the comparisons between
alternatives are what matter, and the API should be re-measured after deployment.

**Tools (all in `backend/scripts/`, reproducible):**

* `benchmark_queries.py` — runs the real dashboard SQL under
  `EXPLAIN (ANALYZE, BUFFERS)` for eight filter scenarios, median of 9 runs.
* `benchmark_indexes.py` — adds one candidate index at a time on top of the
  current indexes, re-runs the query benchmark, drops it.
* `benchmark_api.py` — times real HTTP requests to a running API, 15 runs per
  scenario.

---

## 1. Metric definitions

All metrics are computed over the **filtered set of line items**. With a menu
group filter (e.g. Drinks), the dashboard describes the matching lines, not
the whole bill.

| Metric | Definition | Counts | Zero-value orders |
|---|---|---|---|
| Gross revenue | `SUM(line_revenue)` of matching lines | revenue | included (add ₹0) |
| Orders | bills with ≥ 1 matching line | bills | included |
| Paid orders | bills whose matching revenue > 0 | bills | excluded |
| AOV | gross revenue ÷ paid orders | — | excluded from denominator |
| Units sold | `SUM(quantity)` (free items included) | quantities | included |
| Line items | matching `order_items` rows | rows | included |
| Items per order | line items ÷ orders | — | included |

Unfiltered results: ₹69,480,952 revenue, 110,478 orders (109,887 paid,
591 zero-value), AOV ₹632.29, 434,448 units, 300,000 line items, 2.72 items
per order.

Revenue is **gross** (list price × quantity). The dataset has no discount,
tax, refund or cost fields, so net revenue and margin are not shown.

## 2. Filters

* Date range: half-open `order_datetime >= start AND < end + 1 day`, so the end
  date is included in full without `23:59:59` tricks (tested with a day that
  has orders after 23:00).
* Outlet, menu group, order type, settlement: multi-select, `= ANY(%(values)s)`.
* The same `WHERE` clause is used by every query, so every chart describes the
  same rows.
* Only fixed SQL fragments are placed in query text; all user values are bound
  parameters. Values are also validated against the real distinct values from
  the database (unknown values return 422).
* No Brand filter: the column has one value.
* No day-of-week chart: measured orders per day ranged only 300.7–306.7 across
  weekdays (< 2% spread), so it would show nothing.

## 3. Query design

### Starting point: one query per chart (rejected)

The first implementation had one SQL query per chart. Unfiltered, each took
~187–230 ms, and the group breakdown 645 ms. One default dashboard request
(8 queries) cost **~2,101 ms** of database time.

`EXPLAIN ANALYZE` showed why:

1. **The same work was repeated.** Six of the queries each joined all 300K
   lines to orders (~120 ms) and rolled them up per bill (~55 ms) before
   doing their own small grouping. An index cannot help here: an unfiltered
   query must read every row.
2. **The group breakdown sorted to disk.** `COUNT(DISTINCT bill_no)` forced a
   300K-row sort (`external merge Disk: 8888kB`).

### Alternatives measured (unfiltered, median ms)

| Approach | Time | Outcome |
|---|---|---|
| Per-bill rollup only (the unavoidable floor) | 260 | reference |
| **GROUPING SETS over one per-bill rollup** (all order-level breakdowns) | **354** | **chosen** |
| Temp table of the rollup + 5 simple GROUP BYs (client-timed) | 388 | rejected: similar speed but writes a table on every request |
| Group query with `COUNT(DISTINCT)`, work_mem 4 / 16 / 32 MB | 614 / 680 / 654 | rejected: more memory stops the spill but not the cost (sorting 300K rows on text) |
| Two-level group query (group, bill) then group, 4 / 32 MB | 486 / 407 | rejected |
| **Per-item aggregation (all 45 items)** | **222** | **chosen** |

### Final design: two analytical queries per request

**`ORDER_LEVEL_SQL`** — joins lines to orders, applies filters, rolls up to
one row per bill (grouping by the orders primary key), then
`GROUPING SETS ((), (period), (outlet), (order_type), (order_type, settlement), (hour))`.
This produces the KPI totals, the trend, outlet, order-type, channel and
hourly breakdowns from **one** rollup. Because each row of the rollup is one
bill, order counts are `count(*)`, not `COUNT(DISTINCT)`.

**`ITEM_LEVEL_SQL`** — one row per menu item (revenue, units, line count).
Top items and the group breakdown are both derived from it in Python:

* an item belongs to exactly one group, so group totals are sums of items;
* `(bill_no, item)` is unique, so an item's line count equals the number of
  orders containing it.

**Consequence (accepted trade-off):** the group breakdown shows revenue, units
and line items but **not** "orders containing this group". That figure needs
`COUNT(DISTINCT)` and was the 600+ ms query. The charts planned for the
dashboard do not need it.

The SQL lives in `app/queries.py`; all calculations (AOV, ratios, zero-filling,
top-N, partial-week flags) live in `app/service.py`; routes in `app/main.py`
only handle HTTP and validation.

### Result of the redesign (primary-key indexes only, median ms per request)

| Scenario | One query per chart | Two queries |
|---|---|---|
| No filters | ~2,101 | 578 |

All filtered scenarios also improved (see the baseline column in section 4).

## 4. Indexes

Each candidate was added alone on top of the primary keys, ANALYZEd and
measured. Values are the database time of one default dashboard request
(order-level weekly query + item-level query), median ms. These were measured
with `EXPLAIN ANALYZE`, i.e. with plans built for the actual filter values.

| Scenario | PK only | + order_datetime | + item_group | + outlet | + order_type | + settlement |
|---|---|---|---|---|---|---|
| No filters | 578.0 | 576.4 | 567.9 | 587.4 | 596.3 | 576.6 |
| Date, 1 month | 208.0 | 179.8 | 209.7 | 213.1 | 209.0 | 218.2 |
| Date, 1 week | 146.9 | 140.3 | 150.5 | 148.9 | 149.9 | 152.7 |
| Outlet | 298.6 | 310.5 | 295.1 | 284.1 | 309.8 | 303.7 |
| Group | 325.2 | **391.8** | **263.9** | 321.6 | 321.5 | 331.6 |
| Date + outlet | 55.7 | **127.6** | 57.0 | **127.3** | 58.6 | **145.5** |
| Date + group | 135.9 | 117.5 | **47.0** | 130.2 | 134.1 | 133.4 |
| Multiple filters | 84.9 | 67.3 | 80.1 | 72.1 | 70.2 | 57.8 |

A second, separate run of the item_group comparison reproduced the result:
group 353.4 → 298.4 ms, date + group 137.3 → 47.9 ms, while no-filter
(598.9 → 610.6) and outlet (313.9 → 320.1) stayed within noise.

### Kept: `order_items(item_group)`

* **Evidence:** date + group improved ~65% (136 → 47 ms, reproduced as
  137 → 48 ms); group-only improved ~16–19%. No other scenario got worse
  beyond run-to-run noise. The plan shows why: a bitmap index scan reads
  only the matching group's lines (15,322 Desserts lines) from the 300K-row
  table instead of scanning all of it.
* **Trade-off:** 2,056 kB of storage, and the ETL's key/index step rose from
  ~0.36 s to 0.73 s. Small next to the gain for a filter the dashboard offers
  prominently.
* Note that `item_group` has only 7 values. A "low-cardinality columns don't
  need indexes" rule of thumb would have rejected it; measurement showed it
  helps because it filters the large table.

### Rejected: `orders(order_datetime)`

* **Evidence:** helped some date filters (1 month 208 → 180 ms, multiple
  85 → 67 ms) but made **date + outlet 2.3× slower (56 → 128 ms)** and
  **group slower (325 → 392 ms)**.
* **Why it hurts:** the expensive table is `order_items`, not `orders`.
  Without the index, a selective date + outlet filter used a nested loop
  with 928 primary-key lookups into `order_items` (29 ms). With the index,
  reading `orders` became cheaper and the planner switched to a hash join that
  scans all 300K `order_items` rows (66 ms). Speeding up the small table
  changed the join strategy for the worse.
* A mixed result with a large regression is not worth keeping.

### Rejected: `orders(outlet)`

* **Evidence:** outlet-only 299 → 284 ms (small), but date + outlet
  56 → 127 ms — the same join-strategy regression as above.

### Rejected: `orders(order_type)`

* **Evidence:** no meaningful change anywhere; no-filter slightly slower
  (578 → 596 ms). Three values over 110K orders: nothing to gain.

### Rejected: `orders(settlement)`

* **Evidence:** multiple filters improved 85 → 58 ms (that scenario filters
  on SwiggyPay), but date + outlet regressed 56 → 146 ms, and other scenarios
  were flat or slightly worse. A gain in one narrow combination does not
  justify a large regression in another.

### Final indexes

| Index | Size | Purpose |
|---|---|---|
| `orders_pkey (bill_no)` | 2,448 kB | integrity; join target |
| `order_items_pkey (bill_no, item)` | 12 MB | integrity (no duplicate lines); serves joins via leading `bill_no` |
| `order_items_item_group_idx (item_group)` | 2,056 kB | menu-group filters (measured above) |

The kept index is created by the ETL (`etl/sql/add_constraints.sql`) after the
bulk load, with the rejected candidates and reasons recorded there.

## 5. Filter options loaded once at startup

`/api/filters` needs the distinct outlets, groups, order types, settlements
and the date bounds; the dashboard needs the same values to validate input.
That query measured **~300 ms** (DISTINCT over text). Running it per request
would add about 50% to the unfiltered dashboard. The data only changes when
the ETL is re-run offline, so the API loads the options once at startup.
**Consequence:** restart the API after re-running the ETL (a Render redeploy
does this).

This is the only cached data. No response caching was added.

## 6. The prepared-statement issue

### What was observed

The first API benchmark (two consecutive runs, same script and scenarios)
gave a stable result for every scenario except the 6-month date range:
**340 ms in run 1, 597 ms in run 2**, each with tight spread. That is not
noise.

### Cause

psycopg automatically turns a query into a server-side prepared statement
after it has run 5 times on a connection. After that, PostgreSQL may switch
to a **generic plan** — one plan reused for any parameter values, chosen
without knowing the actual dates. The query benchmark (EXPLAIN ANALYZE) never
uses prepared statements, so it could not see this; only timing the real HTTP
path exposed it.

Direct test, 30 executions on one connection, 6-month range (client-timed ms):

| Setting | Query | Runs 1–5 | Runs 11–30 |
|---|---|---|---|
| auto-prepare (default) | order-level | 197 | **314** |
| auto-prepare (default) | item-level | 135 | **267** |
| `prepare_threshold=None` | order-level | 193 | 196 |
| `prepare_threshold=None` | item-level | 139 | 133 |

### The inconvenient part

After the change, the **1-week range got slower** (see section 7). Repeating
the same 30-run test for a 1-week range:

| Setting | Query | Runs 1–5 | Runs 11–30 |
|---|---|---|---|
| auto-prepare (default) | order-level | 66 | **38** |
| auto-prepare (default) | item-level | 54 | **32** |
| `prepare_threshold=None` | order-level | 64 | 63 |
| `prepare_threshold=None` | item-level | 51 | 68 |

Comparing the two plans for the item-level query explains it:

| Plan | 1-week range | 6-month range |
|---|---|---|
| Generic (nested loop; assumes ~325 orders) | **34 ms** | 345 ms |
| Custom (hash join, full `order_items` scan) | 78 ms | **185 ms** |

Neither plan is right everywhere. The generic plan always uses a nested loop,
which is ideal for a narrow range and poor for a wide one. The custom plan
estimated the 1-week row count almost exactly (1,169 estimated vs 1,044
actual) and still chose the full scan. So PostgreSQL's cost model is pricing
index lookups as more expensive than they really are when the data is cached.

### Decision: keep `prepare_threshold=None`

* It removes the worst case (6-month range 597 → 325 ms) and makes timing
  independent of how many times a connection has run a query, which the
  default behaviour is not.
* Cost: 1-week ranges are ~45 ms slower (73–76 → 116–122 ms).
* Planning each execution costs under 1 ms.

The likely root cause of the narrow-range plan choice is the planner's
cost settings (probably `random_page_cost`, whose default assumes slow
random disk access). **This hypothesis has not been tested** and nothing was
changed for it; see section 9.

## 7. Final API timings

Real HTTP requests to a freshly restarted API (final code), 15 runs per
scenario, two consecutive runs. "Before" is the same benchmark with the
default auto-prepare behaviour. Median ms (p95 in brackets).

| Scenario | Before, run 1 | Before, run 2 | **After, run 1** | **After, run 2** | Response size |
|---|---|---|---|---|---|
| Unfiltered (week) | 519 (585) | 504 (603) | **490 (531)** | **488 (503)** | 8,802 B |
| Unfiltered (day) | 500 (802) | 507 (571) | **491 (503)** | **498 (598)** | 37,401 B |
| Wide date, 6 months | 340 (812) | 597 (667) | **326 (338)** | **325 (334)** | 6,218 B |
| Narrow date, 1 week | 73 (89) | 76 (85) | **122 (152)** | **116 (119)** | 4,250 B |
| Outlet | 266 (277) | 269 (288) | **257 (278)** | **255 (299)** | 8,209 B |
| Group | 254 (277) | 258 (293) | **249 (259)** | **246 (263)** | 8,012 B |
| Date + group | 51 (56) | 54 (70) | **51 (52)** | **51 (52)** | 3,079 B |
| Multiple filters | 85 (92) | 85 (162) | **85 (87)** | **85 (92)** | 3,898 B |

First request after a fresh start: 561 ms before, 527 ms after.

In every scenario, almost all of the time is the two SQL queries (the
`meta.query_ms` value in each response was within a few ms of the wall time).
Responses are aggregates only, 3–37 kB; raw rows are never sent.

## 8. Verification

* **ETL tests:** 27 passed (including the two database tests).
* **Backend tests:** 39 passed, also confirmed in a clean virtual environment
  installed from `requirements-dev.txt`.
* Expected values in the backend tests are computed by **pandas directly from
  the original Excel file**, with no ETL code and no SQL, so the database is
  never used to check itself. Covered: KPIs and every breakdown under nine
  filter combinations (unfiltered, date, single day, one outlet, two outlets,
  group, order type, settlement, multiple), end-date inclusion, group-filter
  scope (revenue is less than the full bills' revenue), zero-value orders and
  AOV, day and week trends, partial-week flags, zero-filled gaps, a range
  outside the data, nine invalid inputs (422), and an injection attempt.
* **The tests catch real bugs:** deliberately breaking AOV, the end-date
  boundary and the group filter produced 8, 7 and 6 failures respectively.
* **Database sanity check (final):** 300,000 line items, 110,478 orders,
  ₹69,480,952 gross revenue, 434,448 units, 8,611 zero-price lines, 591
  zero-value orders.

## 9. Remaining concerns

1. **Narrow date ranges.** About 45 ms slower than they could be, because of
   the planner's cost model (section 6). A session setting such as a lower
   `random_page_cost` might fix it, but that is untested and depends on the
   hosted database's storage, so it should be measured there, not tuned
   locally.
2. **The unfiltered view costs ~490 ms**, and it is the default view, so every
   visitor pays it. That is close to the per-bill rollup floor (~260 ms) plus
   grouping. If the hosted database is much slower, the evidence-based next
   step would be a small in-process cache for repeated filter sets. Decide
   after measuring the hosted database.
3. **Hosted performance is unknown.** All numbers here are local. Render's
   free tier also sleeps when idle, so the first request after a pause will
   be slow regardless of query design.
4. **No per-group order counts**, by design (section 3).
5. The ETL database tests read `TEST_DATABASE_URL` from the environment and,
   unlike the backend tests, do not load `.env`, so they are skipped unless
   it is exported.
6. FastAPI's test client prints a deprecation warning about `httpx`. It does
   not affect results.
