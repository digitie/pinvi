from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from geoalchemy2.elements import WKTElement
from pykma import wgs84_to_kma_grid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.etl.weather import client as weather_client_module
from app.etl.weather.client import AirKoreaApiClient, DataGoApiError, KmaWeatherApiClient
from app.etl.weather.loader import (
    build_sigungu_weather_grid_mappings_from_boundaries,
    load_air_quality_forecasts,
    load_air_quality_sido_measurements,
    load_air_quality_stations,
    load_kma_alerts,
    load_mid_term_weather,
    load_short_term_weather_for_grids,
    resolve_mid_term_region_mappings_for_address,
    seed_kma_mid_term_regions,
)
from app.models.address import (
    AddressCodeStandard,
    RegionBoundaryImportBatch,
    RegionRawVWorldBoundary,
    RegionServingBoundary,
)
from app.models.weather import (
    AirQualityRawForecast,
    AirQualityRawSidoMeasurement,
    AirQualityRawStation,
    AirQualityServingForecast,
    AirQualityServingSidoMeasurement,
    AirQualityServingStation,
    WeatherKmaAlertStationCode,
    WeatherMidForecastRegion,
    WeatherMidRegionAddressMapping,
    WeatherRawKmaAlert,
    WeatherRawMidTerm,
    WeatherRawShortTerm,
    WeatherServingKmaAlert,
    WeatherServingMidTerm,
    WeatherServingShortTerm,
    WeatherShortTermGridMapping,
)

KST = ZoneInfo("Asia/Seoul")


class FakeKmaWeatherClient:
    def fetch_ultra_short_nowcast(self, *, nx: int, ny: int) -> list[dict[str, str]]:
        assert (nx, ny) == (60, 127)
        return [
            {
                "baseDate": "20260426",
                "baseTime": "1200",
                "category": "T1H",
                "obsrValue": "21.4",
            },
            {
                "baseDate": "20260426",
                "baseTime": "1200",
                "category": "REH",
                "obsrValue": "48",
            },
            {
                "baseDate": "20260426",
                "baseTime": "1200",
                "obsrValue": "ignored",
            },
        ]

    def fetch_ultra_short_forecast(self, *, nx: int, ny: int) -> list[dict[str, str]]:
        assert (nx, ny) == (60, 127)
        return [
            {
                "baseDate": "20260426",
                "baseTime": "1230",
                "fcstDate": "20260426",
                "fcstTime": "1400",
                "category": "SKY",
                "fcstValue": "1",
            }
        ]

    def fetch_village_forecast(self, *, nx: int, ny: int) -> list[dict[str, str]]:
        assert (nx, ny) == (60, 127)
        return [
            {
                "baseDate": "20260426",
                "baseTime": "1100",
                "fcstDate": "20260427",
                "fcstTime": "0900",
                "category": "TMP",
                "fcstValue": "18",
            }
        ]

    def fetch_weather_warnings(self, *, from_date: date, to_date: date) -> list[dict[str, str]]:
        assert from_date == date(2026, 4, 25)
        assert to_date == date(2026, 4, 26)
        return [
            {
                "stnId": "108",
                "stnNm": "전국",
                "title": "풍랑주의보 발표",
                "tmFc": "202604261100",
                "tmSeq": "1",
            }
        ]

    def fetch_weather_infos(self, *, from_date: date, to_date: date) -> list[dict[str, str]]:
        return [
            {
                "stnId": "109",
                "stnNm": "서울",
                "title": "기상정보",
                "tmFc": "202604261200",
                "tmSeq": "2",
            }
        ]

    def fetch_weather_breaking_news(
        self, *, from_date: date, to_date: date
    ) -> list[dict[str, str]]:
        return []

    def fetch_mid_outlook(self, *, stn_id: str) -> list[dict[str, str]]:
        assert stn_id == "108"
        return [{"stnId": "108", "tmFc": "202604260600", "wfSv": "전국 대체로 맑음"}]

    def fetch_mid_land_forecast(self, *, reg_id: str) -> list[dict[str, str]]:
        assert reg_id == "11B00000"
        return [
            {
                "regId": "11B00000",
                "tmFc": "202604260600",
                "wf3Am": "맑음",
                "wf3Pm": "구름많음",
                "rnSt3Am": "10",
                "rnSt3Pm": "20",
                "wf8": "흐림",
                "rnSt8": "40",
            }
        ]

    def fetch_mid_temperature(self, *, reg_id: str) -> list[dict[str, str]]:
        assert reg_id == "11B10101"
        return [
            {
                "regId": "11B10101",
                "tmFc": "202604260600",
                "taMin3": "12",
                "taMax3": "23",
            }
        ]


