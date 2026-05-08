from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_public_data_place_loader import _seed_legal_boundary

from app.etl.ocean import khoa_indices as ocean_module
from app.etl.ocean.khoa_indices import (
    KHOA_MUDFLAT_INDEX_DATASET_KEY,
    KHOA_SEA_SPLIT_INDEX_DATASET_KEY,
    KhoaOceanIndexClient,
    KhoaOceanIndexDatasetDefinition,
    load_khoa_ocean_index_dataset,
)
from app.models.ocean import (
    OceanActivityIndexForecast,
    OceanActivityIndexLocation,
    OceanActivityIndexSourceRecord,
)

KST = ZoneInfo("Asia/Seoul")


class FakeKhoaOceanIndexClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetch_rows(
        self,
        definition: KhoaOceanIndexDatasetDefinition,
        *,
        req_date: date | None = None,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        assert definition.dataset_key
        assert req_date == date(2026, 5, 1)
        return (
            {
                "serviceKey": "***",
                "type": "json",
                "pageNo": "1",
                "numOfRows": "300",
                "reqDate": "20260501",
            },
            self.rows,
        )


def test_khoa_ocean_index_client_fetches_data_go_gateway_rows(monkeypatch: Any) -> None:
    monkeypatch.setattr(ocean_module, "MAX_PAGE_SIZE", 1)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page_no = request.url.params["pageNo"]
        item = {
            "1": {"placeName": "첫 갯벌", "predcYmd": "20260501"},
            "2": {"placeName": "둘째 갯벌", "predcYmd": "20260501"},
        }[page_no]
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "OK"},
                    "body": {"totalCount": "2", "items": {"item": [item]}},
                }
            },
        )

    client = KhoaOceanIndexClient(
        service_key="test-key%3D%3D",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    request_params, rows = client.fetch_rows(
        ocean_module.KHOA_OCEAN_INDEX_DATASETS[KHOA_MUDFLAT_INDEX_DATASET_KEY],
        req_date=date(2026, 5, 1),
    )

    assert [row["placeName"] for row in rows] == ["첫 갯벌", "둘째 갯벌"]
    assert request_params["serviceKey"] == "***"
    assert len(requests) == 2
    assert requests[0].url.host == "apis.data.go.kr"
    assert requests[0].url.path.endswith("/1192136/fcstMudflatv2")
    assert requests[0].url.params["serviceKey"] == "test-key=="
    assert "serviceKey=test-key%3D%3D" in str(requests[0].url)
    assert "%253D" not in str(requests[0].url)
    assert requests[0].url.params["reqDate"] == "20260501"


def test_khoa_ocean_index_client_redacts_service_key_on_http_error() -> None:
    secret = "secret-key%3D%3D"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request, text="temporary provider failure")

    client = KhoaOceanIndexClient(
        service_key=secret,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ocean_module.KhoaOceanIndexError) as exc_info:
        client.fetch_rows(
            ocean_module.KHOA_OCEAN_INDEX_DATASETS[KHOA_MUDFLAT_INDEX_DATASET_KEY],
            req_date=date(2026, 5, 1),
        )

    message = str(exc_info.value)
    assert "khoa_mudflat_index_forecast request failed" in message
    assert "serviceKey=***" in message
    assert secret not in message
    assert "secret-key" not in message


def test_khoa_ocean_index_loader_maps_coordinate_and_is_idempotent(
    db_session: Session,
) -> None:
    _seed_legal_boundary(db_session)
    rows = [
        {
            "placeCode": "MUD001",
            "placeName": "테스트 갯벌",
            "lat": "37.500000004",
            "lot": "127.000000004",
            "predcYmd": "20260501",
            "predcNoonSeCd": "AM",
            "exprnBgngTm": "09:00",
            "exprnEndTm": "12:30",
            "wthr": "맑음",
            "artmp": "23.4",
            "wspd": "3.2",
            "totalIndex": "좋음",
            "lastScr": "85",
        },
        {"placeCode": "SKIP", "predcYmd": "20260501"},
    ]

    collected_at = datetime(2026, 5, 1, 6, 40, tzinfo=KST)
    result = load_khoa_ocean_index_dataset(
        db_session,
        KHOA_MUDFLAT_INDEX_DATASET_KEY,
        FakeKhoaOceanIndexClient(rows),
        collected_at=collected_at,
        req_date=date(2026, 5, 1),
    )
    second_result = load_khoa_ocean_index_dataset(
        db_session,
        KHOA_MUDFLAT_INDEX_DATASET_KEY,
        FakeKhoaOceanIndexClient(rows),
        collected_at=collected_at,
        req_date=date(2026, 5, 1),
    )
    db_session.commit()

    locations = db_session.scalars(select(OceanActivityIndexLocation)).all()
    source_records = db_session.scalars(select(OceanActivityIndexSourceRecord)).all()
    forecasts = db_session.scalars(select(OceanActivityIndexForecast)).all()

    assert result.raw_row_count == 2
    assert result.source_record_count == 1
    assert result.location_upsert_count == 1
    assert result.forecast_row_count == 1
    assert result.mapped_legal_dong_count == 1
    assert result.skipped_row_count == 1
    assert second_result.source_record_count == 0
    assert len(locations) == 1
    assert len(source_records) == 1
    assert len(forecasts) == 1

    location = locations[0]
    forecast = forecasts[0]
    assert location.provider_dataset_key == KHOA_MUDFLAT_INDEX_DATASET_KEY
    assert location.provider_place_code == "MUD001"
    assert location.display_name == "테스트 갯벌"
    assert location.legal_dong_code == "1111010100"
    assert location.address_mapping_method == "postgis_point_in_polygon"
    assert forecast.forecast_date == date(2026, 5, 1)
    assert forecast.forecast_slot == "AM"
    assert forecast.activity_start_at == datetime(2026, 5, 1, 9, 0, tzinfo=KST)
    assert forecast.activity_end_at == datetime(2026, 5, 1, 12, 30, tzinfo=KST)
    assert str(forecast.index_score) == "85.000"
    assert forecast.total_index == "좋음"
    assert forecast.weather == "맑음"


def test_khoa_sea_split_loader_keeps_activity_time_text_when_times_are_unstructured(
    db_session: Session,
) -> None:
    rows = [
        {
            "placeName": "테스트 바다갈라짐",
            "predcYmd": "20260501",
            "exprnHrCn": "10:00~13:00, 22:00~23:00",
            "grdCn": "매우좋음",
            "score": "90",
        }
    ]

    result = load_khoa_ocean_index_dataset(
        db_session,
        KHOA_SEA_SPLIT_INDEX_DATASET_KEY,
        FakeKhoaOceanIndexClient(rows),
        collected_at=datetime(2026, 5, 1, 18, 50, tzinfo=KST),
        req_date=date(2026, 5, 1),
    )
    db_session.commit()

    location = db_session.scalar(select(OceanActivityIndexLocation))
    forecast = db_session.scalar(select(OceanActivityIndexForecast))

    assert result.forecast_row_count == 1
    assert location is not None
    assert location.address_mapping_method == "unmapped"
    assert forecast is not None
    assert forecast.activity_time_text == "10:00~13:00, 22:00~23:00"
    assert forecast.grade == "매우좋음"
    assert str(forecast.index_score) == "90.000"
