from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

JUSO_ROAD_ADDRESS_FIELD_COUNT = 24
JUSO_DELIMITER_CANDIDATES = ("|", "\t")
SOURCE_YEAR_MONTH_PATTERN = re.compile(r"(?P<year_month>\d{6})")


def _clean(value: str) -> str:
    return value.strip()


def _clean_optional(value: str) -> str | None:
    cleaned = _clean(value)
    return cleaned or None


def _decode_juso_bytes(raw_bytes: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return raw_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError("juso", b"", 0, 1, "unable to decode Juso address file")


def _detect_delimiter(line: str) -> str:
    matched_delimiters = [
        delimiter
        for delimiter in JUSO_DELIMITER_CANDIDATES
        if len(line.split(delimiter)) == JUSO_ROAD_ADDRESS_FIELD_COUNT
    ]

    if len(matched_delimiters) != 1:
        raise ValueError("Unable to detect Juso delimiter from the first non-empty line.")

    return matched_delimiters[0]


def derive_source_year_month(path: Path) -> str:
    match = SOURCE_YEAR_MONTH_PATTERN.search(path.name)
    if match is None:
        raise ValueError(f"Unable to derive source year-month from file name: {path.name}")

    return match.group("year_month")


@dataclass(frozen=True)
class JusoRoadAddressRecord:
    road_address_management_no: str
    legal_dong_code: str
    sido_name: str
    sigungu_name: str
    legal_eupmyeondong_name: str
    legal_ri_name: str | None
    mountain_yn: str
    jibun_main_no: str
    jibun_sub_no: str
    road_name_code: str
    road_name: str
    underground_yn: str
    building_main_no: str
    building_sub_no: str
    administrative_dong_code: str | None
    administrative_dong_name: str | None
    postal_code: str | None
    previous_road_address: str | None
    effective_date: str
    apartment_yn: str | None
    change_reason_code: str
    building_registry_name: str | None
    sigungu_building_name: str | None
    note: str | None
    raw_line: str

    @classmethod
    def from_line(cls, line: str, *, delimiter: str) -> JusoRoadAddressRecord:
        fields = line.split(delimiter)
        if len(fields) != JUSO_ROAD_ADDRESS_FIELD_COUNT:
            raise ValueError(
                f"Expected {JUSO_ROAD_ADDRESS_FIELD_COUNT} fields, got {len(fields)} fields."
            )

        return cls(
            road_address_management_no=_clean(fields[0]),
            legal_dong_code=_clean(fields[1]),
            sido_name=_clean(fields[2]),
            sigungu_name=_clean(fields[3]),
            legal_eupmyeondong_name=_clean(fields[4]),
            legal_ri_name=_clean_optional(fields[5]),
            mountain_yn=_clean(fields[6]),
            jibun_main_no=_clean(fields[7]),
            jibun_sub_no=_clean(fields[8]),
            road_name_code=_clean(fields[9]),
            road_name=_clean(fields[10]),
            underground_yn=_clean(fields[11]),
            building_main_no=_clean(fields[12]),
            building_sub_no=_clean(fields[13]),
            administrative_dong_code=_clean_optional(fields[14]),
            administrative_dong_name=_clean_optional(fields[15]),
            postal_code=_clean_optional(fields[16]),
            previous_road_address=_clean_optional(fields[17]),
            effective_date=_clean(fields[18]),
            apartment_yn=_clean_optional(fields[19]),
            change_reason_code=_clean(fields[20]),
            building_registry_name=_clean_optional(fields[21]),
            sigungu_building_name=_clean_optional(fields[22]),
            note=_clean_optional(fields[23]),
            raw_line=line,
        )


@dataclass(frozen=True)
class ParsedJusoRoadAddressFile:
    source_path: Path
    source_file_name: str
    source_year_month: str
    file_hash: str
    encoding: str
    delimiter: str
    rows: list[JusoRoadAddressRecord]


def parse_juso_road_address_file(
    path: Path | str,
    *,
    source_year_month: str | None = None,
) -> ParsedJusoRoadAddressFile:
    source_path = Path(path)
    raw_bytes = source_path.read_bytes()
    decoded_text, encoding = _decode_juso_bytes(raw_bytes)
    file_hash = sha256(raw_bytes).hexdigest()

    lines = [line.rstrip("\r") for line in decoded_text.splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"Juso address file is empty: {source_path}")

    delimiter = _detect_delimiter(lines[0])
    rows = [JusoRoadAddressRecord.from_line(line, delimiter=delimiter) for line in lines]

    return ParsedJusoRoadAddressFile(
        source_path=source_path,
        source_file_name=source_path.name,
        source_year_month=source_year_month or derive_source_year_month(source_path),
        file_hash=file_hash,
        encoding=encoding,
        delimiter=delimiter,
        rows=rows,
    )
