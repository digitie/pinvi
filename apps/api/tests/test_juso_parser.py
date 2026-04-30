from __future__ import annotations

from pathlib import Path

import pytest

from app.etl.juso.parser import (
    derive_source_year_month,
    parse_juso_related_jibun_file,
    parse_juso_road_address_file,
)


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


def _build_related_jibun_row(**overrides: str) -> str:
    fields = [
        "11110101310001200009400000",  # road_address_management_no
        "1111010100",  # legal_dong_code
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


def test_parse_juso_road_address_file_preserves_string_codes(tmp_path: Path) -> None:
    source_file = tmp_path / "202604_rnaddrkor_sample.txt"
    source_file.write_text(
        "\n".join(
            [
                _build_juso_row(
                    legal_dong_code="0111010100",
                    administrative_dong_code="0111051500",
                ),
                _build_juso_row(
                    road_address_management_no="1111010100100010001",
                    legal_dong_code="0111010200",
                    legal_eupmyeondong_name="Sajik-dong",
                ),
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_juso_road_address_file(source_file)

    assert parsed.source_file_name == source_file.name
    assert parsed.source_year_month == "202604"
    assert parsed.delimiter == "|"
    assert len(parsed.rows) == 2
    assert parsed.rows[0].legal_dong_code == "0111010100"
    assert parsed.rows[0].administrative_dong_code == "0111051500"


def test_parse_juso_road_address_file_detects_tab_delimiter(tmp_path: Path) -> None:
    source_file = tmp_path / "202604_rnaddrkor_tab.txt"
    source_file.write_text(_build_juso_row().replace("|", "\t"), encoding="utf-8")

    parsed = parse_juso_road_address_file(source_file)

    assert parsed.delimiter == "\t"


def test_parse_juso_road_address_file_uses_unknown_effective_date_sentinel(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "202604_rnaddrkor_blank_effective_date.txt"
    source_file.write_text(_build_juso_row(effective_date=""), encoding="utf-8")

    parsed = parse_juso_road_address_file(source_file)

    assert parsed.rows[0].effective_date == "00000000"


def test_parse_juso_road_address_file_rejects_invalid_field_count(tmp_path: Path) -> None:
    source_file = tmp_path / "202604_rnaddrkor_invalid.txt"
    source_file.write_text("a|b|c", encoding="utf-8")

    with pytest.raises(ValueError, match="delimiter|fields"):
        parse_juso_road_address_file(source_file)


def test_parse_juso_related_jibun_file_preserves_string_codes(tmp_path: Path) -> None:
    source_file = tmp_path / "202604_jibun_rnaddrkor_sample.txt"
    source_file.write_text(
        "\n".join(
            [
                _build_related_jibun_row(legal_dong_code="0111010100"),
                _build_related_jibun_row(
                    road_address_management_no="1111010200100010000",
                    legal_dong_code="0111010200",
                    legal_eupmyeondong_name="Sajik-dong",
                ),
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_juso_related_jibun_file(source_file)

    assert parsed.source_file_name == source_file.name
    assert parsed.source_year_month == "202604"
    assert parsed.delimiter == "|"
    assert len(parsed.rows) == 2
    assert parsed.rows[0].legal_dong_code == "0111010100"
    assert parsed.rows[1].legal_eupmyeondong_name == "Sajik-dong"


def test_parse_juso_related_jibun_file_rejects_invalid_field_count(tmp_path: Path) -> None:
    source_file = tmp_path / "202604_jibun_rnaddrkor_invalid.txt"
    source_file.write_text("a|b|c", encoding="utf-8")

    with pytest.raises(ValueError, match="delimiter|fields"):
        parse_juso_related_jibun_file(source_file)


def test_derive_source_year_month_requires_year_month_in_filename(tmp_path: Path) -> None:
    source_file = tmp_path / "rnaddrkor_sample.txt"
    source_file.write_text(_build_juso_row(), encoding="utf-8")

    with pytest.raises(ValueError, match="source year-month"):
        derive_source_year_month(source_file)
