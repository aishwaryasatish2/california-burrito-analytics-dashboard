# Decision record

Each entry: **Decision → Reason → Alternative → Why not → Evidence.**
Evidence is either a measurement, a property of the dataset found during
inspection, or, where marked, a requirement or judgment call. Timings were
measured locally (PostgreSQL 16, 1-CPU sandbox); details are in
[`phase2-report.md`](phase2-report.md).

---

## Data and ETL

### 1. Read the Excel file with python-calamine
- **Reason:** the file is read once per ETL run and read speed dominates the run.
- **Alternative:** pandas' default engine (openpyxl).
- **Why not:** about 9× slower for identical output.
- **Evidence:** full 300,000-row read: calamine 5.4 s, openpyxl 47.4 s; the two outputs compared equal.

### 2. One-time ETL into a database, not reading Excel per request
- **Reason:** the data is static, and every dashboard view filters and aggregates the same rows.
- **Alternative:** parse the Excel file in the API.
- **Why not:** each read costs seconds before any calculation starts.
- **Evidence:** Excel read alone took 4.95–6.33 s across ETL runs.

### 3. PostgreSQL rather than SQLite
- **Reason:** project requirement. The assessment evaluates working with data and databases, and the dashboard's filtering and aggregation run in SQL on the server.
- **Alternative:** SQLite (simpler to deploy).
- **Why not:** chosen on the requirement, not on performance.
- **Evidence:** none measured. SQLite was not benchmarked, so no speed claim is made.

### 4. Validate strictly, load in one transaction, reconcile before commit
- **Reason:** a silently wrong database is worse than a failed load.
- **Alternative:** load first and check afterwards.
- **Why not:** a bad run would replace good data.
- **Evidence:**
  - a deliberately corrupted file exits with code 1 and names the Excel row, and the database keeps its 300,000 rows;
  - a test confirms that a failed reconciliation rolls back;
  - totals agree three ways (calamine + pandas, openpyxl + plain Python, SQL): 300,000 lines, 110,478 bills, ₹69,480,952, 434,448 units.

### 5. Bulk load with PostgreSQL COPY
- **Reason:** standard bulk path for 300K rows.
- **Alternative:** row-by-row INSERTs.
- **Why not:** not measured here; COPY was fast enough that no alternative was needed.
- **Evidence:** COPY of both tables took 1.28–1.47 s.

### 6. Keep zero-price lines and zero-value bills
- **Reason:** they are real complimentary items and real orders.
- **Alternative:** drop them as noise.
- **Why not:** that would under-count orders and units.
- **Evidence:**
  - all 8,611 zero-price lines are "Dip - BBQ" or "Dip - Mayo";
  - the 591 zero-value bills contain only those dips.

### 7. Do not load or analyse Brand
- **Reason:** no analytical value.
- **Alternative:** a Brand column and filter.
- **Why not:** a filter with one option does nothing.
- **Evidence:** every row has the same Brand value, "Burger Town".

## Schema

### 8. Split into `orders` and `order_items`
- **Reason:** a bill is one order, and its outlet, time, order type and settlement belong to the order, not to each line.
- **Alternative:** one flat table mirroring the Excel file.
- **Why not:**
  - it repeats order attributes on every line;
  - order counts would need `COUNT(DISTINCT)`.
- **Evidence:**
  - those four attributes were identical within every one of the 110,478 bills (checked in inspection, enforced by the ETL);
  - BillNo values are contiguous and globally unique.

### 9. `(bill_no, item)` as the primary key of `order_items`
- **Reason:** the natural key; it enforces "no duplicate line items" in the database itself.
- **Alternative:** a surrogate id.
- **Why not:** it adds a column and enforces nothing.
- **Evidence:** no item appears twice in any bill.

### 10. `line_revenue` as a generated column
- **Reason:** price × quantity is computed by PostgreSQL, so it cannot drift from its inputs.
- **Alternative:** compute revenue in every query, or store a copied value.
- **Why not:** the formula would be repeated, or a stored copy could disagree with its inputs.
- **Evidence:** the reconciliation compares this generated sum with an independent pandas sum.

