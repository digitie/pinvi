from __future__ import annotations

import csv
import hashlib
import html
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.etl.archive import safe_extract_zip
from app.etl.juso.legal_dong_loader import (
    _derive_code_level,
    _derive_sido_code,
    _derive_sigungu_code,
)
from app.models.address import AddressCodeStandard, AddressRawLegalDongCode

DATA_GO_LEGAL_DONG_PAGE_URL = "https://www.data.go.kr/data/15063424/fileData.do"
DATA_GO_LEGAL_DONG_PROVIDER = "data_go_legal_dong"
LEGACY_VWORLD_LEGAL_DONG_PROVIDER = "vworld_lawd_cd"
LEGAL_DONG_CODE_CSV_ENCODINGS = ("utf-8-sig", "cp949")
DATA_GO_REQUEST_HEADERS = {
    "User-Agent": "TripMate-ETL/0.1 (+https://www.data.go.kr/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
DATA_GO_SERVICE_KEY_QUERY_NAME = "serviceKey"
DATA_GO_SERVICE_KEY_REDACTION = "***"

FIELD_LEGAL_DONG_CODE = "\ubc95\uc815\ub3d9\ucf54\ub4dc"
FIELD_SIDO_NAME = "\uc2dc\ub3c4\uba85"
FIELD_SIGUNGU_NAME = "\uc2dc\uad70\uad6c\uba85"
FIELD_EUPMYEONDONG_NAME = "\uc74d\uba74\ub3d9\uba85"
FIELD_RI_NAME = "\ub9ac\uba85"
FIELD_SORT_ORDER = "\uc21c\uc704"
FIELD_CREATED_DATE = "\uc0dd\uc131\uc77c\uc790"
FIELD_DELETED_DATE = "\uc0ad\uc81c\uc77c\uc790"
FIELD_PREVIOUS_LEGAL_DONG_CODE = "\uacfc\uac70\ubc95\uc815\ub3d9\ucf54\ub4dc"
FIELD_LEGACY_LEGAL_DONG_NAME = "\ubc95\uc815\ub3d9\uba85"
FIELD_LEGACY_DISCONTINUED_STATUS = "\ud3d0\uc9c0\uc5ec\ubd80"

DATA_GO_REQUIRED_FIELDS = (
    FIELD_LEGAL_DONG_CODE,
    FIELD_SIDO_NAME,
    FIELD_SIGUNGU_NAME,
    FIELD_EUPMYEONDONG_NAME,
    FIELD_RI_NAME,
    FIELD_SORT_ORDER,
    FIELD_CREATED_DATE,
    FIELD_DELETED_DATE,
    FIELD_PREVIOUS_LEGAL_DONG_CODE,
)
LEGACY_REQUIRED_FIELDS = (
    FIELD_LEGAL_DONG_CODE,
    FIELD_LEGACY_LEGAL_DONG_NAME,
    FIELD_LEGACY_DISCONTINUED_STATUS,
)
LEGACY_STATUS_ACTIVE = "\uc874\uc7ac"
LEGACY_STATUS_DISCONTINUED = "\ud3d0\uc9c0"


@dataclass(frozen=True)
class LegalDongCodeCsvLoadResult:
    source_file_name: str
    source_file_hash: str
    raw_row_count: int
    raw_rows_inserted: int
    active_code_count: int
    discontinued_code_count: int
    retained_missing_code_count: int


@dataclass(frozen=True)
class LegalDongCodeDownloadResult:
    page_url: str
    download_url: str
    file_path: Path
    source_file_hash: str


@dataclass(frozen=True)
class LegalDongCodeCsvRecord:
    legal_dong_code: str
    legal_dong_name: str
    discontinued_status: str
    raw_line: str
    source_provider: str
    sido_name: str | None = None
    sigungu_name: str | None = None
    legal_eupmyeondong_name: str | None = None
    legal_ri_name: str | None = None
    source_sort_order: int | None = None
    source_created_date: str | None = None
    source_deleted_date: str | None = None
    previous_legal_dong_code: str | None = None


def download_latest_legal_dong_code_csv(
    download_dir: Path | str,
    *,
    page_url: str = DATA_GO_LEGAL_DONG_PAGE_URL,
    service_key: str | None = None,
    client: httpx.Client | None = None,
) -> LegalDongCodeDownloadResult:
    target_dir = Path(download_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    owns_client = client is None
    resolved_client = client or httpx.Client(
        follow_redirects=True,
        headers=DATA_GO_REQUEST_HEADERS,
        timeout=30.0,
    )
    try:
        page_response = resolved_client.get(page_url)
        page_response.raise_for_status()
        download_url = _extract_data_go_content_url(page_response.text, page_url)
        request_download_url = _with_data_go_service_key(
            download_url,
            _resolve_data_go_service_key(service_key),
        )

        file_response = resolved_client.get(request_download_url)
        file_response.raise_for_status()
        file_name = _resolve_download_file_name(file_response, request_download_url)
        file_path = target_dir / file_name
        file_path.write_bytes(file_response.content)
    finally:
        if owns_client:
            resolved_client.close()

    return LegalDongCodeDownloadResult(
        page_url=page_url,
        download_url=_redact_data_go_service_key(request_download_url),
        file_path=file_path,
        source_file_hash=_sha256_file(file_path),
    )


def load_latest_legal_dong_code_from_data_go(
    session: Session,
    download_dir: Path | str,
    *,
    page_url: str = DATA_GO_LEGAL_DONG_PAGE_URL,
    client: httpx.Client | None = None,
) -> LegalDongCodeCsvLoadResult:
    downloaded = download_latest_legal_dong_code_csv(
        download_dir,
        page_url=page_url,
        client=client,
    )
    return load_legal_dong_code_csv(
        session,
        downloaded.file_path,
        source_file_hash=downloaded.source_file_hash,
    )


def load_legal_dong_code_zip(
    session: Session,
    zip_path: Path | str,
) -> LegalDongCodeCsvLoadResult:
    source_path = Path(zip_path)
    with tempfile.TemporaryDirectory(prefix="tripmate-lawd-cd-") as temporary_directory:
        extract_dir = Path(temporary_directory)
        safe_extract_zip(source_path, extract_dir)
        csv_path = _find_csv_file(extract_dir)
        return load_legal_dong_code_csv(
            session,
            csv_path,
            source_file_name=source_path.name,
            source_file_hash=_sha256_file(source_path),
        )


def load_legal_dong_code_csv(
    session: Session,
    csv_path: Path | str,
    *,
    source_file_name: str | None = None,
    source_file_hash: str | None = None,
) -> LegalDongCodeCsvLoadResult:
    source_path = Path(csv_path)
    resolved_source_file_name = source_file_name or source_path.name
    resolved_source_file_hash = source_file_hash or _sha256_file(source_path)
    source_effective_date = _derive_source_effective_date(resolved_source_file_name)
    source_year_month = source_effective_date[:6]
    records = _parse_legal_dong_code_csv(source_path)

    existing_raw_row_count = session.scalar(
        select(func.count())
        .select_from(AddressRawLegalDongCode)
        .where(AddressRawLegalDongCode.source_file_hash == resolved_source_file_hash)
    )
    if existing_raw_row_count not in (0, len(records)):
        raise RuntimeError(
            "Partial raw ingest detected for legal-dong code source file hash "
            f"{resolved_source_file_hash}."
        )

    raw_rows_inserted = 0
    if existing_raw_row_count == 0:
        session.add_all(
            [
                AddressRawLegalDongCode(
                    source_file_name=resolved_source_file_name,
                    source_file_hash=resolved_source_file_hash,
                    row_number=row_number,
                    legal_dong_code=record.legal_dong_code,
                    legal_dong_name=record.legal_dong_name,
                    discontinued_status=record.discontinued_status,
                    sido_name=record.sido_name,
                    sigungu_name=record.sigungu_name,
                    legal_eupmyeondong_name=record.legal_eupmyeondong_name,
                    legal_ri_name=record.legal_ri_name,
                    source_sort_order=record.source_sort_order,
                    source_created_date=record.source_created_date,
                    source_deleted_date=record.source_deleted_date,
                    previous_legal_dong_code=record.previous_legal_dong_code,
                    raw_line=record.raw_line,
                )
                for row_number, record in enumerate(records, start=1)
            ]
        )
        raw_rows_inserted = len(records)

    parent_name_index = {record.legal_dong_code: record.legal_dong_name for record in records}
    existing_codes = {
        row.legal_dong_code: row for row in session.scalars(select(AddressCodeStandard)).all()
    }
    loaded_codes = {record.legal_dong_code for record in records}

    active_code_count = 0
    discontinued_code_count = 0
    for record in records:
        is_discontinued = _is_record_discontinued(record)
        if is_discontinued:
            discontinued_code_count += 1
        else:
            active_code_count += 1

        values = _build_code_standard_values(
            record,
            parent_name_index=parent_name_index,
            source_effective_date=source_effective_date,
            source_year_month=source_year_month,
            source_file_name=resolved_source_file_name,
            source_file_hash=resolved_source_file_hash,
            is_discontinued=is_discontinued,
        )
        existing = existing_codes.get(record.legal_dong_code)
        if existing is None:
            session.add(AddressCodeStandard(legal_dong_code=record.legal_dong_code, **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)

    retained_missing_code_count = 0
    for legal_dong_code, existing in existing_codes.items():
        if legal_dong_code in loaded_codes:
            continue
        existing.is_active = False
        existing.is_discontinued = True
        existing.source_status = "missing_from_latest_download"
        retained_missing_code_count += 1

    session.flush()
    return LegalDongCodeCsvLoadResult(
        source_file_name=resolved_source_file_name,
        source_file_hash=resolved_source_file_hash,
        raw_row_count=len(records),
        raw_rows_inserted=raw_rows_inserted,
        active_code_count=active_code_count,
        discontinued_code_count=discontinued_code_count,
        retained_missing_code_count=retained_missing_code_count,
    )


def _extract_data_go_content_url(page_html: str, page_url: str) -> str:
    match = re.search(r'"contentUrl"\s*:\s*"(?P<url>[^"]+)"', page_html)
    if match is None:
        raise ValueError("data.go.kr page does not contain a structured contentUrl.")
    return urljoin(page_url, html.unescape(match.group("url")))


def _resolve_data_go_service_key(service_key: str | None) -> str | None:
    if service_key is not None:
        value = service_key.strip()
    else:
        value = (get_settings().data_go_service_key or "").strip()
    return value or None


def _with_data_go_service_key(download_url: str, service_key: str | None) -> str:
    if not service_key:
        return download_url

    split_url = urlsplit(download_url)
    query_items = parse_qsl(split_url.query, keep_blank_values=True)
    if any(key.lower() == DATA_GO_SERVICE_KEY_QUERY_NAME.lower() for key, _ in query_items):
        return download_url

    query_items.append((DATA_GO_SERVICE_KEY_QUERY_NAME, service_key))
    return urlunsplit(
        (
            split_url.scheme,
            split_url.netloc,
            split_url.path,
            urlencode(query_items),
            split_url.fragment,
        )
    )


def _redact_data_go_service_key(download_url: str) -> str:
    split_url = urlsplit(download_url)
    query_items = parse_qsl(split_url.query, keep_blank_values=True)
    redacted_items = [
        (
            key,
            DATA_GO_SERVICE_KEY_REDACTION
            if key.lower() == DATA_GO_SERVICE_KEY_QUERY_NAME.lower()
            else value,
        )
        for key, value in query_items
    ]
    return urlunsplit(
        (
            split_url.scheme,
            split_url.netloc,
            split_url.path,
            urlencode(redacted_items),
            split_url.fragment,
        )
    )


def _resolve_download_file_name(response: httpx.Response, download_url: str) -> str:
    disposition = response.headers.get("content-disposition", "")
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?(?P<name>[^";]+)"?', disposition)
    if match:
        candidate = Path(html.unescape(match.group("name"))).name
    else:
        candidate = Path(download_url.split("?", 1)[0]).name
    if not candidate or candidate == "fileDownload.do":
        candidate = "data_go_legal_dong_code.csv"
    if not candidate.lower().endswith(".csv"):
        candidate = f"{candidate}.csv"
    return candidate


def _find_csv_file(extract_dir: Path) -> Path:
    csv_files = list(extract_dir.rglob("*.csv"))
    if len(csv_files) != 1:
        raise ValueError(f"Expected exactly one legal-dong code CSV, found {len(csv_files)}.")
    return csv_files[0]


def _parse_legal_dong_code_csv(csv_path: Path) -> list[LegalDongCodeCsvRecord]:
    text = _read_text_with_known_encoding(csv_path)
    lines = text.splitlines()
    reader = csv.DictReader(lines)
    if reader.fieldnames == list(DATA_GO_REQUIRED_FIELDS):
        return _parse_data_go_rows(reader, lines)
    if reader.fieldnames == list(LEGACY_REQUIRED_FIELDS):
        return _parse_legacy_rows(reader, lines)
    raise ValueError(
        "Legal-dong code CSV fields must be either "
        f"{list(DATA_GO_REQUIRED_FIELDS)} or {list(LEGACY_REQUIRED_FIELDS)}, "
        f"got {reader.fieldnames}."
    )


def _parse_data_go_rows(
    reader: csv.DictReader[str],
    lines: list[str],
) -> list[LegalDongCodeCsvRecord]:
    records: list[LegalDongCodeCsvRecord] = []
    seen_codes: set[str] = set()
    for row_number, row in enumerate(reader, start=1):
        legal_dong_code = _required(row, FIELD_LEGAL_DONG_CODE, row_number)
        if len(legal_dong_code) != 10:
            raise ValueError(f"Row {row_number}: legal_dong_code must be 10 characters.")
        if legal_dong_code in seen_codes:
            raise ValueError(f"Row {row_number}: duplicated legal_dong_code {legal_dong_code}.")

        sido_name = _optional(row, FIELD_SIDO_NAME)
        sigungu_name = _optional(row, FIELD_SIGUNGU_NAME)
        legal_eupmyeondong_name = _optional(row, FIELD_EUPMYEONDONG_NAME)
        legal_ri_name = _optional(row, FIELD_RI_NAME)
        legal_dong_name = _join_name_parts(
            sido_name,
            sigungu_name,
            legal_eupmyeondong_name,
            legal_ri_name,
        )
        if not legal_dong_name:
            raise ValueError(f"Row {row_number}: legal_dong_name cannot be derived.")

        seen_codes.add(legal_dong_code)
        source_deleted_date = _optional(row, FIELD_DELETED_DATE)
        records.append(
            LegalDongCodeCsvRecord(
                legal_dong_code=legal_dong_code,
                legal_dong_name=legal_dong_name,
                discontinued_status="deleted" if source_deleted_date else "active",
                raw_line=lines[row_number],
                source_provider=DATA_GO_LEGAL_DONG_PROVIDER,
                sido_name=sido_name,
                sigungu_name=sigungu_name,
                legal_eupmyeondong_name=legal_eupmyeondong_name,
                legal_ri_name=legal_ri_name,
                source_sort_order=_optional_int(row, FIELD_SORT_ORDER, row_number),
                source_created_date=_optional(row, FIELD_CREATED_DATE),
                source_deleted_date=source_deleted_date,
                previous_legal_dong_code=_optional(row, FIELD_PREVIOUS_LEGAL_DONG_CODE),
            )
        )
    return records


def _parse_legacy_rows(
    reader: csv.DictReader[str],
    lines: list[str],
) -> list[LegalDongCodeCsvRecord]:
    records: list[LegalDongCodeCsvRecord] = []
    seen_codes: set[str] = set()
    for row_number, row in enumerate(reader, start=1):
        legal_dong_code = _required(row, FIELD_LEGAL_DONG_CODE, row_number)
        legal_dong_name = _required(row, FIELD_LEGACY_LEGAL_DONG_NAME, row_number)
        discontinued_status = _required(row, FIELD_LEGACY_DISCONTINUED_STATUS, row_number)
        if len(legal_dong_code) != 10:
            raise ValueError(f"Row {row_number}: legal_dong_code must be 10 characters.")
        if legal_dong_code in seen_codes:
            raise ValueError(f"Row {row_number}: duplicated legal_dong_code {legal_dong_code}.")
        if discontinued_status not in {LEGACY_STATUS_ACTIVE, LEGACY_STATUS_DISCONTINUED}:
            raise ValueError(
                f"Row {row_number}: unsupported discontinued status {discontinued_status!r}."
            )
        seen_codes.add(legal_dong_code)
        records.append(
            LegalDongCodeCsvRecord(
                legal_dong_code=legal_dong_code,
                legal_dong_name=legal_dong_name,
                discontinued_status=discontinued_status,
                raw_line=lines[row_number],
                source_provider=LEGACY_VWORLD_LEGAL_DONG_PROVIDER,
            )
        )
    return records


def _build_code_standard_values(
    record: LegalDongCodeCsvRecord,
    *,
    parent_name_index: dict[str, str],
    source_effective_date: str,
    source_year_month: str,
    source_file_name: str,
    source_file_hash: str,
    is_discontinued: bool,
) -> dict[str, object]:
    sido_code = _derive_sido_code(record.legal_dong_code)
    sigungu_code = _derive_sigungu_code(record.legal_dong_code)
    code_level = _derive_code_level(record.legal_dong_code)

    if record.source_provider == DATA_GO_LEGAL_DONG_PROVIDER:
        sido_name = record.sido_name
        sigungu_name = record.sigungu_name
        legal_eupmyeondong_name = (
            record.legal_eupmyeondong_name if code_level == "legal_dong" else None
        )
        legal_ri_name = record.legal_ri_name if code_level == "legal_dong" else None
    else:
        sido_name = parent_name_index.get(sido_code)
        sigungu_full_name = parent_name_index.get(sigungu_code)
        if sido_name is None and sigungu_full_name is not None:
            sido_name = sigungu_full_name
        sigungu_name = _remove_prefix(sigungu_full_name, sido_name)
        legal_remainder = _remove_prefix(record.legal_dong_name, sigungu_full_name or sido_name)
        legal_parts = legal_remainder.split(maxsplit=1) if legal_remainder else []
        legal_eupmyeondong_name = (
            legal_parts[0] if code_level == "legal_dong" and legal_parts else None
        )
        legal_ri_name = (
            legal_parts[1] if code_level == "legal_dong" and len(legal_parts) > 1 else None
        )

        if code_level == "sido":
            sido_name = record.legal_dong_name
            sigungu_name = None
        elif code_level == "sigungu":
            sigungu_name = _remove_prefix(record.legal_dong_name, sido_name)

    return {
        "code_level": code_level,
        "code_name": record.legal_dong_name,
        "sido_code": sido_code,
        "sigungu_code": sigungu_code,
        "sido_name": sido_name,
        "sigungu_name": sigungu_name,
        "legal_eupmyeondong_name": legal_eupmyeondong_name,
        "legal_ri_name": legal_ri_name,
        "full_legal_dong_name": record.legal_dong_name,
        "source_effective_date": source_effective_date,
        "source_change_reason_code": "00",
        "source_provider": record.source_provider,
        "source_status": record.discontinued_status,
        "source_file_name": source_file_name,
        "source_year_month": source_year_month,
        "source_file_hash": source_file_hash,
        "source_sort_order": record.source_sort_order,
        "source_created_date": record.source_created_date,
        "source_deleted_date": record.source_deleted_date,
        "previous_legal_dong_code": record.previous_legal_dong_code,
        "is_discontinued": is_discontinued,
        "is_active": not is_discontinued,
    }


def _is_record_discontinued(record: LegalDongCodeCsvRecord) -> bool:
    return bool(record.source_deleted_date) or record.discontinued_status in {
        "deleted",
        LEGACY_STATUS_DISCONTINUED,
    }


def _read_text_with_known_encoding(path: Path) -> str:
    for encoding in LEGAL_DONG_CODE_CSV_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(
        "legal_dong_code",
        path.read_bytes()[:64],
        0,
        1,
        f"unsupported encoding; tried {LEGAL_DONG_CODE_CSV_ENCODINGS}",
    )


def _required(row: dict[str, str], field: str, row_number: int) -> str:
    value = row[field].strip()
    if not value:
        raise ValueError(f"Row {row_number}: {field} is required.")
    return value


def _optional(row: dict[str, str], field: str) -> str | None:
    value = row[field].strip()
    return value or None


def _optional_int(row: dict[str, str], field: str, row_number: int) -> int | None:
    value = _optional(row, field)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Row {row_number}: {field} must be an integer.") from exc


def _join_name_parts(*parts: str | None) -> str:
    return " ".join(part for part in parts if part)


def _remove_prefix(value: str | None, prefix: str | None) -> str | None:
    if not value:
        return None
    if prefix and value.startswith(prefix):
        return value[len(prefix) :].strip() or None
    return value


def _derive_source_effective_date(source_file_name: str) -> str:
    match = re.search(r"(20\d{6})", source_file_name)
    if match:
        return match.group(1)
    return "00000000"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
