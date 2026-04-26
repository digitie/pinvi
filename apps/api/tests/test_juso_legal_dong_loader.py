from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.etl.juso.legal_dong_loader import (
    load_juso_legal_dong_codes,
    load_juso_legal_dong_codes_from_files,
)
from app.models.address import AddressCodeStandard, AddressRawJusoRoadAddress


def _build_juso_row(**overrides: str) -> str:
    fields = [
        "1111010100100010000",  # road_address_management_no
        "1111010100",  # legal_dong_code
        "Seoul",
        "Jongno-gu",
        "Cheongun-dong",
        "",
        "0",
        "1",
        "0",
        "111100000001",
        "Pirundae-ro",
        "0",
        "10",
        "0",
        "1111051500",
        "Cheongunhyoja-dong",
        "03001",
        "",
        "20260410",
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


def test_load_juso_legal_dong_codes_ingests_raw_rows_and_rebuilds_code_table(
    db_session: Session,
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "202604_rnaddrkor_sample.txt"
    source_file.write_text(
        "\n".join(
            [
                _build_juso_row(
                    road_address_management_no="1111010100100010000",
                    legal_dong_code="0111010100",
                    administrative_dong_code="0111051500",
                    legal_eupmyeondong_name="Cheongun-dong",
                    effective_date="20260410",
                ),
                _build_juso_row(
                    road_address_management_no="1111010100100010001",
                    legal_dong_code="0111010100",
                    administrative_dong_code="0111051500",
                    legal_eupmyeondong_name="Cheongun-dong",
                    effective_date="20260411",
                ),
                _build_juso_row(
                    road_address_management_no="1111010200100010000",
                    legal_dong_code="0111010200",
                    administrative_dong_code="0111051500",
                    legal_eupmyeondong_name="Sajik-dong",
                    effective_date="20260410",
                ),
                _build_juso_row(
                    road_address_management_no="1111010300100010000",
                    legal_dong_code="0111010300",
                    administrative_dong_code="0111051500",
                    legal_eupmyeondong_name="Gwanghwamun-dong",
                    change_reason_code="63",
                    effective_date="20260410",
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = load_juso_legal_dong_codes(db_session, source_file)
    db_session.commit()

    raw_rows = db_session.scalars(
        select(AddressRawJusoRoadAddress).order_by(AddressRawJusoRoadAddress.row_number)
    ).all()
    legal_dong_rows = db_session.scalars(
        select(AddressCodeStandard).order_by(AddressCodeStandard.legal_dong_code)
    ).all()

    assert result.source_part_count == 1
    assert result.raw_row_count == 4
    assert result.raw_rows_inserted == 4
    assert result.legal_dong_code_count == 2
    assert len(raw_rows) == 4
    assert [row.legal_dong_code for row in legal_dong_rows] == ["0111010100", "0111010200"]
    assert legal_dong_rows[0].full_legal_dong_name == "Seoul Jongno-gu Cheongun-dong"
    assert legal_dong_rows[0].source_effective_date == "20260411"


def test_load_juso_legal_dong_codes_is_idempotent_for_the_same_file(
    db_session: Session,
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "202604_rnaddrkor_sample.txt"
    source_file.write_text(
        "\n".join(
            [
                _build_juso_row(
                    road_address_management_no="1111010100100010000",
                    legal_dong_code="0111010100",
                    legal_eupmyeondong_name="Cheongun-dong",
                ),
                _build_juso_row(
                    road_address_management_no="1111010200100010000",
                    legal_dong_code="0111010200",
                    legal_eupmyeondong_name="Sajik-dong",
                ),
            ]
        ),
        encoding="utf-8",
    )

    first_result = load_juso_legal_dong_codes(db_session, source_file)
    db_session.commit()

    second_result = load_juso_legal_dong_codes(db_session, source_file)
    db_session.commit()

    raw_row_count = db_session.query(AddressRawJusoRoadAddress).count()
    legal_dong_count = db_session.query(AddressCodeStandard).count()

    assert first_result.raw_rows_inserted == 2
    assert second_result.raw_rows_inserted == 0
    assert raw_row_count == 2
    assert legal_dong_count == 2


def test_load_juso_legal_dong_codes_rejects_conflicting_names_for_same_code(
    db_session: Session,
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "202604_rnaddrkor_conflict.txt"
    source_file.write_text(
        "\n".join(
            [
                _build_juso_row(
                    road_address_management_no="1111010100100010000",
                    legal_dong_code="0111010100",
                    legal_eupmyeondong_name="Cheongun-dong",
                ),
                _build_juso_row(
                    road_address_management_no="1111010100100010001",
                    legal_dong_code="0111010100",
                    legal_eupmyeondong_name="Tongin-dong",
                ),
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Conflicting legal dong names"):
        load_juso_legal_dong_codes(db_session, source_file)


def test_load_juso_legal_dong_codes_from_files_merges_multiple_region_files(
    db_session: Session,
    tmp_path: Path,
) -> None:
    seoul_file = tmp_path / "rnaddrkor_seoul.txt"
    seoul_file.write_text(
        "\n".join(
            [
                _build_juso_row(
                    road_address_management_no="1111010100100010000",
                    legal_dong_code="0111010100",
                    legal_eupmyeondong_name="Cheongun-dong",
                ),
                _build_juso_row(
                    road_address_management_no="1111010200100010000",
                    legal_dong_code="0111010200",
                    legal_eupmyeondong_name="Sajik-dong",
                ),
            ]
        ),
        encoding="utf-8",
    )
    busan_file = tmp_path / "rnaddrkor_busan.txt"
    busan_file.write_text(
        "\n".join(
            [
                _build_juso_row(
                    road_address_management_no="2611010100100010000",
                    legal_dong_code="2611010100",
                    sido_name="Busan",
                    sigungu_name="Jung-gu",
                    legal_eupmyeondong_name="Donggwang-dong",
                    administrative_dong_code="2611051500",
                    administrative_dong_name="Donggwang-dong",
                    road_name_code="261100000001",
                ),
            ]
        ),
        encoding="utf-8",
    )

    snapshot_hash = sha256(seoul_file.read_bytes() + busan_file.read_bytes()).hexdigest()
    result = load_juso_legal_dong_codes_from_files(
        db_session,
        [seoul_file, busan_file],
        source_year_month="202603",
        source_file_name="202603_도로명주소 한글_전체분.zip",
        source_file_hash=snapshot_hash,
    )
    db_session.commit()

    raw_rows = db_session.scalars(
        select(AddressRawJusoRoadAddress).order_by(
            AddressRawJusoRoadAddress.source_file_name,
            AddressRawJusoRoadAddress.row_number,
        )
    ).all()
    legal_dong_rows = db_session.scalars(
        select(AddressCodeStandard).order_by(AddressCodeStandard.legal_dong_code)
    ).all()

    assert result.source_part_count == 2
    assert result.raw_row_count == 3
    assert result.raw_rows_inserted == 3
    assert result.legal_dong_code_count == 3
    assert len(raw_rows) == 3
    assert [row.source_file_name for row in raw_rows] == [
        "rnaddrkor_busan.txt",
        "rnaddrkor_seoul.txt",
        "rnaddrkor_seoul.txt",
    ]
    assert [row.legal_dong_code for row in legal_dong_rows] == [
        "0111010100",
        "0111010200",
        "2611010100",
    ]
    assert {row.source_file_name for row in legal_dong_rows} == {
        "202603_도로명주소 한글_전체분.zip"
    }
    assert {row.source_file_hash for row in legal_dong_rows} == {snapshot_hash}
