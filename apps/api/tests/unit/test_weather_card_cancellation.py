"""직접 weather 수집 실패·호출자 취소는 시작한 모든 형제 작업을 회수한다."""

import asyncio
from typing import Any

import pytest

from app.clients.kor_travel_weather import KorTravelWeatherError
from app.services.weather_card import _AsofWindow, _fetch_location_values


@pytest.mark.asyncio
@pytest.mark.parametrize("caller_cancel", [False, True])
async def test_direct_card_joins_sibling_cleanup(caller_cancel: bool) -> None:
    started = asyncio.Event()
    cleaned = asyncio.Event()
    children: list[asyncio.Task[Any]] = []

    class Client:
        async def latest(self, *_: Any, **__: Any) -> tuple[()]:
            await started.wait()
            if caller_cancel:
                await asyncio.Event().wait()
            raise KorTravelWeatherError("fixture failure")

        async def forecast(self, *_: Any, **__: Any) -> tuple[()]:
            current = asyncio.current_task()
            assert current is not None
            children.append(current)
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()
            return ()

    pending = asyncio.create_task(
        _fetch_location_values(
            Client(), "fixture", window=_AsofWindow(no_data=False, from_=None, to=None)
        )
    )  # type: ignore[arg-type]
    try:
        await started.wait()
        if caller_cancel:
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            assert await pending == []
        assert cleaned.is_set()
    finally:
        pending.cancel()
        for child in children:
            child.cancel()
        await asyncio.gather(pending, *children, return_exceptions=True)
