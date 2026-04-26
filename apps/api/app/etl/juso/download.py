from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast
from urllib import parse, request
from zipfile import ZipFile

JUSO_BASE_URL = "https://business.juso.go.kr"
JUSO_SELECT_DOWNLOAD_LIST_PATH = "/api/jst/selectAttrbDBDwldList"
JUSO_DOWNLOAD_PATH = "/api/jst/download"
JUSO_ROAD_ADDRESS_KOREAN_DATASET_DETAIL_SN = "1"
JUSO_MONTHLY_FULL_APPLY_DATA_CODE = "11"
JUSO_MONTHLY_FULL_FILE_TYPE = "ALLRNADR_KOR"
DEFAULT_TIMEOUT_SECONDS = 60


class JusoDownloadError(RuntimeError):
    """Raised when the Juso download flow cannot resolve or fetch an archive."""


class _HttpResponse(Protocol):
    def __enter__(self) -> _HttpResponse: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def read(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True)
class JusoMonthlyRoadAddressArchive:
    dataset_detail_serial: str
    source_year_month: str
    apply_data_code: str
    file_type_name: str
    file_name: str
    real_file_name: str
    ctpv_class_code: str | None
    file_serial_no: str | None
    attachment_no: str | None

    @property
    def registration_year(self) -> str:
        return self.source_year_month[:4]

    def to_download_query(self) -> dict[str, str]:
        return {
            "reqType": self.file_type_name,
            "ctprvnCd": self.ctpv_class_code or "",
            "stdde": self.source_year_month,
            "fileName": self.file_name,
            "realFileName": self.real_file_name,
            "intFileNo": self.file_serial_no or "0",
            "intNum": self.attachment_no or "0",
            "regYmd": self.registration_year,
        }


@dataclass(frozen=True)
class DownloadedJusoRoadAddressArchive:
    metadata: JusoMonthlyRoadAddressArchive
    archive_path: Path
    archive_hash: str


@dataclass(frozen=True)
class ExtractedJusoRoadAddressArchive:
    downloaded_archive: DownloadedJusoRoadAddressArchive
    road_address_paths: list[Path]
    related_jibun_paths: list[Path]


def _previous_year_month(year_month: str) -> str:
    year = int(year_month[:4])
    month = int(year_month[4:6])
    if month == 1:
        return f"{year - 1:04d}12"
    return f"{year:04d}{month - 1:02d}"


def _safe_extract_member(zip_file: ZipFile, member_name: str, destination_dir: Path) -> Path:
    destination_root = destination_dir.resolve()
    destination_path = (destination_dir / member_name).resolve()
    if destination_root != destination_path and destination_root not in destination_path.parents:
        raise JusoDownloadError(
            f"Refusing to extract archive member outside destination: {member_name}"
        )

    zip_file.extract(member_name, destination_dir)
    return destination_path


