from typing import Literal

from pydantic import BaseModel, Field

BoundaryLevel = Literal["sido", "sigungu", "legal_dong"]


class RegionBoundaryResponse(BaseModel):
    boundary_level: str
    region_code: str
    region_name: str
    sido_code: str
    sigungu_code: str | None
    legal_dong_code: str | None
    parent_region_code: str | None
    full_region_name: str
    address_code_matched: bool


class RadiusRegionQuery(BaseModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    radius_meters: float = Field(gt=0, le=100000)
    boundary_level: BoundaryLevel
