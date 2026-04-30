from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.etl.juso.legal_dong_loader import (
    DISCONTINUED_CHANGE_REASON_CODE,
    _build_full_legal_dong_name,
    _derive_sido_code,
    _derive_sigungu_code,
    _LegalDongSnapshot,
    _validate_record,
    upsert_address_code_snapshots_from_juso,
)
from app.etl.juso.parser import (
    InspectedJusoFile,
    JusoRoadAddressRecord,
    ParsedJusoRoadAddressFile,
    inspect_juso_road_address_file,
    iter_juso_road_address_records,
    parse_juso_road_address_file,
)
from app.models.address import (
    AddressRawJusoRoadAddress,
    AddressServingJusoRoadAddress,
)

JUSO_RAW_INSERT_BATCH_SIZE = 3000
JUSO_SERVING_UPSERT_BATCH_SIZE = 1000
JUSO_INSERT_BATCH_SIZE = JUSO_RAW_INSERT_BATCH_SIZE


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
    inspected_files = [
        inspect_juso_road_address_file(file_path, source_year_month=source_year_month)
        for file_path in file_paths
    ]
    return _load_juso_road_address_snapshot_file_streams(
        session,
        inspected_files,
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
    inspected_files = [
        InspectedJusoFile(
            source_path=parsed_file.source_path,
            source_file_name=parsed_file.source_file_name,
            source_year_month=parsed_file.source_year_month,
            file_hash=parsed_file.file_hash,
            encoding=parsed_file.encoding,
            delimiter=parsed_file.delimiter,
            row_count=len(parsed_file.rows),
        )
        for parsed_file in parsed_files
    ]
    return _load_juso_road_address_records(
        session,
        inspected_files,
        record_sources=[
            list(enumerate(parsed_file.rows, start=1)) for parsed_file in parsed_files
        ],
        serving_record_sources=[
            list(enumerate(parsed_file.rows, start=1)) for parsed_file in parsed_files
        ],
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
    )


def _load_juso_road_address_snapshot_file_streams(
    session: Session,
    inspected_files: Sequence[InspectedJusoFile],
    *,
    source_file_name: str,
    source_year_month: str,
    source_file_hash: str,
) -> JusoRoadAddressLoadResult:
    record_sources = [
        iter_juso_road_address_records(
            inspected.source_path,
            encoding=inspected.encoding,
            delimiter=inspected.delimiter,
        )
        for inspected in inspected_files
    ]
    return _load_juso_road_address_records(
        session,
        inspected_files,
        record_sources=record_sources,
        serving_record_sources=[
            iter_juso_road_address_records(
                inspected.source_path,
                encoding=inspected.encoding,
                delimiter=inspected.delimiter,
            )
            for inspected in inspected_files
        ],
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
    )


def _load_juso_road_address_records(
    session: Session,
    inspected_files: Sequence[InspectedJusoFile],
    *,
    record_sources: Sequence[Iterable[tuple[int, JusoRoadAddressRecord]]],
    serving_record_sources: Sequence[Iterable[tuple[int, JusoRoadAddressRecord]]],
    source_file_name: str,
    source_year_month: str,
    source_file_hash: str,
) -> JusoRoadAddressLoadResult:
    if not inspected_files:
        raise ValueError("At least one Juso road-address file is required.")

    raw_rows_inserted = 0
    raw_row_count = 0
    legal_dong_snapshots: dict[str, _LegalDongSnapshot] = {}
    for inspected_file, records in zip(inspected_files, record_sources, strict=True):
        if inspected_file.source_year_month != source_year_month:
            raise ValueError(
                "All Juso road-address files must share the same source year-month. "
                f"Expected {source_year_month}, got {inspected_file.source_year_month}."
            )

        existing_raw_row_count = session.scalar(
            select(func.count())
            .select_from(AddressRawJusoRoadAddress)
            .where(AddressRawJusoRoadAddress.source_file_hash == inspected_file.file_hash)
        )
        if existing_raw_row_count not in (0, inspected_file.row_count):
            raise RuntimeError(
                f"Partial raw ingest detected for Juso source file hash {inspected_file.file_hash}."
            )

        raw_batch: list[dict[str, object]] = []
        if existing_raw_row_count == 0:
            should_insert_raw = True
        else:
            should_insert_raw = False

        for row_number, record in records:
            raw_row_count += 1
            _merge_legal_dong_snapshot(legal_dong_snapshots, record, raw_row_count)
            if not should_insert_raw:
                continue
            raw_batch.append(
                {
                    "source_file_name": inspected_file.source_file_name,
                    "source_year_month": inspected_file.source_year_month,
                    "source_file_hash": inspected_file.file_hash,
                    "row_number": row_number,
                    "delimiter": "pipe" if inspected_file.delimiter == "|" else "tab",
                    "road_address_management_no": record.road_address_management_no,
                    "legal_dong_code": record.legal_dong_code,
                    "road_name_code": record.road_name_code,
                    "administrative_dong_code": record.administrative_dong_code,
                    "effective_date": record.effective_date,
                    "change_reason_code": record.change_reason_code,
                    "raw_line": record.raw_line,
                }
            )
            if len(raw_batch) >= JUSO_RAW_INSERT_BATCH_SIZE:
                session.execute(insert(AddressRawJusoRoadAddress), raw_batch)
                raw_rows_inserted += len(raw_batch)
                raw_batch.clear()
        if raw_batch:
            session.execute(insert(AddressRawJusoRoadAddress), raw_batch)
            raw_rows_inserted += len(raw_batch)

    upsert_address_code_snapshots_from_juso(
        session,
        sorted(legal_dong_snapshots.values(), key=lambda snapshot: snapshot.legal_dong_code),
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
    )
    session.flush()

    session.execute(delete(AddressServingJusoRoadAddress))
    for records in serving_record_sources:
        serving_batch: list[dict[str, object]] = []
        for row_number, record in records:
            snapshot = _road_address_snapshot_from_record(record, row_number)
            if snapshot is None:
                continue
            serving_batch.append(
                _road_address_snapshot_values(
                    snapshot,
                    source_file_name,
                    source_year_month,
                    source_file_hash,
                )
            )
            if len(serving_batch) >= JUSO_SERVING_UPSERT_BATCH_SIZE:
                _upsert_road_address_serving_batch(session, serving_batch)
                serving_batch.clear()
        if serving_batch:
            _upsert_road_address_serving_batch(session, serving_batch)
    session.flush()
    active_road_address_count = int(
        session.scalar(select(func.count()).select_from(AddressServingJusoRoadAddress)) or 0
    )

    return JusoRoadAddressLoadResult(
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
        source_part_count=len(inspected_files),
        raw_row_count=raw_row_count,
        raw_rows_inserted=raw_rows_inserted,
        active_road_address_count=active_road_address_count,
        legal_dong_code_count=len(legal_dong_snapshots),
    )


def _build_road_address_snapshots(
    records: list[JusoRoadAddressRecord],
) -> list[_RoadAddressSnapshot]:
    snapshots: dict[str, _RoadAddressSnapshot] = {}

    for row_number, record in enumerate(records, start=1):
        _merge_road_address_snapshot(snapshots, record, row_number)

    return sorted(snapshots.values(), key=lambda snapshot: snapshot.road_address_management_no)


def _merge_road_address_snapshot(
    snapshots: dict[str, _RoadAddressSnapshot],
    record: JusoRoadAddressRecord,
    row_number: int,
) -> None:
    candidate = _road_address_snapshot_from_record(record, row_number)
    if candidate is None:
        return

    existing = snapshots.get(candidate.road_address_management_no)
    if existing is None:
        snapshots[candidate.road_address_management_no] = candidate
        return

    if candidate.source_effective_date > existing.source_effective_date:
        snapshots[candidate.road_address_management_no] = candidate
        return

    if candidate.source_effective_date == existing.source_effective_date and candidate != existing:
        raise ValueError(
            f"Conflicting road-address rows found for {candidate.road_address_management_no}."
        )


def _road_address_snapshot_from_record(
    record: JusoRoadAddressRecord,
    row_number: int,
) -> _RoadAddressSnapshot | None:
    _validate_record(record, row_number)

    if record.change_reason_code == DISCONTINUED_CHANGE_REASON_CODE:
        return None

    return _RoadAddressSnapshot(
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


def _merge_legal_dong_snapshot(
    snapshots: dict[str, _LegalDongSnapshot],
    record: JusoRoadAddressRecord,
    row_number: int,
) -> None:
    _validate_record(record, row_number)

    if record.change_reason_code == DISCONTINUED_CHANGE_REASON_CODE:
        return

    candidate = _LegalDongSnapshot(
        legal_dong_code=record.legal_dong_code,
        sido_code=_derive_sido_code(record.legal_dong_code),
        sigungu_code=_derive_sigungu_code(record.legal_dong_code),
        sido_name=record.sido_name,
        sigungu_name=record.sigungu_name,
        legal_eupmyeondong_name=record.legal_eupmyeondong_name,
        legal_ri_name=record.legal_ri_name,
        full_legal_dong_name=_build_full_legal_dong_name(record),
        source_effective_date=record.effective_date,
        source_change_reason_code=record.change_reason_code,
    )

    existing = snapshots.get(candidate.legal_dong_code)
    if existing is None:
        snapshots[candidate.legal_dong_code] = candidate
        return

    if (
        existing.sido_name,
        existing.sigungu_name,
        existing.legal_eupmyeondong_name,
        existing.legal_ri_name,
    ) != (
        candidate.sido_name,
        candidate.sigungu_name,
        candidate.legal_eupmyeondong_name,
        candidate.legal_ri_name,
    ):
        raise ValueError(
            "Conflicting legal dong names found for "
            f"{candidate.legal_dong_code}: "
            f"{existing.full_legal_dong_name!r} vs {candidate.full_legal_dong_name!r}"
        )

    if candidate.source_effective_date >= existing.source_effective_date:
        snapshots[candidate.legal_dong_code] = candidate


def _road_address_snapshot_values(
    snapshot: _RoadAddressSnapshot,
    source_file_name: str,
    source_year_month: str,
    source_file_hash: str,
) -> dict[str, object]:
    return {
        "road_address_management_no": snapshot.road_address_management_no,
        "legal_dong_code": snapshot.legal_dong_code,
        "road_name_code": snapshot.road_name_code,
        "administrative_dong_code": snapshot.administrative_dong_code,
        "sido_name": snapshot.sido_name,
        "sigungu_name": snapshot.sigungu_name,
        "legal_eupmyeondong_name": snapshot.legal_eupmyeondong_name,
        "legal_ri_name": snapshot.legal_ri_name,
        "road_name": snapshot.road_name,
        "administrative_dong_name": snapshot.administrative_dong_name,
        "mountain_yn": snapshot.mountain_yn,
        "jibun_main_no": snapshot.jibun_main_no,
        "jibun_sub_no": snapshot.jibun_sub_no,
        "underground_yn": snapshot.underground_yn,
        "building_main_no": snapshot.building_main_no,
        "building_sub_no": snapshot.building_sub_no,
        "postal_code": snapshot.postal_code,
        "previous_road_address": snapshot.previous_road_address,
        "apartment_yn": snapshot.apartment_yn,
        "building_registry_name": snapshot.building_registry_name,
        "sigungu_building_name": snapshot.sigungu_building_name,
        "note": snapshot.note,
        "full_legal_dong_name": snapshot.full_legal_dong_name,
        "full_road_address": snapshot.full_road_address,
        "source_effective_date": snapshot.source_effective_date,
        "source_change_reason_code": snapshot.source_change_reason_code,
        "source_file_name": source_file_name,
        "source_year_month": source_year_month,
        "source_file_hash": source_file_hash,
        "is_active": True,
    }


def _upsert_road_address_serving_batch(
    session: Session,
    batch: Sequence[dict[str, object]],
) -> None:
    if not batch:
        return

    statement = pg_insert(AddressServingJusoRoadAddress).values(list(batch))
    excluded = statement.excluded
    update_columns = {
        "legal_dong_code": excluded.legal_dong_code,
        "road_name_code": excluded.road_name_code,
        "administrative_dong_code": excluded.administrative_dong_code,
        "sido_name": excluded.sido_name,
        "sigungu_name": excluded.sigungu_name,
        "legal_eupmyeondong_name": excluded.legal_eupmyeondong_name,
        "legal_ri_name": excluded.legal_ri_name,
        "road_name": excluded.road_name,
        "administrative_dong_name": excluded.administrative_dong_name,
        "mountain_yn": excluded.mountain_yn,
        "jibun_main_no": excluded.jibun_main_no,
        "jibun_sub_no": excluded.jibun_sub_no,
        "underground_yn": excluded.underground_yn,
        "building_main_no": excluded.building_main_no,
        "building_sub_no": excluded.building_sub_no,
        "postal_code": excluded.postal_code,
        "previous_road_address": excluded.previous_road_address,
        "apartment_yn": excluded.apartment_yn,
        "building_registry_name": excluded.building_registry_name,
        "sigungu_building_name": excluded.sigungu_building_name,
        "note": excluded.note,
        "full_legal_dong_name": excluded.full_legal_dong_name,
        "full_road_address": excluded.full_road_address,
        "source_effective_date": excluded.source_effective_date,
        "source_change_reason_code": excluded.source_change_reason_code,
        "source_file_name": excluded.source_file_name,
        "source_year_month": excluded.source_year_month,
        "source_file_hash": excluded.source_file_hash,
        "is_active": excluded.is_active,
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[AddressServingJusoRoadAddress.road_address_management_no],
            set_=update_columns,
            where=(
                excluded.source_effective_date
                > AddressServingJusoRoadAddress.source_effective_date
            ),
        )
    )


def _batched(
    rows: Iterable[dict[str, object]],
    batch_size: int,
) -> Iterable[list[dict[str, object]]]:
    batch: list[dict[str, object]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


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
