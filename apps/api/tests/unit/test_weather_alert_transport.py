"""사용자가 받는 특보의 잘못된 지역·불완전 타입은 경계에서 거절한다."""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_weather import KorTravelWeatherClient, KorTravelWeatherContractError


def alert_response() -> dict[str, Any]:
    stamp = "2026-11-05T09:30:00+00:00"
    return {
        "namespace": "kr_bjd",
        "bjd_code": "26",
        "region_status": "known",
        "mapping_version": "owned-fixture",
        "mapping_valid_from": stamp,
        "mapping_coverage": "partial",
        "unverified_scope_count": 0,
        "collection_status": "success",
        "last_attempt_at": stamp,
        "last_success_at": stamp,
        "last_error_code": None,
        "fresh": True,
        "events_complete": True,
        "retained_since": stamp,
        "history_available_since": stamp,
        "queried_since": stamp,
        "absence_is_clear": False,
        "events": [],
    }


async def test_alert_events_exact_public_query_without_credentials() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": alert_response()})

    async with httpx.AsyncClient(
        base_url="http://weather.test", transport=httpx.MockTransport(handler)
    ) as http:
        value = await KorTravelWeatherClient(http).alert_events(
            bjd_code="26", since=datetime(2026, 11, 5, 9, 30, tzinfo=UTC)
        )
    assert value.events == [] and value.absence_is_clear is False
    assert seen[0].url.path == "/v1/weather/alert-events"
    assert dict(seen[0].url.params) == {"bjd_code": "26", "since": "2026-11-05T09:30:00+00:00"}
    assert "authorization" not in seen[0].headers


@pytest.mark.parametrize(
    "field,value",
    [
        ("namespace", "forecast_zone"),
        ("bjd_code", "11"),
        ("fresh", "false"),
        ("events_complete", 1),
        ("absence_is_clear", True),
        ("last_success_at", "2026-11-05T09:30:00"),
        ("events", None),
    ],
)
async def test_alert_events_rejects_dangerous_contract(field: str, value: Any) -> None:
    data = alert_response()
    data[field] = value
    async with httpx.AsyncClient(
        base_url="http://weather.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": data})),
    ) as http:
        with pytest.raises(KorTravelWeatherContractError):
            await KorTravelWeatherClient(http).alert_events(
                bjd_code="26", since=datetime(2026, 11, 5, tzinfo=UTC)
            )


@pytest.mark.parametrize(
    "code,since",
    [
        ("260", datetime(2026, 11, 5, tzinfo=UTC)),
        ("invalid", datetime(2026, 11, 5, tzinfo=UTC)),
        ("26", datetime(2026, 11, 5)),
    ],
)
async def test_alert_invalid_query_never_calls_provider(code: str, since: datetime) -> None:
    def forbidden(_: httpx.Request) -> httpx.Response:
        pytest.fail("invalid input must not call Weather")

    async with httpx.AsyncClient(
        base_url="http://weather.test", transport=httpx.MockTransport(forbidden)
    ) as http:
        with pytest.raises(ValueError):
            await KorTravelWeatherClient(http).alert_events(bjd_code=code, since=since)


async def test_alert_events_scope_is_compared_at_whole_seconds_across_offsets() -> None:
    """서버가 초 단위·KST 표기로 범위를 돌려줘도 같은 순간이면 받는다."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = alert_response()
        body["queried_since"] = "2026-11-05T18:30:00+09:00"
        return httpx.Response(200, json={"data": body})

    async with httpx.AsyncClient(
        base_url="http://weather.test", transport=httpx.MockTransport(handler)
    ) as http:
        value = await KorTravelWeatherClient(http).alert_events(
            bjd_code="26", since=datetime(2026, 11, 5, 9, 30, 0, 700_000, tzinfo=UTC)
        )
    assert value.absence_is_clear is False
    assert seen[0].url.params["since"] == "2026-11-05T09:30:00+00:00"
