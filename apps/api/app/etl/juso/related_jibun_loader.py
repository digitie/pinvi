from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.etl.juso.parser import (
    InspectedJusoFile,
    JusoRelatedJibunRecord,
    ParsedJusoRelatedJibunFile,
    inspect_juso_related_jibun_file,
    iter_juso_related_jibun_records,
)
from app.models.address import (
    AddressRawJusoRelatedJibun,
    AddressServingJusoRelatedJibun,
    AddressServingJusoRoadAddress,
)

JUSO_RELATED_JIBUN_INSERT_BATCH_SIZE = 5000


@dataclass(frozen=True)
class JusoRelatedJibunLoadResult:
    source_file_name: str
    source_year_month: str
    source_file_hash: str
    source_part_count: int
    raw_row_count: int
    raw_rows_inserted: int
    active_related_jibun_count: int


@dataclass(frozen=True)
class _RelatedJibunSnapshot:
    road_address_management_no: str
    legal_dong_code: str
    road_name_code: str
    sido_name: str
    sigungu_name: str
    legal_eupmyeondong_name: str
    legal_ri_name: str | None
    mountain_yn: str
    jibun_main_no: str
    jibun_sub_no: str
    underground_yn: str
    building_main_no: str
    building_sub_no: str
    note: str | None
    full_legal_dong_name: str
    full_jibun_address: str


def load_juso_related_jibun_from_files(
    session: Session,
    file_paths: Sequence[Path | str],
    *,
    source_year_month: str,
    source_file_name: str,
    source_file_hash: str,
) -> JusoRelatedJibunLoadResult:
    inspected_files = [
        inspect_juso_related_jibun_file(file_path, source_year_month=source_year_month)
        for file_path in file_paths
    ]
    return _load_juso_related_jibun_file_streams(
        session,
        inspected_files,
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
    )


def _load_juso_related_jibun_file_streams(
    session: Session,
    inspected_files: Sequence[InspectedJusoFile],
    *,
    source_file_name: str,
    source_year_month: str,
    source_file_hash: str,
) -> JusoRelatedJibunLoadResult:
    record_sources = [
        iter_juso_related_jibun_records(
            inspected.source_path,
            encoding=inspected.encoding,
            delimiter=inspected.delimiter,
        )
        for inspected in inspected_files
    ]
    return _load_juso_related_jibun_records(
        session,
        inspected_files,
        record_sources=record_sources,
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
    )


def _load_juso_related_jibun_files(
    session: Session,
    parsed_files: Sequence[ParsedJusoRelatedJibunFile],
    *,
    source_file_name: str,
    source_year_month: str,
    source_file_hash: str,
) -> JusoRelatedJibunLoadResult:
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
    return _load_juso_related_jibun_records(
        session,
        inspected_files,
        record_sources=[list(enumerate(parsed_file.rows, start=1)) for parsed_file in parsed_files],
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
    )


def _load_juso_related_jibun_records(
    session: Session,
    inspected_files: Sequence[InspectedJusoFile],
    *,
    record_sources: Sequence[Iterable[tuple[int, JusoRelatedJibunRecord]]],
    source_file_name: str,
    source_year_month: str,
    source_file_hash: str,
) -> JusoRelatedJibunLoadResult:
    if not inspected_files:
        raise ValueError("At least one Juso related-jibun file is required.")

    raw_rows_inserted = 0
    raw_row_count = 0
    snapshots: dict[tuple[str, str, str, str, str], _RelatedJibunSnapshot] = {}
    available_road_address_ids = set(
        session.scalars(select(AddressServingJusoRoadAddress.road_address_management_no)).all()
    )

    for inspected_file, records in zip(inspected_files, record_sources, strict=True):
        if inspected_file.source_year_month != source_year_month:
            raise ValueError(
                "All Juso related-jibun files must share the same source year-month. "
                f"Expected {source_year_month}, got {inspected_file.source_year_month}."
            )

        existing_raw_row_count = session.scalar(
            select(func.count())
            .select_from(AddressRawJusoRelatedJibun)
            .where(AddressRawJusoRelatedJibun.source_file_hash == inspected_file.file_hash)
        )
        if existing_raw_row_count not in (0, inspected_file.row_count):
            raise RuntimeError(
                "Partial raw ingest detected for Juso related-jibun source file hash "
                f"{inspected_file.file_hash}."
            )

        should_insert_raw = existing_raw_row_count == 0
        raw_batch: list[dict[str, object]] = []
        for row_number, record in records:
            raw_row_count += 1
            _merge_related_jibun_snapshot(
                snapshots,
                record,
                raw_row_count,
                available_road_address_ids,
            )
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
                    "sido_name": record.sido_name,
                    "sigungu_name": record.sigungu_name,
                    "legal_eupmyeondong_name": record.legal_eupmyeondong_name,
                    "legal_ri_name": record.legal_ri_name,
                    "mountain_yn": record.mountain_yn,
                    "jibun_main_no": record.jibun_main_no,
                    "jibun_sub_no": record.jibun_sub_no,
                    "road_name_code": record.road_name_code,
                    "underground_yn": record.underground_yn,
                    "building_main_no": record.building_main_no,
                    "building_sub_no": record.building_sub_no,
                    "note": record.note,
                    "raw_line": record.raw_line,
                }
            )
            if len(raw_batch) >= JUSO_RELATED_JIBUN_INSERT_BATCH_SIZE:
                session.execute(insert(AddressRawJusoRelatedJibun), raw_batch)
                raw_rows_inserted += len(raw_batch)
                raw_batch.clear()
        if raw_batch:
            session.execute(insert(AddressRawJusoRelatedJibun), raw_batch)
            raw_rows_inserted += len(raw_batch)

    session.execute(delete(AddressServingJusoRelatedJibun))
    for batch in _batched(
        (
            _related_jibun_snapshot_values(
                snapshot,
                source_file_name,
                source_year_month,
                source_file_hash,
            )
            for snapshot in sorted(
                snapshots.values(), key=lambda snapshot: snapshot.full_jibun_address
            )
        ),
        JUSO_RELATED_JIBUN_INSERT_BATCH_SIZE,
    ):
        session.execute(insert(AddressServingJusoRelatedJibun), batch)
    session.flush()

    return JusoRelatedJibunLoadResult(
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
        source_part_count=len(inspected_files),
        raw_row_count=raw_row_count,
        raw_rows_inserted=raw_rows_inserted,
        active_related_jibun_count=len(snapshots),
    )