class PartiallyFailingKmaWeatherClient(FakeKmaWeatherClient):
    def fetch_ultra_short_forecast(self, *, nx: int, ny: int) -> list[dict[str, str]]:
        raise RuntimeError("provider timeout")


class FakeAirKoreaClient:
    def fetch_station_list(self, *, sido_name: str | None = None) -> list[dict[str, str]]:
        assert sido_name == "서울"
        return [
            {
                "stationName": "청운효자동",
                "mangName": "도시대기",
                "addr": "서울 종로구 청운효자동",
                "dmX": "37.580400",
                "dmY": "126.970700",
                "item": "SO2, CO, O3, NO2, PM10, PM25",
                "year": "2020",
            }
        ]

    def fetch_forecast_dispatches(self, *, inform_code: str | None = None) -> list[dict[str, str]]:
        return [
            {
                "informCode": inform_code or "PM10",
                "dataTime": "2026-04-26 11시 발표",
                "informData": "2026-04-27",
                "informOverall": "전 권역이 보통으로 예상됩니다.",
                "informCause": "원활한 대기 확산",
                "informGrade": "서울 : 보통",
                "actionKnack": "실외활동 가능",
            }
        ]

    def fetch_sido_measurements(self, *, sido_name: str) -> list[dict[str, str]]:
        assert sido_name == "서울"
        return [
            {
                "stationName": "청운효자동",
                "mangName": "도시대기",
                "dataTime": "2026-04-26 12:00",
                "khaiValue": "55",
                "khaiGrade": "2",
                "pm10Value": "31",
                "pm10Grade": "2",
                "pm25Value": "14",
                "pm25Grade": "2",
                "no2Value": "0.020",
                "no2Grade": "2",
                "o3Value": "0.030",
                "o3Grade": "2",
                "coValue": "0.4",
                "coGrade": "1",
                "so2Value": "0.003",
                "so2Grade": "1",
                "pm10Flag": "",
                "pm25Flag": "",
                "no2Flag": "",
                "o3Flag": "",
                "coFlag": "",
                "so2Flag": "",
            }
        ]


def test_short_term_loader_stores_raw_and_upserts_serving_with_kst_datetime(
    db_session: Session,
) -> None:
    result = load_short_term_weather_for_grids(
        db_session,
        FakeKmaWeatherClient(),  # type: ignore[arg-type]
        grids=[(60, 127)],
        collected_at=datetime(2026, 4, 26, 12, 5, tzinfo=KST),
    )
    db_session.commit()

    serving_rows = db_session.scalars(
        select(WeatherServingShortTerm).order_by(WeatherServingShortTerm.category_code)
    ).all()

    assert result.requested_grid_count == 1
    assert result.requested_endpoint_count == 3
    assert result.raw_row_count == 4
    assert result.serving_row_count == 4
    assert result.skipped_row_count == 1
    assert result.fetch_error_count == 0
    assert db_session.scalar(select(WeatherRawShortTerm)) is not None
    assert [
        (row.category_code, row.normalized_category, row.value, row.unit) for row in serving_rows
    ] == [
        ("REH", "humidity", "48", "%"),
        ("SKY", "sky", "1", None),
        ("T1H", "temperature", "21.4", "deg_c"),
        ("TMP", "temperature", "18", "deg_c"),
    ]
    assert serving_rows[0].observed_at == datetime(2026, 4, 26, 12, 0, tzinfo=KST)


