"""GET /api/service — outlet service KPIs from mart_service / mart_service_worst."""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.db import get_db

router = APIRouter()

WORST_LIMIT = 10


@router.get("/api/service")
def get_service(
    region: str | None = Query(None),
    warehouse: str | None = Query(None),
    route: str | None = Query(None),
    outlet: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    where, params = _build_filters(region, warehouse, route, outlet, date_from, date_to)

    rows = [dict(row) for row in db.execute(f"SELECT * FROM mart_service {where} ORDER BY month, outlet_code", params)]
    worst_outlets = [
        dict(row)
        for row in db.execute(
            f"SELECT * FROM mart_service_worst {where} ORDER BY fill_rate_eaches ASC LIMIT {WORST_LIMIT}", params
        )
    ]

    return {"rows": rows, "worst_outlets": worst_outlets}


def _build_filters(
    region: str | None,
    warehouse: str | None,
    route: str | None,
    outlet: str | None,
    date_from: str | None,
    date_to: str | None,
) -> tuple[str, list]:
    clauses = []
    params: list = []

    if region:
        clauses.append("region_name = ?")
        params.append(region)
    if warehouse:
        clauses.append("warehouse_code = ?")
        params.append(warehouse)
    if route:
        clauses.append("route_code = ?")
        params.append(route)
    if outlet:
        clauses.append("outlet_code = ?")
        params.append(outlet)
    if date_from:
        clauses.append("month >= ?")
        params.append(date_from[:7])
    if date_to:
        clauses.append("month <= ?")
        params.append(date_to[:7])

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params
