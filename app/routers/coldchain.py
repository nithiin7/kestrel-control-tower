"""GET /api/coldchain — cold-chain KPIs from mart_coldchain (grain: warehouse x route x month).

mart_coldchain has no outlet_code or region_name column (it's below outlet grain and
doesn't carry region), so `region` and `outlet` filters are resolved against dim_warehouses/
dim_regions and dim_outlets respectively before filtering the mart.
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.db import get_db
from app.routers.filters import build_hierarchy_filters

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
    where, params = build_hierarchy_filters(region, warehouse, route, outlet, date_from, date_to)

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
