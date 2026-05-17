from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from geoalchemy2.elements import WKTElement
from shapely.geometry import LineString
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.etl.outdoor.forest_features import (
    load_krforest_mountain_story_areas,
    load_krforest_spatial_features,
    load_krforest_spatial_points,
    load_mois_outdoor_license_records,
)
from app.models.address import (
    AddressCodeStandard,
    RegionBoundaryImportBatch,
    RegionRawVWorldBoundary,
    RegionServingBoundary,
)
from app.models.place import (
    AreaDetail,
    MapFeature,
    MapFeatureProviderRef,
    MapFeatureSourceLink,
    OutdoorFeatureProfile,
    PlaceDetail,
    RouteDetail,
    SourceRecord,
)

KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class _Coordinate:
    longitude: float
    latitude: float

    def as_tuple(self) -> tuple[float, float]:
        return self.longitude, self.latitude


@dataclass(frozen=True)
class _ForestPointRecord:
    name: str
    coordinate: _Coordinate
    category: str | None = None
    address: str | None = None
    phone_number: str | None = None
    homepage_url: str | None = None
    owner_name: str | None = None
    operation_status: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _ForestRouteRecord:
    name: str
    geometry: Any
    coordinate: _Coordinate | None = None
    source_file: str | None = None
    layer_name: str | None = None
    geometry_type: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _MoisCoordinates:
    wgs84_point: _Coordinate


@dataclass(frozen=True)
class _MoisRecord:
    business_name: str
    coordinates: _MoisCoordinates
    is_open: bool | None
    service_slug: str
    title: str
    raw: dict[str, Any]


def test_outdoor_feature_loaders_persist_place_area_route_and_support_records(
    db_session: Session,
) -> None:
    _seed_legal_boundary(db_session)
    collected_at = datetime(2026, 5, 18, 9, 0, tzinfo=KST)

    place_result = load_krforest_spatial_points(
        db_session,
        "krforest_recreation_forest_arboretum",
        [
            _ForestPointRecord(
                name="테스트 수목원",
                category="수목원",
                coordinate=_Coordinate(127.0, 37.5),
                address="서울특별시 종로구 세종대로 1",
                phone_number="02-100-2000",
                homepage_url="forest.example",
                owner_name="테스트시",
                raw={"관리번호": "ARB-1", "name": "테스트 수목원"},
            )
        ],
        collected_at=collected_at,
    )
    route_result = load_krforest_spatial_features(
        db_session,
        "krforest_hiking_trail",
        [
            _ForestRouteRecord(
                name="테스트 등산로",
                geometry=LineString([(126.95, 37.45), (127.05, 37.55)]),
                source_file="trail.zip",
                layer_name="trail",
                geometry_type="LineString",
                bbox=(126.95, 37.45, 127.05, 37.55),
                raw={"OBJECTID": "TRAIL-1", "거리": "3.2km", "소요시간": "2시간 30분"},
            )
        ],
        collected_at=collected_at,
    )
    area_result = load_krforest_mountain_story_areas(
        db_session,
        [
            {
                "mntiid": "MNT-1",
                "mntiname": "테스트산",
                "longitude": "127.0",
                "latitude": "37.5",
                "mntiadd": "서울특별시 종로구",
                "mntihigh": "838m",
                "mntisummary": "테스트 산행지",
            }
        ],
        collected_at=collected_at,
    )
    support_result = load_mois_outdoor_license_records(
        db_session,
        "general_campgrounds",
        [
            _MoisRecord(
                business_name="테스트 야영장",
                coordinates=_MoisCoordinates(_Coordinate(127.0, 37.5)),
                is_open=False,
                service_slug="general_campgrounds",
                title="일반야영장업",
                raw={
                    "MNG_NO": "CAMP-1",
                    "BPLC_NM": "테스트 야영장",
                    "RDNWHLADDR": "서울특별시 종로구 세종대로 1",
                    "SITE_TEL": "02-300-4000",
                    "SALS_STTS_CD": "03",
                    "SALS_STTS_NM": "폐업",
                },
            )
        ],
        collected_at=collected_at,
    )
    second_place_result = load_krforest_spatial_points(
        db_session,
        "krforest_recreation_forest_arboretum",
        [
            _ForestPointRecord(
                name="테스트 수목원",
                category="수목원",
                coordinate=_Coordinate(127.0, 37.5),
                address="서울특별시 종로구 세종대로 1",
                phone_number="02-100-2000",
                homepage_url="forest.example",
                owner_name="테스트시",
                raw={"관리번호": "ARB-1", "name": "테스트 수목원"},
            )
        ],
        collected_at=collected_at,
    )
    db_session.commit()

    assert place_result.raw_record_count == 1
    assert place_result.source_record_count == 1
    assert place_result.feature_upsert_count == 1
    assert place_result.mapped_legal_dong_count == 1
    assert route_result.feature_upsert_count == 1
    assert area_result.feature_upsert_count == 1
    assert support_result.feature_upsert_count == 1
    assert second_place_result.source_record_count == 0

    features = {row.name: row for row in db_session.scalars(select(MapFeature)).all()}
    assert set(features) == {"테스트 수목원", "테스트 등산로", "테스트산", "테스트 야영장"}
    assert len(db_session.scalars(select(SourceRecord)).all()) == 4
    assert len(db_session.scalars(select(MapFeatureProviderRef)).all()) == 4
    assert len(db_session.scalars(select(MapFeatureSourceLink)).all()) == 4

    arboretum = features["테스트 수목원"]
    arboretum_profile = db_session.get(OutdoorFeatureProfile, arboretum.id)
    arboretum_detail = db_session.get(PlaceDetail, arboretum.id)
    assert arboretum.category_code == "01020302"
    assert arboretum.category_name == "수목원"
    assert arboretum.website_url == "https://forest.example"
    assert arboretum.legal_dong_code == "1111010100"
    assert arboretum_profile is not None
    assert arboretum_profile.outdoor_kind == "arboretum"
    assert arboretum_detail is not None
    assert arboretum_detail.address_resolution_status == "resolved"

    route = features["테스트 등산로"]
    route_profile = db_session.get(OutdoorFeatureProfile, route.id)
    route_detail = db_session.get(RouteDetail, route.id)
    assert route.feature_type == "route"
    assert route.geometry_kind == "line"
    assert route_profile is not None
    assert route_profile.distance_m == 3200
    assert route_profile.duration_min == 150
    assert route_detail is not None
    assert route_detail.route_kind == "hiking"
    assert route_detail.distance_m == 3200
    assert route_detail.duration_min == 150

    mountain = features["테스트산"]
    mountain_profile = db_session.get(OutdoorFeatureProfile, mountain.id)
    mountain_detail = db_session.get(AreaDetail, mountain.id)
    assert mountain.feature_type == "area"
    assert mountain.category_code == "01020200"
    assert mountain_profile is not None
    assert mountain_profile.outdoor_kind == "mountain"
    assert mountain_profile.extra["height"] == "838m"
    assert mountain_detail is not None
    assert mountain_detail.area_kind == "mountain"

    campground = features["테스트 야영장"]
    campground_profile = db_session.get(OutdoorFeatureProfile, campground.id)
    campground_detail = db_session.get(PlaceDetail, campground.id)
    assert campground.status == "inactive"
    assert campground.is_visible is False
    assert campground_profile is not None
    assert campground_profile.outdoor_kind == "campground"
    assert campground_profile.feature_role == "support"
    assert campground_detail is not None
    assert campground_detail.operation_status == "closed"


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
        ufid="UFID-OUTDOOR-1",
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
