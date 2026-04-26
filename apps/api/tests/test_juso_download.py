from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.etl.juso.download import JusoDownloadClient, JusoMonthlyRoadAddressArchive


class _FakeResponse(BytesIO):
    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def _build_inventory_response() -> dict[str, object]:
    return {
        "status": 200,
        "results": {
            "allMonthFileList": [
                {
                    "crtrYm": "202601",
                    "fileTypeNm": "ALLRNADR_KOR",
                    "fileNm": "202601_도로명주소 한글_전체분.zip",
                    "tmprFileNm": "RNADDR_KOR_2601.zip",
                    "isExist": "Y",
                    "ctpvClsfCd": "00",
                    "fileSn": None,
                    "atflNo": None,
                },
                {
                    "crtrYm": "202603",
                    "fileTypeNm": "ALLRNADR_KOR",
                    "fileNm": "202603_도로명주소 한글_전체분.zip",
                    "tmprFileNm": "RNADDR_KOR_2603.zip",
                    "isExist": "Y",
                    "ctpvClsfCd": "00",
                    "fileSn": None,
                    "atflNo": None,
                },
                {
                    "crtrYm": "202604",
                    "fileTypeNm": "ALLRNADR_KOR",
                    "fileNm": None,
                    "tmprFileNm": None,
                    "isExist": "N",
                    "ctpvClsfCd": "00",
                    "fileSn": None,
                    "atflNo": None,
                },
            ]
        },
    }


def _build_zip_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as zip_file:
        zip_file.writestr("rnaddrkor_seoul.txt", "row-one")
        zip_file.writestr("rnaddrkor_busan.txt", "row-two")
        zip_file.writestr("jibun_rnaddrkor_seoul.txt", "jibun-row")
        zip_file.writestr("ignored/readme.txt", "ignore-me")
    return buffer.getvalue()


def test_resolve_monthly_full_road_address_archive_for_requested_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = JusoDownloadClient()
    inventory = _build_inventory_response()
    monkeypatch.setattr(
        client,
        "fetch_download_inventory",
        lambda *, reference_year_month: inventory,
    )

    archive = client.resolve_monthly_full_road_address_archive(source_year_month="202603")

    assert archive.source_year_month == "202603"
    assert archive.file_name == "202603_도로명주소 한글_전체분.zip"
    assert archive.real_file_name == "RNADDR_KOR_2603.zip"
    assert archive.to_download_query()["reqType"] == "ALLRNADR_KOR"


def test_resolve_monthly_full_road_address_archive_uses_latest_available_when_unspecified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = JusoDownloadClient()
    inventory = _build_inventory_response()
    monkeypatch.setattr(client, "_get_reference_year_month", lambda: "202604")
    monkeypatch.setattr(
        client,
        "fetch_download_inventory",
        lambda *, reference_year_month: inventory,
    )

    archive = client.resolve_monthly_full_road_address_archive()

    assert archive.source_year_month == "202603"


def test_download_archive_and_extract_relevant_text_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive = JusoMonthlyRoadAddressArchive(
        dataset_detail_serial="1",
        source_year_month="202603",
        apply_data_code="11",
        file_type_name="ALLRNADR_KOR",
        file_name="202603_도로명주소 한글_전체분.zip",
        real_file_name="RNADDR_KOR_2603.zip",
        ctpv_class_code="00",
        file_serial_no=None,
        attachment_no=None,
    )
    zip_bytes = _build_zip_bytes()
    client = JusoDownloadClient()
    monkeypatch.setattr(client, "_open", lambda url, data=None: _FakeResponse(zip_bytes))

    downloaded = client.download_archive(archive, tmp_path / "downloads")
    extracted = client.extract_archive(downloaded, tmp_path / "extracted")

    assert downloaded.archive_path.name == "202603_도로명주소 한글_전체분.zip"
    assert downloaded.archive_hash == sha256(zip_bytes).hexdigest()
    assert [path.name for path in extracted.road_address_paths] == [
        "rnaddrkor_busan.txt",
        "rnaddrkor_seoul.txt",
    ]
    assert [path.name for path in extracted.related_jibun_paths] == ["jibun_rnaddrkor_seoul.txt"]