### 11. No lookup tables, no stored hour/week/day columns
- **Reason:** the dimensions are tiny, and the time parts are one-line SQL expressions.
- **Alternative:** dimension tables and derived columns.
- **Why not:** more schema with no shown benefit.
- **Evidence:**
  - 6 outlets, 7 groups, 3 order types, 4 settlements;
  - `EXPLAIN ANALYZE` showed query time dominated by the join (~120 ms) and per-bill rollup (~55 ms), not by date expressions. The date expressions were not measured separately.

## Metric definitions

### 12. AOV excludes zero-revenue orders; Orders includes them
- **Reason:** a complimentary-only bill is a real order but says nothing about spend.
- **Alternative:** divide by all orders.
- **Why not:** this lowers AOV with orders that had no paid items.
- **Evidence:** AOV is ₹632.29 on 109,887 paid orders versus ₹628.91 on all 110,478.

### 13. A group filter changes the scope to matching lines
- **Reason:** with Group = Drinks, the dashboard answers questions about drinks lines, not whole baskets.
- **Alternative:** filter bills but report full-basket totals.
- **Why not:** that mixes two scopes on one screen.
- **Evidence:** a test confirms drinks revenue is below the full revenue of the bills containing drinks. The UI shows a scope note whenever a group filter is active.

### 14. Gross revenue only; no profit, margin or customer metrics
- **Reason:** report only what the fields support.
- **Alternative:** net revenue, margin, retention.
- **Why not:** the inputs do not exist.
- **Evidence:** there are no discount, tax, refund or cost fields, and no customer identifier.

## Query design and performance

### 15. Aggregate on the server; send only aggregates
- **Reason:** the browser should never process 300K rows.
- **Alternative:** send raw rows to the browser.
- **Why not:** large payloads and slow client-side work.
- **Evidence:** dashboard responses are 3–37 kB.

### 16. Two analytical queries per request
- **Decision:** one per-bill rollup with GROUPING SETS for all order-level breakdowns, plus one per-item aggregation.
- **Reason:** the per-bill rollup was the expensive step and was being repeated by every chart.
- **Alternatives:**
  - one query per chart;
  - a temp table of the rollup.
- **Why not:**
  - one query per chart repeated the same join six times;
  - the temp table writes a table on every request for similar speed.
- **Evidence (unfiltered request, database time):**
  - one query per chart: ~2,101 ms;
  - two queries: ~578 ms;
  - GROUPING SETS 354 ms versus temp table 388 ms.

### 17. No per-group order counts
- **Reason:** that figure needs `COUNT(DISTINCT bill_no)`, the slowest query, and the planned charts do not use it.
- **Alternative:** keep the separate group query.
- **Why not:** its cost was out of proportion to its value.
- **Evidence:** 614–680 ms even with more `work_mem`, versus 222 ms for the per-item query, which covers both groups and top items.

### 18. Indexes: keep `order_items(item_group)` only
- **Reason:** keep only indexes that measurably helped the real queries.
- **Alternative:** index every filterable column.
- **Why not:** most candidates did not help, and two made common cases slower.
- **Evidence (median ms per request):**
  - **item_group, kept:** date + group 136 → 47 (reproduced 137 → 48); group 325 → 264. No regressions. Cost: 2 MB of storage and +0.37 s ETL.
  - **order_datetime, rejected:** helped some date ranges (208 → 180), but date + outlet went 56 → 128 because the planner switched to a full `order_items` scan.
  - **outlet, rejected:** the same date + outlet regression (56 → 127).
  - **order_type, rejected:** no meaningful change.
  - **settlement, rejected:** one case improved (85 → 58), but date + outlet regressed (56 → 146).