class JusoDownloadClient:
    def __init__(
        self,
        *,
        base_url: str = JUSO_BASE_URL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def _open(self, url: str, *, data: bytes | None = None) -> _HttpResponse:
        request_object = request.Request(url, data=data)
        if data is not None:
            request_object.add_header("Content-Type", "application/json")
        request_object.add_header("User-Agent", "TripMate/0.1")
        return cast(_HttpResponse, request.urlopen(request_object, timeout=self._timeout_seconds))

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8")
        with self._open(f"{self._base_url}{path}", data=body) as response:
            return cast(dict[str, object], json.loads(response.read().decode("utf-8")))

    def _get_reference_year_month(self) -> str:
        return date.today().strftime("%Y%m")

    def fetch_download_inventory(self, *, reference_year_month: str) -> dict[str, object]:
        return self._post_json(
            JUSO_SELECT_DOWNLOAD_LIST_PATH,
            {
                "rtlDtaDtlSn": JUSO_ROAD_ADDRESS_KOREAN_DATASET_DETAIL_SN,
                "year": reference_year_month[:4],
                "month": str(int(reference_year_month[4:6])),
                "expand": "Y",
            },
        )

    def resolve_monthly_full_road_address_archive(
        self,
        *,
        source_year_month: str | None = None,
    ) -> JusoMonthlyRoadAddressArchive:
        if source_year_month is not None:
            inventory_response = self.fetch_download_inventory(
                reference_year_month=source_year_month
            )
            return self._select_monthly_full_archive(
                inventory_response=inventory_response,
                source_year_month=source_year_month,
            )

        reference_year_month = self._get_reference_year_month()
        candidates: list[JusoMonthlyRoadAddressArchive] = []
        for probe_year_month in (reference_year_month, _previous_year_month(reference_year_month)):
            inventory_response = self.fetch_download_inventory(
                reference_year_month=probe_year_month
            )
            candidates.extend(self._list_monthly_full_archives(inventory_response))

        if not candidates:
            raise JusoDownloadError("No monthly Juso road-address archive is currently available.")

        return max(candidates, key=lambda archive: archive.source_year_month)

    def _list_monthly_full_archives(
        self,
        inventory_response: dict[str, object],
    ) -> list[JusoMonthlyRoadAddressArchive]:
        results = inventory_response.get("results")
        if not isinstance(results, dict):
            raise JusoDownloadError("Unexpected Juso inventory response: missing results object.")

        raw_file_list = results.get("allMonthFileList")
        if not isinstance(raw_file_list, list):
            return []

        archives: list[JusoMonthlyRoadAddressArchive] = []
        for item in raw_file_list:
            if not isinstance(item, dict):
                continue
            if item.get("isExist") != "Y":
                continue
            if item.get("fileTypeNm") != JUSO_MONTHLY_FULL_FILE_TYPE:
                continue
            file_name = item.get("fileNm")
            real_file_name = item.get("tmprFileNm")
            source_year_month = item.get("crtrYm")
            if not isinstance(file_name, str) or not isinstance(real_file_name, str):
                continue
            if not isinstance(source_year_month, str):
                continue

            archives.append(
                JusoMonthlyRoadAddressArchive(
                    dataset_detail_serial=JUSO_ROAD_ADDRESS_KOREAN_DATASET_DETAIL_SN,
                    source_year_month=source_year_month,
                    apply_data_code=JUSO_MONTHLY_FULL_APPLY_DATA_CODE,
                    file_type_name=JUSO_MONTHLY_FULL_FILE_TYPE,
                    file_name=file_name,
                    real_file_name=real_file_name,
                    ctpv_class_code=_as_optional_string(item.get("ctpvClsfCd")),
                    file_serial_no=_as_optional_string(item.get("fileSn")),
                    attachment_no=_as_optional_string(item.get("atflNo")),
                )
            )

        return archives

    def _select_monthly_full_archive(
        self,
        *,
        inventory_response: dict[str, object],
        source_year_month: str,
    ) -> JusoMonthlyRoadAddressArchive:
        archives = self._list_monthly_full_archives(inventory_response)
        for archive in archives:
            if archive.source_year_month == source_year_month:
                return archive

        raise JusoDownloadError(
            f"No monthly Juso road-address archive is available for {source_year_month}."
        )

    def download_archive(
        self,
        archive: JusoMonthlyRoadAddressArchive,
        destination_dir: Path | str,
    ) -> DownloadedJusoRoadAddressArchive:
        destination_path = Path(destination_dir)
        destination_path.mkdir(parents=True, exist_ok=True)

        archive_path = destination_path / archive.file_name
        archive_hash_builder = sha256()
        download_url = (
            f"{self._base_url}{JUSO_DOWNLOAD_PATH}?{parse.urlencode(archive.to_download_query())}"
        )

        with self._open(download_url) as response, archive_path.open("wb") as output_file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                archive_hash_builder.update(chunk)
                output_file.write(chunk)

        return DownloadedJusoRoadAddressArchive(
            metadata=archive,
            archive_path=archive_path,
            archive_hash=archive_hash_builder.hexdigest(),
        )

    def extract_archive(
        self,
        downloaded_archive: DownloadedJusoRoadAddressArchive,
        destination_dir: Path | str,
    ) -> ExtractedJusoRoadAddressArchive:
        destination_path = Path(destination_dir)
        destination_path.mkdir(parents=True, exist_ok=True)

        road_address_paths: list[Path] = []
        related_jibun_paths: list[Path] = []

        with ZipFile(downloaded_archive.archive_path) as zip_file:
            for member_name in sorted(zip_file.namelist()):
                normalized_name = Path(member_name).name.lower()
                if normalized_name.startswith("rnaddrkor_") and normalized_name.endswith(".txt"):
                    road_address_paths.append(
                        _safe_extract_member(zip_file, member_name, destination_path)
                    )
                elif normalized_name.startswith("jibun_rnaddrkor_") and normalized_name.endswith(
                    ".txt"
                ):
                    related_jibun_paths.append(
                        _safe_extract_member(zip_file, member_name, destination_path)
                    )

        if not road_address_paths:
            raise JusoDownloadError(
                "Downloaded Juso archive does not contain any rnaddrkor_*.txt files."
            )

        return ExtractedJusoRoadAddressArchive(
            downloaded_archive=downloaded_archive,
            road_address_paths=sorted(road_address_paths),
            related_jibun_paths=sorted(related_jibun_paths),
        )


def _as_optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)
