from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest
from visitkorea import (
    ContentType,
    KrTourApiClient,
    RelatedTourItem,
    TourApiAuthError,
    TourApiHubClient,
    TourApiModel,
    TourApiRateLimitError,
    Wgs84Coordinate,
    clean_tourapi_html,
    copyright_display_info,
)

from app.core.config import Settings
from app.core.kto import build_kto_hub_client, build_kto_kor_client


class _FakeTourApiResponse:
    def __init__(self, payload: Mapping[str, Any], *, status_code: int = 200) -> None:
        self._payload = payload
        self.text = json.dumps(payload)
        self.status_code = status_code

    def json(self) -> Mapping[str, Any]:
        return self._payload


class _FakeTourApiSession:
    def __init__(self, responses: _FakeTourApiResponse | list[_FakeTourApiResponse]) -> None:
        self._responses = responses if isinstance(responses, list) else [responses]
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any],
        timeout: float,
    ) -> _FakeTourApiResponse:
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        if not self._responses:
            raise AssertionError("no fake TourAPI response left")
        return self._responses.pop(0)


def test_kto_client_factory_returns_visitkorea_clients_without_adapter_layer() -> None:
    settings = Settings(
        kto_service_key="dummy-kto-key",
        kto_mobile_app="TripMate-Test",
        kto_mobile_os="WEB",
        kto_timeout_seconds=1.5,
        kto_max_retries=0,
    )

    kor_client = build_kto_kor_client(settings)
    hub_client = build_kto_hub_client(settings)

    assert isinstance(kor_client, KrTourApiClient)
    assert isinstance(hub_client, TourApiHubClient)
    assert kor_client.service_name == "KorService2"
    assert kor_client.mobile_os == "WEB"
    assert kor_client.mobile_app == "TripMate-Test"
    assert kor_client.timeout == 1.5
    assert hub_client.related_tour.definition.service_name == "TarRlteTarService1"


def test_kto_client_factory_requires_tripmate_prefixed_service_key() -> None:
    with pytest.raises(TourApiAuthError, match="TRIPMATE_KTO_SERVICE_KEY"):
        build_kto_kor_client(Settings(kto_service_key=None))


def test_visitkorea_location_query_preserves_tourapi_fields_and_coordinate_order() -> None:
    session = _FakeTourApiSession(
        _FakeTourApiResponse(
            _tour_payload(
                {
                    "contentid": "126508",
                    "contenttypeid": "12",
                    "title": "경복궁",
                    "addr1": "서울특별시 종로구 사직로 161",
                    "addr2": "",
                    "areacode": "1",
                    "sigungucode": "23",
                    "mapx": "126.9769",
                    "mapy": "37.5796",
                    "dist": "142.5",
                    "cpyrhtDivCd": "Type1",
                    "modifiedtime": "20260430112233",
                }
            )
        )
    )
    client = KrTourApiClient(
        "dummy-kto-key",
        mobile_os="WEB",
        mobile_app="TripMate-Test",
        session=session,
        timeout=1.5,
        retries=0,
    )

    page = client.location_based_list(
        coordinate=Wgs84Coordinate(lat=37.5796, lon=126.9769),
        radius=15_000,
        content_type_id=ContentType.TOURIST_ATTRACTION,
    )

    assert session.calls[0]["url"].endswith("/KorService2/locationBasedList2")
    assert session.calls[0]["params"]["mapX"] == 126.9769
    assert session.calls[0]["params"]["mapY"] == 37.5796
    assert session.calls[0]["params"]["radius"] == 15_000
    assert session.calls[0]["params"]["contentTypeId"] == "12"
    assert page.context.service_name == "KorService2"
    assert page.context.endpoint == "locationBasedList2"
    assert page.context.request_params["MobileOS"] == "WEB"
    assert page.context.request_params["MobileApp"] == "TripMate-Test"
    assert page.context.request_params["contentTypeId"] == "12"
    assert "serviceKey" not in page.context.request_params
    assert page.endpoint == "locationBasedList2"
    assert page.has_next_page is False
    assert isinstance(page.items[0], TourApiModel)
    assert page.items[0].title == "경복궁"
    assert page.items[0].addr2 is None
    assert page.items[0].map_x == 126.9769
    assert page.items[0].map_y == 37.5796
    assert page.items[0].coordinate == Wgs84Coordinate(lat=37.5796, lon=126.9769)
    assert page.items[0].model_dump()["title"] == "경복궁"
    assert page.items[0].model_dump(mode="json")["modified_time"] == "2026-04-30T11:22:33+09:00"
    assert page.items[0].raw["cpyrhtDivCd"] == "Type1"
    assert copyright_display_info(page.items[0].copyright_division_code).code == "Type1"


