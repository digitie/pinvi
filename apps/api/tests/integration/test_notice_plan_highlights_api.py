"""`GET /notice-plans/{id}/highlights` — 추천 여행 주변 축제·큐레이션(실 DB + Map MockTransport)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest

from app.clients.kor_travel_map import KorTravelMapClient
from app.main import app
from app.models.user import User
from app.services.notice_plan import create_plan_with_pois

pytestmark = pytest.mark.asyncio


async def _seed_plan(session_factory, *, is_published: bool = True) -> uuid.UUID:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        admin = User(
            email=f"admin_{uuid.uuid4().hex[:8]}@pinvi.test",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        plan = await create_plan_with_pois(
            db,
            admin_id=admin.user_id,
            slug=f"gangneung-{uuid.uuid4().hex[:6]}",
            title="강릉 바다 코스",
            is_published=is_published,
            pois=[
                {
                    "day_index": 1,
                    "sort_order": "a0",
                    "feature_id": "f_gyeongpo",
                    "feature_snapshot": {
                        "name": "경포해변",
                        "lon": 128.908,
                        "lat": 37.806,
                        "address": {"sido_code": "51", "road": "강원 강릉시 창해로 514"},
                    },
                }
            ],
        )
        return plan.curated_plan_id


def _map_client() -> KorTravelMapClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/curations":
            data = {
                "items": [
                    {
                        "feature": {
                            "feature_id": "f_ojukheon",
                            "name": "오죽헌",
                            "kind": "place",
                            "category": "01020100",
                            "lon": 128.879,
                            "lat": 37.779,
                            "address": {"road": "강원 강릉시 율곡로3139번길 24"},
                        },
                        "curations": [
                            {
                                "theme_name": "한국관광 100선",
                                "title": "한국관광 100선",
                                "edition_key": "2025-2026",
                                "item_summary": None,
                                "source_url": None,
                                "status": "included",
                            }
                        ],
                        "curation_count": 1,
                    }
                ]
            }
        else:
            data = {
                "months": [],
                "items": [
                    {
                        "feature_id": "f_fest",
                        "festival_name": "강릉 겨울바다 축제",
                        "event_status": "scheduled",
                        "address": {},
                        "source_providers": ["tourapi"],
                        "updated_at": "2026-11-01T00:00:00Z",
                        "event_start_date": None,
                        "event_end_date": None,
                        "lon": 128.9,
                        "lat": 37.8,
                    }
                ],
            }
        return httpx.Response(200, json={"data": data, "meta": {}})

    http = httpx.AsyncClient(
        base_url="http://kor-travel-map.test", transport=httpx.MockTransport(handler)
    )
    return KorTravelMapClient(http, public_api_key="k", max_attempts=1)


async def test_highlights_returns_curated_and_events(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    plan_id = await _seed_plan(session_factory)
    map_client = _map_client()
    app.state.kor_travel_map_client = map_client
    try:
        resp = await client.get(f"/notice-plans/{plan_id}/highlights")
    finally:
        app.state.kor_travel_map_client = None
        await map_client.aclose()
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["notice_plan_id"] == str(plan_id)
    assert data["window_basis"] == "upcoming"
    assert data["region_scope"] == "sido"
    assert data["unavailable"] == []
    assert [c["name"] for c in data["curated"]] == ["오죽헌"]
    assert data["curated"][0]["themes"][0]["edition_key"] == "2025-2026"
    assert [e["name"] for e in data["events"]] == ["강릉 겨울바다 축제"]


async def test_highlights_without_map_degrades_to_unavailable(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    plan_id = await _seed_plan(session_factory)
    app.state.kor_travel_map_client = None
    resp = await client.get(f"/notice-plans/{plan_id}/highlights")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["unavailable"] == ["curated", "events"]


async def test_highlights_hidden_for_unpublished_plan(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    plan_id = await _seed_plan(session_factory, is_published=False)
    resp = await client.get(f"/notice-plans/{plan_id}/highlights")
    assert resp.status_code == 404
