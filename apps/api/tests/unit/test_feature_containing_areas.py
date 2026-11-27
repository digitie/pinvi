"""장소 상세 카드의 "○○국립공원 안 / ○○ 보호지역 안" — Map containing-areas 소비.

Map `GET /v1/features/{feature_id}/containing-areas`(2026-11-27)를 client가 어떻게 부르고, 상세 카드가
플래그·실패·계약 밖 행을 어떻게 다루는지 본다. 플래그 기본값이 off인 이유: Map이 국립공원 경계를
재적재(3 km 버퍼 → 실제 경계)하기 전에는 버퍼 면이 은평·도봉 시가지까지 "북한산 안"으로 답한다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.api.v1 import features as features_api
from app.clients.kor_travel_map import KorTravelMapClient, KorTravelMapUnavailable
from app.core.config import Settings
from app.schemas.feature import PlaceDetailCard

pytestmark = pytest.mark.asyncio

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> KorTravelMapClient:
    http = httpx.AsyncClient(
        base_url="http://kor_travel_map.test", transport=httpx.MockTransport(handler)
    )
    return KorTravelMapClient(http, max_attempts=1, backoff_base_seconds=0.0)  # type: ignore[arg-type]


_AREAS = [
    {
        "feature_id": "a-small",
        "feature_uuid": "a-small",
        "name": "우이령",
        "category": "01070300",
        "area_kind": "protected_area",
        "boundary_source": "knps",
        "area_square_meters": 1.5e6,
        "marker_icon": "park",
        "marker_color": "P-06",
    },
    {
        "feature_id": "a-park",
        "feature_uuid": "a-park",
        "name": "북한산 국립공원",
        "category": "01020101",
        "area_kind": "national_park",
        "boundary_source": "knps",
        "area_square_meters": 7.9e7,
        "marker_icon": "park",
        "marker_color": "P-06",
    },
]


def _ok(items: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": {"lon": 126.99, "lat": 37.68, "feature_id": "f1", "items": items},
            "meta": {},
        },
    )


async def test_client_sends_kinds_and_page_size_and_keeps_map_order() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok(_AREAS)

    rows = await _client(handler).get_feature_containing_areas(
        "f1", area_kinds=["national_park", "protected_area"], page_size=5
    )

    assert [row["name"] for row in rows] == ["우이령", "북한산 국립공원"]
    request = seen[0]
    assert request.url.path == "/v1/features/f1/containing-areas"
    assert request.url.params.get_list("area_kind") == ["national_park", "protected_area"]
    assert request.url.params["page_size"] == "5"


async def test_client_maps_missing_feature_to_empty() -> None:
    status_code = 404
    rows = await _client(
        lambda _r: httpx.Response(status_code, json={"detail": "x"})
    ).get_feature_containing_areas("f1")

    assert rows == []


async def test_client_rejects_dot_segment_and_escapes_slash() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok([])

    client = _client(handler)
    assert await client.get_feature_containing_areas("..") == []
    assert seen == []
    await client.get_feature_containing_areas("a/b")
    assert seen[0].url.raw_path.startswith(b"/v1/features/a%2Fb/containing-areas")


def _card() -> PlaceDetailCard:
    return PlaceDetailCard(feature_id="f1", name="도선사")


class _FakeClient:
    def __init__(self, result: list[dict[str, Any]] | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    async def get_feature_containing_areas(
        self, feature_id: str, *, area_kinds: tuple[str, ...] = (), page_size: int = 10
    ) -> list[dict[str, Any]]:
        self.calls.append((feature_id, tuple(area_kinds)))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _enable(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
    monkeypatch.setattr(features_api.settings, "pinvi_map_containing_areas_enabled", enabled)


async def test_flag_off_by_default_and_never_calls_map(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings.model_fields["pinvi_map_containing_areas_enabled"].default is False
    _enable(monkeypatch, False)
    client = _FakeClient(_AREAS)
    card = _card()

    await features_api._attach_containing_areas(card, client, "f1")  # type: ignore[arg-type]

    assert client.calls == []
    assert card.containing_areas == []
    assert card.degraded_providers == []


async def test_flag_on_attaches_areas_in_map_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch, True)
    client = _FakeClient(_AREAS)
    card = _card()

    await features_api._attach_containing_areas(card, client, "f1")  # type: ignore[arg-type]

    assert client.calls == [("f1", ("national_park", "protected_area", "hazard_zone"))]
    assert [(a.name, a.area_kind) for a in card.containing_areas] == [
        ("우이령", "protected_area"),
        ("북한산 국립공원", "national_park"),
    ]
    dumped = card.model_dump()["containing_areas"][0]
    assert set(dumped) == {"feature_id", "name", "area_kind"}


async def test_out_of_contract_row_is_dropped_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch, True)
    client = _FakeClient([{"feature_id": "bad", "name": "", "area_kind": "x"}, _AREAS[1]])
    card = _card()

    await features_api._attach_containing_areas(card, client, "f1")  # type: ignore[arg-type]

    assert [a.feature_id for a in card.containing_areas] == ["a-park"]
    assert card.degraded_providers == []


async def test_map_failure_degrades_without_failing_card(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch, True)
    client = _FakeClient(KorTravelMapUnavailable("down"))
    card = _card()

    await features_api._attach_containing_areas(card, client, "f1")  # type: ignore[arg-type]

    assert card.containing_areas == []
    assert card.degraded_providers == ["containing_areas"]


async def test_route_and_area_cards_are_not_attached(monkeypatch: pytest.MonkeyPatch) -> None:
    """Map 판정은 대표점 한 점이다 — 선·면 카드에 "○○ 안"을 붙이면 둘레길이 공원 안이 된다."""
    from app.schemas.feature import GenericDetailCard

    _enable(monkeypatch, True)
    client = _FakeClient(_AREAS)
    for kind in ("route", "area"):
        card = GenericDetailCard(feature_id="r1", name="지리산 둘레길", kind=kind)
        await features_api._attach_containing_areas(card, client, "r1")  # type: ignore[arg-type]
        assert card.containing_areas == []
    assert client.calls == []
