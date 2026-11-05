"""Dagster 전용 좁은 내부 경계. 사용자 JWT·관리자 토큰을 사용하지 않는다."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from app.clients.kor_travel_map import OptionalKorTravelMapHttpClientDep
from app.clients.kor_travel_weather import OptionalKorTravelWeatherClientDep
from app.core.config import settings
from app.schemas.envelope import Envelope
from app.services.telegram_planner import plan_due

router = APIRouter(tags=["telegram"])


@router.post("/internal/telegram/plan", response_model=Envelope[dict[str, int]])
async def plan_notifications(
    map_client: OptionalKorTravelMapHttpClientDep,
    weather_client: OptionalKorTravelWeatherClientDep,
    planner_key: Annotated[str | None, Header(alias="X-Pinvi-Notification-Planner-Key")] = None,
) -> Envelope[dict[str, int]]:
    expected = settings.pinvi_telegram_planner_key
    if (
        not expected
        or planner_key is None
        or not hmac.compare_digest(expected.encode(), planner_key.encode())
    ):
        raise HTTPException(
            404, detail={"code": "RESOURCE_NOT_FOUND", "message": "경로를 찾을 수 없습니다."}
        )
    return Envelope.of(await plan_due(map_client=map_client, weather_client=weather_client))
