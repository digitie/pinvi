from __future__ import annotations

from collections.abc import Generator, Sequence
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_kma_beach_weather_loader import _seed_legal_boundary, _seed_road_address

from app.db.session import get_db
from app.etl.beach import sources as beach_source_module
from app.etl.beach.sources import (
    KhoaBeachIndexClient,
    KhoaBeachObservationClient,
    load_khoa_beach_index_forecasts,
    load_khoa_beach_observations,
    load_mof_beach_info,
    load_mof_beach_water_quality,
)
from app.main import create_app
from app.models.beach import (
    BeachIndexForecast,
    BeachObservation,
    BeachProfile,
    BeachProviderRef,
    BeachSourceRecord,
    BeachWaterQualityMeasurement,
)

KST = ZoneInfo("Asia/Seoul")


class FakeKhoaBeachObservationClient:
    def fetch_observatory_list(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "BCH001",
                "name": "테스트 해수욕장",
                "lat": "37.500000004",
                "lon": "127.000000004",
                "data_type": "BEACH",
            }
        ]

    def fetch_observation(self, beach_code: str) -> tuple[dict[str, str], dict[str, Any] | None]:
        return (
            {"BeachCode": beach_code, "ServiceKey": "***", "ResultType": "json"},
            {
                "beach_code": beach_code,
                "beach_name": "테스트 해수욕장",
                "obs_post_name": "테스트 관측소",
                "obs_time": "2026-05-01 09:00:00",
                "tide": "보통",
                "wave_height": "0.3",
                "water_temp": "21.5",
                "wind_speed": "4.2",
                "wind_direct": "동",
                "day1_am_status": "좋음",
                "obs_last_req_cnt": "1/10000",
            },
        )


