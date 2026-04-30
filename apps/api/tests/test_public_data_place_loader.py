from __future__ import annotations

import io
import zipfile
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from geoalchemy2.elements import WKTElement
from pyproj import Transformer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.etl.places import public_data_places as public_place_module
from app.etl.places.public_data_places import (
    DataGoFilePageCsvClient,
    DataGoStandardApiClient,
    GoCampingApiClient,
    PublicPlaceDatasetDefinition,
    load_public_place_dataset,
)
from app.models.address import (
    AddressCodeStandard,
    RegionBoundaryImportBatch,
    RegionRawVWorldBoundary,
    RegionServingBoundary,
)
from app.models.place import (
    MapFeature,
    MapFeatureProviderRef,
    MapFeatureWebLink,
    PlaceDetail,
    SourceRecord,
)

KST = ZoneInfo("Asia/Seoul")


class FakePublicPlaceClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetch_rows(self, definition: PublicPlaceDatasetDefinition) -> list[dict[str, Any]]:
        assert definition.dataset_key
        return self.rows


def test_data_go_standard_api_client_fetches_paginated_rows(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(public_place_module, "MAX_PAGE_SIZE", 1)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page_no = request.url.params["pageNo"]
        item = {"1": {"rcrfrstNm": "첫 휴양림"}, "2": {"rcrfrstNm": "둘째 휴양림"}}[page_no]
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "OK"},
                    "body": {"totalCount": "2", "items": {"item": [item]}},
                }
            },
        )

    client = DataGoStandardApiClient(
        service_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    rows = client.fetch_rows(public_place_module.PUBLIC_PLACE_DATASETS["public_recreation_forest"])

    assert [row["rcrfrstNm"] for row in rows] == ["첫 휴양림", "둘째 휴양림"]
    assert len(requests) == 2
    assert requests[0].url.path.endswith("/tn_pubr_public_rcrfrst_api")
    assert requests[0].url.params["serviceKey"] == "test-key"
    assert requests[0].url.params["type"] == "json"


def test_data_go_standard_api_client_retries_transient_transport_error(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(public_place_module, "REQUEST_RETRY_SECONDS", 0)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("connection reset", request=request)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "OK"},
                    "body": {
                        "totalCount": "1",
                        "items": {"item": [{"rcrfrstNm": "재시도 휴양림"}]},
                    },
                }
            },
        )

    client = DataGoStandardApiClient(
        service_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    rows = client.fetch_rows(public_place_module.PUBLIC_PLACE_DATASETS["public_recreation_forest"])

    assert calls == 2
    assert rows[0]["rcrfrstNm"] == "재시도 휴양림"


def test_tourist_information_center_dataset_uses_official_standard_api_path() -> None:
    definition = public_place_module.PUBLIC_PLACE_DATASETS["public_tourist_information_center"]

    assert definition.standard_api_path == "tn_pubr_public_trsmic_api"
    assert definition.source_page_url == "https://www.data.go.kr/data/15013112/standard.do"
    assert definition.default_category_code == "01060101"


def test_go_camping_api_client_fetches_rows_with_required_params() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "0000", "resultMsg": "OK"},
                    "body": {
                        "totalCount": "1",
                        "items": {
                            "item": [
                                {
                                    "contentId": "100",
                                    "facltNm": "테스트 고캠핑",
                                    "addr1": "서울특별시 종로구 세종대로 1",
                                    "mapX": "127.0",
                                    "mapY": "37.5",
                                }
                            ]
                        },
                    },
                }
            },
        )

    client = GoCampingApiClient(
        service_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    rows = client.fetch_rows(public_place_module.PUBLIC_PLACE_DATASETS["public_campground"])

    assert rows[0]["contentId"] == "100"
    assert requests[0].url.host == "apis.data.go.kr"
    assert requests[0].url.path.endswith("/B551011/GoCamping/basedList")
    assert requests[0].url.params["serviceKey"] == "test-key"
    assert requests[0].url.params["MobileOS"] == "ETC"
    assert requests[0].url.params["MobileApp"] == "TripMate"
    assert requests[0].url.params["_type"] == "json"


def test_data_go_file_page_csv_client_extracts_download_url_and_zip_csv() -> None:
    zip_bytes = _build_zip_csv(
        "수목원.csv",
        "수목원명,주소,위도,경도\n국립테스트수목원,서울특별시 종로구 세종대로 1,37.5,127.0\n",
        encoding="cp949",
    )
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path.endswith("/fileData.do"):
            return httpx.Response(
                200,
                text=(
                    '{"@type":"DataDownload","contentUrl":'
                    '"https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_1"}'
                ),
            )
        return httpx.Response(200, content=zip_bytes)

    client = DataGoFilePageCsvClient(client=httpx.Client(transport=httpx.MockTransport(handler)))

    rows = client.fetch_rows(public_place_module.PUBLIC_PLACE_DATASETS["public_arboretum_basic"])

    assert rows == [
        {
            "수목원명": "국립테스트수목원",
            "주소": "서울특별시 종로구 세종대로 1",
            "위도": "37.5",
            "경도": "127.0",
        }
    ]
    assert requested_urls[1].startswith("https://www.data.go.kr/cmm/cmm/fileDownload.do")


def test_data_go_file_page_csv_client_retries_page_and_download_transport_errors(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(public_place_module, "REQUEST_RETRY_SECONDS", 0)
    zip_bytes = _build_zip_csv(
        "arboretum.csv",
        "name,address,latitude,longitude\nTest Garden,Seoul,37.5,127.0\n",
        encoding="utf-8",
    )
    calls: list[str] = []
    page_failed = False
    download_failed = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal page_failed, download_failed
        calls.append(str(request.url))
        if request.url.path.endswith("/fileData.do"):
            if not page_failed:
                page_failed = True
                raise httpx.ConnectError("connection reset", request=request)
            return httpx.Response(
                200,
                text=(
                    '{"@type":"DataDownload","contentUrl":'
                    '"https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_1"}'
                ),
                request=request,
            )
        if not download_failed:
            download_failed = True
            raise httpx.ConnectError("connection reset", request=request)
        return httpx.Response(200, content=zip_bytes, request=request)

    client = DataGoFilePageCsvClient(client=httpx.Client(transport=httpx.MockTransport(handler)))

    rows = client.fetch_rows(public_place_module.PUBLIC_PLACE_DATASETS["public_arboretum_basic"])

    assert calls == [
        "https://www.data.go.kr/data/15109934/fileData.do?recommendDataYn=Y",
        "https://www.data.go.kr/data/15109934/fileData.do?recommendDataYn=Y",
        "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_1",
        "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_1",
    ]
    assert rows == [
        {
            "name": "Test Garden",
            "address": "Seoul",
            "latitude": "37.5",
            "longitude": "127.0",
        }
    ]


def test_public_recreation_forest_loader_promotes_common_fields_and_keeps_extra_json(
    db_session: Session,
) -> None:
    _seed_legal_boundary(db_session)
    rows = [
        {
            "rcrfrstNm": " <b>테스트 자연휴양림</b> ",
            "rcrfrstType": "공유림",
            "rdnmadr": "서울특별시 종로구 세종대로 1",
            "latitude": "37.500000",
            "longitude": "127.000000",
            "telephoneNumber": "02-111-2222",
            "homepageUrl": "www.forest.example",
            "rcrfrstAr": "12345",
            "mainFcltyNm": "숲속의집<br>야영장",
            "referenceDate": "2026-04-01",
        }
    ]

    result = load_public_place_dataset(
        db_session,
        "public_recreation_forest",
        FakePublicPlaceClient(rows),
        collected_at=datetime(2026, 4, 27, 10, 0, tzinfo=KST),
    )
    second_result = load_public_place_dataset(
        db_session,
        "public_recreation_forest",
        FakePublicPlaceClient(rows),
        collected_at=datetime(2026, 4, 27, 10, 5, tzinfo=KST),
    )
    db_session.commit()

    features = db_session.scalars(select(MapFeature)).all()
    source_records = db_session.scalars(select(SourceRecord)).all()
    provider_refs = db_session.scalars(select(MapFeatureProviderRef)).all()
    web_links = db_session.scalars(select(MapFeatureWebLink)).all()

    assert result.raw_row_count == 1
    assert result.source_record_count == 1
    assert result.place_upsert_count == 1
    assert result.mapped_legal_dong_count == 1
    assert second_result.source_record_count == 0
    assert len(features) == 1
    assert len(source_records) == 1
    assert len(provider_refs) == 1
    assert len(web_links) == 1

    feature = features[0]
    detail = db_session.get(PlaceDetail, feature.id)
    assert detail is not None
    assert feature.name == "테스트 자연휴양림"
    assert feature.feature_type == "place"
    assert feature.category_code == "03030201"
    assert feature.legal_dong_code == "1111010100"
    assert feature.is_visible is True
    assert feature.phone == "02-111-2222"
    assert detail.address_resolution_status == "resolved"
    assert detail.extra["rcrfrstAr"] == "12345"
    assert detail.extra["mainFcltyNm"] == "숲속의집 야영장"
    assert "rdnmadr" not in detail.extra
    assert web_links[0].url == "https://www.forest.example"


def test_public_place_category_mapping_for_requested_datasets(db_session: Session) -> None:
    _seed_legal_boundary(db_session)
    definitions = [
        (
            "public_arboretum_basic",
            {
                "수목원아이디": "arboretum-test-1",
                "수목원명": "국립테스트수목원",
                "전체주소": "서울특별시 종로구 세종대로 1",
                "위도": "37.5",
                "경도": "127.0",
                "봄대표수종": "소나무",
            },
            "01030101",
        ),
        (
            "public_tourist_information_center",
            {
                "trsmicNm": "테스트 관광안내소",
                "trsmicLcNm": "테스트역 1층",
                "rdnmadr": "서울특별시 종로구 세종대로 1",
                "latitude": "37.5",
                "longitude": "127.0",
                "trsmicPhoneNumber": "02-333-4444",
                "homepageUrl": "tour.example",
                "additServiceInfo": "와이파이+짐보관",
            },
            "01060101",
        ),
        (
            "public_museum_art_gallery",
            {
                "fcltyNm": "테스트 미술관",
                "fcltyType": "공립 미술관",
                "rdnmadr": "서울특별시 종로구 세종대로 1",
                "latitude": "37.5",
                "longitude": "127.0",
                "fcltyIntrcn": "<p>전시 공간</p>",
            },
            "01040201",
        ),
    ]

    for dataset_key, row, _expected_category in definitions:
        load_public_place_dataset(
            db_session,
            dataset_key,
            FakePublicPlaceClient([row]),
            collected_at=datetime(2026, 4, 27, 11, 0, tzinfo=KST),
        )
    db_session.commit()

    rows = db_session.scalars(select(MapFeature).order_by(MapFeature.name)).all()

    categories_by_name = {row.name: row.category_code for row in rows}
    assert categories_by_name == {
        "국립테스트수목원": "01030101",
        "테스트 관광안내소": "01060101",
        "테스트 미술관": "01040201",
    }
    details = {
        detail.feature_id: detail for detail in db_session.scalars(select(PlaceDetail)).all()
    }
    museum_feature = next(row for row in rows if row.name == "테스트 미술관")
    assert details[museum_feature.id].extra["fcltyIntrcn"] == "전시 공간"
    tourist_feature = next(row for row in rows if row.name == "테스트 관광안내소")
    tourist_detail = details[tourist_feature.id]
    assert tourist_feature.phone == "02-333-4444"
    assert tourist_feature.website_url == "https://tour.example"
    assert tourist_detail.extra["additServiceInfo"] == "와이파이+짐보관"


def test_public_campground_loader_converts_epsg5174_and_hides_closed_places(
    db_session: Session,
) -> None:
    _seed_legal_boundary(db_session)
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:5174", always_xy=True)
    x, y = transformer.transform(127.0, 37.5)

    result = load_public_place_dataset(
        db_session,
        "public_campground",
        FakePublicPlaceClient(
            [
                {
                    "사업장명": "테스트 글램핑",
                    "소재지전체주소": "서울특별시 종로구 세종대로 1",
                    "좌표정보(x)": f"{x:.3f}",
                    "좌표정보(y)": f"{y:.3f}",
                    "상세영업상태명": "폐업",
                    "야영(캠핑)장구분": "글램핑",
                    "폐업일자": "20260401",
                    "편의시설": "샤워장",
                }
            ]
        ),
        collected_at=datetime(2026, 4, 27, 12, 0, tzinfo=KST),
    )
    db_session.commit()

    feature = db_session.scalar(select(MapFeature))

    assert result.mapped_legal_dong_count == 1
    assert feature is not None
    detail = db_session.get(PlaceDetail, feature.id)
    assert detail is not None
    assert feature.category_code == "03060201"
    assert feature.status == "inactive"
    assert feature.is_visible is False
    assert detail.operation_status == "closed"
    assert detail.closed_on is not None
    assert feature.legal_dong_code == "1111010100"
    assert abs(float(feature.longitude or 0) - 127.0) < 0.0001
    assert abs(float(feature.latitude or 0) - 37.5) < 0.0001
    assert detail.extra["편의시설"] == "샤워장"


def _build_zip_csv(name: str, text: str, *, encoding: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, text.encode(encoding))
    return buffer.getvalue()


def _seed_legal_boundary(session: Session) -> None:
    session.add(
        AddressCodeStandard(
            legal_dong_code="1111010100",
            code_level="legal_dong",
            code_name="청운동",
            sido_code="1100000000",
            sigungu_code="1111000000",
            sido_name="서울특별시",
            sigungu_name="종로구",
            legal_eupmyeondong_name="청운동",
            legal_ri_name=None,
            full_legal_dong_name="서울특별시 종로구 청운동",
            source_effective_date="20260401",
            source_change_reason_code="00",
            source_provider="test",
            source_status="active",
            source_file_name="test.csv",
            source_year_month="202604",
            source_file_hash="hash",
            source_sort_order=None,
            source_created_date=None,
            source_deleted_date=None,
            previous_legal_dong_code=None,
            is_discontinued=False,
            is_active=True,
        )
    )
    batch = RegionBoundaryImportBatch(
        source_file_name="boundary.zip",
        source_file_hash="boundary-hash",
        layer_code="N3A_G0110000",
        boundary_level="legal_dong",
        source_encoding="cp949",
        source_srid=5179,
        serving_srid=4326,
        row_count=1,
        status="loaded",
    )
    session.add(batch)
    session.flush()

    raw = RegionRawVWorldBoundary(
        import_batch_id=batch.id,
        row_number=1,
        layer_code="N3A_G0110000",
        boundary_level="legal_dong",
        ufid="UFID-1",
        bjcd="1111010100",
        name="청운동",
        divi="HJD",
        scls="0",
        fmta="0",
        raw_attributes={"A1": "서울특별시"},
        source_file_name="boundary.zip",
        source_file_hash="boundary-hash",
        geom=WKTElement(
            "MULTIPOLYGON(((126.9 37.4, 127.1 37.4, 127.1 37.6, 126.9 37.6, 126.9 37.4)))",
            srid=5179,
        ),
    )
    session.add(raw)
    session.flush()

    session.add(
        RegionServingBoundary(
            raw_boundary_id=raw.id,
            import_batch_id=batch.id,
            layer_code="N3A_G0110000",
            boundary_level="legal_dong",
            region_code="1111010100",
            region_name="청운동",
            sido_code="1100000000",
            sigungu_code="1111000000",
            legal_dong_code="1111010100",
            parent_region_code="1111000000",
            full_region_name="서울특별시 종로구 청운동",
            address_code_standard_code="1111010100",
            address_code_matched=True,
            source_file_name="boundary.zip",
            source_file_hash="boundary-hash",
            geom=WKTElement(
                "MULTIPOLYGON(((126.9 37.4, 127.1 37.4, 127.1 37.6, 126.9 37.6, 126.9 37.4)))",
                srid=4326,
            ),
        )
    )
    session.flush()
