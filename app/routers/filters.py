"""Shared WHERE-clause builder for marts filtered by the warehouse/route/outlet hierarchy.

Used by endpoints whose mart is below outlet grain (no outlet_code or region_name
column), so `region` and `outlet` are resolved against dim_warehouses/dim_regions
and dim_outlets respectively before filtering the mart.
"""


def build_hierarchy_filters(
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
    return where, params
