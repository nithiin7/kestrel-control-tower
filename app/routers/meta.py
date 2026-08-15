"""GET /api/health and GET /api/meta/filters — shared filter bar data."""

import sqlite3

from fastapi import APIRouter, Depends

from app.db import get_db

router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/api/meta/filters")
def get_filters(db: sqlite3.Connection = Depends(get_db)) -> dict:
    regions = [
        dict(row)
        for row in db.execute("SELECT region_id, region_code, region_name FROM dim_regions ORDER BY region_name")
    ]
    warehouses = [
        dict(row)
        for row in db.execute(
            "SELECT warehouse_id, warehouse_code, warehouse_name, region_id FROM dim_warehouses ORDER BY warehouse_code"
        )
    ]
    routes = [
        dict(row) for row in db.execute("SELECT route_id, route_code, warehouse_id FROM dim_routes ORDER BY route_code")
    ]
    outlets = [
        dict(row)
        for row in db.execute(
            "SELECT outlet_code, outlet_name, region_id, route_id FROM dim_outlets ORDER BY outlet_code"
        )
    ]
    fiscal_quarters = [
        row[0]
        for row in db.execute(
            "SELECT DISTINCT fiscal_quarter_label, fiscal_year_start_year, fiscal_quarter FROM dim_date "
            "ORDER BY fiscal_year_start_year, fiscal_quarter"
        )
    ]

    return {
        "regions": regions,
        "warehouses": warehouses,
        "routes": routes,
        "outlets": outlets,
        "fiscal_quarters": fiscal_quarters,
    }
