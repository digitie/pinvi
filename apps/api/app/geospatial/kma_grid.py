"""KMA DFS grid conversion helpers.

The Korea Meteorological Administration short-term forecast APIs use the
DFS Lambert Conformal Conic grid (`nx`, `ny`). These helpers convert between
WGS84 latitude/longitude degrees and that grid.

Reference: https://gist.github.com/fronteer-kr/14d7f779d52a21ac2f16
"""

from dataclasses import dataclass
from math import atan, atan2, cos, floor, log, pi, pow, sin, sqrt, tan
from typing import Final

EARTH_RADIUS_KM: Final = 6371.00877
GRID_KM: Final = 5.0
STANDARD_LATITUDE_1: Final = 30.0
STANDARD_LATITUDE_2: Final = 60.0
ORIGIN_LONGITUDE: Final = 126.0
ORIGIN_LATITUDE: Final = 38.0
ORIGIN_X: Final = 43.0
ORIGIN_Y: Final = 136.0

DEG_TO_RAD: Final = pi / 180.0
RAD_TO_DEG: Final = 180.0 / pi


@dataclass(frozen=True, slots=True)
class KmaGridPoint:
    """KMA DFS grid point used by short-term weather APIs."""

    nx: int
    ny: int


@dataclass(frozen=True, slots=True)
class Wgs84Point:
    """WGS84 point in latitude/longitude order."""

    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class _Projection:
    scaled_earth_radius: float
    cone_constant: float
    projection_factor: float
    origin_radius: float


def wgs84_to_kma_grid(latitude: float, longitude: float) -> KmaGridPoint:
    """Convert WGS84 latitude/longitude degrees to KMA DFS `nx`, `ny`."""

    _validate_wgs84(latitude=latitude, longitude=longitude)
    projection = _projection()

    radius = tan(pi * 0.25 + latitude * DEG_TO_RAD * 0.5)
    radius = (
        projection.scaled_earth_radius
        * projection.projection_factor
        / pow(radius, projection.cone_constant)
    )

    theta = longitude * DEG_TO_RAD - ORIGIN_LONGITUDE * DEG_TO_RAD
    if theta > pi:
        theta -= 2.0 * pi
    if theta < -pi:
        theta += 2.0 * pi
    theta *= projection.cone_constant

    nx = floor(radius * sin(theta) + ORIGIN_X + 0.5)
    ny = floor(projection.origin_radius - radius * cos(theta) + ORIGIN_Y + 0.5)
    return KmaGridPoint(nx=nx, ny=ny)


def kma_grid_to_wgs84(nx: int, ny: int) -> Wgs84Point:
    """Convert KMA DFS `nx`, `ny` to WGS84 latitude/longitude degrees."""

    _validate_grid(nx=nx, ny=ny)
    projection = _projection()

    xn = float(nx) - ORIGIN_X
    yn = projection.origin_radius - float(ny) + ORIGIN_Y
    radius = sqrt(xn * xn + yn * yn)
    if projection.cone_constant < 0.0:
        radius = -radius

    latitude_rad = pow(
        projection.scaled_earth_radius * projection.projection_factor / radius,
        1.0 / projection.cone_constant,
    )
    latitude_rad = 2.0 * atan(latitude_rad) - pi * 0.5

    if abs(xn) <= 0.0:
        theta = 0.0
    elif abs(yn) <= 0.0:
        theta = pi * 0.5
        if xn < 0.0:
            theta = -theta
    else:
        theta = atan2(xn, yn)

    longitude_rad = theta / projection.cone_constant + ORIGIN_LONGITUDE * DEG_TO_RAD
    return Wgs84Point(latitude=latitude_rad * RAD_TO_DEG, longitude=longitude_rad * RAD_TO_DEG)


def _projection() -> _Projection:
    scaled_earth_radius = EARTH_RADIUS_KM / GRID_KM
    standard_latitude_1 = STANDARD_LATITUDE_1 * DEG_TO_RAD
    standard_latitude_2 = STANDARD_LATITUDE_2 * DEG_TO_RAD
    origin_latitude = ORIGIN_LATITUDE * DEG_TO_RAD

    cone_constant_base = tan(pi * 0.25 + standard_latitude_2 * 0.5) / tan(
        pi * 0.25 + standard_latitude_1 * 0.5
    )
    cone_constant = log(cos(standard_latitude_1) / cos(standard_latitude_2)) / log(
        cone_constant_base
    )

    projection_factor = tan(pi * 0.25 + standard_latitude_1 * 0.5)
    projection_factor = (
        pow(projection_factor, cone_constant) * cos(standard_latitude_1) / cone_constant
    )

    origin_radius = tan(pi * 0.25 + origin_latitude * 0.5)
    origin_radius = (
        scaled_earth_radius * projection_factor / pow(origin_radius, cone_constant)
    )

    return _Projection(
        scaled_earth_radius=scaled_earth_radius,
        cone_constant=cone_constant,
        projection_factor=projection_factor,
        origin_radius=origin_radius,
    )


def _validate_wgs84(latitude: float, longitude: float) -> None:
    if not -90.0 <= latitude <= 90.0:
        msg = f"latitude must be between -90 and 90 degrees: {latitude}"
        raise ValueError(msg)
    if not -180.0 <= longitude <= 180.0:
        msg = f"longitude must be between -180 and 180 degrees: {longitude}"
        raise ValueError(msg)


def _validate_grid(nx: int, ny: int) -> None:
    if nx < 1:
        msg = f"nx must be positive: {nx}"
        raise ValueError(msg)
    if ny < 1:
        msg = f"ny must be positive: {ny}"
        raise ValueError(msg)

