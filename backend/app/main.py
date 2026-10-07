"""HTTP layer: routing, input validation and error responses only.
SQL lives in queries.py and calculations in service.py."""
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app import db, queries, service
from app.queries import Filters
from app.schemas import Dashboard, FilterOptions

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.open_pool()
    # Filter options are loaded once: the data only changes when the ETL is
    # re-run (followed by an API restart), and the DISTINCT query measured
    # ~300 ms, which would otherwise be added to every dashboard request.
    with db.get_connection() as conn:
        app.state.filter_options = queries.fetch_filter_options(conn)
    yield
    db.close_pool()


app = FastAPI(title="Burger Town Analytics API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    try:
        with db.get_connection() as conn:
            conn.execute("SELECT 1")
    except Exception:
        raise HTTPException(status_code=503, detail="Database unreachable")
    return {"status": "ok", "database": "ok"}


@app.get("/api/filters", response_model=FilterOptions)
def filters(request: Request):
    return request.app.state.filter_options


def _checked(values, allowed, name):
    """Reject values that do not exist in the data; return a sorted tuple so
    the same selection always produces identical query parameters."""
    unique = sorted(set(values))
    invalid = [v for v in unique if v not in allowed]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {name}: {invalid}. Allowed values: {allowed}",
        )
    return tuple(unique)


@app.get("/api/dashboard", response_model=Dashboard)
def dashboard(
    request: Request,
    start: date | None = Query(None, description="Inclusive start date, YYYY-MM-DD"),
    end: date | None = Query(None, description="Inclusive end date, YYYY-MM-DD"),
    outlet: list[str] = Query(default=[]),
    group: list[str] = Query(default=[]),
    order_type: list[str] = Query(default=[]),
    settlement: list[str] = Query(default=[]),
    granularity: Literal["day", "week"] = "week",
):
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")

    options = request.app.state.filter_options
    filters = Filters(
        start=start,
        end=end,
        outlets=_checked(outlet, options["outlets"], "outlet"),
        groups=_checked(group, options["groups"], "group"),
        order_types=_checked(order_type, options["order_types"], "order_type"),
        settlements=_checked(settlement, options["settlements"], "settlement"),
    )
    with db.get_connection() as conn:
        return service.build_dashboard(
            conn, filters, granularity, options["min_date"], options["max_date"]
        )
