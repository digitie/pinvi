from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.etl.juso.legal_dong_loader import load_juso_legal_dong_codes
from app.models.address import AddressCodeStandard, AddressRawJusoRoadAddress


def _build_juso_row(**overrides: str) -> str:
    fields = [
        "1111010100100010000",  # road_address_management_no
        "1111010100",  # legal_dong_code
        "서울특별시",
        "종로구",
        "청운동",
        "",
        "0",
        "1",
        "0",
        "111100000001",
        "자하문로",
        "0",
        "10",
        "0",
        "1111051500",
        "청운효자동",
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
                    legal_eupmyeondong_name="청운동",
                    effective_date="20260410",
                ),
                _build_juso_row(
                    road_address_management_no="1111010100100010001",
                    legal_dong_code="0111010100",
                    administrative_dong_code="0111051500",
                    legal_eupmyeondong_name="청운동",
                    effective_date="20260411",
                ),
                _build_juso_row(
                    road_address_management_no="1111010200100010000",
                    legal_dong_code="0111010200",
                    administrative_dong_code="0111051500",
                    legal_eupmyeondong_name="신교동",
                    effective_date="20260410",
                ),
                _build_juso_row(
                    road_address_management_no="1111010300100010000",
                    legal_dong_code="0111010300",
                    administrative_dong_code="0111051500",
                    legal_eupmyeondong_name="궁정동",
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

    assert result.raw_row_count == 4
    assert result.raw_rows_inserted == 4
    assert result.legal_dong_code_count == 2
    assert len(raw_rows) == 4
    assert [row.legal_dong_code for row in legal_dong_rows] == ["0111010100", "0111010200"]
    assert legal_dong_rows[0].full_legal_dong_name == "서울특별시 종로구 청운동"
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
                    legal_eupmyeondong_name="청운동",
                ),
                _build_juso_row(
                    road_address_management_no="1111010200100010000",
                    legal_dong_code="0111010200",
                    legal_eupmyeondong_name="신교동",
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
                    legal_eupmyeondong_name="청운동",
                ),
                _build_juso_row(
                    road_address_management_no="1111010100100010001",
                    legal_dong_code="0111010100",
                    legal_eupmyeondong_name="신문로1가",
                ),
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Conflicting legal dong names"):
        load_juso_legal_dong_codes(db_session, source_file)
