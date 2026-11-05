"""직접 weather 카드와 관리자 요청은 각 설정 예산을 사용한다."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.clients import kor_travel_weather
from app.services import admin_weather_values, weather_card


async def test_direct_card_reads_its_configured_budget(monkeypatch) -> None:
    seen = []

    async def collect(*_args, **_kwargs):
        scope = kor_travel_weather._call_scope.get()
        seen.append(scope.deadline - asyncio.get_running_loop().time())
        return [], None

    monkeypatch.setattr(
        weather_card,
        "settings",
        SimpleNamespace(pinvi_kor_travel_weather_request_budget_seconds=0.25),
        raising=False,
    )
    monkeypatch.setattr(weather_card, "_collect_direct", collect)
    await weather_card.resolve_and_collect_deduped_values(
        None,
        feature_id="fixture",
        lat=37.5,
        lon=127.0,
        asof=None,
        weather_client=None,
    )
    assert 0.20 < seen[0] <= 0.25


async def test_admin_uses_its_budget_instead_of_card_budget(monkeypatch) -> None:
    seen = []

    async def collect(*_args, **kwargs):
        seen.append(kwargs.get("direct_budget_seconds"))
        return [], None

    monkeypatch.setattr(
        admin_weather_values,
        "settings",
        SimpleNamespace(pinvi_kor_travel_weather_admin_request_budget_seconds=0.8),
        raising=False,
    )
    monkeypatch.setattr(admin_weather_values, "collect_weather_values", collect)
    await admin_weather_values.build_admin_feature_weather_values(
        None,
        feature_id="fixture",
        lat=37.5,
        lon=127.0,
        asof=None,
        weather_client=None,
    )
    assert seen == [0.8]
