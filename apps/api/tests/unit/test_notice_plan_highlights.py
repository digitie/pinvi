"""추천 여행 주변 정보(`services/notice_plan_highlights.py`) 순수 로직 + 구역 격리."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_map import KorTravelMapClient
from app.services import notice_plan_highlights as hl

TODAY = date(2026, 11, 16)


def _festival(
    feature_id: str,
    *,
    start: str | None,
    end: str | None,
    status: str = "scheduled",
    lon: float | None = 128.9,
    lat: float | None = 37.75,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "feature_id": feature_id,
        "festival_name": f"축제 {feature_id}",
        "event_status": status,
        "address": {"road": "강원 강릉시 어딘가"},
        "source_providers": ["tourapi"],
        "updated_at": "2026-11-01T00:00:00Z",
        "event_start_date": start,
        "event_end_date": end,
        "lon": lon,
        "lat": lat,
        **extra,
    }


def _group(feature_id: str, lon: float, lat: float, *, status: str = "included") -> dict[str, Any]:
    return {
        "feature": {
            "feature_id": feature_id,
            "name": f"장소 {feature_id}",
            "kind": "place",
            "category": "01070100",
            "lon": lon,
            "lat": lat,
            "address": {"road": "강원 강릉시 경포로 1"},
        },
        "curations": [
            {
                "theme_name": "한국관광 100선",
                "title": "한국관광 100선",
                "edition_key": "2025-2026",
                "item_summary": "  바다와   호수  ",
                "source_url": "https://example.test/100",
                "status": status,
            }
        ],
        "curation_count": 1,
    }


# --- 기간 창 -----------------------------------------------------------------


def test_window_uses_plan_dates_while_plan_not_over() -> None:
    window = hl.plan_event_window(date(2026, 12, 1), date(2026, 12, 3), TODAY)
    assert (window.start, window.end, window.basis) == (
        date(2026, 12, 1),
        date(2026, 12, 3),
        "plan",
    )


def test_window_falls_back_to_upcoming_for_past_or_undated_plans() -> None:
    past = hl.plan_event_window(date(2025, 5, 1), date(2025, 5, 3), TODAY)
    undated = hl.plan_event_window(None, None, TODAY)
    for window in (past, undated):
        assert window.basis == "upcoming"
        assert window.start == TODAY
        assert (window.end - window.start).days == hl.UPCOMING_WINDOW_DAYS


def test_window_months_skip_past_days_and_cap_at_two() -> None:
    long_plan = hl.plan_event_window(date(2026, 10, 1), date(2027, 3, 1), TODAY)
    assert hl.window_months(long_plan, TODAY) == [(2026, 11), (2026, 12)]
    single = hl.plan_event_window(date(2026, 12, 24), date(2026, 12, 26), TODAY)
    assert hl.window_months(single, TODAY) == [(2026, 12)]


# --- 시도 코드 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        ({"address": {"sido_code": "51"}}, "51"),
        ({"address": {"sigungu_code": "51150"}}, "51"),
        ({"address": {"bjd_code": "5115010100"}}, "51"),
        ({"sigungu_code": "26350"}, "26"),
        ({"address": {"road": "주소만"}}, None),
        ({"address": {"sido_code": "xx"}}, None),
        ({}, None),
    ],
)
def test_snapshot_sido_code(snapshot: dict[str, Any], expected: str | None) -> None:
    assert hl.snapshot_sido_code(snapshot) == expected


# --- 축제 고르기 -------------------------------------------------------------


def test_select_events_keeps_overlapping_live_events_nearest_first() -> None:
    window = hl.plan_event_window(date(2026, 12, 1), date(2026, 12, 3), TODAY)
    anchors = [(128.90, 37.75)]
    picks = hl.select_events(
        [
            _festival("far", start="2026-12-02", end="2026-12-02", lon=129.5, lat=37.0),
            _festival("near", start="2026-11-30", end="2026-12-05", homepage_url="https://f"),
            _festival("near", start="2026-11-30", end="2026-12-05"),  # 월 2회 조회 중복
            _festival("before", start="2026-11-01", end="2026-11-20"),
            _festival("after", start="2026-12-10", end="2026-12-12"),
            _festival("ended", start="2026-12-01", end="2026-12-02", status="ended"),
            _festival("undated", start=None, end=None, status="ongoing"),
            _festival("unknown", start=None, end=None, status="unknown"),
            {"feature_id": "broken"},
        ],
        window=window,
        today=TODAY,
        anchors=anchors,
    )
    assert [p.feature_id for p in picks] == ["near", "undated", "far"]
    assert picks[0].distance_m == 0.0
    assert picks[0].homepage_url == "https://f"
    assert picks[0].address == "강원 강릉시 어딘가"


def test_select_events_drops_days_already_past_in_running_plan() -> None:
    window = hl.plan_event_window(date(2026, 11, 10), date(2026, 11, 20), TODAY)
    picks = hl.select_events(
        [_festival("gone", start="2026-11-10", end="2026-11-12")],
        window=window,
        today=TODAY,
        anchors=[],
    )
    assert picks == []


def test_select_events_clips_long_content_and_caps_count() -> None:
    window = hl.plan_event_window(None, None, TODAY)
    raw = [
        _festival(f"e{i:02d}", start="2026-11-20", end="2026-11-21", festival_content="가" * 500)
        for i in range(hl.EVENT_LIMIT + 5)
    ]
    picks = hl.select_events(raw, window=window, today=TODAY, anchors=[])
    assert len(picks) == hl.EVENT_LIMIT
    assert picks[0].summary is not None
    assert len(picks[0].summary) == hl.SUMMARY_MAX_CHARS
    assert picks[0].summary.endswith("…")


# --- 큐레이션 고르기 ---------------------------------------------------------


def test_select_curated_excludes_plan_features_and_non_included_memberships() -> None:
    picks = hl.select_curated(
        [
            _group("in-plan", 128.9, 37.75),
            _group("candidate-only", 128.9, 37.75, status="candidate"),
            _group("far", 129.3, 37.5),
            _group("near", 128.91, 37.76),
            {"feature": {"feature_id": "broken"}},
        ],
        exclude_feature_ids={"in-plan"},
        anchors=[(128.9, 37.75)],
    )
    assert [p.feature_id for p in picks] == ["near", "far"]
    assert picks[0].themes[0].collection_title == "한국관광 100선"
    assert picks[0].themes[0].summary == "바다와 호수"
    assert picks[0].address == "강원 강릉시 경포로 1"


# --- 조립: Map 호출·구역 격리 -------------------------------------------------


def _poi(feature_id: str | None, snapshot: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(feature_id=feature_id, feature_snapshot=snapshot)


def _patch_plan(
    monkeypatch: pytest.MonkeyPatch,
    *,
    starts_on: date | None,
    ends_on: date | None,
    pois: list[SimpleNamespace],
) -> uuid.UUID:
    plan_id = uuid.uuid4()
    plan = SimpleNamespace(curated_plan_id=plan_id, starts_on=starts_on, ends_on=ends_on)

    async def fake_plan(_db: object, *, notice_plan_id: uuid.UUID) -> SimpleNamespace:
        return plan

    async def fake_pois(_db: object, *, notice_plan_id: uuid.UUID) -> list[SimpleNamespace]:
        return pois

    monkeypatch.setattr(hl, "get_published_plan", fake_plan)
    monkeypatch.setattr(hl, "list_plan_pois", fake_pois)
    return plan_id


def _client(handler: Any) -> KorTravelMapClient:
    http = httpx.AsyncClient(
        base_url="http://kor-travel-map.test", transport=httpx.MockTransport(handler)
    )
    return KorTravelMapClient(http, public_api_key="k", max_attempts=1, backoff_base_seconds=0)


_GANGNEUNG = {"lon": 128.9, "lat": 37.75, "address": {"sido_code": "51", "road": "강릉"}}


async def test_build_queries_sido_months_and_bbox(monkeypatch: pytest.MonkeyPatch) -> None:
    plan_id = _patch_plan(
        monkeypatch,
        starts_on=date(2026, 11, 28),
        ends_on=date(2026, 12, 2),
        pois=[_poi("in-plan", _GANGNEUNG)],
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/v1/curations":
            data = {"items": [_group("in-plan", 128.9, 37.75), _group("near", 128.91, 37.76)]}
        else:
            data = {
                "months": [],
                "items": [_festival("fest", start="2026-12-01", end="2026-12-03")],
            }
        return httpx.Response(200, json={"data": data, "meta": {}})

    client = _client(handler)
    try:
        result = await hl.build_plan_highlights(
            object(),  # type: ignore[arg-type]
            notice_plan_id=plan_id,
            client=client,
            today=TODAY,
        )
    finally:
        await client.aclose()

    assert result.window_basis == "plan"
    assert result.region_scope == "sido"
    assert result.unavailable == []
    assert [p.feature_id for p in result.curated] == ["near"]
    assert [e.feature_id for e in result.events] == ["fest"]

    festival_calls = [r for r in seen if r.url.path == "/v1/public/festivals/monthly"]
    assert sorted(r.url.params["month"] for r in festival_calls) == ["11", "12"]
    assert {r.url.params["sido_code"] for r in festival_calls} == {"51"}
    curation_call = next(r for r in seen if r.url.path == "/v1/curations")
    assert float(curation_call.url.params["min_lon"]) == pytest.approx(128.85)
    assert float(curation_call.url.params["max_lat"]) == pytest.approx(37.80)


async def test_build_isolates_a_failing_section(monkeypatch: pytest.MonkeyPatch) -> None:
    plan_id = _patch_plan(
        monkeypatch, starts_on=None, ends_on=None, pois=[_poi("a", _GANGNEUNG)]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/curations":
            return httpx.Response(503, json={"error": {"code": "UNAVAILABLE"}})
        data = {"months": [], "items": [_festival("fest", start="2026-11-20", end="2026-11-22")]}
        return httpx.Response(200, json={"data": data, "meta": {}})

    client = _client(handler)
    try:
        result = await hl.build_plan_highlights(
            object(),  # type: ignore[arg-type]
            notice_plan_id=plan_id,
            client=client,
            today=TODAY,
        )
    finally:
        await client.aclose()

    assert result.window_basis == "upcoming"
    assert result.unavailable == ["curated"]
    assert result.curated == []
    assert [e.feature_id for e in result.events] == ["fest"]


async def test_build_without_codes_goes_nationwide_and_without_coords_skips_curated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_id = _patch_plan(
        monkeypatch, starts_on=None, ends_on=None, pois=[_poi(None, {"name": "메모만"})]
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"months": [], "items": []}, "meta": {}})

    client = _client(handler)
    try:
        result = await hl.build_plan_highlights(
            object(),  # type: ignore[arg-type]
            notice_plan_id=plan_id,
            client=client,
            today=TODAY,
        )
    finally:
        await client.aclose()

    assert result.region_scope == "nationwide"
    assert result.unavailable == []
    assert all(r.url.path == "/v1/public/festivals/monthly" for r in seen)
    assert all("sido_code" not in r.url.params for r in seen)


async def test_build_without_map_client_marks_both_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_id = _patch_plan(monkeypatch, starts_on=None, ends_on=None, pois=[])
    result = await hl.build_plan_highlights(
        object(),  # type: ignore[arg-type]
        notice_plan_id=plan_id,
        client=None,
        today=TODAY,
    )
    assert result.unavailable == ["curated", "events"]
    assert result.curated == [] and result.events == []