### 19. Load filter options once at API startup
- **Reason:** they only change when the ETL re-runs.
- **Alternative:** query them on every request.
- **Why not:** it would add about 50% to every dashboard request.
- **Evidence:** the DISTINCT query measured ~300 ms. Consequence: restart the API after re-running the ETL.

### 20. Disable automatic prepared statements (`prepare_threshold=None`)
- **Reason:** after 5 runs psycopg prepares statements, and PostgreSQL may switch to a generic plan that ignores the actual dates.
- **Alternative:** psycopg's default.
- **Why not:** timing depended on how often a connection had run the query.
- **Evidence:**
  - the 6-month range was 340 ms in one API benchmark run and 597 ms in the next; it is now 326 / 325 ms;
  - **trade-off:** 1-week ranges got slower, 73 / 76 → 116 / 122 ms, because the generic plan happened to suit narrow ranges (34 ms versus 78 ms).

### 21. No response cache or Redis (for now)
- **Reason:** no measured need yet.
- **Alternative:** an in-process or external cache.
- **Why not:** the decision should come from hosted measurements, not local ones.
- **Evidence:** the slowest local request (unfiltered) is ~490 ms, mostly SQL. To be revisited after deployment.

## Dashboard

### 22. Weekly trend by default, daily on request, no monthly chart
- **Reason:** a one-year view without misleading month ends.
- **Alternative:** monthly bars.
- **Why not:** June 2025 and June 2026 are both half-months and would look like drops.
- **Evidence:**
  - the data runs 17 Jun 2025 – 16 Jun 2026;
  - the first and last weeks are flagged partial by the API and drawn with hollow markers and a note.

### 23. Revenue and orders as two aligned charts with zero baselines
- **Reason:** both series need a readable scale.
- **Alternative:** one chart with two y-axes.
- **Why not:** dual axes are easy to misread.
- **Evidence:**
  - weekly revenue is ~₹13–14 L against ~2,100 orders;
  - the first render, without zero baselines, started the revenue axis at ~₹4 L, which made small week-to-week changes look large.

### 24. Filters: date, outlet, menu group, order type, settlement
- **Reason:** these are the real dimensions of the data.
- **Alternatives:** Brand and Item filters.
- **Why not:**
  - Brand has a single value;
  - 45 items would make an unwieldy control, and the Top Items table already covers item-level detail.
- **Evidence:** dimension counts from inspection.

### 25. No day-of-week chart
- **Reason:** a chart should show something.
- **Alternative:** a weekday breakdown.
- **Why not:** the pattern is flat.
- **Evidence:** 300.7–306.7 orders per day across weekdays (< 2% spread).

### 26. Settlement shown as "Channel / settlement", within order type
- **Reason:** describe the field honestly.
- **Alternative:** label it "Payment method".
- **Why not:** that would imply data the field does not contain.
- **Evidence:**
  - SwiggyPay and ZomatoPay appear only on Delivery, and Dineout never does;
  - "Cash/Card/Coupon" is one combined source value.

### 27. Filter state in React, mirrored to the URL with `replaceState`
- **Reason:** controls must respond instantly, and views should be shareable.
- **Alternative:** drive the state from the URL with the Next.js router.
- **Why not:** the router updates asynchronously, so checkboxes snapped back after a click.
- **Evidence:** the browser test failed with "Clicking the checkbox did not change its state" and passed after the change.

### 28. Check URL filter values against `/api/filters` before loading data
- **Reason:** a stale or edited link should not show filters that don't exist.
- **Alternative:** pass URL values straight to the API.
- **Why not:** unknown values reach the API and come back as a 422 error.
- **Evidence:** a browser test loads `?outlet=Atlantis&…&start=2026-02-30`; the invalid values are dropped and no error appears.

### 29. Debounce requests (250 ms) and cancel superseded ones
- **Reason:** several quick selections should cost one query.
- **Alternative:** one request per change.
- **Why not:** each request costs real database time (up to ~490 ms).
- **Evidence:** a browser test makes three rapid selections and sees one request carrying all three.

