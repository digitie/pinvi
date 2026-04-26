from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.etl.juso.download import (
    DownloadedJusoRoadAddressArchive,
    ExtractedJusoRoadAddressArchive,
    JusoDownloadClient,
    JusoMonthlyRoadAddressArchive,
)
from app.etl.juso.pipeline import download_and_load_juso_address_dataset
from app.models.address import (
    AddressCodeStandard,
    AddressRawJusoRelatedJibun,
    AddressRawJusoRoadAddress,
    AddressServingJusoRelatedJibun,
    AddressServingJusoRoadAddress,
)


def _build_juso_row(**overrides: str) -> str:
    fields = [
        "11110101310001200009400000",
        "1111010100",
        "Seoul",
        "Jongno-gu",
        "Cheongun-dong",
        "",
        "0",
        "144",
        "3",
        "111103100012",
        "Pirundae-ro",
        "0",
        "94",
        "0",
        "1111051500",
        "Cheongunhyoja-dong",
        "03047",
        "",
        "20110729",
        "0",
        "31",
        "",
        "",
        "",
    ]

    field_by_name = {
        "road_address_management_no": 0,
        "legal_dong_code": 1,
        "sido_name": 2,
        "sigungu_name": 3,
        "legal_eupmyeondong_name": 4,
        "legal_ri_name": 5,
        "mountain_yn": 6,
        "jibun_main_no": 7,
        "jibun_sub_no": 8,
        "road_name_code": 9,
        "road_name": 10,
        "underground_yn": 11,
        "building_main_no": 12,
        "building_sub_no": 13,
        "administrative_dong_code": 14,
        "administrative_dong_name": 15,
        "postal_code": 16,
        "previous_road_address": 17,
        "effective_date": 18,
        "apartment_yn": 19,
        "change_reason_code": 20,
        "building_registry_name": 21,
        "sigungu_building_name": 22,
        "note": 23,
    }

    for key, value in overrides.items():
        fields[field_by_name[key]] = value

    return "|".join(fields)


def _build_related_jibun_row(**overrides: str) -> str:
    fields = [
        "11110101310001200009400000",
        "1111010100",
        "Seoul",
        "Jongno-gu",
        "Cheongun-dong",
        "",
        "0",
        "144",
        "3",
        "111103100012",
        "0",
        "94",
        "0",
        "",
    ]

    field_by_name = {
        "road_address_management_no": 0,
        "legal_dong_code": 1,
        "sido_name": 2,
        "sigungu_name": 3,
        "legal_eupmyeondong_name": 4,
        "legal_ri_name": 5,
        "mountain_yn": 6,
        "jibun_main_no": 7,
        "jibun_sub_no": 8,
        "road_name_code": 9,
        "underground_yn": 10,
        "building_main_no": 11,
        "building_sub_no": 12,
        "note": 13,
    }

    for key, value in overrides.items():
        fields[field_by_name[key]] = value

    return "|".join(fields)


def _build_zip_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as zip_file:
        zip_file.writestr(
            "rnaddrkor_seoul.txt",
            "\n".join(
                [
                    _build_juso_row(),
                    _build_juso_row(
                        road_address_management_no="11110119200500100014900000",
                        legal_dong_code="1111012000",
                        legal_eupmyeondong_name="Sinmunno 1-ga",
                        road_name_code="111102005001",
                        road_name="Sajik-ro 8-gil",
                        building_main_no="149",
                    ),
                ]
            ),
        )
        zip_file.writestr(
            "rnaddrkor_busan.txt",
            _build_juso_row(
                road_address_management_no="26110101001000100009400000",
                legal_dong_code="2611010100",
                sido_name="Busan",
                sigungu_name="Jung-gu",
                legal_eupmyeondong_name="Donggwang-dong",
                administrative_dong_code="2611051500",
                administrative_dong_name="Donggwang-dong",
                road_name_code="261103100012",
            ),
        )
        zip_file.writestr(
            "jibun_rnaddrkor_seoul.txt",
            "\n".join(
                [
                    _build_related_jibun_row(),
                    _build_related_jibun_row(
                        road_address_management_no="11110119200500100014900000",
                        legal_dong_code="1111012000",
                        legal_eupmyeondong_name="Sinmunno 1-ga",
                        jibun_main_no="150",
                    ),
                ]
            ),
        )
    return buffer.getvalue()


