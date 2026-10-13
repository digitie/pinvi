"""API의 Admin Dagster live query를 **이 lock의 dagster**로 검증한다.

`apps/api/app/services/admin_etl.py`의 `_PINVI_DAGSTER_LIVE_QUERY`는 Dagster webserver에
보내는 GraphQL 문자열이다. API 단위 테스트는 응답을 흉내 낼 뿐이라, 필드 이름·인자·
입력 타입(`RepositorySelector`, `RunsFilter`)이 실제 스키마와 어긋나도 초록이다 — 운영에서
`degraded`로만 드러난다. API 환경에는 dagster가 없으므로 검증은 dagster_graphql이
설치된 ETL 환경(= 운영 webserver와 같은 lock)에서 한다.

세 가지를 본다.
1. 문서가 스키마에서 유효한가.
2. `last_tick` 조회 창(`PINVI_DAGSTER_*_TICK_WINDOW_SECONDS`)이 이 code location의 schedule
   cron 주기·sensor 최소 간격을 덮는가 — 창이 정의보다 짧으면 정상 instigator가 `last_tick=null`
   로 보인다.
3. 창이 실제로 tick storage까지 닿는가 — 이 location을 in-process로 실은 Dagster에 문서를
   실행해 storage `get_ticks`가 받는 `after`를 본다. 창이 없으면 webserver가 instigator마다 전체
   tick 이력을 읽어 공유 `job_ticks`에서 statement timeout에 걸린다(2026-10-13).

query·상수는 import하지 않고 소스에서 읽는다(API 패키지는 이 환경에 없다).
"""

from __future__ import annotations

import ast
import time
from collections.abc import Callable
from itertools import islice, pairwise
from pathlib import Path
from typing import Any

import pytest
from graphql import GraphQLSchema, parse, validate

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ADMIN_ETL = _REPO_ROOT / "apps" / "api" / "app" / "services" / "admin_etl.py"
_QUERY_NAME = "_PINVI_DAGSTER_LIVE_QUERY"
_SCHEDULE_WINDOW_NAME = "PINVI_DAGSTER_SCHEDULE_TICK_WINDOW_SECONDS"
_SENSOR_WINDOW_NAME = "PINVI_DAGSTER_SENSOR_TICK_WINDOW_SECONDS"
_LOCATION_NAME = "pinvi.etl.definitions"


def _module_constant(name: str) -> Any:
    module = ast.parse(_ADMIN_ETL.read_text(encoding="utf-8"))
    values = [
        node.value.value
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
        and isinstance(node.value, ast.Constant)
    ]
    assert len(values) == 1, f"리터럴 상수 {name}를 정확히 하나 찾지 못했다: {_ADMIN_ETL}"
    return values[0]


def _live_query() -> str:
    query = _module_constant(_QUERY_NAME)
    assert isinstance(query, str)
    return query


def _window(name: str) -> int:
    window = _module_constant(name)
    assert isinstance(window, int) and window > 0, f"{name}는 양의 정수 초여야 한다: {window!r}"
    return window


def _dagster_schema() -> GraphQLSchema:
    from dagster_graphql.schema import create_schema

    schema = create_schema().graphql_schema
    assert isinstance(schema, GraphQLSchema)
    return schema


def test_the_admin_live_query_is_valid_against_the_locked_dagster_schema() -> None:
    errors = validate(_dagster_schema(), parse(_live_query()))
    assert errors == [], [error.message for error in errors]


def test_the_schema_check_rejects_an_unknown_field() -> None:
    """검증이 공허하지 않다 — 스키마에 없는 필드는 거부된다."""
    broken = _live_query().replace("assetNodes { groupName }", "assetNodes { noSuchField }")
    assert broken != _live_query()
    errors = validate(_dagster_schema(), parse(broken))
    assert any("noSuchField" in error.message for error in errors)


def _cron_period_seconds(cron: str, timezone: str | None) -> float:
    """연속 두 실행 사이의 가장 긴 간격(초)."""
    from dagster._utils.schedules import cron_string_iterator

    fires = list(
        islice(
            cron_string_iterator(
                start_timestamp=time.time(), cron_string=cron, execution_timezone=timezone
            ),
            8,
        )
    )
    return max((later - earlier).total_seconds() for earlier, later in pairwise(fires))


def test_the_schedule_window_covers_twice_the_longest_cron_period() -> None:
    """어느 schedule이든 정상이라면 창 안에 tick이 적어도 하나 든다(주기의 2배)."""
    from pinvi.etl.definitions import defs

    periods: dict[str, float] = {}
    for schedule in defs.get_repository_def().schedule_defs:
        crons = (
            [schedule.cron_schedule]
            if isinstance(schedule.cron_schedule, str)
            else list(schedule.cron_schedule)
        )
        periods[schedule.name] = max(
            _cron_period_seconds(cron, schedule.execution_timezone) for cron in crons
        )
    assert periods, "schedule이 하나도 없다"
    window = _window(_SCHEDULE_WINDOW_NAME)
    longest = max(periods, key=periods.__getitem__)
    assert periods[longest] * 2 <= window, (
        f"{longest}의 주기 {periods[longest]:.0f}초 × 2 > {_SCHEDULE_WINDOW_NAME}={window}"
    )