def test_visitkorea_related_tour_helper_returns_typed_records_without_tripmate_adapter() -> None:
    session = _FakeTourApiSession(
        _FakeTourApiResponse(
            _tour_payload(
                {
                    "baseYm": "202504",
                    "tAtsCd": "3dbadaccd57c18ae536e552040025fa8",
                    "tAtsNm": "간현관광지",
                    "areaCd": "51",
                    "areaNm": "강원특별자치도",
                    "signguCd": "51130",
                    "signguNm": "원주시",
                    "rlteTatsCd": "0bfeca2105aa7bf8d83e4622e5da19ec",
                    "rlteTatsNm": "뮤지엄산",
                    "rlteRegnCd": "51",
                    "rlteRegnNm": "강원특별자치도",
                    "rlteSignguCd": "51130",
                    "rlteSignguNm": "원주시",
                    "rlteCtgryLclsNm": "관광지",
                    "rlteCtgryMclsNm": "문화관광",
                    "rlteCtgrySclsNm": "전시시설",
                    "rlteRank": "1",
                }
            )
        )
    )
    hub_client = TourApiHubClient(
        "dummy-kto-key",
        mobile_os="WEB",
        mobile_app="TripMate-Test",
        session=session,
        timeout=1.5,
        retries=0,
    )

    page = hub_client.related_tour.area_based_list(
        base_ym="202504",
        area_cd="51",
        signgu_cd="51130",
    )

    assert session.calls[0]["url"].endswith("/TarRlteTarService1/areaBasedList1")
    assert session.calls[0]["params"]["baseYm"] == "202504"
    assert session.calls[0]["params"]["areaCd"] == "51"
    assert session.calls[0]["params"]["signguCd"] == "51130"
    assert isinstance(page.items[0], RelatedTourItem)
    assert page.items[0].baseYm == "202504"
    assert page.items[0].rlteTatsNm == "뮤지엄산"
    assert page.items[0].rlteRank == "1"
    assert page.context.service_name == "TarRlteTarService1"
    assert page.context.endpoint == "areaBasedList1"
    assert "serviceKey" not in page.context.request_params


def test_visitkorea_pagination_and_display_helpers_are_used_directly() -> None:
    session = _FakeTourApiSession(
        [
            _FakeTourApiResponse(
                _tour_payload(
                    {"code": "1", "name": "서울"},
                    page_no=1,
                    num_of_rows=1,
                    total_count=2,
                )
            ),
            _FakeTourApiResponse(
                _tour_payload(
                    {"code": "2", "name": "인천"},
                    page_no=2,
                    num_of_rows=1,
                    total_count=2,
                )
            ),
        ]
    )
    client = KrTourApiClient(
        "dummy-kto-key",
        mobile_os="WEB",
        mobile_app="TripMate-Test",
        session=session,
        timeout=1.5,
        retries=0,
    )

    pages = list(client.iter_pages(client.area_codes, num_of_rows=1, max_pages=2))

    assert [page.page_no for page in pages] == [1, 2]
    assert [item.code for page in pages for item in page.items] == ["1", "2"]
    assert pages[0].has_next_page is True
    assert pages[0].next_page_no == 2
    assert [call["params"]["pageNo"] for call in session.calls] == [1, 2]
    assert copyright_display_info(" type-03 ").known is True
    assert clean_tourapi_html("<p>첫 줄<br>둘째 줄</p>") == "첫 줄\n둘째 줄"


def test_visitkorea_exception_metadata_is_available_without_tripmate_mapping() -> None:
    session = _FakeTourApiSession(
        _FakeTourApiResponse({"message": "traffic limit"}, status_code=429)
    )
    client = KrTourApiClient(
        "dummy-kto-key",
        mobile_os="WEB",
        mobile_app="TripMate-Test",
        session=session,
        timeout=1.5,
        retries=0,
    )

    with pytest.raises(TourApiRateLimitError) as exc_info:
        client.area_codes()

    error = exc_info.value
    assert error.metadata["status_code"] == 429
    assert error.metadata["endpoint"] == "areaCode2"
    assert error.metadata["service_name"] == "KorService2"
    assert error.metadata["failure_kind"] == "rate_limit"
    assert "dummy-kto-key" not in str(error)


def _tour_payload(
    item: Mapping[str, Any],
    *,
    page_no: int = 1,
    num_of_rows: int = 10,
    total_count: int = 1,
) -> dict[str, Any]:
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {
                "items": {"item": item},
                "numOfRows": num_of_rows,
                "pageNo": page_no,
                "totalCount": total_count,
            },
        }
    }
