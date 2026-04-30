from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.address import RegionServingBoundary
from app.schemas.region import BoundaryLevel, RegionBoundaryResponse
from app.services.region_boundary import (
    find_boundaries_within_radius,
    find_boundary_covering_point,
)

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("/covering-point", response_model=RegionBoundaryResponse)
def get_region_covering_point(
    db: Annotated[Session, Depends(get_db)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    latitude: Annotated[float, Query(ge=-90, le=90)],
    boundary_level: BoundaryLevel = "legal_dong",
) -> RegionBoundaryResponse:
    boundary = find_boundary_covering_point(
        db,
        longitude=longitude,
        latitude=latitude,
        boundary_level=boundary_level,
    )
    if boundary is None:
        raise HTTPException(status_code=404, detail="해당 좌표를 포함하는 행정경계를 찾지 못했다.")
    return _to_response(boundary)


@router.get("/within-radius", response_model=list[RegionBoundaryResponse])
def get_regions_within_radius(
    db: Annotated[Session, Depends(get_db)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    latitude: Annotated[float, Query(ge=-90, le=90)],
    radius_meters: Annotated[float, Query(gt=0, le=100000)],
    boundary_level: BoundaryLevel,
) -> list[RegionBoundaryResponse]:
    boundaries = find_boundaries_within_radius(
        db,
        longitude=longitude,
        latitude=latitude,
        radius_meters=radius_meters,
        boundary_level=boundary_level,
    )
    return [_to_response(boundary) for boundary in boundaries]


def _to_response(boundary: RegionServingBoundary) -> RegionBoundaryResponse:
    return RegionBoundaryResponse.model_validate(
        {
            "boundary_level": boundary.boundary_level,
            "region_code": boundary.region_code,
            "region_name": boundary.region_name,
            "sido_code": boundary.sido_code,
            "sigungu_code": boundary.sigungu_code,
            "legal_dong_code": boundary.legal_dong_code,
            "parent_region_code": boundary.parent_region_code,
            "full_region_name": boundary.full_region_name,
            "address_code_matched": boundary.address_code_matched,
        }
    )
