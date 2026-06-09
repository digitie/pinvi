"""Feature Pydantic schema 단위 테스트."""

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
    WeatherTimepoint,
)


class TestCoordValidation:
    def test_valid_korea_coord(self) -> None:
        c = Coord(longitude=127.0, latitude=37.5)
        assert c.longitude == 127.0
        assert c.latitude == 37.5

    def test_reject_out_of_korea_west(self) -> None:
        with pytest.raises(ValidationError):
            Coord(longitude=120.0, latitude=37.5)  # 124 미만

    def test_reject_out_of_korea_north(self) -> None:
        with pytest.raises(ValidationError):
            Coord(longitude=127.0, latitude=44.0)  # 43 초과


class TestBBoxValidation:
    def test_valid(self) -> None:
        bb = BBox(lng_min=126.0, lat_min=37.0, lng_max=127.0, lat_max=37.5)
        assert bb.as_tuple() == (126.0, 37.0, 127.0, 37.5)


class TestFeatureSummary:
    def test_feature_id_is_opaque_string(self) -> None:
        summary = FeatureSummary(
            feature_id="place:abc123",
            kind="place",
            title="경복궁",
            coord=Coord(longitude=126.9770, latitude=37.5796),
            marker_color="P-01",
            marker_icon="monument",
        )
        assert summary.feature_id == "place:abc123"

    def test_marker_color_pattern(self) -> None:
        FeatureSummary(
            feature_id="place:gyeongbokgung",
            kind="place",
            title="경복궁",
            coord=Coord(longitude=126.9770, latitude=37.5796),
            marker_color="P-01",
            marker_icon="monument",
        )

    def test_marker_color_invalid_pattern(self) -> None:
        with pytest.raises(ValidationError):
            FeatureSummary(
                feature_id="place:gyeongbokgung",
                kind="place",
                title="경복궁",
                coord=Coord(longitude=126.9770, latitude=37.5796),
                marker_color="P-99X",  # X 들어가서 invalid
                marker_icon="monument",
            )


class TestFeatureCluster:
    def test_minimum_count(self) -> None:
        FeatureCluster(
            cluster_id="sigungu-11680",
            center=Coord(longitude=127.0, latitude=37.5),
            feature_count=5,
            sample_kinds=["place", "event"],
            bbox=BBox(lng_min=126.9, lat_min=37.4, lng_max=127.1, lat_max=37.6),
        )

    def test_reject_single_feature_cluster(self) -> None:
        with pytest.raises(ValidationError):
            FeatureCluster(
                cluster_id="x",
                center=Coord(longitude=127.0, latitude=37.5),
                feature_count=1,  # 클러스터는 2개 이상
                sample_kinds=["place"],
                bbox=BBox(lng_min=126.9, lat_min=37.4, lng_max=127.1, lat_max=37.6),
            )


class TestFeatureDetail:
    def test_minimal(self) -> None:
        d = FeatureDetail(
            feature_id="place:gyeongbokgung",
            kind="place",
            title="경복궁",
            coord=Coord(longitude=126.9770, latitude=37.5796),
            marker_color="P-03",
            marker_icon="monument",
            updated_at=datetime.now(UTC),
        )
        assert d.detail == {}
        assert d.source_ids == []


class TestFeatureWeatherCard:
    def test_empty_card(self) -> None:
        c = FeatureWeatherCard(feature_id="weather:gyeongbokgung", asof=datetime.now(UTC))
        assert c.short_term == []
        assert c.daily == []
        assert c.sources == []

    def test_with_timepoints(self) -> None:
        tp = WeatherTimepoint(asof=datetime.now(UTC), temp_c=22.5, condition="clear")
        c = FeatureWeatherCard(
            feature_id="weather:gyeongbokgung",
            asof=datetime.now(UTC),
            short_term=[tp],
            sources=["kma:short_term:11B10101"],
        )
        assert c.short_term[0].temp_c == 22.5


class TestFeatureRequestCreate:
    def test_minimum(self) -> None:
        r = FeatureRequestCreate(
            kind="place",
            title="새로운 카페",
            coord=Coord(longitude=127.0, latitude=37.5),
        )
        assert r.note is None
        assert r.categories == []

    def test_categories(self) -> None:
        r = FeatureRequestCreate(
            kind="place",
            title="새로운 카페",
            coord=Coord(longitude=127.0, latitude=37.5),
            categories=["카페", "디저트"],
        )
        assert r.categories == ["카페", "디저트"]

    def test_title_too_long(self) -> None:
        with pytest.raises(ValidationError):
            FeatureRequestCreate(
                kind="place",
                title="x" * 201,
                coord=Coord(longitude=127.0, latitude=37.5),
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
            coord=Coord(longitude=127.0, latitude=37.5),
            created_at=created_at,
        )
        assert r.request_id == request_id
        assert r.status == "pending"
        assert r.categories == []
