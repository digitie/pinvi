from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.address import RegionServingBoundary


def find_boundary_covering_point(
    session: Session,
    *,
    longitude: float,
    latitude: float,
    boundary_level: str = "legal_dong",
) -> RegionServingBoundary | None:
    point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
    statement = (
        select(RegionServingBoundary)
        .where(RegionServingBoundary.boundary_level == boundary_level)
        .where(func.ST_Covers(RegionServingBoundary.geom, point))
        .order_by(func.ST_Area(RegionServingBoundary.geom))
        .limit(1)
    )
    return session.scalar(statement)


def find_boundaries_within_radius(
    session: Session,
    *,
    longitude: float,
    latitude: float,
    radius_meters: float,
    boundary_level: str,
) -> list[RegionServingBoundary]:
    point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
    projected_point = func.ST_Transform(point, 5179)
    projected_geom = func.ST_Transform(RegionServingBoundary.geom, 5179)
    statement = (
        select(RegionServingBoundary)
        .where(RegionServingBoundary.boundary_level == boundary_level)
        .where(func.ST_DWithin(projected_geom, projected_point, radius_meters))
        .order_by(RegionServingBoundary.region_code)
    )
    return list(session.scalars(statement).all())