### 30. "Ask About Your Data": six fixed questions, answered in the browser from the dashboard response
- **Reason:** requested as a small question-based feature, not a chatbot. All six questions can be answered from fields `/api/dashboard` already returns, so no backend change or extra request is needed.
- **Alternatives:**
  - a free-text or chat interface;
  - a new API endpoint per question.
- **Why not:**
  - free text would invite questions the data cannot answer (customers, profit, causes), against the scope rule in entry 14;
  - new endpoints would change the measured, tested backend for numbers the response already holds.
- **Evidence:**
  - browser checks recompute each question's expected rows in Python from the raw API response and compare them with the displayed table, for all six questions;
  - a check confirms the section has no text input;
  - edge cases are tested: one outlet, Dine-In only (no delivery orders), a menu group filter, and no matching data (the section is hidden).

### 31. Insights & Opportunities show gaps in the data, not causes or recommendations
- **Reason:** the data supports shares, gaps and ranks. It cannot show why numbers differ or what would improve them: there are no costs, customers or experiments.
- **Alternatives:**
  - advice-style text with suggested actions or explanations;
  - generated summaries.
- **Why not:** the fields do not support them, and the project's rule is not to invent conclusions.
- **Evidence:**
  - every statement is a calculation on the displayed result: share of total, gap to the next or lowest item, rank, aggregator share of delivery orders;
  - small gaps are reported as small: the highest outlet AOV is ₹7.41 (1.2%) above the lowest, and the panel states exactly that;
  - the panel says "They show where the numbers differ, not why";
  - browser checks verify the figures in three of the insights against an independent calculation.

## Judgment calls (not measured)

### 32. Dashboard labelled "California Burrito"
- **Reason:** owner's decision; the dashboard is presented for the assessing company.
- **Note:** the dataset's Brand value is "Burger Town" and the menu is burgers. The API is unchanged and its docs title still says "Burger Town".

### 33. Next.js 15.5 rather than 16
- **Reason:** stability and familiarity.
- **Evidence:** none measured.

### 34. Restrained theme: green data, red accent, sand bands; IBM Plex Sans self-hosted
- **Reason:**
  - colour never encodes outlet or group, so one hue (green) avoids implying categories;
  - red is kept to a few accents (the rule above the KPIs, the selected question) and is not used for data, because red reads as "decline" in analytics;
  - sand marks the filter bar and the insights panel; text is black on white;
  - the font is bundled with the app rather than loaded from a fonts CDN at build time.
- **Alternative:** red as the main data colour, or one colour per outlet or group.
- **Why not:** red data would read as a decline, and per-category colours would imply differences the single-hue charts do not claim.
- **Evidence:**
  - contrast was calculated: green `#2F6B3C` is 6.38:1 and red `#B3261E` is 6.54:1 on white; control borders `#8F8268` are 3.78:1 on white and 3.22:1 on sand; the orders-line tint `#5A9366` is 3.62:1;
  - the lightest green tint (inline bars, third donut slice) is below 3:1 and is always shown next to numbers;
  - browser checks confirm the applied colours (red KPI rule, sand band, green bars) and that the stylesheet has no gradients.
- **Note:** the palette is an interpretation of red, green, sand, white and black, not official brand values.

## Testing

### 35. Check results against the source file, not against the database
- **Reason:** the database must not validate itself.
- **Alternative:** compare API output with SQL.
- **Why not:** a shared bug would pass.
- **Evidence:**
  - backend tests recompute expected values with pandas from the Excel file (39 tests);
  - deliberately breaking AOV, the end-date boundary and the group filter produced 8, 7 and 6 failures;
  - browser checks compare displayed KPIs with the API, and recompute each Ask About Your Data answer in Python from the raw API response (86 checks). They are written in Python Playwright, the browser tooling available in this environment.

---

## Open items to revisit with hosted measurements

- **Response caching** (entry 21): decide once the hosted API's timings are known.
- **Narrow date ranges:** they are ~45 ms slower after entry 20. A planner cost setting may fix this, but that is untested.
