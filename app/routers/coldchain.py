"""GET /api/coldchain — cold-chain KPIs from mart_coldchain (grain: warehouse x route x month).

mart_coldchain has no outlet_code or region_name column (it's below outlet grain and
doesn't carry region), so `region` and `outlet` filters are resolved against dim_warehouses/
dim_regions and dim_outlets respectively before filtering the mart.
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.db import get_db

router = APIRouter()

WORST_LIMIT = 10


@router.get("/api/coldchain")
def get_coldchain(
    region: str | None = Query(None),
    warehouse: str | None = Query(None),
    route: str | None = Query(None),
    outlet: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    clauses = []
    params: list = []

    if region:
        clauses.append(
            "warehouse_id IN (SELECT w.warehouse_id FROM dim_warehouses w "
            "JOIN dim_regions r ON w.region_id = r.region_id WHERE r.region_name = ?)"
        )
        params.append(region)
    if warehouse:
        clauses.append("warehouse_code = ?")
        params.append(warehouse)
    if outlet:
        clauses.append("route_id IN (SELECT route_id FROM dim_outlets WHERE outlet_code = ?)")
        params.append(outlet)
    if route:
        clauses.append("route_code = ?")
        params.append(route)
    if date_from:
        clauses.append("month >= ?")
        params.append(date_from[:7])
    if date_to:
        clauses.append("month <= ?")
        params.append(date_to[:7])

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    rows = [dict(row) for row in db.execute(f"SELECT * FROM mart_coldchain {where} ORDER BY month, route_code", params)]
    worst_routes = [
        dict(row)
        for row in db.execute(
            f"SELECT * FROM mart_coldchain {where} "
            f"ORDER BY excursions_per_100_chilled_deliveries DESC LIMIT {WORST_LIMIT}",
            params,
        )
    ]

    return {"rows": rows, "worst_routes": worst_routes}
