from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.etl.juso.legal_dong_loader import (
    DISCONTINUED_CHANGE_REASON_CODE,
    _build_full_legal_dong_name,
    _build_legal_dong_snapshots,
    _validate_record,
    upsert_address_code_snapshots_from_juso,
)
from app.etl.juso.parser import (
    JusoRoadAddressRecord,
    ParsedJusoRoadAddressFile,
    parse_juso_road_address_file,
)
from app.models.address import (
    AddressRawJusoRoadAddress,
    AddressServingJusoRoadAddress,
)


@dataclass(frozen=True)
class JusoRoadAddressLoadResult:
    source_file_name: str
    source_year_month: str
    source_file_hash: str
    source_part_count: int
    raw_row_count: int
    raw_rows_inserted: int
    active_road_address_count: int
    legal_dong_code_count: int


@dataclass(frozen=True)
class _RoadAddressSnapshot:
    road_address_management_no: str
    legal_dong_code: str
    road_name_code: str
    administrative_dong_code: str | None
    sido_name: str
    sigungu_name: str
    legal_eupmyeondong_name: str
    legal_ri_name: str | None
    road_name: str
    administrative_dong_name: str | None
    mountain_yn: str
    jibun_main_no: str
    jibun_sub_no: str
    underground_yn: str
    building_main_no: str
    building_sub_no: str
    postal_code: str | None
    previous_road_address: str | None
    apartment_yn: str | None
    building_registry_name: str | None
    sigungu_building_name: str | None
    note: str | None
    full_legal_dong_name: str
    full_road_address: str
    source_effective_date: str
    source_change_reason_code: str


def load_juso_road_address_snapshot(
    session: Session,
    file_path: Path | str,
    *,
    source_year_month: str | None = None,
) -> JusoRoadAddressLoadResult:
    parsed_file = parse_juso_road_address_file(file_path, source_year_month=source_year_month)
    return load_juso_road_address_snapshot_from_files(
        session,
        [parsed_file.source_path],
        source_year_month=parsed_file.source_year_month,
        source_file_name=parsed_file.source_file_name,
        source_file_hash=parsed_file.file_hash,
    )


def load_juso_road_address_snapshot_from_files(
    session: Session,
    file_paths: Sequence[Path | str],
    *,
    source_year_month: str,
    source_file_name: str,
    source_file_hash: str,
) -> JusoRoadAddressLoadResult:
    parsed_files = [
        parse_juso_road_address_file(file_path, source_year_month=source_year_month)
        for file_path in file_paths
    ]
    return _load_juso_road_address_snapshot_files(
        session,
        parsed_files,
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
    )


def _load_juso_road_address_snapshot_files(
    session: Session,
    parsed_files: Sequence[ParsedJusoRoadAddressFile],
    *,
    source_file_name: str,
    source_year_month: str,
    source_file_hash: str,
) -> JusoRoadAddressLoadResult:
    if not parsed_files:
        raise ValueError("At least one Juso road-address file is required.")

    raw_rows_inserted = 0
    all_records: list[JusoRoadAddressRecord] = []
    for parsed_file in parsed_files:
        if parsed_file.source_year_month != source_year_month:
            raise ValueError(
                "All Juso road-address files must share the same source year-month. "
                f"Expected {source_year_month}, got {parsed_file.source_year_month}."
            )

        existing_raw_row_count = session.scalar(
            select(func.count())
            .select_from(AddressRawJusoRoadAddress)
            .where(AddressRawJusoRoadAddress.source_file_hash == parsed_file.file_hash)
        )
        if existing_raw_row_count not in (0, len(parsed_file.rows)):
            raise RuntimeError(
                f"Partial raw ingest detected for Juso source file hash {parsed_file.file_hash}."
            )

        if existing_raw_row_count == 0:
            session.add_all(
                [
                    AddressRawJusoRoadAddress(
                        source_file_name=parsed_file.source_file_name,
                        source_year_month=parsed_file.source_year_month,
                        source_file_hash=parsed_file.file_hash,
                        row_number=row_number,
                        delimiter="pipe" if parsed_file.delimiter == "|" else "tab",
                        road_address_management_no=record.road_address_management_no,
                        legal_dong_code=record.legal_dong_code,
                        road_name_code=record.road_name_code,
                        administrative_dong_code=record.administrative_dong_code,
                        effective_date=record.effective_date,
                        change_reason_code=record.change_reason_code,
                        raw_line=record.raw_line,
                    )
                    for row_number, record in enumerate(parsed_file.rows, start=1)
                ]
            )
            raw_rows_inserted += len(parsed_file.rows)

        all_records.extend(parsed_file.rows)

    road_address_snapshots = _build_road_address_snapshots(all_records)
    legal_dong_snapshots = _build_legal_dong_snapshots(all_records)

    session.execute(delete(AddressServingJusoRoadAddress))
    session.add_all(
        [
            AddressServingJusoRoadAddress(
                road_address_management_no=snapshot.road_address_management_no,
                legal_dong_code=snapshot.legal_dong_code,
                road_name_code=snapshot.road_name_code,
                administrative_dong_code=snapshot.administrative_dong_code,
                sido_name=snapshot.sido_name,
                sigungu_name=snapshot.sigungu_name,
                legal_eupmyeondong_name=snapshot.legal_eupmyeondong_name,
                legal_ri_name=snapshot.legal_ri_name,
                road_name=snapshot.road_name,
                administrative_dong_name=snapshot.administrative_dong_name,
                mountain_yn=snapshot.mountain_yn,
                jibun_main_no=snapshot.jibun_main_no,
                jibun_sub_no=snapshot.jibun_sub_no,
                underground_yn=snapshot.underground_yn,
                building_main_no=snapshot.building_main_no,
                building_sub_no=snapshot.building_sub_no,
                postal_code=snapshot.postal_code,
                previous_road_address=snapshot.previous_road_address,
                apartment_yn=snapshot.apartment_yn,
                building_registry_name=snapshot.building_registry_name,
                sigungu_building_name=snapshot.sigungu_building_name,
                note=snapshot.note,
                full_legal_dong_name=snapshot.full_legal_dong_name,
                full_road_address=snapshot.full_road_address,
                source_effective_date=snapshot.source_effective_date,
                source_change_reason_code=snapshot.source_change_reason_code,
                source_file_name=source_file_name,
                source_year_month=source_year_month,
                source_file_hash=source_file_hash,
                is_active=True,
            )
            for snapshot in road_address_snapshots
        ]
    )

    upsert_address_code_snapshots_from_juso(
        session,
        legal_dong_snapshots,
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
    )
    session.flush()

    return JusoRoadAddressLoadResult(
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
        source_part_count=len(parsed_files),
        raw_row_count=len(all_records),
        raw_rows_inserted=raw_rows_inserted,
        active_road_address_count=len(road_address_snapshots),
        legal_dong_code_count=len(legal_dong_snapshots),
    )


