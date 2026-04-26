from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.etl.juso.related_jibun_loader import load_juso_related_jibun_from_files
from app.etl.juso.road_address_loader import load_juso_road_address_snapshot_from_files
from app.models.address import (
    AddressCodeStandard,
    AddressRawJusoRelatedJibun,
    AddressRawJusoRoadAddress,
    AddressServingJusoRelatedJibun,
    AddressServingJusoRoadAddress,
)


def _build_juso_row(**overrides: str) -> str:
    fields = [
        "11110101310001200009400000",
        "1111010100",
        "Seoul",
        "Jongno-gu",
        "Cheongun-dong",
        "",
        "0",
        "144",
        "3",
        "111103100012",
        "Pirundae-ro",
        "0",
        "94",
        "0",
        "1111051500",
        "Cheongunhyoja-dong",
        "03047",
        "",
        "20110729",
        "0",
        "31",
        "",
        "",
        "",
    ]

    field_by_name = {
        "road_address_management_no": 0,
        "legal_dong_code": 1,
        "sido_name": 2,
        "sigungu_name": 3,
        "legal_eupmyeondong_name": 4,
        "legal_ri_name": 5,
        "mountain_yn": 6,
        "jibun_main_no": 7,
        "jibun_sub_no": 8,
        "road_name_code": 9,
        "road_name": 10,
        "underground_yn": 11,
        "building_main_no": 12,
        "building_sub_no": 13,
        "administrative_dong_code": 14,
        "administrative_dong_name": 15,
        "postal_code": 16,
        "previous_road_address": 17,
        "effective_date": 18,
        "apartment_yn": 19,
        "change_reason_code": 20,
        "building_registry_name": 21,
        "sigungu_building_name": 22,
        "note": 23,
    }

    for key, value in overrides.items():
        fields[field_by_name[key]] = value

    return "|".join(fields)


def _build_related_jibun_row(**overrides: str) -> str:
    fields = [
        "11110101310001200009400000",
        "1111010100",
        "Seoul",
        "Jongno-gu",
        "Cheongun-dong",
        "",
        "0",
        "144",
        "3",
        "111103100012",
        "0",
        "94",
        "0",
        "",
    ]

    field_by_name = {
        "road_address_management_no": 0,
        "legal_dong_code": 1,
        "sido_name": 2,
        "sigungu_name": 3,
        "legal_eupmyeondong_name": 4,
        "legal_ri_name": 5,
        "mountain_yn": 6,
        "jibun_main_no": 7,
        "jibun_sub_no": 8,
        "road_name_code": 9,
        "underground_yn": 10,
        "building_main_no": 11,
        "building_sub_no": 12,
        "note": 13,
    }

    for key, value in overrides.items():
        fields[field_by_name[key]] = value

    return "|".join(fields)


def test_load_juso_road_address_snapshot_from_files_rebuilds_serving_tables(
    db_session: Session,
    tmp_path: Path,
) -> None:
    seoul_file = tmp_path / "rnaddrkor_seoul.txt"
    seoul_file.write_text(
        "\n".join(
            [
                _build_juso_row(),
                _build_juso_row(
                    road_address_management_no="11110119200500100014900000",
                    legal_dong_code="1111012000",
                    legal_eupmyeondong_name="Sinmunno 1-ga",
                    road_name_code="111102005001",
                    road_name="Sajik-ro 8-gil",
                    building_main_no="149",
                ),
            ]
        ),
        encoding="utf-8",
    )
    busan_file = tmp_path / "rnaddrkor_busan.txt"
    busan_file.write_text(
        _build_juso_row(
            road_address_management_no="26110101001000100009400000",
            legal_dong_code="2611010100",
            sido_name="Busan",
            sigungu_name="Jung-gu",
            legal_eupmyeondong_name="Donggwang-dong",
            administrative_dong_code="2611051500",
            administrative_dong_name="Donggwang-dong",
            road_name_code="261103100012",
        ),
        encoding="utf-8",
    )

    snapshot_hash = sha256(seoul_file.read_bytes() + busan_file.read_bytes()).hexdigest()
    result = load_juso_road_address_snapshot_from_files(
        db_session,
        [seoul_file, busan_file],
        source_year_month="202603",
        source_file_name="202603_도로명주소 한글_전체분.zip",
        source_file_hash=snapshot_hash,
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(AddressRawJusoRoadAddress)).all()
    serving_rows = db_session.scalars(
        select(AddressServingJusoRoadAddress).order_by(
            AddressServingJusoRoadAddress.road_address_management_no
        )
    ).all()
    code_rows = db_session.scalars(
        select(AddressCodeStandard).order_by(AddressCodeStandard.legal_dong_code)
    ).all()

    assert result.source_part_count == 2
    assert result.raw_row_count == 3
    assert result.raw_rows_inserted == 3
    assert result.active_road_address_count == 3
    assert result.legal_dong_code_count == 3
    assert len(raw_rows) == 3
    assert len(serving_rows) == 3
    assert len(code_rows) == 3
    assert serving_rows[0].full_road_address.endswith("94")
    assert {row.source_file_name for row in serving_rows} == {"202603_도로명주소 한글_전체분.zip"}


