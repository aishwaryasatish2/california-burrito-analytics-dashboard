-- Run after COPY: building each index once over loaded data is cheaper than
-- maintaining it row by row during the load.

ALTER TABLE orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (bill_no);

-- (bill_no, item) is the natural key: an item never repeats within a bill.
-- Its index leads with bill_no, so it also serves joins to orders.
ALTER TABLE order_items
    ADD CONSTRAINT order_items_pkey PRIMARY KEY (bill_no, item);

ALTER TABLE order_items
    ADD CONSTRAINT order_items_bill_no_fkey
    FOREIGN KEY (bill_no) REFERENCES orders (bill_no);

-- Query-specific indexes: only those that measurably helped the real dashboard
-- queries (backend/scripts/benchmark_indexes.py) are kept.
--
-- Kept: a menu-group filter now reads only that group's lines from the large
-- table instead of all 300K (date + Desserts: ~137 ms -> ~48 ms per request).
CREATE INDEX order_items_item_group_idx ON order_items (item_group);
--
-- Tested and rejected:
--   orders(order_datetime) - faster for some date ranges, but made the planner
--     switch to a full order_items scan for date + outlet (~56 ms -> ~128 ms).
--   orders(outlet) - same regression for date + outlet.
--   orders(order_type), orders(settlement) - no meaningful change.
