from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.etl.weather.beach import (
    KMA_BEACH_SUN_ENDPOINT,
    KMA_BEACH_TIDE_ENDPOINT,
    KMA_BEACH_ULTRA_SHORT_ENDPOINT,
    KMA_BEACH_WATER_TEMP_ENDPOINT,
    KMA_BEACH_WAVE_ENDPOINT,
    KmaBeachWeatherClient,
    load_beach_catalog,
    load_beach_weather_for_active_locations,
)
from app.models.address import (
    AddressCodeStandard,
    AddressServingJusoRoadAddress,
    RegionBoundaryImportBatch,
    RegionRawVWorldBoundary,
    RegionServingBoundary,
)
from app.models.place import (
    MapFeature,
    MapFeatureProviderRef,
    MapFeatureSourceLink,
    PlaceDetail,
    SourceRecord,
)
from app.models.weather import WeatherBeachLocation, WeatherRawBeach, WeatherServingBeach

KST = ZoneInfo("Asia/Seoul")


class FakeBeachCatalogClient:
    def fetch_beach_catalog_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "순번": "1",
                "해수욕장": "테스트 해수욕장",
                "nx": "60",
                "ny": "127",
                "경도": "127.000000004",
                "위도": "37.500000004",
                "_source_file_name": "기상청48_전국해수욕장_날씨_조회서비스_위경도.xlsx",
                "_source_file_hash": "catalog-hash",
                "_source_row_number": 2,
            }
        ]


class TwoBeachCatalogClient(FakeBeachCatalogClient):
    def fetch_beach_catalog_rows(self) -> list[dict[str, Any]]:
        rows = super().fetch_beach_catalog_rows()
        second = dict(rows[0])
        second["순번"] = "2"
        second["해수욕장"] = "실패 해수욕장"
        second["_source_row_number"] = 3
        rows.append(second)
        return rows


class FlakyCatalogDownloadHttpClient:
    def __init__(self) -> None:
        self.call_count = 0

    def get(self, *args: Any, **kwargs: Any) -> httpx.Response:
        self.call_count += 1
        if self.call_count == 1:
            raise httpx.ConnectError("connection reset by peer")
        request = httpx.Request("GET", "https://example.test/catalog.zip")
        return httpx.Response(200, content=b"catalog-archive", request=request)


