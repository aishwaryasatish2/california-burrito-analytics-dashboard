-- Rebuilt from scratch on every ETL run (inside one transaction).
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;

-- One row per bill. Outlet, datetime, order type and settlement were verified
-- to be identical on every line of a bill, so they live here, not on items.
CREATE TABLE orders (
    bill_no        INTEGER   NOT NULL,
    outlet         TEXT      NOT NULL,
    order_datetime TIMESTAMP NOT NULL,  -- source has no timezone; assumed IST
    order_type     TEXT      NOT NULL,
    settlement     TEXT      NOT NULL
);

-- One row per line item.
CREATE TABLE order_items (
    bill_no      INTEGER NOT NULL,
    item         TEXT    NOT NULL,
    item_group   TEXT    NOT NULL,
    price        INTEGER NOT NULL CHECK (price >= 0),
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    -- Computed by PostgreSQL so it can never disagree with price * quantity.
    line_revenue INTEGER GENERATED ALWAYS AS (price * quantity) STORED
);
