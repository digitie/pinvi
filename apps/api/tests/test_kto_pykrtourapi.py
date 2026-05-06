from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest
from pykrtourapi import (
    ContentType,
    KrTourApiClient,
    TourApiAuthError,
    TourApiHubClient,
    TourApiModel,
    Wgs84Coordinate,
)

from app.core.config import Settings
from app.core.kto import build_kto_hub_client, build_kto_kor_client


class _FakeTourApiResponse:
    status_code = 200

    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> Mapping[str, Any]:
        return self._payload


class _FakeTourApiSession:
    def __init__(self, response: _FakeTourApiResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any],
        timeout: float,
    ) -> _FakeTourApiResponse:
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        return self.response


def test_kto_client_factory_returns_pykrtourapi_clients_without_adapter_layer() -> None:
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
    assert hub_client.service("related_tour").definition.service_name == "TarRlteTarService1"


def test_kto_client_factory_requires_tripmate_prefixed_service_key() -> None:
    with pytest.raises(TourApiAuthError, match="TRIPMATE_KTO_SERVICE_KEY"):
        build_kto_kor_client(Settings(kto_service_key=None))


def test_pykrtourapi_location_query_preserves_tourapi_fields_and_coordinate_order() -> None:
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
        coordinate=Wgs84Coordinate(longitude=126.9769, latitude=37.5796),
        radius=15_000,
        content_type_id=ContentType.TOURIST_ATTRACTION,
    )

    assert session.calls[0]["url"].endswith("/KorService2/locationBasedList2")
    assert session.calls[0]["params"]["mapX"] == 126.9769
    assert session.calls[0]["params"]["mapY"] == 37.5796
    assert session.calls[0]["params"]["radius"] == 15_000
    assert session.calls[0]["params"]["contentTypeId"] == "12"
    assert isinstance(page.items[0], TourApiModel)
    assert page.items[0].title == "경복궁"
    assert page.items[0].addr2 is None
    assert page.items[0].map_x == 126.9769
    assert page.items[0].map_y == 37.5796
    assert page.items[0].coordinate == Wgs84Coordinate(longitude=126.9769, latitude=37.5796)
    assert page.items[0].model_dump()["title"] == "경복궁"
    assert page.items[0].raw["cpyrhtDivCd"] == "Type1"


def _tour_payload(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {
                "items": {"item": item},
                "numOfRows": 10,
                "pageNo": 1,
                "totalCount": 1,
            },
        }
    }