def test_short_term_weather_loader_keeps_partial_grid_results_on_fetch_error(
    db_session: Session,
) -> None:
    result = load_short_term_weather_for_grids(
        db_session,
        PartiallyFailingKmaWeatherClient(),  # type: ignore[arg-type]
        grids=[(60, 127)],
        collected_at=datetime(2026, 4, 26, 12, 40, tzinfo=KST),
    )
    db_session.commit()

    serving_rows = db_session.scalars(select(WeatherServingShortTerm)).all()

    assert result.requested_endpoint_count == 3
    assert result.raw_row_count == 3
    assert result.serving_row_count == 3
    assert result.skipped_row_count == 2
    assert result.fetch_error_count == 1
    assert len(serving_rows) == 3


def test_sigungu_boundary_mapping_builds_kma_grid_mapping(db_session: Session) -> None:
    _add_address_code_and_boundary(db_session, boundary_level="sigungu", region_code="1111000000")
    expected_grid = wgs84_to_kma_grid(latitude=37.5805, longitude=126.9710)

    result = build_sigungu_weather_grid_mappings_from_boundaries(db_session)
    db_session.commit()

    mapping = db_session.scalar(select(WeatherShortTermGridMapping))

    assert result.mapping_count == 1
    assert result.skipped_count == 0
    assert mapping is not None
    assert mapping.region_code_type == "sigungu"
    assert mapping.region_code == "1111000000"
    assert mapping.legal_dong_code == "1111000000"
    assert (mapping.nx, mapping.ny) == (expected_grid.nx, expected_grid.ny)


def test_kma_alert_loader_stores_station_codes_and_alert_rows(db_session: Session) -> None:
    result = load_kma_alerts(
        db_session,
        FakeKmaWeatherClient(),  # type: ignore[arg-type]
        from_date=date(2026, 4, 25),
        to_date=date(2026, 4, 26),
        collected_at=datetime(2026, 4, 26, 12, 10, tzinfo=KST),
    )
    db_session.commit()

    stations = db_session.scalars(
        select(WeatherKmaAlertStationCode).order_by(WeatherKmaAlertStationCode.stn_id)
    ).all()
    serving_rows = db_session.scalars(
        select(WeatherServingKmaAlert).order_by(WeatherServingKmaAlert.alert_type)
    ).all()

    assert result.raw_row_count == 2
    assert result.serving_row_count == 2
    assert result.station_count == 2
    assert db_session.scalar(select(WeatherRawKmaAlert)) is not None
    assert [(station.stn_id, station.station_name) for station in stations] == [
        ("108", "전국"),
        ("109", "서울"),
    ]
    assert [row.alert_type for row in serving_rows] == ["information", "warning"]


def test_kma_alert_loader_deduplicates_station_codes_within_one_run(
    db_session: Session,
) -> None:
    class DuplicateStationClient(FakeKmaWeatherClient):
        def fetch_weather_infos(self, *, from_date: date, to_date: date) -> list[dict[str, str]]:
            return [
                {
                    "stnId": "108",
                    "stnNm": "전국",
                    "title": "기상정보",
                    "tmFc": "202604261200",
                    "tmSeq": "2",
                }
            ]

    result = load_kma_alerts(
        db_session,
        DuplicateStationClient(),  # type: ignore[arg-type]
        from_date=date(2026, 4, 25),
        to_date=date(2026, 4, 26),
        collected_at=datetime(2026, 4, 26, 12, 10, tzinfo=KST),
    )
    db_session.commit()

    assert result.raw_row_count == 2
    assert result.serving_row_count == 2
    assert result.station_count == 1
    assert db_session.scalars(select(WeatherKmaAlertStationCode)).all()[0].stn_id == "108"


