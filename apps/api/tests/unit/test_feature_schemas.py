"""Feature Pydantic schema 단위 테스트 (kor_travel_map REST 셰입 정합)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.feature import (
    BBox,
    Coord,
    FeatureCluster,
    FeatureDetail,
    FeatureRequestCreate,
    FeatureRequestResponse,
    FeatureSummary,
    FeatureWeatherCard,
    WeatherMetric,
)


class TestCoordValidation:
    def test_valid_korea_coord(self) -> None:
        c = Coord(lon=127.0, lat=37.5)
        assert c.lon == 127.0
        assert c.lat == 37.5

    def test_reject_out_of_korea_west(self) -> None:
        with pytest.raises(ValidationError):
            Coord(lon=120.0, lat=37.5)  # 124 미만

    def test_reject_out_of_korea_north(self) -> None:
        with pytest.raises(ValidationError):
            Coord(lon=127.0, lat=44.0)  # 43 초과


class TestBBoxValidation:
    def test_valid(self) -> None:
        bb = BBox(lng_min=126.0, lat_min=37.0, lng_max=127.0, lat_max=37.5)
        assert bb.as_tuple() == (126.0, 37.0, 127.0, 37.5)


class TestFeatureSummary:
    def test_feature_id_is_opaque_string_with_defaults(self) -> None:
        summary = FeatureSummary(
            feature_id="f_1168010100_p_abc123",
            kind="place",
            name="경복궁",
            coord=Coord(lon=126.9770, lat=37.5796),
        )
        assert summary.feature_id == "f_1168010100_p_abc123"
        assert summary.name == "경복궁"
        # marker_* 는 kor_travel_map nullable → Pinvi 기본값으로 채움
        assert summary.marker_color == "P-13"
        assert summary.marker_icon == "marker"
        assert summary.status is None
        assert summary.distance_m is None

    def test_coord_is_optional(self) -> None:
        # kor_travel_map lon/lat nullable — point geometry 없는 feature
        summary = FeatureSummary(feature_id="f1", kind="notice", name="공지")
        assert summary.coord is None

    def test_status_and_distance(self) -> None:
        summary = FeatureSummary(
            feature_id="f1",
            kind="place",
            name="근처",
            coord=Coord(lon=127.0, lat=37.5),
            status="active",
            distance_m=42.0,
        )
        assert summary.status == "active"
        assert summary.distance_m == 42.0

    def test_marker_color_invalid_pattern(self) -> None:
        with pytest.raises(ValidationError):
            FeatureSummary(
                feature_id="f1",
                kind="place",
                name="경복궁",
                marker_color="P-99X",  # X 들어가서 invalid
            )


class TestFeatureCluster:
    def test_cluster_key_and_flat_coord(self) -> None:
        cluster = FeatureCluster(
            cluster_key="11680",  # 행정구역 코드(자연키)
            coord=Coord(lon=127.0, lat=37.5),
            feature_count=5,
        )
        assert cluster.cluster_key == "11680"
        assert cluster.feature_count == 5
        assert (cluster.coord.lon, cluster.coord.lat) == (127.0, 37.5)

    def test_reject_zero_count(self) -> None:
        with pytest.raises(ValidationError):
            FeatureCluster(
                cluster_key="x",
                coord=Coord(lon=127.0, lat=37.5),
                feature_count=0,  # 최소 1
            )


class TestFeatureDetail:
    def test_minimal_defaults(self) -> None:
        d = FeatureDetail(
            feature_id="f_1168010100_p_gbg",
            kind="place",
            name="경복궁",
            coord=Coord(lon=126.9770, lat=37.5796),
            updated_at=datetime.now(UTC),
        )
        assert d.detail == {}
        assert d.urls == {}
        assert d.address is None

    def test_structured_address_and_codes(self) -> None:
        d = FeatureDetail(
            feature_id="f1",
            kind="place",
            name="경복궁",
            coord=Coord(lon=127.0, lat=37.5),
            address={"road": "서울 종로구 사직로 161"},
            sigungu_code="11110",
            urls={"homepage": "https://example.test"},
            updated_at=datetime.now(UTC),
        )
        assert d.address == {"road": "서울 종로구 사직로 161"}
        assert d.sigungu_code == "11110"
        assert d.urls == {"homepage": "https://example.test"}


class TestFeatureWeatherCard:
    def test_empty_card(self) -> None:
        c = FeatureWeatherCard(feature_id="f_weather_gbg")
        assert c.metrics == []
        assert c.source_styles == []
        assert c.is_stale is False
        assert c.asof is None

    def test_with_metrics(self) -> None:
        metric = WeatherMetric(
            metric_key="T1H",
            metric_name="기온",
            forecast_style="nowcast",
            value_number=22.5,
            unit="℃",
        )
        c = FeatureWeatherCard(
            feature_id="f_weather_gbg",
            source_styles=["nowcast"],
            metrics=[metric],
        )
        assert c.metrics[0].metric_key == "T1H"
        assert c.metrics[0].value_number == 22.5
        assert c.source_styles == ["nowcast"]


class TestFeatureRequestCreate:
    def test_minimum(self) -> None:
        r = FeatureRequestCreate(
            kind="place",
            title="새로운 카페",
            coord=Coord(lon=127.0, lat=37.5),
        )
        assert r.note is None
        assert r.categories == []

    def test_categories(self) -> None:
        r = FeatureRequestCreate(
            kind="place",
            title="새로운 카페",
            coord=Coord(lon=127.0, lat=37.5),
            categories=["카페", "디저트"],
        )
        assert r.categories == ["카페", "디저트"]

    def test_title_too_long(self) -> None:
        with pytest.raises(ValidationError):
            FeatureRequestCreate(
                kind="place",
                title="x" * 201,
                coord=Coord(lon=127.0, lat=37.5),
            )

    def test_rejects_non_suggestion_kind(self) -> None:
        # 사용자 제안 kind는 place/event만(#108 리뷰) — notice/price/... 거부.
        with pytest.raises(ValidationError):
            FeatureRequestCreate(
                kind="notice",  # type: ignore[arg-type]
                title="운영 공지 제안",
                coord=Coord(lon=127.0, lat=37.5),
            )


class TestFeatureRequestResponse:
    def test_pending_response(self) -> None:
        request_id = uuid.uuid4()
        created_at = datetime.now(UTC)
        r = FeatureRequestResponse(
            request_id=request_id,
            status="pending",
            kind="place",
            title="새로운 카페",
            coord=Coord(lon=127.0, lat=37.5),
            created_at=created_at,
        )
        assert r.request_id == request_id
        assert r.status == "pending"
        assert r.categories == []
