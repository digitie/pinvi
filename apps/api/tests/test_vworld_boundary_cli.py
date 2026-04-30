from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import shapefile
from pyproj import Transformer
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.cli.vworld_boundary import import_vworld_boundary_archives
from app.models.address import AddressCodeStandard, RegionServingBoundary
from app.models.etl import AdminNotification, EtlRunLog, TelegramSystemNotificationOutbox

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


def test_import_vworld_boundary_archives_records_etl_log(
    db_session: Session,
    tmp_path: Path,
) -> None:
    session_factory = _build_session_factory(db_session)
    with session_factory() as setup_session:
        _add_address_code(setup_session)
        setup_session.commit()
    zip_path = _write_boundary_zip(tmp_path)

    results = import_vworld_boundary_archives(session_factory, [zip_path])

    with session_factory() as verify_session:
        run_log = verify_session.scalar(select(EtlRunLog))
        serving_boundary_count = verify_session.query(RegionServingBoundary).count()
        assert len(results) == 1
        assert run_log is not None
        assert run_log.dataset_key == "vworld_boundary_upload"
        assert run_log.run_key == "N3A_G0110000"
        assert run_log.status == "success"
        assert serving_boundary_count == 1


def test_import_vworld_boundary_archives_persists_failure_log(
    db_session: Session,
    tmp_path: Path,
) -> None:
    session_factory = _build_session_factory(db_session)
    bad_zip_path = tmp_path / "N3A_G0110000.zip"
    with zipfile.ZipFile(bad_zip_path, "w") as archive:
        archive.writestr("README.txt", "not a shapefile")

    with pytest.raises(ValueError):
        import_vworld_boundary_archives(session_factory, [bad_zip_path])

    with session_factory() as verify_session:
        run_log = verify_session.scalar(select(EtlRunLog))
        admin_notification = verify_session.scalar(select(AdminNotification))
        telegram_outbox = verify_session.scalar(select(TelegramSystemNotificationOutbox))

        assert run_log is not None
        assert run_log.status == "failed"
        assert run_log.dataset_key == "vworld_boundary_upload"
        assert run_log.run_key == "N3A_G0110000"
        assert admin_notification is not None
        assert admin_notification.etl_run_log_id == run_log.id
        assert telegram_outbox is not None
        assert telegram_outbox.etl_run_log_id == run_log.id


def _build_session_factory(db_session: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)


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


def _write_boundary_zip(tmp_path: Path) -> Path:
    layer_code = "N3A_G0110000"
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
    writer.record(
        "100037608069G01110100000000000001",
        "1111010100",
        "청운동",
        "HJD010",
        "G0018117",
        "R23120001",
    )
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
