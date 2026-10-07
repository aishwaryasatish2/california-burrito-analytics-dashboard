"""Central PostgreSQL connection pool (one per API process)."""
import os

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

pool: ConnectionPool | None = None


def open_pool():
    global pool
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    # Small pool: one dashboard request uses one connection for all its
    # queries, and a single free-tier instance serves few concurrent users.
    pool = ConnectionPool(
        database_url,
        min_size=1,
        max_size=int(os.environ.get("DB_POOL_MAX_SIZE", "5")),
        # prepare_threshold=None: psycopg otherwise prepares a statement after 5
        # runs, after which PostgreSQL may switch to a generic plan that ignores
        # the actual date/filter values. Measured on a 6-month date filter, that
        # roughly doubled query time (~200 ms -> ~300 ms per query); planning
        # each execution costs under 1 ms.
        kwargs={"row_factory": dict_row, "prepare_threshold": None},
        open=True,
    )
    pool.wait()


def close_pool():
    if pool is not None:
        pool.close()


def get_connection():
    return pool.connection()
