from __future__ import annotations

import zipfile
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.etl.vworld.legal_dong_code_loader import (
    DATA_GO_LEGAL_DONG_PAGE_URL,
    download_latest_legal_dong_code_csv,
    load_latest_legal_dong_code_from_data_go,
    load_legal_dong_code_csv,
    load_legal_dong_code_zip,
)
from app.models.address import AddressCodeStandard, AddressRawLegalDongCode


def test_load_data_go_legal_dong_code_csv_sets_canonical_code_standard(
    db_session: Session,
    tmp_path: Path,
) -> None:
    csv_path = _write_data_go_code_csv(
        tmp_path,
        [
            ("1100000000", "서울특별시", "", "", "", "11", "1988-04-23", "", ""),
            ("1111000000", "서울특별시", "종로구", "", "", "1", "1988-04-23", "", ""),
            ("1111010100", "서울특별시", "종로구", "청운동", "", "1", "1988-04-23", "", ""),
            (
                "1111010200",
                "서울특별시",
                "종로구",
                "신교동",
                "",
                "2",
                "1988-04-23",
                "2024-01-01",
                "1111010199",
            ),
            ("3611000000", "세종특별자치시", "", "", "", "1", "2012-07-01", "", ""),
            ("3611010100", "세종특별자치시", "", "반곡동", "", "1", "2020-07-15", "", ""),
        ],
    )

    result = load_legal_dong_code_csv(db_session, csv_path)
    db_session.commit()

    rows = db_session.scalars(
        select(AddressCodeStandard).order_by(AddressCodeStandard.legal_dong_code)
    ).all()
    raw_rows = db_session.scalars(select(AddressRawLegalDongCode)).all()

    assert result.raw_row_count == 6
    assert result.raw_rows_inserted == 6
    assert result.active_code_count == 5
    assert result.discontinued_code_count == 1
    assert len(raw_rows) == 6
    assert [row.legal_dong_code for row in rows] == [
        "1100000000",
        "1111000000",
        "1111010100",
        "1111010200",
        "3611000000",
        "3611010100",
    ]
    assert rows[0].code_level == "sido"
    assert rows[0].source_provider == "data_go_legal_dong"
    assert rows[1].code_level == "sigungu"
    assert rows[2].code_level == "legal_dong"
    assert rows[2].sido_code == "1100000000"
    assert rows[2].sigungu_code == "1111000000"
    assert rows[2].legal_eupmyeondong_name == "청운동"
    assert rows[2].source_created_date == "1988-04-23"
    assert rows[2].source_sort_order == 1
    assert rows[3].is_active is False
    assert rows[3].is_discontinued is True
    assert rows[3].source_deleted_date == "2024-01-01"
    assert rows[3].previous_legal_dong_code == "1111010199"
    assert rows[4].sido_name == "세종특별자치시"
    assert rows[4].sigungu_name is None
    assert rows[5].sido_name == "세종특별자치시"
    assert rows[5].sigungu_name is None
    assert rows[5].legal_eupmyeondong_name == "반곡동"


def test_load_legacy_vworld_zip_retains_missing_existing_codes_for_fk_safety(
    db_session: Session,
    tmp_path: Path,
) -> None:
    first_csv = _write_legacy_code_csv(
        tmp_path / "first",
        [
            ("1100000000", "서울특별시", "존재"),
            ("1111000000", "서울특별시 종로구", "존재"),
            ("1111010100", "서울특별시 종로구 청운동", "존재"),
        ],
    )
    load_legal_dong_code_csv(db_session, first_csv, source_file_name="LSCT_LAWDCD_20250101.csv")

    second_csv = _write_legacy_code_csv(
        tmp_path / "second",
        [
            ("1100000000", "서울특별시", "존재"),
            ("1111000000", "서울특별시 종로구", "존재"),
        ],
    )
    zip_path = tmp_path / "LSCT_LAWDCD_20250201.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(second_csv, arcname="LSCT_LAWDCD_20250201.csv")

    result = load_legal_dong_code_zip(db_session, zip_path)
    db_session.commit()

    retained = db_session.get(AddressCodeStandard, "1111010100")
    assert result.retained_missing_code_count == 1
    assert retained is not None
    assert retained.is_active is False
    assert retained.is_discontinued is True
    assert retained.source_status == "missing_from_latest_download"


def test_download_latest_legal_dong_code_csv_uses_data_go_content_url(tmp_path: Path) -> None:
    csv_bytes = _data_go_csv_text(
        [("1100000000", "서울특별시", "", "", "", "11", "1988-04-23", "", "")]
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == DATA_GO_LEGAL_DONG_PAGE_URL:
            return httpx.Response(
                200,
                text=(
                    '<script type="application/ld+json">'
                    '{"contentUrl":"https://www.data.go.kr/cmm/cmm/fileDownload.do?'
                    'atchFileId=FILE_1&fileDetailSn=1&insertDataPrcus=N"}'
                    "</script>"
                ),
            )
        return httpx.Response(
            200,
            content=csv_bytes,
            headers={"content-disposition": 'attachment; filename="legal_dong.csv"'},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = download_latest_legal_dong_code_csv(tmp_path, client=client)

    assert result.download_url.startswith("https://www.data.go.kr/cmm/cmm/fileDownload.do")
    assert result.file_path.name == "legal_dong.csv"
    assert result.file_path.read_bytes() == csv_bytes


def test_load_latest_legal_dong_code_from_data_go_downloads_and_loads(
    db_session: Session,
    tmp_path: Path,
) -> None:
    csv_bytes = _data_go_csv_text(
        [
            ("1100000000", "서울특별시", "", "", "", "11", "1988-04-23", "", ""),
            ("1111000000", "서울특별시", "종로구", "", "", "1", "1988-04-23", "", ""),
        ]
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == DATA_GO_LEGAL_DONG_PAGE_URL:
            return httpx.Response(
                200,
                text='{"contentUrl":"https://www.data.go.kr/cmm/cmm/fileDownload.do?x=1"}',
            )
        return httpx.Response(200, content=csv_bytes)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = load_latest_legal_dong_code_from_data_go(db_session, tmp_path, client=client)
    db_session.commit()

    assert result.raw_row_count == 2
    assert db_session.get(AddressCodeStandard, "1111000000") is not None


def _write_data_go_code_csv(tmp_path: Path, rows: list[tuple[str, ...]]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_path / "국토교통부_전국 법정동_20250807.csv"
    csv_path.write_text(_data_go_csv_text(rows), encoding="utf-8")
    return csv_path


def _write_legacy_code_csv(tmp_path: Path, rows: list[tuple[str, str, str]]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_path / "LSCT_LAWDCD_20250101.csv"
    lines = ["법정동코드,법정동명,폐지여부"]
    lines.extend([",".join(row) for row in rows])
    csv_path.write_text("\n".join(lines), encoding="cp949")
    return csv_path


def _data_go_csv_text(rows: list[tuple[str, ...]]) -> str:
    lines = ["법정동코드,시도명,시군구명,읍면동명,리명,순위,생성일자,삭제일자,과거법정동코드"]
    lines.extend([",".join(row) for row in rows])
    return "\n".join(lines)
