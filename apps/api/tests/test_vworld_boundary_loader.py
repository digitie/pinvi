from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import shapefile
from pyproj import Transformer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.etl.vworld.boundary_loader import load_vworld_boundary_zip
from app.models.address import (
    AddressCodeStandard,
    RegionBoundaryImportBatch,
    RegionRawVWorldBoundary,
    RegionServingBoundary,
)
from app.services.region_boundary import (
    find_boundaries_within_radius,
    find_boundary_covering_point,
)

KOREA_UNIFIED_PRJ = (
    'PROJCS["Korea_2000_Korea_Unified_Coordinate_System",'
    'GEOGCS["GCS_Korea_2000",DATUM["D_Korea_2000",'
    'SPHEROID["GRS_1980",6378137.0,298.257222101]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",1000000.0],'
    'PARAMETER["False_Northing",2000000.0],PARAMETER["Central_Meridian",127.5],'
    'PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",38.0],'
    'UNIT["Meter",1.0],AUTHORITY["EPSG",5179]]'
)


def test_vworld_boundary_loader_stores_raw_and_serving_layers(
    db_session: Session,
    tmp_path: Path,
) -> None:
    _add_address_code(db_session)
    zip_path = _write_boundary_zip(
        tmp_path,
        layer_code="N3A_G0110000",
        bjcd="1111010100",
        name="청운동",
        divi="HJD010",
        scls="G0018117",
    )

    result = load_vworld_boundary_zip(db_session, zip_path)

    assert result.layer_code == "N3A_G0110000"
    assert result.boundary_level == "legal_dong"
    assert result.row_count == 1
    assert result.address_code_match_count == 1

    assert db_session.scalar(select(func.count()).select_from(RegionBoundaryImportBatch)) == 1
    assert db_session.scalar(select(func.count()).select_from(RegionRawVWorldBoundary)) == 1
    assert db_session.scalar(select(func.count()).select_from(RegionServingBoundary)) == 1

    raw_srid = db_session.scalar(select(func.ST_SRID(RegionRawVWorldBoundary.geom)))
    serving_srid = db_session.scalar(select(func.ST_SRID(RegionServingBoundary.geom)))
    assert raw_srid == 5179
    assert serving_srid == 4326

    serving = db_session.scalar(select(RegionServingBoundary))
    assert serving is not None
    assert serving.region_code == "1111010100"
    assert serving.legal_dong_code == "1111010100"
    assert serving.sido_code == "1100000000"
    assert serving.sigungu_code == "1111000000"
    assert serving.address_code_standard_code == "1111010100"
    assert serving.address_code_matched is True
    assert serving.full_region_name == "서울특별시 종로구 청운동"


def test_region_boundary_query_helpers_find_point_and_radius(
    db_session: Session,
    tmp_path: Path,
) -> None:
    _add_address_code(db_session)
    zip_path = _write_boundary_zip(
        tmp_path,
        layer_code="N3A_G0110000",
        bjcd="1111010100",
        name="청운동",
        divi="HJD010",
        scls="G0018117",
    )
    load_vworld_boundary_zip(db_session, zip_path)

    boundary = find_boundary_covering_point(
        db_session,
        longitude=126.9707,
        latitude=37.5804,
    )
    nearby = find_boundaries_within_radius(
        db_session,
        longitude=126.9707,
        latitude=37.5804,
        radius_meters=500,
        boundary_level="legal_dong",
    )

    assert boundary is not None
    assert boundary.region_code == "1111010100"
    assert [region.region_code for region in nearby] == ["1111010100"]


def test_vworld_boundary_loader_matches_sido_by_name_when_sido_code_is_absent(
    db_session: Session,
    tmp_path: Path,
) -> None:
    db_session.add(
        AddressCodeStandard(
            legal_dong_code="3611000000",
            code_level="sigungu",
            code_name="세종특별자치시",
            sido_code="3600000000",
            sigungu_code="3611000000",
            sido_name="세종특별자치시",
            sigungu_name=None,
            legal_eupmyeondong_name=None,
            legal_ri_name=None,
            full_legal_dong_name="세종특별자치시",
            source_effective_date="20250101",
            source_change_reason_code="00",
            source_provider="vworld_lawd_cd",
            source_status="존재",
            source_file_name="LSCT_LAWDCD.csv",
            source_year_month="202501",
            source_file_hash="fixture",
            is_discontinued=False,
            is_active=True,
        )
    )
    db_session.flush()
    zip_path = _write_boundary_zip(
        tmp_path,
        layer_code="N3A_G0010000",
        bjcd="3600000000",
        name="세종특별자치시",
        divi="HJD005",
        scls="G0018112",
    )

    result = load_vworld_boundary_zip(db_session, zip_path)
    db_session.commit()

    serving = db_session.scalar(select(RegionServingBoundary))
    assert result.address_code_match_count == 1
    assert serving is not None
    assert serving.region_code == "3600000000"
    assert serving.address_code_standard_code == "3611000000"