def test_mid_term_region_seed_and_loader_keep_reg_id_separate_from_address_codes(
    db_session: Session,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "kma-mid-term-regions.json"
    config_path.write_text(
        json.dumps(
            {
                "source_version": "test-guide",
                "provider": "kma",
                "regions": [
                    {
                        "endpoint": "getMidFcst",
                        "region_kind": "outlook_station",
                        "provider_region_id": "108",
                        "region_name": "전국",
                    },
                    {
                        "endpoint": "getMidLandFcst",
                        "region_kind": "land",
                        "provider_region_id": "11B00000",
                        "region_name": "서울ㆍ인천ㆍ경기도",
                    },
                    {
                        "endpoint": "getMidTa",
                        "region_kind": "temperature",
                        "provider_region_id": "11B10101",
                        "region_name": "서울",
                    },
                ],
                "mappings": [
                    {
                        "endpoint": "getMidLandFcst",
                        "provider_region_kind": "land",
                        "provider_region_id": "11B00000",
                        "sido_code": "1100000000",
                        "mapping_method": "exact",
                        "priority": 10,
                    },
                    {
                        "endpoint": "getMidTa",
                        "provider_region_kind": "temperature",
                        "provider_region_id": "11B10101",
                        "sido_code": "1100000000",
                        "mapping_method": "exact",
                        "priority": 10,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    seed_result = seed_kma_mid_term_regions(
        db_session,
        config_path=config_path,
        collected_at=datetime(2026, 4, 26, 13, 0, tzinfo=KST),
    )
    load_result = load_mid_term_weather(
        db_session,
        FakeKmaWeatherClient(),  # type: ignore[arg-type]
        config_path=config_path,
        collected_at=datetime(2026, 4, 26, 13, 5, tzinfo=KST),
    )
    db_session.commit()

    land_region = db_session.scalar(
        select(WeatherMidForecastRegion).where(
            WeatherMidForecastRegion.provider_region_id == "11B00000"
        )
    )
    mapping = db_session.scalar(select(WeatherMidRegionAddressMapping))
    land_forecast = db_session.scalar(
        select(WeatherServingMidTerm)
        .where(WeatherServingMidTerm.provider_region_id == "11B00000")
        .where(WeatherServingMidTerm.forecast_slot == "am")
    )
    temp_forecast = db_session.scalar(
        select(WeatherServingMidTerm).where(WeatherServingMidTerm.provider_region_id == "11B10101")
    )

    assert seed_result.region_count == 3
    assert seed_result.mapping_count == 2
    assert load_result.requested_region_count == 3
    assert load_result.raw_row_count == 3
    assert load_result.serving_row_count >= 4
    assert db_session.scalar(select(WeatherRawMidTerm)) is not None
    assert land_region is not None
    assert land_region.provider_region_id != "1100000000"
    assert mapping is not None
    assert mapping.sido_code == "1100000000"
    assert mapping.provider_region_id == "11B00000"
    resolved_mappings = resolve_mid_term_region_mappings_for_address(
        db_session,
        legal_dong_code="1111010100",
    )
    assert {item.provider_region_id for item in resolved_mappings} == {"11B00000", "11B10101"}
    assert land_forecast is not None
    assert land_forecast.forecast_date == date(2026, 4, 29)
    assert land_forecast.weather_summary == "맑음"
    assert land_forecast.rain_probability == "10"
    assert land_forecast.mapping_method == "exact"
    assert temp_forecast is not None
    assert temp_forecast.min_temperature == "12"
    assert temp_forecast.max_temperature == "23"


def test_air_quality_station_loader_maps_station_coordinates_to_legal_dong(
    db_session: Session,
) -> None:
    _add_address_code_and_boundary(
        db_session, boundary_level="legal_dong", region_code="1111010100"
    )

    result = load_air_quality_stations(
        db_session,
        FakeAirKoreaClient(),  # type: ignore[arg-type]
        sido_names=["서울"],
        collected_at=datetime(2026, 4, 26, 12, 20, tzinfo=KST),
    )
    db_session.commit()

    station = db_session.scalar(select(AirQualityServingStation))

    assert result.raw_row_count == 1
    assert result.serving_row_count == 1
    assert result.mapped_row_count == 1
    assert db_session.scalar(select(AirQualityRawStation)) is not None
    assert station is not None
    assert station.longitude == Decimal("126.97070000")
    assert station.latitude == Decimal("37.58040000")
    assert station.legal_dong_code == "1111010100"
    assert station.mapping_method == "postgis_point_in_polygon"


def test_air_quality_station_loader_fetches_all_stations_by_default(
    db_session: Session,
) -> None:
    class AllStationClient:
        def fetch_station_list(self, *, sido_name: str | None = None) -> list[dict[str, str]]:
            assert sido_name is None
            return [
                {
                    "stationName": "중구",
                    "mangName": "도시대기",
                    "addr": "서울 중구 덕수궁길 15",
                    "dmX": "37.580400",
                    "dmY": "126.970700",
                    "item": "SO2, CO, O3, NO2, PM10, PM2.5",
                    "year": "1995",
                }
            ]

    result = load_air_quality_stations(
        db_session,
        AllStationClient(),  # type: ignore[arg-type]
        collected_at=datetime(2026, 4, 26, 12, 20, tzinfo=KST),
    )
    db_session.commit()

    station = db_session.scalar(select(AirQualityServingStation))
    raw = db_session.scalar(select(AirQualityRawStation))

    assert result.raw_row_count == 1
    assert station is not None
    assert station.sido_name == "서울"
    assert raw is not None
    assert raw.request_sido_name == "서울"


def test_air_quality_forecast_and_measurement_loaders_store_serving_rows(
    db_session: Session,
) -> None:
    forecast_result = load_air_quality_forecasts(
        db_session,
        FakeAirKoreaClient(),  # type: ignore[arg-type]
        inform_codes=["PM10"],
        collected_at=datetime(2026, 4, 26, 12, 30, tzinfo=KST),
    )
    measurement_result = load_air_quality_sido_measurements(
        db_session,
        FakeAirKoreaClient(),  # type: ignore[arg-type]
        sido_names=["서울"],
        collected_at=datetime(2026, 4, 26, 12, 35, tzinfo=KST),
    )
    db_session.commit()

    forecast = db_session.scalar(select(AirQualityServingForecast))
    measurement = db_session.scalar(select(AirQualityServingSidoMeasurement))

    assert forecast_result.raw_row_count == 1
    assert forecast_result.serving_row_count == 1
    assert measurement_result.requested_sido_count == 1
    assert measurement_result.raw_row_count == 1
    assert measurement_result.serving_row_count == 1
    assert measurement_result.skipped_row_count == 0
    assert db_session.scalar(select(AirQualityRawForecast)) is not None
    assert db_session.scalar(select(AirQualityRawSidoMeasurement)) is not None
    assert forecast is not None
    assert forecast.inform_code == "PM10"
    assert measurement is not None
    assert measurement.pm25_value == "14"
    assert measurement.no2_grade == "2"
    assert measurement.o3_grade == "2"
    assert measurement.co_grade == "1"
    assert measurement.so2_grade == "1"


def test_air_quality_measurement_loader_skips_missing_data_time(
    db_session: Session,
) -> None:
    class MissingDataTimeClient:
        def fetch_sido_measurements(self, *, sido_name: str) -> list[dict[str, str | None]]:
            assert sido_name == "test-sido"
            return [
                {
                    "stationName": "valid-station",
                    "dataTime": "2026-04-26 12:00",
                    "pm25Value": "14",
                },
                {
                    "stationName": "missing-time-station",
                    "dataTime": None,
                    "pm25Value": None,
                },
            ]

    result = load_air_quality_sido_measurements(
        db_session,
        MissingDataTimeClient(),  # type: ignore[arg-type]
        sido_names=["test-sido"],
        collected_at=datetime(2026, 4, 26, 12, 35, tzinfo=KST),
    )
    db_session.commit()

    assert result.raw_row_count == 2
    assert result.serving_row_count == 1
    assert result.skipped_row_count == 1
    assert (
        db_session.scalar(
            select(AirQualityRawSidoMeasurement).where(
                AirQualityRawSidoMeasurement.station_name == "missing-time-station"
            )
        )
        is not None
    )
    assert (
        db_session.scalar(
            select(AirQualityServingSidoMeasurement).where(
                AirQualityServingSidoMeasurement.station_name == "missing-time-station"
            )
        )
        is None
    )


def test_data_go_clients_require_service_key() -> None:
    kma_client = KmaWeatherApiClient(service_key="")
    air_client = AirKoreaApiClient(service_key="")

    with pytest.raises(DataGoApiError, match="service key"):
        kma_client.fetch_ultra_short_nowcast(nx=60, ny=127)
    with pytest.raises(DataGoApiError, match="service key"):
        air_client.fetch_sido_measurements(sido_name="서울")


def test_kma_client_treats_no_data_response_as_empty() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "03", "resultMsg": "NO_DATA"},
                    "body": {"items": {"item": []}, "totalCount": 0},
                }
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = KmaWeatherApiClient(service_key="local-test-key", client=http_client)
        rows = client.fetch_weather_breaking_news(
            from_date=date(2026, 4, 25),
            to_date=date(2026, 4, 26),
        )

    assert rows == []
    assert seen_requests[0].url.params["ServiceKey"] == "local-test-key"


def test_kma_client_delegates_explicit_short_term_call_to_pykma() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
                    "body": {
                        "items": {
                            "item": {
                                "baseDate": "20260507",
                                "baseTime": "1200",
                                "category": "T1H",
                                "obsrValue": "22.1",
                                "nx": "60",
                                "ny": "127",
                            }
                        },
                        "pageNo": 1,
                        "numOfRows": 1000,
                        "totalCount": 1,
                    },
                }
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = KmaWeatherApiClient(service_key="local-test-key", client=http_client)
        rows = client.fetch_ultra_short_nowcast(
            nx=60,
            ny=127,
            base_date="20260507",
            base_time="1200",
        )

    params = seen_requests[0].url.params
    assert seen_requests[0].url.path.endswith("/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst")
    assert params["ServiceKey"] == "local-test-key"
    assert params["numOfRows"] == "1000"
    assert rows == [
        {
            "baseDate": "20260507",
            "baseTime": "1200",
            "category": "T1H",
            "obsrValue": "22.1",
            "nx": "60",
            "ny": "127",
        }
    ]


def test_kma_client_throttles_configured_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_requests: list[httpx.Request] = []
    current_time = [100.0]
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "03", "resultMsg": "NO_DATA"},
                    "body": {"items": {"item": []}, "totalCount": 0},
                }
            },
        )

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        current_time[0] += seconds

    monkeypatch.setattr(weather_client_module.time, "monotonic", lambda: current_time[0])
    monkeypatch.setattr(weather_client_module.time, "sleep", fake_sleep)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = KmaWeatherApiClient(
            service_key="local-test-key",
            client=http_client,
            request_delay_seconds=2.5,
        )
        client.fetch_weather_infos(from_date=date(2026, 4, 25), to_date=date(2026, 4, 26))
        client.fetch_weather_breaking_news(
            from_date=date(2026, 4, 25),
            to_date=date(2026, 4, 26),
        )

    assert len(seen_requests) == 2
    assert sleeps == [2.5]


