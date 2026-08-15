"""GET /api/price_position — competitor price gap from mart_price_position (grain: city x category x sku_code x week).

mart_price_position has no warehouse/route/outlet columns — competitor prices are scraped
by city, not by Kestrel's internal distribution hierarchy — so `warehouse`/`route`/`outlet`
are accepted for filter-contract consistency with the other endpoints but have no effect
here. `region` is resolved via each city's warehouse region (each of the 4 BazaarPulse
cities maps to exactly one region).
"""

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.db import get_db

router = APIRouter()


@router.get("/api/price_position")
def get_price_position(
    region: str | None = Query(None),
    warehouse: str | None = Query(None),
    route: str | None = Query(None),
    outlet: str | None = Query(None),
    city: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    clauses = []
    params: list = []

    if region:
        clauses.append(
            "city IN (SELECT DISTINCT w.city FROM dim_warehouses w "
            "JOIN dim_regions r ON w.region_id = r.region_id WHERE r.region_name = ?)"
        )
        params.append(region)
    if city:
        clauses.append("city = ?")
        params.append(city)
    if date_from:
        clauses.append("week >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("week <= ?")
        params.append(date_to)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    rows = [
        dict(row)
        for row in db.execute(
            "SELECT city, category, sku_code, week, kestrel_mrp_inr, competitor_mrp_inr, "
            "competitor_price_median_inr AS competitor_price_inr, "
            "competitor_price_min_inr, competitor_listing_count, gap_pct, gap_pct_vs_min "
            f"FROM mart_price_position {where} ORDER BY week, city, sku_code",
            params,
        )
    ]

    return {"rows": rows}