def test_vworld_boundary_loader_matches_data_go_sejong_sido_name(
    db_session: Session,
    tmp_path: Path,
) -> None:
    db_session.add(
        AddressCodeStandard(
            legal_dong_code="3611000000",
            code_level="sigungu",
            code_name="세종특별자치시 세종시",
            sido_code="3600000000",
            sigungu_code="3611000000",
            sido_name="세종특별자치시",
            sigungu_name="세종시",
            legal_eupmyeondong_name=None,
            legal_ri_name=None,
            full_legal_dong_name="세종특별자치시 세종시",
            source_effective_date="20250807",
            source_change_reason_code="00",
            source_provider="data_go_legal_dong",
            source_status="active",
            source_file_name="국토교통부_전국 법정동_20250807.csv",
            source_year_month="202508",
            source_file_hash="fixture",
            is_discontinued=False,
            is_active=True,
        )
    )
    db_session.flush()
    zip_path = _write_boundary_zip(
        tmp_path,
        layer_code="N3A_G0010000",
        bjcd="3600000000",
        name="세종특별자치시",
        divi="HJD005",
        scls="G0018112",
    )

    result = load_vworld_boundary_zip(db_session, zip_path)
    db_session.commit()

    serving = db_session.scalar(select(RegionServingBoundary))
    assert result.address_code_match_count == 1
    assert serving is not None
    assert serving.address_code_standard_code == "3611000000"


def test_vworld_boundary_loader_rejects_unknown_zip_name(
    db_session: Session,
    tmp_path: Path,
) -> None:
    zip_path = tmp_path / "unknown.zip"
    with zipfile.ZipFile(zip_path, "w"):
        pass

    try:
        load_vworld_boundary_zip(db_session, zip_path)
    except ValueError as exc:
        assert "Unsupported VWorld boundary ZIP name" in str(exc)
    else:
        raise AssertionError("Expected unsupported ZIP name to fail.")


def test_vworld_boundary_loader_rejects_zip_path_traversal(
    db_session: Session,
    tmp_path: Path,
) -> None:
    zip_path = tmp_path / "N3A_G0110000.zip"
    escaped_path = tmp_path.parent / "N3A_G0110000.shp"
    if escaped_path.exists():
        escaped_path.unlink()
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../N3A_G0110000.shp", "not a shapefile")

    with pytest.raises(ValueError, match="Unsafe ZIP member path"):
        load_vworld_boundary_zip(db_session, zip_path)

    assert not escaped_path.exists()


def _add_address_code(db_session: Session) -> None:
    db_session.add(
        AddressCodeStandard(
            legal_dong_code="1111010100",
            code_level="legal_dong",
            code_name="서울특별시 종로구 청운동",
            sido_code="1100000000",
            sigungu_code="1111000000",
            sido_name="서울특별시",
            sigungu_name="종로구",
            legal_eupmyeondong_name="청운동",
            legal_ri_name=None,
            full_legal_dong_name="서울특별시 종로구 청운동",
            source_effective_date="20240101",
            source_change_reason_code="00",
            source_provider="fixture",
            source_status="존재",
            source_file_name="fixture.txt",
            source_year_month="202401",
            source_file_hash="fixture",
            is_discontinued=False,
            is_active=True,
        )
    )
    db_session.flush()


def _write_boundary_zip(
    tmp_path: Path,
    *,
    layer_code: str,
    bjcd: str,
    name: str,
    divi: str,
    scls: str,
) -> Path:
    shapefile_dir = tmp_path / layer_code
    shapefile_dir.mkdir()
    shapefile_base = shapefile_dir / layer_code
    writer = shapefile.Writer(
        str(shapefile_base),
        shapeType=shapefile.POLYGON,
        encoding="cp949",
    )
    writer.field("UFID", "C", size=34)
    writer.field("BJCD", "C", size=10)
    writer.field("NAME", "C", size=100)
    writer.field("DIVI", "C", size=20)
    writer.field("SCLS", "C", size=8)
    writer.field("FMTA", "C", size=9)
    writer.record("100037608069G01110100000000000001", bjcd, name, divi, scls, "R23120001")
    writer.poly([_projected_square()])
    writer.close()
    shapefile_base.with_suffix(".prj").write_text(KOREA_UNIFIED_PRJ, encoding="utf-8")

    zip_path = tmp_path / f"{layer_code}.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for suffix in (".shp", ".shx", ".dbf", ".prj"):
            file_path = shapefile_base.with_suffix(suffix)
            archive.write(file_path, arcname=file_path.name)
    return zip_path


def _projected_square() -> list[tuple[float, float]]:
    transformer = Transformer.from_crs(4326, 5179, always_xy=True)
    lon_lat_points = [
        (126.9680, 37.5780),
        (126.9740, 37.5780),
        (126.9740, 37.5830),
        (126.9680, 37.5830),
        (126.9680, 37.5780),
    ]
    return [transformer.transform(longitude, latitude) for longitude, latitude in lon_lat_points]