def test_kma_client_retries_rate_limited_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_requests: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        if len(seen_requests) == 1:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
                    "body": {
                        "items": {
                            "item": {
                                "baseDate": "20260507",
                                "baseTime": "1200",
                                "category": "T1H",
                                "obsrValue": "22.1",
                            }
                        },
                        "pageNo": 1,
                        "numOfRows": 1000,
                        "totalCount": 1,
                    },
                }
            },
        )

    monkeypatch.setattr(weather_client_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = KmaWeatherApiClient(
            service_key="local-test-key",
            client=http_client,
            rate_limit_max_retries=1,
            rate_limit_retry_backoff_seconds=30,
        )
        rows = client.fetch_ultra_short_nowcast(
            nx=60,
            ny=127,
            base_date="20260507",
            base_time="1200",
        )

    assert len(seen_requests) == 2
    assert sleeps == [30]
    assert rows == [
        {
            "baseDate": "20260507",
            "baseTime": "1200",
            "category": "T1H",
            "obsrValue": "22.1",
        }
    ]


def test_airkorea_client_extracts_list_items() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
                    "body": {
                        "items": [
                            {"informCode": "PM10", "dataTime": "2026-04-30"},
                            {"informCode": "PM25", "dataTime": "2026-04-30"},
                        ],
                        "totalCount": 2,
                    },
                }
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = AirKoreaApiClient(service_key="local-test-key", client=http_client)
        rows = client.fetch_forecast_dispatches(inform_code="PM10")

    assert [row["informCode"] for row in rows] == ["PM10", "PM25"]