def test_load_juso_related_jibun_from_files_rebuilds_serving_relations(
    db_session: Session,
    tmp_path: Path,
) -> None:
    road_file = tmp_path / "rnaddrkor_seoul.txt"
    road_file.write_text(
        "\n".join(
            [
                _build_juso_row(),
                _build_juso_row(
                    road_address_management_no="11110119200500100014900000",
                    legal_dong_code="1111012000",
                    legal_eupmyeondong_name="Sinmunno 1-ga",
                    road_name_code="111102005001",
                    road_name="Sajik-ro 8-gil",
                    building_main_no="149",
                ),
            ]
        ),
        encoding="utf-8",
    )
    road_snapshot_hash = sha256(road_file.read_bytes()).hexdigest()
    load_juso_road_address_snapshot_from_files(
        db_session,
        [road_file],
        source_year_month="202603",
        source_file_name="202603_도로명주소 한글_전체분.zip",
        source_file_hash=road_snapshot_hash,
    )

    related_file = tmp_path / "jibun_rnaddrkor_seoul.txt"
    related_file.write_text(
        "\n".join(
            [
                _build_related_jibun_row(),
                _build_related_jibun_row(
                    road_address_management_no="11110119200500100014900000",
                    legal_dong_code="1111012000",
                    legal_eupmyeondong_name="Sinmunno 1-ga",
                    jibun_main_no="150",
                ),
            ]
        ),
        encoding="utf-8",
    )

    related_snapshot_hash = sha256(related_file.read_bytes()).hexdigest()
    result = load_juso_related_jibun_from_files(
        db_session,
        [related_file],
        source_year_month="202603",
        source_file_name="202603_도로명주소 한글_전체분.zip",
        source_file_hash=related_snapshot_hash,
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(AddressRawJusoRelatedJibun)).all()
    serving_rows = db_session.scalars(
        select(AddressServingJusoRelatedJibun).order_by(
            AddressServingJusoRelatedJibun.full_jibun_address
        )
    ).all()

    assert result.source_part_count == 1
    assert result.raw_row_count == 2
    assert result.raw_rows_inserted == 2
    assert result.active_related_jibun_count == 2
    assert len(raw_rows) == 2
    assert len(serving_rows) == 2
    assert serving_rows[0].road_address_management_no in {
        "11110101310001200009400000",
        "11110119200500100014900000",
    }
    assert "Jongno-gu" in serving_rows[0].full_jibun_address


def test_load_juso_related_jibun_from_files_rejects_unknown_road_address_management_no(
    db_session: Session,
    tmp_path: Path,
) -> None:
    related_file = tmp_path / "jibun_rnaddrkor_seoul.txt"
    related_file.write_text(_build_related_jibun_row(), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown road_address_management_no"):
        load_juso_related_jibun_from_files(
            db_session,
            [related_file],
            source_year_month="202603",
            source_file_name="202603_도로명주소 한글_전체분.zip",
            source_file_hash=sha256(related_file.read_bytes()).hexdigest(),
        )