def test_the_sensor_window_covers_ten_sensor_intervals() -> None:
    """daemon이 잠시 멈추거나 tick이 늦어도 창이 비지 않는다(최소 간격의 10배 이상)."""
    from dagster._core.definitions.sensor_definition import DEFAULT_SENSOR_DAEMON_INTERVAL

    from pinvi.etl.definitions import defs

    intervals = {
        sensor.name: sensor.minimum_interval_seconds or DEFAULT_SENSOR_DAEMON_INTERVAL
        for sensor in defs.get_repository_def().sensor_defs
    }
    assert intervals, "sensor가 하나도 없다"
    window = _window(_SENSOR_WINDOW_NAME)
    slowest = max(intervals, key=intervals.__getitem__)
    assert intervals[slowest] * 10 <= window, (
        f"{slowest}의 최소 간격 {intervals[slowest]}초 × 10 > {_SENSOR_WINDOW_NAME}={window}"
    )


def _live_variables(now: float) -> dict[str, Any]:
    """API의 `_pinvi_dagster_live_variables()`와 같은 모양. 이름이 갈리면 실행이 거부된다."""
    repository_tag = {"key": ".dagster/repository", "value": f"__repository__@{_LOCATION_NAME}"}
    return {
        "scheduleTicksAfter": now - _window(_SCHEDULE_WINDOW_NAME),
        "sensorTicksAfter": now - _window(_SENSOR_WINDOW_NAME),
        "repositorySelector": {
            "repositoryLocationName": _LOCATION_NAME,
            "repositoryName": "__repository__",
        },
        "runsFilter": {"tags": [repository_tag]},
        "runLimit": 30,
        "activeRunsFilter": {
            "tags": [repository_tag],
            "statuses": ["NOT_STARTED", "QUEUED", "STARTING", "STARTED", "CANCELING"],
        },
        "activeRunLimit": 1000,
    }


def test_the_live_query_passes_the_window_down_to_tick_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """문서를 실제 Dagster로 실행해 storage `get_ticks`가 `after`를 받는지 본다.

    query 문자열이 아니라 효과에 묶는다: `afterTimestamp`가 빠지거나 다른 인자로 바뀌어
    storage가 전체 이력을 읽게 되면 `after=None`으로 떨어진다. instigator마다 정확히 한 번
    조회되는지도 세어 단언이 공허하지 않게 한다.

    아래 import와 이 파일의 `cron_string_iterator`·`DEFAULT_SENSOR_DAEMON_INTERVAL`은 dagster의
    비공개 경로다(1.13.24에서 확인). `uv.lock`의 dagster를 올릴 때 이 파일을 함께 본다. 이 테스트는
    in-process code location 적재로 약 20초가 걸린다.
    """
    from dagster._core.instance_for_test import instance_for_test
    from dagster._core.remote_origin import InProcessCodeLocationOrigin
    from dagster._core.types.loadable_target_origin import LoadableTargetOrigin
    from dagster._core.workspace.context import WorkspaceProcessContext
    from dagster._core.workspace.load_target import InProcessWorkspaceLoadTarget
    from dagster_graphql.test.utils import execute_dagster_graphql

    seen_after: list[float | None] = []
    with instance_for_test() as instance:
        storage = instance.schedule_storage
        assert storage is not None
        real_get_ticks: Callable[..., Any] = storage.get_ticks

        def recording_get_ticks(
            origin_id: str,
            selector_id: str,
            before: float | None = None,
            after: float | None = None,
            limit: int | None = None,
            statuses: Any = None,
        ) -> Any:
            seen_after.append(after)
            return real_get_ticks(
                origin_id, selector_id, before=before, after=after, limit=limit, statuses=statuses
            )

        monkeypatch.setattr(storage, "get_ticks", recording_get_ticks)
        origin = InProcessCodeLocationOrigin(
            LoadableTargetOrigin(module_name=_LOCATION_NAME), location_name=_LOCATION_NAME
        )
        started = time.time()
        with WorkspaceProcessContext(instance, InProcessWorkspaceLoadTarget([origin])) as process:
            result = execute_dagster_graphql(
                process.create_request_context(), _live_query(), _live_variables(started)
            )

    assert not result.errors
    repository = result.data["repositoryOrError"]
    assert repository["__typename"] == "Repository", repository
    instigators = len(repository["schedules"]) + len(repository["sensors"])
    assert instigators > 0
    assert len(seen_after) == instigators, seen_after
    widest = max(_window(_SCHEDULE_WINDOW_NAME), _window(_SENSOR_WINDOW_NAME))
    for after in seen_after:
        assert after is not None, "tick 조회가 창 없이 storage에 닿았다"
        assert started - widest <= after <= started