def _build_related_jibun_snapshots(
    records: list[JusoRelatedJibunRecord],
    available_road_address_ids: set[str],
) -> list[_RelatedJibunSnapshot]:
    snapshots: dict[tuple[str, str, str, str, str], _RelatedJibunSnapshot] = {}

    for row_number, record in enumerate(records, start=1):
        _merge_related_jibun_snapshot(snapshots, record, row_number, available_road_address_ids)

    return sorted(snapshots.values(), key=lambda snapshot: snapshot.full_jibun_address)


def _merge_related_jibun_snapshot(
    snapshots: dict[tuple[str, str, str, str, str], _RelatedJibunSnapshot],
    record: JusoRelatedJibunRecord,
    row_number: int,
    available_road_address_ids: set[str],
) -> None:
    _validate_related_jibun_record(record, row_number)
    if record.road_address_management_no not in available_road_address_ids:
        raise ValueError(
            "Related-jibun row references an unknown road_address_management_no: "
            f"{record.road_address_management_no}"
        )

    key = (
        record.road_address_management_no,
        record.legal_dong_code,
        record.mountain_yn,
        record.jibun_main_no,
        record.jibun_sub_no,
    )
    candidate = _RelatedJibunSnapshot(
        road_address_management_no=record.road_address_management_no,
        legal_dong_code=record.legal_dong_code,
        road_name_code=record.road_name_code,
        sido_name=record.sido_name,
        sigungu_name=record.sigungu_name,
        legal_eupmyeondong_name=record.legal_eupmyeondong_name,
        legal_ri_name=record.legal_ri_name,
        mountain_yn=record.mountain_yn,
        jibun_main_no=record.jibun_main_no,
        jibun_sub_no=record.jibun_sub_no,
        underground_yn=record.underground_yn,
        building_main_no=record.building_main_no,
        building_sub_no=record.building_sub_no,
        note=record.note,
        full_legal_dong_name=_build_full_legal_dong_name(record),
        full_jibun_address=_build_full_jibun_address(record),
    )

    existing = snapshots.get(key)
    if existing is None:
        snapshots[key] = candidate
        return

    if existing != candidate:
        raise ValueError(
            "Conflicting related-jibun rows found for "
            f"{record.road_address_management_no} / {record.legal_dong_code} / "
            f"{record.jibun_main_no}-{record.jibun_sub_no}."
        )


def _related_jibun_snapshot_values(
    snapshot: _RelatedJibunSnapshot,
    source_file_name: str,
    source_year_month: str,
    source_file_hash: str,
) -> dict[str, object]:
    return {
        "road_address_management_no": snapshot.road_address_management_no,
        "legal_dong_code": snapshot.legal_dong_code,
        "road_name_code": snapshot.road_name_code,
        "sido_name": snapshot.sido_name,
        "sigungu_name": snapshot.sigungu_name,
        "legal_eupmyeondong_name": snapshot.legal_eupmyeondong_name,
        "legal_ri_name": snapshot.legal_ri_name,
        "mountain_yn": snapshot.mountain_yn,
        "jibun_main_no": snapshot.jibun_main_no,
        "jibun_sub_no": snapshot.jibun_sub_no,
        "underground_yn": snapshot.underground_yn,
        "building_main_no": snapshot.building_main_no,
        "building_sub_no": snapshot.building_sub_no,
        "note": snapshot.note,
        "full_legal_dong_name": snapshot.full_legal_dong_name,
        "full_jibun_address": snapshot.full_jibun_address,
        "source_file_name": source_file_name,
        "source_year_month": source_year_month,
        "source_file_hash": source_file_hash,
        "is_active": True,
    }


def _batched(
    values: Iterable[dict[str, object]],
    batch_size: int,
) -> Iterable[list[dict[str, object]]]:
    batch: list[dict[str, object]] = []
    for value in values:
        batch.append(value)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _build_full_legal_dong_name(record: JusoRelatedJibunRecord) -> str:
    parts = [
        record.sido_name,
        record.sigungu_name,
        record.legal_eupmyeondong_name,
    ]
    if record.legal_ri_name:
        parts.append(record.legal_ri_name)
    return " ".join(parts)


def _build_full_jibun_address(record: JusoRelatedJibunRecord) -> str:
    address_tail = record.jibun_main_no
    if record.jibun_sub_no and record.jibun_sub_no != "0":
        address_tail = f"{address_tail}-{record.jibun_sub_no}"
    if record.mountain_yn == "1":
        address_tail = f"산 {address_tail}"
    return " ".join([_build_full_legal_dong_name(record), address_tail])


def _validate_related_jibun_record(record: JusoRelatedJibunRecord, row_number: int) -> None:
    if not record.road_address_management_no:
        raise ValueError(f"Row {row_number}: road_address_management_no is required.")
    if len(record.legal_dong_code) != 10:
        raise ValueError(f"Row {row_number}: legal_dong_code must be 10 characters.")
    if len(record.road_name_code) != 12:
        raise ValueError(f"Row {row_number}: road_name_code must be 12 characters.")