class _FakeJusoDownloadClient(JusoDownloadClient):
    def __init__(self, zip_bytes: bytes) -> None:
        super().__init__(base_url="https://example.test")
        self._zip_bytes = zip_bytes
        self._archive = JusoMonthlyRoadAddressArchive(
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

    def resolve_monthly_full_road_address_archive(
        self,
        *,
        source_year_month: str | None = None,
    ) -> JusoMonthlyRoadAddressArchive:
        assert source_year_month in (None, "202603")
        return self._archive

    def download_archive(
        self,
        archive: JusoMonthlyRoadAddressArchive,
        destination_dir: Path | str,
    ) -> DownloadedJusoRoadAddressArchive:
        destination_path = Path(destination_dir)
        destination_path.mkdir(parents=True, exist_ok=True)
        archive_path = destination_path / archive.file_name
        archive_path.write_bytes(self._zip_bytes)
        return DownloadedJusoRoadAddressArchive(
            metadata=archive,
            archive_path=archive_path,
            archive_hash=sha256(self._zip_bytes).hexdigest(),
        )

    def extract_archive(
        self,
        downloaded_archive: DownloadedJusoRoadAddressArchive,
        destination_dir: Path | str,
    ) -> ExtractedJusoRoadAddressArchive:
        return super().extract_archive(downloaded_archive, destination_dir)


def test_download_and_load_juso_address_dataset(
    db_session: Session,
    tmp_path: Path,
) -> None:
    client = _FakeJusoDownloadClient(_build_zip_bytes())

    result = download_and_load_juso_address_dataset(
        db_session,
        tmp_path / "juso-workdir",
        source_year_month="202603",
        client=client,
    )
    db_session.commit()

    raw_road_rows = db_session.scalars(
        select(AddressRawJusoRoadAddress).order_by(
            AddressRawJusoRoadAddress.source_file_name,
            AddressRawJusoRoadAddress.row_number,
        )
    ).all()
    raw_related_rows = db_session.scalars(
        select(AddressRawJusoRelatedJibun).order_by(
            AddressRawJusoRelatedJibun.source_file_name,
            AddressRawJusoRelatedJibun.row_number,
        )
    ).all()
    serving_road_rows = db_session.scalars(
        select(AddressServingJusoRoadAddress).order_by(
            AddressServingJusoRoadAddress.road_address_management_no
        )
    ).all()
    serving_related_rows = db_session.scalars(
        select(AddressServingJusoRelatedJibun).order_by(
            AddressServingJusoRelatedJibun.full_jibun_address
        )
    ).all()
    legal_dong_rows = db_session.scalars(
        select(AddressCodeStandard).order_by(AddressCodeStandard.legal_dong_code)
    ).all()

    assert result.source_year_month == "202603"
    assert result.archive_file_name == "202603_도로명주소 한글_전체분.zip"
    assert result.road_address_file_count == 2
    assert result.related_jibun_file_count == 1
    assert result.road_address_load_result.source_part_count == 2
    assert result.road_address_load_result.raw_row_count == 3
    assert result.road_address_load_result.active_road_address_count == 3
    assert result.related_jibun_load_result.raw_row_count == 2
    assert result.related_jibun_load_result.active_related_jibun_count == 2
    assert len(raw_road_rows) == 3
    assert len(raw_related_rows) == 2
    assert len(serving_road_rows) == 3
    assert len(serving_related_rows) == 2
    assert len(legal_dong_rows) == 3
    assert serving_road_rows[0].source_file_name == "202603_도로명주소 한글_전체분.zip"
    assert serving_related_rows[0].source_file_name == "202603_도로명주소 한글_전체분.zip"
    assert result.archive_path.exists()
