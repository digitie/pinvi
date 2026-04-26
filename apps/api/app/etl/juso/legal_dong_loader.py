from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.etl.juso.parser import (
    JusoRoadAddressRecord,
    ParsedJusoRoadAddressFile,
    parse_juso_road_address_file,
)
from app.models.address import AddressCodeStandard, AddressRawJusoRoadAddress

DISCONTINUED_CHANGE_REASON_CODE = "63"


@dataclass(frozen=True)
class JusoLegalDongLoadResult:
    source_file_name: str
    source_year_month: str
    source_file_hash: str
    source_part_count: int
    raw_row_count: int
    raw_rows_inserted: int
    legal_dong_code_count: int


@dataclass(frozen=True)
class _LegalDongSnapshot:
    legal_dong_code: str
    sido_code: str
    sigungu_code: str
    sido_name: str
    sigungu_name: str
    legal_eupmyeondong_name: str
    legal_ri_name: str | None
    full_legal_dong_name: str
    source_effective_date: str
    source_change_reason_code: str


def _build_full_legal_dong_name(record: JusoRoadAddressRecord) -> str:
    parts = [
        record.sido_name,
        record.sigungu_name,
        record.legal_eupmyeondong_name,
    ]
    if record.legal_ri_name:
        parts.append(record.legal_ri_name)
    return " ".join(parts)


def _derive_sido_code(legal_dong_code: str) -> str:
    return f"{legal_dong_code[:2]}00000000"


def _derive_sigungu_code(legal_dong_code: str) -> str:
    return f"{legal_dong_code[:5]}00000"


def _derive_code_level(legal_dong_code: str) -> str:
    if legal_dong_code[2:] == "00000000":
        return "sido"
    if legal_dong_code[5:] == "00000":
        return "sigungu"
    return "legal_dong"


def _validate_record(record: JusoRoadAddressRecord, row_number: int) -> None:
    if len(record.legal_dong_code) != 10:
        raise ValueError(f"Row {row_number}: legal_dong_code must be 10 characters.")
    if len(record.road_name_code) != 12:
        raise ValueError(f"Row {row_number}: road_name_code must be 12 characters.")
    if not record.road_address_management_no:
        raise ValueError(f"Row {row_number}: road_address_management_no is required.")
    if len(record.effective_date) != 8:
        raise ValueError(f"Row {row_number}: effective_date must be YYYYMMDD.")


def _build_legal_dong_snapshots(records: list[JusoRoadAddressRecord]) -> list[_LegalDongSnapshot]:
    snapshots: dict[str, _LegalDongSnapshot] = {}

    for row_number, record in enumerate(records, start=1):
        _validate_record(record, row_number)

        if record.change_reason_code == DISCONTINUED_CHANGE_REASON_CODE:
            continue

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
            continue

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

    return sorted(snapshots.values(), key=lambda snapshot: snapshot.legal_dong_code)


def upsert_address_code_snapshots_from_juso(
    session: Session,
    snapshots: Sequence[_LegalDongSnapshot],
    *,
    source_file_name: str,
    source_year_month: str,
    source_file_hash: str,
) -> None:
    existing_rows = {
        row.legal_dong_code: row
        for row in session.scalars(
            select(AddressCodeStandard).where(
                AddressCodeStandard.legal_dong_code.in_(
                    [snapshot.legal_dong_code for snapshot in snapshots]
                )
            )
        ).all()
    }

    for snapshot in snapshots:
        existing = existing_rows.get(snapshot.legal_dong_code)
        if existing is not None and existing.source_provider == "vworld_lawd_cd":
            continue

        values = {
            "code_level": _derive_code_level(snapshot.legal_dong_code),
            "code_name": snapshot.full_legal_dong_name,
            "sido_code": snapshot.sido_code,
            "sigungu_code": snapshot.sigungu_code,
            "sido_name": snapshot.sido_name,
            "sigungu_name": snapshot.sigungu_name,
            "legal_eupmyeondong_name": snapshot.legal_eupmyeondong_name,
            "legal_ri_name": snapshot.legal_ri_name,
            "full_legal_dong_name": snapshot.full_legal_dong_name,
            "source_effective_date": snapshot.source_effective_date,
            "source_change_reason_code": snapshot.source_change_reason_code,
            "source_provider": "juso_road_address",
            "source_status": "derived_from_juso",
            "source_file_name": source_file_name,
            "source_year_month": source_year_month,
            "source_file_hash": source_file_hash,
            "is_discontinued": False,
            "is_active": True,
        }

        if existing is None:
            session.add(AddressCodeStandard(legal_dong_code=snapshot.legal_dong_code, **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)


def load_juso_legal_dong_codes(
    session: Session,
    file_path: Path | str,
    *,
    source_year_month: str | None = None,
) -> JusoLegalDongLoadResult:
    parsed_file = parse_juso_road_address_file(file_path, source_year_month=source_year_month)
    return _load_juso_legal_dong_code_files(
        session,
        [parsed_file],
        source_file_name=parsed_file.source_file_name,
        source_year_month=parsed_file.source_year_month,
        source_file_hash=parsed_file.file_hash,
    )


def load_juso_legal_dong_codes_from_files(
    session: Session,
    file_paths: Sequence[Path | str],
    *,
    source_year_month: str,
    source_file_name: str,
    source_file_hash: str,
) -> JusoLegalDongLoadResult:
    parsed_files = [
        parse_juso_road_address_file(file_path, source_year_month=source_year_month)
        for file_path in file_paths
    ]
    return _load_juso_legal_dong_code_files(
        session,
        parsed_files,
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
    )


def _load_juso_legal_dong_code_files(
    session: Session,
    parsed_files: Sequence[ParsedJusoRoadAddressFile],
    *,
    source_file_name: str,
    source_year_month: str,
    source_file_hash: str,
) -> JusoLegalDongLoadResult:
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

    legal_dong_snapshots = _build_legal_dong_snapshots(all_records)

    upsert_address_code_snapshots_from_juso(
        session,
        legal_dong_snapshots,
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
    )
    session.flush()

    return JusoLegalDongLoadResult(
        source_file_name=source_file_name,
        source_year_month=source_year_month,
        source_file_hash=source_file_hash,
        source_part_count=len(parsed_files),
        raw_row_count=len(all_records),
        raw_rows_inserted=raw_rows_inserted,
        legal_dong_code_count=len(legal_dong_snapshots),
    )
