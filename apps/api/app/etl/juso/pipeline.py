from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.etl.juso.download import JusoDownloadClient
from app.etl.juso.related_jibun_loader import (
    JusoRelatedJibunLoadResult,
    load_juso_related_jibun_from_files,
)
from app.etl.juso.road_address_loader import (
    JusoRoadAddressLoadResult,
    load_juso_road_address_snapshot_from_files,
)


@dataclass(frozen=True)
class JusoAddressDatasetDownloadLoadResult:
    source_year_month: str
    archive_path: Path
    archive_file_name: str
    archive_hash: str
    road_address_file_count: int
    related_jibun_file_count: int
    road_address_load_result: JusoRoadAddressLoadResult
    related_jibun_load_result: JusoRelatedJibunLoadResult


def download_and_load_juso_address_dataset(
    session: Session,
    workdir: Path | str,
    *,
    source_year_month: str | None = None,
    client: JusoDownloadClient | None = None,
) -> JusoAddressDatasetDownloadLoadResult:
    juso_client = client or JusoDownloadClient()
    archive = juso_client.resolve_monthly_full_road_address_archive(
        source_year_month=source_year_month
    )

    root_dir = Path(workdir) / archive.source_year_month
    downloaded_archive = juso_client.download_archive(archive, root_dir / "downloads")
    extracted_archive = juso_client.extract_archive(downloaded_archive, root_dir / "extracted")

    road_address_load_result = load_juso_road_address_snapshot_from_files(
        session,
        extracted_archive.road_address_paths,
        source_year_month=archive.source_year_month,
        source_file_name=archive.file_name,
        source_file_hash=downloaded_archive.archive_hash,
    )
    related_jibun_load_result = load_juso_related_jibun_from_files(
        session,
        extracted_archive.related_jibun_paths,
        source_year_month=archive.source_year_month,
        source_file_name=archive.file_name,
        source_file_hash=downloaded_archive.archive_hash,
    )

    return JusoAddressDatasetDownloadLoadResult(
        source_year_month=archive.source_year_month,
        archive_path=downloaded_archive.archive_path,
        archive_file_name=archive.file_name,
        archive_hash=downloaded_archive.archive_hash,
        road_address_file_count=len(extracted_archive.road_address_paths),
        related_jibun_file_count=len(extracted_archive.related_jibun_paths),
        road_address_load_result=road_address_load_result,
        related_jibun_load_result=related_jibun_load_result,
    )


download_and_load_juso_legal_dong_codes = download_and_load_juso_address_dataset
JusoLegalDongDownloadLoadResult = JusoAddressDatasetDownloadLoadResult
