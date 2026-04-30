from __future__ import annotations

from collections.abc import Generator

from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import create_app
from app.models.address import (
    RegionBoundaryImportBatch,
    RegionRawVWorldBoundary,
    RegionServingBoundary,
)


def test_covering_point_region_api_returns_legal_dong(db_session: Session) -> None:
    _add_boundary(db_session)
    client = _build_client(db_session)

    response = client.get(
        "/regions/covering-point",
        params={"longitude": 126.9707, "latitude": 37.5804},
    )

    assert response.status_code == 200
    assert response.json()["region_code"] == "1111010100"


def test_within_radius_region_api_returns_boundaries(db_session: Session) -> None:
    _add_boundary(db_session)
    client = _build_client(db_session)

    response = client.get(
        "/regions/within-radius",
        params={
            "longitude": 126.9707,
            "latitude": 37.5804,
            "radius_meters": 500,
            "boundary_level": "legal_dong",
        },
    )

    assert response.status_code == 200
    assert [row["region_code"] for row in response.json()] == ["1111010100"]


def _build_client(db_session: Session) -> TestClient:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _add_boundary(db_session: Session) -> None:
    polygon_4326 = (
        "MULTIPOLYGON(((126.9680 37.5780,126.9740 37.5780,126.9740 37.5830,"
        "126.9680 37.5830,126.9680 37.5780)))"
    )
    batch = RegionBoundaryImportBatch(
        source_file_name="N3A_G0110000.zip",
        source_file_hash="fixture",
        layer_code="N3A_G0110000",
        boundary_level="legal_dong",
        source_encoding="cp949",
        source_srid=5179,
        serving_srid=4326,
        row_count=1,
        status="loaded",
    )
    db_session.add(batch)
    db_session.flush()
    raw = RegionRawVWorldBoundary(
        import_batch_id=batch.id,
        row_number=1,
        layer_code="N3A_G0110000",
        boundary_level="legal_dong",
        ufid="100037608069G01110100000000000001",
        bjcd="1111010100",
        name="청운동",
        divi="HJD010",
        scls="G0018117",
        fmta="R23120001",
        raw_attributes={
            "UFID": "100037608069G01110100000000000001",
            "BJCD": "1111010100",
            "NAME": "청운동",
            "DIVI": "HJD010",
            "SCLS": "G0018117",
            "FMTA": "R23120001",
        },
        source_file_name="N3A_G0110000.zip",
        source_file_hash="fixture",
        geom=WKTElement(polygon_4326, srid=5179),
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        RegionServingBoundary(
            raw_boundary_id=raw.id,
            import_batch_id=batch.id,
            layer_code="N3A_G0110000",
            boundary_level="legal_dong",
            region_code="1111010100",
            region_name="청운동",
            sido_code="1100000000",
            sigungu_code="1111000000",
            legal_dong_code="1111010100",
            parent_region_code="1111000000",
            full_region_name="서울특별시 종로구 청운동",
            address_code_standard_code=None,
            address_code_matched=False,
            source_file_name="N3A_G0110000.zip",
            source_file_hash="fixture",
            geom=WKTElement(polygon_4326, srid=4326),
        )
    )
    db_session.flush()