class FakeKhoaBeachIndexClient:
    def fetch_index_forecast_rows(
        self,
        *,
        req_date: date | None = None,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return (
            {"serviceKey": "***", "type": "json", "pageNo": "1", "numOfRows": "300"},
            [
                {
                    "bbchNm": "테스트 해수욕장",
                    "lat": "37.500000004",
                    "lot": "127.000000004",
                    "predcYmd": "20260501",
                    "predcNoonSeCd": "AM",
                    "maxWvhgt": "0.5",
                    "avgWtem": "21.4",
                    "avgArtmp": "26.2",
                    "maxWspd": "5.1",
                    "totalIndex": "좋음",
                    "lastScr": "82",
                }
            ],
        )


class FakeMofBeachInfoClient:
    def fetch_info_rows(self, sido_names: Sequence[str] = ("서울",)) -> list[dict[str, Any]]:
        return [
            {
                "num": "MOF-1",
                "sidoNm": "서울",
                "gugunNm": "종로구",
                "staNm": "테스트 해수욕장",
                "beachWid": "25.5",
                "beachLen": "1200",
                "beachKnd": "백사장",
                "linkAddr": "beach.example",
                "linkNm": "테스트 해수욕장",
                "beachImg": "https://example.com/beach.jpg",
                "linkTel": "02-123-4567",
                "lat": "37.500000004",
                "lon": "127.000000004",
            }
        ]


class FakeMofBeachWaterQualityClient:
    def fetch_quality_rows(
        self,
        *,
        year: int,
        sido_names: Sequence[str] = ("서울",),
    ) -> list[dict[str, Any]]:
        return [
            {
                "num": "MOF-1",
                "sidoNm": "서울",
                "gugunNm": "종로구",
                "staNm": "테스트 해수욕장",
                "resNum": "1차",
                "resLoc": "대표 지점",
                "res1": "적합",
                "res2": "적합",
                "resYn": "적합",
                "resYear": str(year),
                "resDate": "2026-05-01",
                "resKnd": "개장 전",
                "resLocDetail": "중앙",
                "lat": "37.500000004",
                "lon": "127.000000004",
            }
        ]


def test_khoa_beach_index_client_uses_data_go_gateway_endpoint(monkeypatch: Any) -> None:
    monkeypatch.setattr(beach_source_module, "MAX_PAGE_SIZE", 1)
    requests: list[Any] = []

    def handler(request: Any) -> Any:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "OK"},
                    "body": {
                        "totalCount": "1",
                        "items": {
                            "item": [
                                {
                                    "bbchNm": "테스트 해수욕장",
                                    "predcYmd": "20260501",
                                    "predcNoonSeCd": "AM",
                                }
                            ]
                        },
                    },
                }
            },
        )

    client = KhoaBeachIndexClient(
        service_key="test-key%3D%3D",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    request_params, rows = client.fetch_index_forecast_rows(req_date=date(2026, 5, 1))

    assert rows[0]["bbchNm"] == "테스트 해수욕장"
    assert request_params["serviceKey"] == "***"
    assert requests[0].url.host == "apis.data.go.kr"
    assert requests[0].url.path.endswith("/1192136/fcstBeachv2")
    assert requests[0].url.params["serviceKey"] == "test-key=="
    assert "serviceKey=test-key%3D%3D" in str(requests[0].url)
    assert "%253D" not in str(requests[0].url)
    assert requests[0].url.params["reqDate"] == "20260501"


def test_khoa_beach_observation_client_accepts_top_level_observatory_list() -> None:
    def handler(request: Any) -> httpx.Response:
        assert str(request.url).endswith("/oceandata/openapi/getOpenApiInfo.do")
        return httpx.Response(
            200,
            json={
                "observatoryList": [
                    {
                        "id": "BCH001",
                        "name": "테스트 해수욕장",
                        "data_type": "BEACH",
                        "lat": 37.5,
                        "lon": 127.0,
                    }
                ]
            },
        )

    client = KhoaBeachObservationClient(
        service_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    rows = client.fetch_observatory_list()

    assert rows == [
        {
            "id": "BCH001",
            "name": "테스트 해수욕장",
            "data_type": "BEACH",
            "lat": 37.5,
            "lon": 127.0,
        }
    ]


def test_integrated_beach_sources_share_profile_and_are_queryable(
    db_session: Session,
) -> None:
    _seed_legal_boundary(db_session)
    _seed_road_address(db_session)

    collected_at = datetime(2026, 5, 1, 10, 0, tzinfo=KST)
    observation_result = load_khoa_beach_observations(
        db_session,
        FakeKhoaBeachObservationClient(),
        collected_at=collected_at,
    )
    info_result = load_mof_beach_info(
        db_session,
        FakeMofBeachInfoClient(),
        collected_at=collected_at,
        sido_names=("서울",),
    )
    index_result = load_khoa_beach_index_forecasts(
        db_session,
        FakeKhoaBeachIndexClient(),
        collected_at=collected_at,
        req_date=date(2026, 5, 1),
    )
    quality_result = load_mof_beach_water_quality(
        db_session,
        FakeMofBeachWaterQualityClient(),
        year=2026,
        collected_at=collected_at,
        sido_names=("서울",),
    )
    second_observation_result = load_khoa_beach_observations(
        db_session,
        FakeKhoaBeachObservationClient(),
        collected_at=collected_at,
    )
    db_session.commit()

    profile = db_session.scalar(select(BeachProfile))
    provider_refs = db_session.scalars(select(BeachProviderRef)).all()
    source_records = db_session.scalars(select(BeachSourceRecord)).all()
    observations = db_session.scalars(select(BeachObservation)).all()
    forecasts = db_session.scalars(select(BeachIndexForecast)).all()
    quality_rows = db_session.scalars(select(BeachWaterQualityMeasurement)).all()

    assert observation_result.raw_row_count == 1
    assert second_observation_result.raw_row_count == 0
    assert info_result.source_record_count == 1
    assert index_result.forecast_row_count == 1
    assert quality_result.measurement_row_count == 1
    assert profile is not None
    assert profile.display_name == "테스트 해수욕장"
    assert profile.legal_dong_code == "1111010100"
    assert profile.road_name_code == "111103000001"
    assert profile.address_mapping_method == "juso_building_name_in_legal_dong"
    assert str(profile.beach_width_m) == "25.50"
    assert profile.homepage_url == "https://beach.example"
    assert len(provider_refs) == 4
    assert len(source_records) == 4
    assert len(observations) == 1
    assert len(forecasts) == 1
    assert len(quality_rows) == 1

    client = _build_client(db_session)
    response = client.get("/public/beaches", params={"query": "테스트", "limit": 10})

    assert response.status_code == 200
    payload = response.json()
    beach_payload = payload["beaches"][0]
    assert payload["count"] == 1
    assert beach_payload["display_name"] == "테스트 해수욕장"
    assert beach_payload["latest_observation"]["water_temperature_c"] == "21.500"
    assert beach_payload["latest_water_quality"]["suitability"] == "적합"
    assert beach_payload["upcoming_index_forecasts"][0]["total_index"] == "좋음"
    assert sorted(beach_payload["source_providers"]) == ["data_go_kr", "khoa"]


def _build_client(db_session: Session) -> TestClient:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)
