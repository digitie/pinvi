"""Trip view weather — `kor-travel-weather` location 축 batch, feature batch와 완전 독립
(T-363/P4, ADR-068, 2026-09-17 사용자 방향 전환).

flag가 꺼져 있으면(기본값) 기존 `kor-travel-map` 날짜별 batch 경로를 그대로 쓴다는
것은 `test_trip_view_builder.py`의 기존 weather 테스트가 이미 고정한다. 여기서는
flag on일 때의 **새 경로**(`trip_weather_batch.build_trip_weather_via_kor_travel_weather`)
를 `build_trip_view` 전체 파이프라인을 통해 검증한다.

**핵심 불변식** — 이 새 경로는 feature batch(`get_features`)의 산출물을 전혀 받지
않는다. weather 조회는 POI 자신의 `feature_snapshot.coord`만으로 동작하고, feature가
`retired`/`suppressed`/`missing`이든 feature batch 자체가 실패했든 영향받지 않는다.
아래 테스트들은 이 독립성을 직접 고정한다(특히
`test_flag_on_weather_ignores_retired_feature_state_when_snapshot_has_coord`와
`test_flag_on_weather_survives_feature_batch_failure`).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.clients.kor_travel_map import (
    FeatureTripCard,
    FoundFeatureBatchItem,
    KorTravelMapUnavailable,
    NoDataWeatherBatchItem,
    RetiredFeatureBatchItem,
)
from app.clients.kor_travel_weather import (
    CoordinateRequestOut,
    KorTravelWeatherNotFound,
    KorTravelWeatherUnavailable,
    LocationOut,
    ResolvedWeatherOut,
    WeatherMarkerOut,
    WeatherValueOut,
)
from app.core.config import settings

pytestmark = pytest.mark.asyncio

_SEOUL = ZoneInfo("Asia/Seoul")


def _weather_value(
    *,
    location_id: str,
    metric_key: str,
    target_at: datetime,
    value_number: float | None = 20.0,
    forecast_style: str = "short",
    weather_domain: str = "forecast",
    unit: str | None = "deg_c",
    provider: str = "python-kma-api",
) -> WeatherValueOut:
    return WeatherValueOut(
        value_id=f"wv-{location_id}-{metric_key}-{target_at.isoformat()}",
        location_id=location_id,
        provider=provider,
        dataset_key="kma_short_forecast",
        weather_domain=weather_domain,
        forecast_style=forecast_style,
        metric_key=metric_key,
        target_at=target_at,
        normalization_version="kma-v1",
        collected_at=datetime.now(UTC),
        source_record_key="sr-1",
        value_number=value_number,
        unit=unit,
        known_at=datetime.now(UTC),
    )


class _MapClient:
    """`get_features`만 구현한다 — 반환값은 weather 경로와 **무관**하다(독립성 검증용).

    항상 `RetiredFeatureBatchItem`을 돌려준다: weather가 이 결과를 무시한다는 것 자체가
    이 테스트 스위트의 핵심 단언이다.
    """

    def __init__(self) -> None:
        self.call_count = 0

    async def get_features(
        self,
        feature_ids: list[str],
        *,
        known_row_revisions: Mapping[str, int] | None = None,
    ) -> dict[str, Any]:
        self.call_count += 1
        return {
            feature_id: RetiredFeatureBatchItem(feature_id=feature_id, row_revision=1)
            for feature_id in feature_ids
        }


class _FailingMapClient:
    """`get_features`가 항상 실패한다 — weather가 이 실패에 영향받지 않음을 검증한다."""

    async def get_features(
        self,
        feature_ids: list[str],
        *,
        known_row_revisions: Mapping[str, int] | None = None,
    ) -> dict[str, Any]:
        raise KorTravelMapUnavailable("feature batch down")


class _LegacyMapClient:
    """flag off 테스트 전용 — `get_features`는 found를 돌려줘 구 weather batch 경로가
    실제로 호출되게 한다(retired 등은 애초에 weather batch를 부르지 않으므로 이
    테스트의 목적인 "새 client가 무시됨"을 검증할 수 없다)."""

    async def get_features(
        self,
        feature_ids: list[str],
        *,
        known_row_revisions: Mapping[str, int] | None = None,
    ) -> dict[str, Any]:
        return {
            feature_id: FoundFeatureBatchItem(
                feature_id=feature_id,
                row_revision=1,
                trip_card=FeatureTripCard(
                    feature_id=feature_id,
                    kind="place",
                    name=feature_id,
                    category="attraction",
                    lon=127.0,
                    lat=37.5,
                    address={},
                    marker_icon="marker",
                    marker_color="P-01",
                ),
            )
            for feature_id in feature_ids
        }

    async def get_weather_batch(
        self,
        targets: Mapping[datetime, Sequence[str]],
        *,
        known_at: datetime,
    ) -> dict[datetime, dict[str, Any]]:
        return {
            target_at: {
                feature_id: NoDataWeatherBatchItem(feature_id=feature_id)
                for feature_id in feature_ids
            }
            for target_at, feature_ids in targets.items()
        }


def _location(location_id: str, *, lat: float, lon: float) -> LocationOut:
    return LocationOut(
        location_id=location_id, name=location_id, latitude=lat, longitude=lon, enabled=True
    )


def _resolved(
    *,
    lat: float,
    lon: float,
    location_id: str,
    source_location_ids: Sequence[str] | None = None,
) -> ResolvedWeatherOut:
    primary = _location(location_id, lat=lat, lon=lon)
    sources = (
        tuple(_location(loc_id, lat=lat, lon=lon) for loc_id in source_location_ids)
        if source_location_ids is not None
        else (primary,)
    )
    return ResolvedWeatherOut(
        requested=CoordinateRequestOut(latitude=lat, longitude=lon),
        location=primary,
        distance_km=0.1,
        source_locations=sources,
    )


class _WeatherClient:
    """`resolve`/`markers`/`forecast`만 구현 — `KorTravelWeatherClient`와 같은 시그니처."""

    def __init__(
        self,
        *,
        resolutions: Mapping[tuple[float, float], ResolvedWeatherOut] | None = None,
        forecast_values: Mapping[str, tuple[WeatherValueOut, ...]] | None = None,
        marker_values: Mapping[str, tuple[WeatherValueOut, ...]] | None = None,
        failing_locations: frozenset[str] = frozenset(),
    ) -> None:
        self.resolutions = resolutions or {}
        self.forecast_values = forecast_values or {}
        self.marker_values = marker_values or {}
        self.failing_locations = failing_locations
        self.resolve_calls: list[tuple[float, float, float | None]] = []
        self.markers_calls: list[list[str]] = []
        self.forecast_calls: list[dict[str, Any]] = []

    async def resolve(
        self, *, lat: float, lon: float, radius_km: float | None = None
    ) -> ResolvedWeatherOut:
        self.resolve_calls.append((lat, lon, radius_km))
        outcome = self.resolutions.get((lat, lon))
        if outcome is None:
            raise KorTravelWeatherNotFound(
                "no anchor", status_code=404, code="HTTP_ERROR", detail="없음"
            )
        return outcome

    async def markers(self, location_ids: Sequence[str]) -> tuple[WeatherMarkerOut, ...]:
        ids = list(location_ids)
        self.markers_calls.append(ids)
        return tuple(
            WeatherMarkerOut(location_id=loc, latest=self.marker_values.get(loc, ()), alerts=())
            for loc in ids
        )

    async def forecast(
        self,
        location_id: str,
        *,
        from_: datetime | None = None,
        to: datetime | None = None,
        dataset_key: str | None = None,
        metric_key: str | None = None,
        history: bool = False,
        limit: int | None = None,
    ) -> tuple[WeatherValueOut, ...]:
        self.forecast_calls.append({"location_id": location_id, "from_": from_, "to": to})
        if location_id in self.failing_locations:
            raise KorTravelWeatherUnavailable(f"boom: {location_id}")
        return self.forecast_values.get(location_id, ())


def _snapshot(lon: float | None, lat: float | None) -> dict[str, Any]:
    if lon is None or lat is None:
        return {"title": "저장본"}
    return {"title": "저장본", "coord": {"lon": lon, "lat": lat}}


async def _build_view(  # type: ignore[no-untyped-def]
    session_factory,
    *,
    pois: list[tuple[int, date, str, dict[str, Any]]],
    map_client: Any,
    weather_client: Any,
) -> dict[str, Any]:
    """`pois`: `(day_index, effective_date, feature_id, feature_snapshot)` 목록."""
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.feature_cache import feature_cache
    from app.services.trip_view_builder import build_trip_view

    feature_cache.clear()
    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)
    days_by_index = {day_index: effective_date for day_index, effective_date, _fid, _snap in pois}
    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"trip_weather_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        trip = Trip(trip_id=trip_id, owner_user_id=user_id, title="T-363 테스트 여행")
        db.add(trip)
        db.add_all(
            [
                TripDay(trip_id=trip_id, day_index=day_index, date=effective_date)
                for day_index, effective_date in days_by_index.items()
            ]
        )
        await db.flush()
        db.add_all(
            [
                TripDayPoi(
                    trip_id=trip_id,
                    day_index=day_index,
                    sort_order=f"a{i:02d}",
                    feature_id=feature_id,
                    feature_snapshot=snapshot,
                    added_by_user_id=user_id,
                    currency="KRW",
                )
                for i, (day_index, _eff, feature_id, snapshot) in enumerate(pois)
            ]
        )
        await db.commit()
        await db.refresh(trip)
        view = await build_trip_view(
            db, trip=trip, kor_travel_map_client=map_client, weather_client=weather_client
        )
    feature_cache.clear()
    return view


def _day(view: dict[str, Any], day_index: int) -> dict[str, Any]:
    return next(d for d in view["days"] if d["day_index"] == day_index)


def _at(target_date: date, hour: int = 9) -> datetime:
    return datetime(target_date.year, target_date.month, target_date.day, hour, tzinfo=_SEOUL)


@pytest.fixture(autouse=True)
def _reset_flag() -> Any:
    original = settings.pinvi_kor_travel_weather_trip_view_enabled
    yield
    settings.pinvi_kor_travel_weather_trip_view_enabled = original


async def test_flag_off_ignores_new_weather_client(session_factory) -> None:  # type: ignore[no-untyped-def]
    settings.pinvi_kor_travel_weather_trip_view_enabled = False
    eff_date = date(2026, 10, 1)
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    map_client = _LegacyMapClient()
    weather_client = _WeatherClient()

    view = await _build_view(
        session_factory,
        pois=[(1, eff_date, feature_id, _snapshot(127.0, 37.5))],
        map_client=map_client,
        weather_client=weather_client,
    )

    assert weather_client.resolve_calls == []
    assert weather_client.markers_calls == []
    assert _day(view, 1)["weather_by_feature_id"][feature_id]["state"] == "no_data"


async def test_flag_on_builds_card_and_shares_across_same_location(session_factory) -> None:  # type: ignore[no-untyped-def]
    settings.pinvi_kor_travel_weather_trip_view_enabled = True
    eff_date = date(2026, 10, 1)
    lat, lon = 37.5, 127.0
    f1, f2 = f"f1_{uuid.uuid4().hex[:8]}", f"f2_{uuid.uuid4().hex[:8]}"
    map_client = _MapClient()
    weather_client = _WeatherClient(
        resolutions={(lat, lon): _resolved(lat=lat, lon=lon, location_id="loc-1")},
        forecast_values={
            "loc-1": (
                _weather_value(location_id="loc-1", metric_key="TEMP", target_at=_at(eff_date)),
            )
        },
    )

    view = await _build_view(
        session_factory,
        pois=[
            (1, eff_date, f1, _snapshot(lon, lat)),
            (1, eff_date, f2, _snapshot(lon, lat)),
        ],
        map_client=map_client,
        weather_client=weather_client,
    )

    day = _day(view, 1)
    assert day["weather_by_feature_id"][f1] == {"state": "found", "card_key": "loc-1"}
    assert day["weather_by_feature_id"][f2] == {"state": "found", "card_key": "loc-1"}
    card = day["weather_cards"]["loc-1"]
    assert [m["metric_key"] for m in card["metrics"]] == ["TMP"]
    assert weather_client.markers_calls == [["loc-1"]]
    # 같은 location을 참조하는 feature가 둘이어도 forecast는 location마다 1회.
    assert len(weather_client.forecast_calls) == 1
    assert weather_client.forecast_calls[0]["location_id"] == "loc-1"


async def test_flag_on_weather_ignores_retired_feature_state_when_snapshot_has_coord(  # type: ignore[no-untyped-def]
    session_factory,
) -> None:
    """핵심 불변식 — `_MapClient`는 항상 retired를 돌려주지만 weather는 그와 무관하게 found다."""
    settings.pinvi_kor_travel_weather_trip_view_enabled = True
    eff_date = date(2026, 10, 1)
    lat, lon = 37.5, 127.0
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    map_client = _MapClient()  # get_features는 이 feature를 retired로 답한다.
    weather_client = _WeatherClient(
        resolutions={(lat, lon): _resolved(lat=lat, lon=lon, location_id="loc-1")},
        forecast_values={
            "loc-1": (
                _weather_value(location_id="loc-1", metric_key="TEMP", target_at=_at(eff_date)),
            )
        },
    )

    view = await _build_view(
        session_factory,
        pois=[(1, eff_date, feature_id, _snapshot(lon, lat))],
        map_client=map_client,
        weather_client=weather_client,
    )

    day = _day(view, 1)
    # feature 표시 상태는 여전히 retired다(map 소유, 무변경).
    assert day["pois"][0]["feature_resolution_state"] == "retired"
    # 하지만 weather는 좌표만 보고 독립적으로 found다.
    assert day["weather_by_feature_id"][feature_id] == {"state": "found", "card_key": "loc-1"}


async def test_flag_on_weather_survives_feature_batch_failure(session_factory) -> None:  # type: ignore[no-untyped-def]
    """핵심 불변식 — feature batch(get_features) 자체가 실패해도 weather는 정상 동작한다."""
    settings.pinvi_kor_travel_weather_trip_view_enabled = True
    eff_date = date(2026, 10, 1)
    lat, lon = 37.5, 127.0
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    map_client = _FailingMapClient()
    weather_client = _WeatherClient(
        resolutions={(lat, lon): _resolved(lat=lat, lon=lon, location_id="loc-1")},
        forecast_values={
            "loc-1": (
                _weather_value(location_id="loc-1", metric_key="TEMP", target_at=_at(eff_date)),
            )
        },
    )

    view = await _build_view(
        session_factory,
        pois=[(1, eff_date, feature_id, _snapshot(lon, lat))],
        map_client=map_client,
        weather_client=weather_client,
    )

    day = _day(view, 1)
    # feature 표시 상태는 batch 실패로 unverified다(무변경 — feature 쪽 기존 동작).
    assert day["pois"][0]["feature_resolution_state"] == "unverified"
    # weather는 batch 실패와 무관하게 snapshot 좌표로 독립적으로 found다.
    assert day["weather_by_feature_id"][feature_id] == {"state": "found", "card_key": "loc-1"}


async def test_flag_on_merges_full_source_location_bundle(session_factory) -> None:  # type: ignore[no-untyped-def]
    """§3.3 회귀 가드 — 대표 location에 사실이 없어도 번들의 다른 location 값을 쓴다."""
    settings.pinvi_kor_travel_weather_trip_view_enabled = True
    eff_date = date(2026, 10, 1)
    lat, lon = 37.5, 127.0
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    map_client = _MapClient()
    weather_client = _WeatherClient(
        resolutions={
            (lat, lon): _resolved(
                lat=lat, lon=lon, location_id="loc-a", source_location_ids=["loc-b"]
            )
        },
        forecast_values={
            "loc-a": (),  # 대표 location에는 KMA 사실이 없다.
            "loc-b": (
                _weather_value(location_id="loc-b", metric_key="TEMP", target_at=_at(eff_date)),
            ),
        },
    )

    view = await _build_view(
        session_factory,
        pois=[(1, eff_date, feature_id, _snapshot(lon, lat))],
        map_client=map_client,
        weather_client=weather_client,
    )

    day = _day(view, 1)
    assert day["weather_by_feature_id"][feature_id] == {"state": "found", "card_key": "loc-a"}
    assert [m["metric_key"] for m in day["weather_cards"]["loc-a"]["metrics"]] == ["TMP"]
    requested_locations = {call["location_id"] for call in weather_client.forecast_calls}
    assert requested_locations == {"loc-a", "loc-b"}


async def test_flag_on_no_anchor_marks_no_data_without_network_calls(session_factory) -> None:  # type: ignore[no-untyped-def]
    settings.pinvi_kor_travel_weather_trip_view_enabled = True
    eff_date = date(2026, 10, 1)
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    map_client = _MapClient()
    weather_client = _WeatherClient()  # resolutions 비어있음 -> 항상 NotFound

    view = await _build_view(
        session_factory,
        pois=[(1, eff_date, feature_id, _snapshot(127.0, 37.5))],
        map_client=map_client,
        weather_client=weather_client,
    )

    assert _day(view, 1)["weather_by_feature_id"][feature_id] == {"state": "no_data"}
    assert weather_client.markers_calls == []
    assert weather_client.forecast_calls == []


async def test_flag_on_snapshot_without_coord_is_unavailable(session_factory) -> None:  # type: ignore[no-untyped-def]
    settings.pinvi_kor_travel_weather_trip_view_enabled = True
    eff_date = date(2026, 10, 1)
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    map_client = _MapClient()
    weather_client = _WeatherClient()

    view = await _build_view(
        session_factory,
        pois=[(1, eff_date, feature_id, _snapshot(None, None))],
        map_client=map_client,
        weather_client=weather_client,
    )

    assert _day(view, 1)["weather_by_feature_id"][feature_id] == {"state": "unavailable"}
    assert weather_client.resolve_calls == []


async def test_flag_on_partial_location_failure_still_found(session_factory) -> None:  # type: ignore[no-untyped-def]
    settings.pinvi_kor_travel_weather_trip_view_enabled = True
    eff_date = date(2026, 10, 1)
    lat, lon = 37.5, 127.0
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    map_client = _MapClient()
    weather_client = _WeatherClient(
        resolutions={
            (lat, lon): _resolved(
                lat=lat, lon=lon, location_id="loc-a", source_location_ids=["loc-a", "loc-b"]
            )
        },
        forecast_values={
            "loc-b": (
                _weather_value(location_id="loc-b", metric_key="TEMP", target_at=_at(eff_date)),
            )
        },
        failing_locations=frozenset({"loc-a"}),
    )

    view = await _build_view(
        session_factory,
        pois=[(1, eff_date, feature_id, _snapshot(lon, lat))],
        map_client=map_client,
        weather_client=weather_client,
    )

    day = _day(view, 1)
    assert day["weather_by_feature_id"][feature_id] == {"state": "found", "card_key": "loc-a"}
    assert [m["metric_key"] for m in day["weather_cards"]["loc-a"]["metrics"]] == ["TMP"]


async def test_flag_on_total_location_failure_marks_unavailable_not_no_data(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    """ "부분 실패는 추측하지 않는다" — 실패를 no_data로 지어내지 않고 unavailable로 둔다."""
    settings.pinvi_kor_travel_weather_trip_view_enabled = True
    eff_date = date(2026, 10, 1)
    lat, lon = 37.5, 127.0
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    map_client = _MapClient()
    weather_client = _WeatherClient(
        resolutions={(lat, lon): _resolved(lat=lat, lon=lon, location_id="loc-a")},
        failing_locations=frozenset({"loc-a"}),
    )

    view = await _build_view(
        session_factory,
        pois=[(1, eff_date, feature_id, _snapshot(lon, lat))],
        map_client=map_client,
        weather_client=weather_client,
    )

    assert _day(view, 1)["weather_by_feature_id"][feature_id] == {"state": "unavailable"}


async def test_flag_on_all_success_but_empty_marks_no_data(session_factory) -> None:  # type: ignore[no-untyped-def]
    settings.pinvi_kor_travel_weather_trip_view_enabled = True
    eff_date = date(2026, 10, 1)
    lat, lon = 37.5, 127.0
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    map_client = _MapClient()
    weather_client = _WeatherClient(
        resolutions={(lat, lon): _resolved(lat=lat, lon=lon, location_id="loc-a")},
        forecast_values={"loc-a": ()},
    )

    view = await _build_view(
        session_factory,
        pois=[(1, eff_date, feature_id, _snapshot(lon, lat))],
        map_client=map_client,
        weather_client=weather_client,
    )

    assert _day(view, 1)["weather_by_feature_id"][feature_id] == {"state": "no_data"}


async def test_flag_on_date_slicing_and_no_date_fanout(session_factory) -> None:  # type: ignore[no-untyped-def]
    """같은 feature가 이틀에 걸쳐 나와도 forecast는 location당 1회, day별로 다른 카드를 얻는다."""
    settings.pinvi_kor_travel_weather_trip_view_enabled = True
    day1_date, day2_date = date(2026, 10, 1), date(2026, 10, 3)
    lat, lon = 37.5, 127.0
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    map_client = _MapClient()
    weather_client = _WeatherClient(
        resolutions={(lat, lon): _resolved(lat=lat, lon=lon, location_id="loc-a")},
        forecast_values={
            "loc-a": (
                _weather_value(
                    location_id="loc-a",
                    metric_key="TEMP",
                    value_number=10.0,
                    target_at=_at(day1_date),
                ),
                _weather_value(
                    location_id="loc-a",
                    metric_key="HUMIDITY",
                    value_number=50.0,
                    target_at=_at(day2_date),
                ),
            )
        },
    )

    view = await _build_view(
        session_factory,
        pois=[
            (1, day1_date, feature_id, _snapshot(lon, lat)),
            (2, day2_date, feature_id, _snapshot(lon, lat)),
        ],
        map_client=map_client,
        weather_client=weather_client,
    )

    day1_card = _day(view, 1)["weather_cards"]["loc-a"]
    day2_card = _day(view, 2)["weather_cards"]["loc-a"]
    assert [m["metric_key"] for m in day1_card["metrics"]] == ["TMP"]
    assert [m["metric_key"] for m in day2_card["metrics"]] == ["REH"]
    # 날짜마다 반복 호출하지 않는다 — location당 정확히 1회, from/to로 전체 구간을 덮는다.
    assert len(weather_client.forecast_calls) == 1
    call = weather_client.forecast_calls[0]
    assert call["from_"] == datetime(2026, 10, 1, tzinfo=_SEOUL)
    assert call["to"] == datetime(2026, 10, 4, tzinfo=_SEOUL)


async def test_flag_on_markers_latest_feeds_the_card(session_factory) -> None:  # type: ignore[no-untyped-def]
    """`markers()`의 `latest`도 카드에 반영된다(현재값+특보, forecast()와 별개 경로)."""
    settings.pinvi_kor_travel_weather_trip_view_enabled = True
    eff_date = date(2026, 10, 1)
    lat, lon = 37.5, 127.0
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    map_client = _MapClient()
    weather_client = _WeatherClient(
        resolutions={(lat, lon): _resolved(lat=lat, lon=lon, location_id="loc-a")},
        marker_values={
            "loc-a": (
                _weather_value(
                    location_id="loc-a",
                    metric_key="TEMP",
                    value_number=15.0,
                    forecast_style="observed",
                    target_at=_at(eff_date),
                ),
            )
        },
    )

    view = await _build_view(
        session_factory,
        pois=[(1, eff_date, feature_id, _snapshot(lon, lat))],
        map_client=map_client,
        weather_client=weather_client,
    )

    card = _day(view, 1)["weather_cards"]["loc-a"]
    assert [m["metric_key"] for m in card["metrics"]] == ["T1H"]
