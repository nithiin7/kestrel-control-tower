"""GET /api/money — freight cost per delivered case from mart_money."""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.db import get_db
from app.routers.filters import build_hierarchy_filters

router = APIRouter()


@router.get("/api/money")
def get_money(
    region: str | None = Query(None),
    warehouse: str | None = Query(None),
    route: str | None = Query(None),
    outlet: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    where, params = build_hierarchy_filters(region, warehouse, route, outlet, date_from, date_to)

    rows = [
        dict(row)
        for row in db.execute(
            "SELECT warehouse_id, warehouse_code, route_id, route_code, month, "
            "freight_amount_inr, delivered_cases, "
            "freight_cost_per_delivered_case_inr AS freight_cost_per_case_inr "
            f"FROM mart_money {where} ORDER BY month, route_code",
            params,
        )
    ]

    return {"rows": rows}
