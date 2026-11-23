"""예약 알림 planner schedule gate — 할 일이 있을 때만 run을 띄운다(2026-11-23 감사 §4 #12)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from dagster import DagsterInstance, DagsterRunStatus, build_schedule_context
from dagster._core.remote_origin import (
    RegisteredCodeLocationOrigin,
    RemoteJobOrigin,
    RemoteRepositoryOrigin,
)

from pinvi.etl.definitions import defs
from pinvi.etl.notification_planner_gate import PENDING_PATH
from pinvi.etl.resources import PinviNotificationPlannerResource
from pinvi.etl.run_tags import PINVI_LOCATION_NAME

SCHEDULE_NAME = "pinvi_telegram_notification_planner_schedule"
KEY = "owned-planner-test-key"


def _evaluate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    planner_key: str = KEY,
    active_run: bool = False,
) -> tuple[int, list[httpx.Request]]:
    """정의된 schedule 그대로 한 tick 평가해 run 요청 수와 API 요청을 돌려준다."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(
        PinviNotificationPlannerResource,
        "create_gate_client",
        lambda self: httpx.Client(
            base_url="http://owned.test", transport=httpx.MockTransport(record)
        ),
    )
    schedule = defs.get_schedule_def(SCHEDULE_NAME)
    resource = PinviNotificationPlannerResource(
        base_url="http://owned.test", planner_key=planner_key
    )
    with DagsterInstance.local_temp(tempdir=str(tmp_path)) as instance:
        if active_run:
            job = defs.resolve_job_def(schedule.job_name)
            origin = RemoteJobOrigin(
                RemoteRepositoryOrigin(
                    RegisteredCodeLocationOrigin(PINVI_LOCATION_NAME), "__repository__"
                ),
                job.name,
            )
            instance.create_run_for_job(
                job,
                status=DagsterRunStatus.STARTED,
                tags=dict(job.tags),
                remote_job_origin=origin,
            )
        with build_schedule_context(
            instance=instance,
            scheduled_execution_time=datetime.now(UTC),
            resources={"notification_planner": resource},
        ) as context:
            result = schedule.evaluate_tick(context)
    return len(result.run_requests or []), seen


def _pending(**data: object) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, json={"data": data})


def test_tick_stays_every_minute() -> None:
    # 사용자가 고른 KST 분·특보 30분 창 — tick 간격은 그대로 두고 run만 거른다.
    schedule = defs.get_schedule_def(SCHEDULE_NAME)
    assert schedule.cron_schedule == "* * * * *"
    assert "notification_planner" in schedule.required_resource_keys


def test_no_pending_work_skips_the_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runs, seen = _evaluate(
        monkeypatch, tmp_path, _pending(due=False, users=0, weather=0, daily=0, weekly=0)
    )
    assert runs == 0
    assert len(seen) == 1
    assert seen[0].method == "GET" and seen[0].url.path == PENDING_PATH
    assert seen[0].headers["X-Pinvi-Notification-Planner-Key"] == KEY


def test_pending_work_launches_one_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runs, _ = _evaluate(
        monkeypatch, tmp_path, _pending(due=True, users=1, weather=1, daily=0, weekly=0)
    )
    assert runs == 1


@pytest.mark.parametrize(
    "handler",
    [
        # 점검 경로가 없는 옛 API — 배포 순서와 무관하게 이전처럼 매분 run.
        lambda request: httpx.Response(404, json={"detail": "not found"}),
        lambda request: httpx.Response(503, json={"detail": "private provider error"}),
        lambda request: httpx.Response(200, json={"data": {"due": "yes"}}),
        lambda request: httpx.Response(200, json={"unexpected": True}),
        lambda request: httpx.Response(200, content=b"not json"),
        # JSON이지만 객체가 아닌 본문(프록시 등) — tick을 실패시키지 않고 run을 띄운다.
        lambda request: httpx.Response(200, json=[]),
        lambda request: httpx.Response(200, json=None),
        lambda request: httpx.Response(200, json={"data": []}),
    ],
)
def test_check_failure_fails_open_to_a_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    runs, _ = _evaluate(monkeypatch, tmp_path, handler)
    assert runs == 1


def test_transport_error_fails_open_to_a_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    runs, _ = _evaluate(monkeypatch, tmp_path, refuse)
    assert runs == 1


def test_unconfigured_planner_neither_calls_nor_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runs, seen = _evaluate(monkeypatch, tmp_path, _pending(due=True), planner_key="")
    assert runs == 0
    assert seen == []


def test_active_run_coalesces_before_asking_the_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 진행 중 run이 있으면 점검 HTTP도 부르지 않는다(coalescing이 먼저).
    runs, seen = _evaluate(monkeypatch, tmp_path, _pending(due=True), active_run=True)
    assert runs == 0
    assert seen == []
