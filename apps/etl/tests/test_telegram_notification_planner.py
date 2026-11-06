from __future__ import annotations

import httpx
import pytest
from dagster import build_asset_context

from pinvi.etl.assets.pinvi_telegram_notification_planner import pinvi_telegram_notification_planner
from pinvi.etl.resources import PinviNotificationPlannerResource

pytestmark = pytest.mark.asyncio


async def test_missing_planner_configuration_is_noop() -> None:
    with build_asset_context() as context:
        assert await pinvi_telegram_notification_planner(
            context, PinviNotificationPlannerResource()
        ) == {"enqueued": 0}


@pytest.mark.parametrize(
    "status,body",
    [
        (200, {"data": {"users": 2, "enqueued": 3, "failed": 1}}),
        (503, {"detail": "private provider error"}),
        (200, {"data": {"users": True, "enqueued": -1}}),
    ],
)
async def test_planner_calls_narrow_boundary_and_keeps_error_body_private(
    monkeypatch: pytest.MonkeyPatch, status: int, body: dict
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    monkeypatch.setattr(
        PinviNotificationPlannerResource,
        "create_client",
        lambda self: httpx.AsyncClient(
            base_url="http://owned.test", transport=httpx.MockTransport(handler)
        ),
    )
    resource = PinviNotificationPlannerResource(planner_key="owned-planner-test-key")
    with build_asset_context() as context:
        if status == 200 and body["data"]["enqueued"] == 3:
            assert await pinvi_telegram_notification_planner(context, resource) == {
                "users": 2,
                "enqueued": 3,
                "failed": 1,
            }
        else:
            with pytest.raises(RuntimeError) as error:
                await pinvi_telegram_notification_planner(context, resource)
            assert "private" not in str(error.value) and "owned-planner-test-key" not in str(
                error.value
            )
    assert seen[0].method == "POST" and seen[0].url.path == "/internal/telegram/plan"
    assert seen[0].headers["X-Pinvi-Notification-Planner-Key"] == "owned-planner-test-key"


@pytest.mark.parametrize(
    "data,expected",
    [
        (
            {"users": 0, "enqueued": 0, "failed": 0, "skipped": 1},
            {"users": 0, "enqueued": 0, "failed": 0, "skipped": 1},
        ),
        (
            {"users": 5, "enqueued": 2, "failed": 0, "processed": 3, "deferred": 2},
            {"users": 5, "enqueued": 2, "failed": 0, "processed": 3, "deferred": 2},
        ),
        ({"users": 1, "enqueued": 0, "skipped": -1}, None),
        ({"users": 1, "enqueued": 0, "deferred": True}, None),
    ],
)
async def test_planner_reports_single_flight_and_budget_counts(
    monkeypatch: pytest.MonkeyPatch, data: dict, expected: dict | None
) -> None:
    monkeypatch.setattr(
        PinviNotificationPlannerResource,
        "create_client",
        lambda self: httpx.AsyncClient(
            base_url="http://owned.test",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": data})),
        ),
    )
    resource = PinviNotificationPlannerResource(planner_key="owned-planner-test-key")
    with build_asset_context() as context:
        if expected is None:
            with pytest.raises(RuntimeError):
                await pinvi_telegram_notification_planner(context, resource)
        else:
            assert await pinvi_telegram_notification_planner(context, resource) == expected