def _build_road_address_snapshots(
    records: list[JusoRoadAddressRecord],
) -> list[_RoadAddressSnapshot]:
    snapshots: dict[str, _RoadAddressSnapshot] = {}

    for row_number, record in enumerate(records, start=1):
        _validate_record(record, row_number)

        if record.change_reason_code == DISCONTINUED_CHANGE_REASON_CODE:
            continue

        candidate = _RoadAddressSnapshot(
            road_address_management_no=record.road_address_management_no,
            legal_dong_code=record.legal_dong_code,
            road_name_code=record.road_name_code,
            administrative_dong_code=record.administrative_dong_code,
            sido_name=record.sido_name,
            sigungu_name=record.sigungu_name,
            legal_eupmyeondong_name=record.legal_eupmyeondong_name,
            legal_ri_name=record.legal_ri_name,
            road_name=record.road_name,
            administrative_dong_name=record.administrative_dong_name,
            mountain_yn=record.mountain_yn,
            jibun_main_no=record.jibun_main_no,
            jibun_sub_no=record.jibun_sub_no,
            underground_yn=record.underground_yn,
            building_main_no=record.building_main_no,
            building_sub_no=record.building_sub_no,
            postal_code=record.postal_code,
            previous_road_address=record.previous_road_address,
            apartment_yn=record.apartment_yn,
            building_registry_name=record.building_registry_name,
            sigungu_building_name=record.sigungu_building_name,
            note=record.note,
            full_legal_dong_name=_build_full_legal_dong_name(record),
            full_road_address=_build_full_road_address(record),
            source_effective_date=record.effective_date,
            source_change_reason_code=record.change_reason_code,
        )

        existing = snapshots.get(candidate.road_address_management_no)
        if existing is None:
            snapshots[candidate.road_address_management_no] = candidate
            continue

        if candidate.source_effective_date > existing.source_effective_date:
            snapshots[candidate.road_address_management_no] = candidate
            continue

        if (
            candidate.source_effective_date == existing.source_effective_date
            and candidate != existing
        ):
            raise ValueError(
                f"Conflicting road-address rows found for {candidate.road_address_management_no}."
            )

    return sorted(snapshots.values(), key=lambda snapshot: snapshot.road_address_management_no)


def _build_full_road_address(record: JusoRoadAddressRecord) -> str:
    building_no = record.building_main_no
    if record.building_sub_no and record.building_sub_no != "0":
        building_no = f"{building_no}-{record.building_sub_no}"

    building_tokens: list[str] = []
    if record.underground_yn == "1":
        building_tokens.append("지하")
    building_tokens.append(building_no)

    return " ".join(
        [
            record.sido_name,
            record.sigungu_name,
            record.road_name,
            *building_tokens,
        ]
    )
