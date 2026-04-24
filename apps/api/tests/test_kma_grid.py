import pytest

from app.geospatial.kma_grid import kma_grid_to_wgs84, wgs84_to_kma_grid


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected_nx", "expected_ny"),
    [
        (37.579871128849334, 126.98935225645432, 60, 127),
        (35.101148844565955, 129.02478725562108, 97, 74),
        (33.500946412305076, 126.54663058817043, 53, 38),
    ],
)
def test_wgs84_to_kma_grid_matches_known_kma_examples(
    latitude: float,
    longitude: float,
    expected_nx: int,
    expected_ny: int,
) -> None:
    point = wgs84_to_kma_grid(latitude=latitude, longitude=longitude)

    assert point.nx == expected_nx
    assert point.ny == expected_ny


@pytest.mark.parametrize(
    ("nx", "ny", "expected_latitude", "expected_longitude"),
    [
        (60, 127, 37.579871128849334, 126.98935225645432),
        (97, 74, 35.101148844565955, 129.02478725562108),
        (53, 38, 33.500946412305076, 126.54663058817043),
    ],
)
def test_kma_grid_to_wgs84_matches_known_kma_examples(
    nx: int,
    ny: int,
    expected_latitude: float,
    expected_longitude: float,
) -> None:
    point = kma_grid_to_wgs84(nx=nx, ny=ny)

    assert point.latitude == pytest.approx(expected_latitude, abs=1e-12)
    assert point.longitude == pytest.approx(expected_longitude, abs=1e-12)


def test_wgs84_to_kma_grid_rejects_invalid_coordinate() -> None:
    with pytest.raises(ValueError, match="latitude"):
        wgs84_to_kma_grid(latitude=91.0, longitude=127.0)


def test_kma_grid_to_wgs84_rejects_invalid_grid() -> None:
    with pytest.raises(ValueError, match="nx"):
        kma_grid_to_wgs84(nx=0, ny=127)

