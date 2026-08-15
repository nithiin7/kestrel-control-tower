"""GET /api/money — freight cost per delivered case from mart_money."""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.db import get_db

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