def _add_address_code_and_boundary(
    db_session: Session,
    *,
    boundary_level: str,
    region_code: str,
) -> None:
    db_session.add_all(
        [
            AddressCodeStandard(
                legal_dong_code="1111000000",
                code_level="sigungu",
                code_name="종로구",
                sido_code="1100000000",
                sigungu_code="1111000000",
                sido_name="서울특별시",
                sigungu_name="종로구",
                legal_eupmyeondong_name=None,
                legal_ri_name=None,
                full_legal_dong_name="서울특별시 종로구",
                source_effective_date="20240101",
                source_change_reason_code="00",
                source_provider="fixture",
                source_status="active",
                source_file_name="fixture.csv",
                source_year_month="202401",
                source_file_hash="fixture",
                is_discontinued=False,
                is_active=True,
            ),
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
                source_effective_date="20240101",
                source_change_reason_code="00",
                source_provider="fixture",
                source_status="active",
                source_file_name="fixture.csv",
                source_year_month="202401",
                source_file_hash="fixture",
                is_discontinued=False,
                is_active=True,
            ),
        ]
    )
    db_session.flush()
    polygon_4326 = (
        "MULTIPOLYGON(((126.9680 37.5780,126.9740 37.5780,126.9740 37.5830,"
        "126.9680 37.5830,126.9680 37.5780)))"
    )
    batch = RegionBoundaryImportBatch(
        source_file_name="N3A_G0110000.zip",
        source_file_hash="fixture",
        layer_code="N3A_G0110000",
        boundary_level=boundary_level,
        source_encoding="cp949",
        source_srid=5179,
        serving_srid=4326,
        row_count=1,
        status="loaded",
    )
    db_session.add(batch)
    db_session.flush()
    raw = RegionRawVWorldBoundary(
        import_batch_id=batch.id,
        row_number=1,
        layer_code="N3A_G0110000",
        boundary_level=boundary_level,
        ufid=f"fixture-{region_code}",
        bjcd=region_code,
        name="청운동" if boundary_level == "legal_dong" else "종로구",
        divi="HJD010",
        scls="G0018117",
        fmta="R23120001",
        raw_attributes={},
        source_file_name="N3A_G0110000.zip",
        source_file_hash="fixture",
        geom=WKTElement(polygon_4326, srid=5179),
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        RegionServingBoundary(
            raw_boundary_id=raw.id,
            import_batch_id=batch.id,
            layer_code="N3A_G0110000",
            boundary_level=boundary_level,
            region_code=region_code,
            region_name="청운동" if boundary_level == "legal_dong" else "종로구",
            sido_code="1100000000",
            sigungu_code="1111000000",
            legal_dong_code="1111010100" if boundary_level == "legal_dong" else None,
            parent_region_code="1111000000" if boundary_level == "legal_dong" else "1100000000",
            full_region_name=(
                "서울특별시 종로구 청운동"
                if boundary_level == "legal_dong"
                else "서울특별시 종로구"
            ),
            address_code_standard_code=region_code,
            address_code_matched=True,
            source_file_name="N3A_G0110000.zip",
            source_file_hash="fixture",
            geom=WKTElement(polygon_4326, srid=4326),
        )
    )
    db_session.flush()