class FakeBeachWeatherClient:
    def fetch_ultra_short_forecast(
        self,
        *,
        beach_num: str,
        base_date: str,
        base_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return (
            {
                "dataType": "JSON",
                "beach_num": beach_num,
                "base_date": base_date,
                "base_time": base_time,
            },
            [
                {
                    "beachNum": beach_num,
                    "baseDate": base_date,
                    "baseTime": base_time,
                    "category": "TMP",
                    "fcstDate": "20260601",
                    "fcstTime": "1200",
                    "fcstValue": "24",
                    "nx": "60",
                    "ny": "127",
                }
            ],
        )

    def fetch_village_forecast(
        self,
        *,
        beach_num: str,
        base_date: str,
        base_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        raise AssertionError("not used")

    def fetch_wave_height(
        self,
        *,
        beach_num: str,
        search_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        raise AssertionError("not used")

    def fetch_water_temperature(
        self,
        *,
        beach_num: str,
        search_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        raise AssertionError("not used")

    def fetch_tide_info(
        self,
        *,
        beach_num: str,
        base_date: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        raise AssertionError("not used")

    def fetch_sun_info(
        self,
        *,
        beach_num: str,
        base_date: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        raise AssertionError("not used")


def test_kma_beach_catalog_download_retries_transient_connection_reset() -> None:
    http_client = FlakyCatalogDownloadHttpClient()
    client = KmaBeachWeatherClient(
        service_key="test-key",
        catalog_download_url="https://example.test/catalog.zip",
        client=http_client,  # type: ignore[arg-type]
    )

    assert client._download_catalog_archive() == b"catalog-archive"
    assert http_client.call_count == 2


class PartiallyFailingBeachWeatherClient(FakeBeachWeatherClient):
    def fetch_ultra_short_forecast(
        self,
        *,
        beach_num: str,
        base_date: str,
        base_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        if beach_num == "2":
            raise RuntimeError("provider reset")
        return super().fetch_ultra_short_forecast(
            beach_num=beach_num,
            base_date=base_date,
            base_time=base_time,
        )


class FakeTideSunBeachWeatherClient(FakeBeachWeatherClient):
    def fetch_tide_info(
        self,
        *,
        beach_num: str,
        base_date: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return (
            {"beach_num": beach_num, "base_date": base_date},
            [
                {
                    "beachNum": beach_num,
                    "baseDate": "2026-04-29",
                    "tiTime": "05:30",
                    "tiType": "H",
                    "tilevel": "123",
                    "tiStnld": "station",
                }
            ],
        )

    def fetch_sun_info(
        self,
        *,
        beach_num: str,
        base_date: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return (
            {"beach_num": beach_num, "base_date": base_date},
            [
                {
                    "beachNum": beach_num,
                    "baseDate": "2026-04-29",
                    "sunrise": "05:40",
                    "sunset": "19:22",
                }
            ],
        )


class NoDataBeachWeatherClient(FakeBeachWeatherClient):
    def fetch_wave_height(
        self,
        *,
        beach_num: str,
        search_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return (
            {"beach_num": beach_num, "searchTime": search_time},
            [{"beachNum": beach_num, "tm": "", "wh": "-"}],
        )

    def fetch_water_temperature(
        self,
        *,
        beach_num: str,
        search_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return (
            {"beach_num": beach_num, "searchTime": search_time},
            [{"beachNum": beach_num, "tm": "", "tw": "-"}],
        )

    def fetch_tide_info(
        self,
        *,
        beach_num: str,
        base_date: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return (
            {"beach_num": beach_num, "base_date": base_date},
            [
                {
                    "beachNum": beach_num,
                    "baseDate": "2026-04-29",
                    "tiTime": "",
                    "tiType": "-",
                    "tilevel": "-",
                    "tiStnld": "station",
                }
            ],
        )

    def fetch_sun_info(
        self,
        *,
        beach_num: str,
        base_date: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return (
            {"beach_num": beach_num, "base_date": base_date},
            [
                {
                    "beachNum": beach_num,
                    "baseDate": "2026-04-29",
                    "sunrise": ":",
                    "sunset": ":",
                }
            ],
        )


def test_beach_catalog_loader_promotes_locations_to_places(
    db_session: Session,
) -> None:
    _seed_legal_boundary(db_session)
    _seed_road_address(db_session)

    first_result = load_beach_catalog(
        db_session,
        FakeBeachCatalogClient(),
        collected_at=datetime(2026, 5, 15, 4, 0, tzinfo=KST),
    )
    second_result = load_beach_catalog(
        db_session,
        FakeBeachCatalogClient(),
        collected_at=datetime(2026, 5, 15, 4, 5, tzinfo=KST),
    )
    db_session.commit()

    feature = db_session.scalar(select(MapFeature))
    location = db_session.scalar(select(WeatherBeachLocation))
    source_records = db_session.scalars(select(SourceRecord)).all()
    source_links = db_session.scalars(select(MapFeatureSourceLink)).all()
    provider_ref = db_session.scalar(select(MapFeatureProviderRef))

    assert first_result.place_upsert_count == 1
    assert first_result.location_upsert_count == 1
    assert first_result.source_record_count == 1
    assert first_result.legal_dong_mapped_count == 1
    assert first_result.road_address_mapped_count == 1
    assert second_result.source_record_count == 0
    assert feature is not None
    assert location is not None
    assert provider_ref is not None
    assert len(source_records) == 1
    assert len(source_links) == 1

    detail = db_session.get(PlaceDetail, feature.id)
    assert detail is not None
    assert feature.name == "테스트 해수욕장"
    assert feature.category_code == "01050100"
    assert feature.legal_dong_code == "1111010100"
    assert feature.road_name_code == "111103000001"
    assert feature.road_address_management_no == "1111010100100010000000001"
    assert detail.address_resolution_status == "resolved"
    assert str(feature.longitude) == "127.00000000"
    assert str(feature.latitude) == "37.50000000"
    assert detail.extra["beach_num"] == "1"
    assert detail.extra["address_mapping_method"] == ("juso_building_name_in_legal_dong")
    assert location.map_feature_id == feature.id
    assert location.nx == 60
    assert location.ny == 127
    assert location.address_mapping_method == "juso_building_name_in_legal_dong"


def test_beach_weather_loader_stores_raw_and_serving_rows_idempotently(
    db_session: Session,
) -> None:
    _seed_legal_boundary(db_session)
    _seed_road_address(db_session)
    load_beach_catalog(
        db_session,
        FakeBeachCatalogClient(),
        collected_at=datetime(2026, 5, 15, 4, 0, tzinfo=KST),
    )

    first_result = load_beach_weather_for_active_locations(
        db_session,
        FakeBeachWeatherClient(),
        endpoint=KMA_BEACH_ULTRA_SHORT_ENDPOINT,
        collected_at=datetime(2026, 6, 1, 12, 20, tzinfo=KST),
    )
    second_result = load_beach_weather_for_active_locations(
        db_session,
        FakeBeachWeatherClient(),
        endpoint=KMA_BEACH_ULTRA_SHORT_ENDPOINT,
        collected_at=datetime(2026, 6, 1, 12, 20, tzinfo=KST),
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(WeatherRawBeach)).all()
    serving_rows = db_session.scalars(select(WeatherServingBeach)).all()
    serving = serving_rows[0]

    assert first_result.requested_beach_count == 1
    assert first_result.raw_row_count == 1
    assert first_result.serving_row_count == 1
    assert second_result.raw_row_count == 0
    assert second_result.serving_row_count == 1
    assert len(raw_rows) == 1
    assert len(serving_rows) == 1
    assert serving.beach_num == "1"
    assert serving.endpoint == KMA_BEACH_ULTRA_SHORT_ENDPOINT
    assert serving.base_date == "20260601"
    assert serving.base_time == "1130"
    assert serving.forecast_at is not None
    assert serving.normalized_category == "temperature"
    assert serving.value == "24"


def test_beach_weather_loader_keeps_partial_results_when_one_beach_fails(
    db_session: Session,
) -> None:
    _seed_legal_boundary(db_session)
    _seed_road_address(db_session)
    load_beach_catalog(
        db_session,
        TwoBeachCatalogClient(),
        collected_at=datetime(2026, 5, 15, 4, 0, tzinfo=KST),
    )

    result = load_beach_weather_for_active_locations(
        db_session,
        PartiallyFailingBeachWeatherClient(),
        endpoint=KMA_BEACH_ULTRA_SHORT_ENDPOINT,
        collected_at=datetime(2026, 6, 1, 12, 20, tzinfo=KST),
    )
    db_session.commit()

    raw_rows = db_session.scalars(select(WeatherRawBeach).order_by(WeatherRawBeach.beach_num)).all()
    serving_rows = db_session.scalars(select(WeatherServingBeach)).all()

    assert result.requested_beach_count == 2
    assert result.raw_row_count == 2
    assert result.serving_row_count == 1
    assert result.skipped_row_count == 1
    assert result.fetch_error_count == 1
    assert len(raw_rows) == 2
    assert raw_rows[1].raw_payload["error"] == "provider reset"
    assert len(serving_rows) == 1


def test_beach_tide_and_sun_loader_compacts_provider_dates(
    db_session: Session,
) -> None:
    _seed_legal_boundary(db_session)
    _seed_road_address(db_session)
    load_beach_catalog(
        db_session,
        FakeBeachCatalogClient(),
        collected_at=datetime(2026, 5, 15, 4, 0, tzinfo=KST),
    )

    tide_result = load_beach_weather_for_active_locations(
        db_session,
        FakeTideSunBeachWeatherClient(),
        endpoint=KMA_BEACH_TIDE_ENDPOINT,
        collected_at=datetime(2026, 4, 29, 9, 40, tzinfo=KST),
    )
    sun_result = load_beach_weather_for_active_locations(
        db_session,
        FakeTideSunBeachWeatherClient(),
        endpoint=KMA_BEACH_SUN_ENDPOINT,
        collected_at=datetime(2026, 4, 29, 9, 40, tzinfo=KST),
    )
    db_session.commit()

    serving_rows = db_session.scalars(
        select(WeatherServingBeach).order_by(
            WeatherServingBeach.endpoint,
            WeatherServingBeach.category_code,
        )
    ).all()

    assert tide_result.serving_row_count == 1
    assert sun_result.serving_row_count == 2
    assert [row.base_date for row in serving_rows] == ["20260429", "20260429", "20260429"]
    assert all(row.observed_at is not None for row in serving_rows)
    assert all("-" not in (row.base_date or "") for row in serving_rows)


def test_beach_observed_loaders_skip_provider_no_data_markers(
    db_session: Session,
) -> None:
    _seed_legal_boundary(db_session)
    _seed_road_address(db_session)
    load_beach_catalog(
        db_session,
        FakeBeachCatalogClient(),
        collected_at=datetime(2026, 5, 15, 4, 0, tzinfo=KST),
    )

    client = NoDataBeachWeatherClient()
    wave_result = load_beach_weather_for_active_locations(
        db_session,
        client,
        endpoint=KMA_BEACH_WAVE_ENDPOINT,
        collected_at=datetime(2026, 4, 29, 9, 40, tzinfo=KST),
    )
    temp_result = load_beach_weather_for_active_locations(
        db_session,
        client,
        endpoint=KMA_BEACH_WATER_TEMP_ENDPOINT,
        collected_at=datetime(2026, 4, 29, 9, 40, tzinfo=KST),
    )
    tide_result = load_beach_weather_for_active_locations(
        db_session,
        client,
        endpoint=KMA_BEACH_TIDE_ENDPOINT,
        collected_at=datetime(2026, 4, 29, 9, 40, tzinfo=KST),
    )
    sun_result = load_beach_weather_for_active_locations(
        db_session,
        client,
        endpoint=KMA_BEACH_SUN_ENDPOINT,
        collected_at=datetime(2026, 4, 29, 9, 40, tzinfo=KST),
    )
    db_session.commit()

    serving_rows = db_session.scalars(select(WeatherServingBeach)).all()
    raw_rows = db_session.scalars(select(WeatherRawBeach)).all()

    assert wave_result.serving_row_count == 0
    assert wave_result.skipped_row_count == 1
    assert temp_result.serving_row_count == 0
    assert temp_result.skipped_row_count == 1
    assert tide_result.serving_row_count == 0
    assert tide_result.skipped_row_count == 1
    assert sun_result.serving_row_count == 0
    assert sun_result.skipped_row_count == 2
    assert len(raw_rows) == 4
    assert serving_rows == []


def _seed_road_address(session: Session) -> None:
    session.add(
        AddressServingJusoRoadAddress(
            road_address_management_no="1111010100100010000000001",
            legal_dong_code="1111010100",
            road_name_code="111103000001",
            administrative_dong_code="1111051500",
            sido_name="서울특별시",
            sigungu_name="종로구",
            legal_eupmyeondong_name="청운동",
            legal_ri_name=None,
            road_name="테스트로",
            administrative_dong_name="청운효자동",
            mountain_yn="0",
            jibun_main_no="1",
            jibun_sub_no="0",
            underground_yn="0",
            building_main_no="1",
            building_sub_no="0",
            postal_code="03000",
            previous_road_address=None,
            apartment_yn="0",
            building_registry_name="테스트 해수욕장",
            sigungu_building_name="테스트 해수욕장",
            note=None,
            full_legal_dong_name="서울특별시 종로구 청운동",
            full_road_address="서울특별시 종로구 테스트로 1",
            source_effective_date="20260401",
            source_change_reason_code="00",
            source_file_name="juso.txt",
            source_year_month="202604",
            source_file_hash="juso-hash",
            is_active=True,
        )
    )
    session.flush()


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
