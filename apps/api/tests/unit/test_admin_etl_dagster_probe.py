"""Admin ETL Pinvi Dagster live probe 단위 테스트."""

from __future__ import annotations

import asyncio
import json
import re
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from kortravelcommon.http import BoundedResponseError
from pydantic import ValidationError

from app.core.config import Settings
from app.services import admin_etl

_ROOT = Path(__file__).resolve().parents[4]
_ETL_WORKSPACE = _ROOT / "apps" / "etl" / "workspace.yaml"
_ETL_PYPROJECT = _ROOT / "apps" / "etl" / "pyproject.toml"
_ETL_DOCKERFILE = _ROOT / "apps" / "etl" / "Dockerfile"


def _client(
    payloads: dict[str, httpx.Response],
    seen: list[httpx.Request] | None = None,
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return payloads.get(request.url.path, httpx.Response(404, json={"detail": "not found"}))

    return httpx.AsyncClient(
        base_url="http://dagster.test",
        transport=httpx.MockTransport(handler),
    )


def _graphql_payload() -> dict[str, Any]:
    return {
        "data": {
            "version": "1.13.11",
            "repositoryOrError": {
                "__typename": "Repository",
                "name": "__repository__",
                "location": {"name": "pinvi.etl.definitions"},
                "jobs": [
                    {"name": "kasi_special_days_job", "isJob": True},
                    {"name": "pinvi_email_outbox_job", "isJob": True},
                ],
                "schedules": [
                    {
                        "name": "pinvi_email_outbox_schedule",
                        "pipelineName": "pinvi_email_outbox_job",
                        "cronSchedule": "*/15 * * * *",
                        "executionTimezone": "Asia/Seoul",
                        "scheduleState": {"status": "RUNNING"},
                    }
                ],
                "sensors": [],
                "assetNodes": [
                    {"groupName": "pinvi_kasi"},
                    {"groupName": "pinvi_email"},
                    {"groupName": "pinvi_email"},
                ],
            },
            "activeRuns": {"__typename": "Runs", "results": []},
            "runsOrError": {
                "__typename": "Runs",
                "results": [
                    {
                        "runId": "run-1",
                        "status": "SUCCESS",
                        "jobName": "pinvi_email_outbox_job",
                        "startTime": 1781190000.0,
                        "endTime": 1781190010.0,
                        "updateTime": 1781190010.0,
                    }
                ],
            },
        }
    }


async def test_pinvi_dagster_probe_reads_server_info_repository_and_runs() -> None:
    async with _client(
        {
            "/server_info": httpx.Response(
                200,
                json={
                    "dagster_version": "1.13.10",
                    "dagster_webserver_version": "1.13.11",
                    "dagster_graphql_version": "1.13.11",
                },
            ),
            "/graphql": httpx.Response(200, json=_graphql_payload()),
        }
    ) as client:
        result = await admin_etl._fetch_pinvi_dagster_snapshot(
            client,
            base_url="http://dagster.test",
            start=0.0,
            checked_at=datetime(2026, 6, 28, tzinfo=UTC),
        )

    assert result.status == "ok"
    assert result.dagster_version == "1.13.11"
    assert result.dagster_webserver_version == "1.13.11"
    assert result.repository_count == 1
    assert result.job_count == 2
    assert result.asset_count == 3
    assert result.schedule_count == 1
    assert result.repositories[0].location_name == "pinvi.etl.definitions"
    assert result.repositories[0].asset_groups == ["pinvi_email", "pinvi_kasi"]
    assert result.repositories[0].schedules[0].job_name == "pinvi_email_outbox_job"
    assert result.repositories[0].schedules[0].execution_timezone == "Asia/Seoul"
    assert result.repositories[0].schedules[0].status == "RUNNING"
    assert result.recent_runs[0].job_name == "pinvi_email_outbox_job"
    assert result.recent_runs[0].status == "SUCCESS"
    assert result.recent_runs[0].tags == {}


async def test_pinvi_dagster_probe_degrades_when_graphql_fails() -> None:
    async with _client(
        {
            "/server_info": httpx.Response(
                200,
                json={
                    "dagster_version": "1.13.11",
                    "dagster_webserver_version": "1.13.11",
                    "dagster_graphql_version": "1.13.11",
                },
            ),
            "/graphql": httpx.Response(503, json={"detail": "down"}),
        }
    ) as client:
        result = await admin_etl._fetch_pinvi_dagster_snapshot(
            client,
            base_url="http://dagster.test",
            start=0.0,
            checked_at=datetime(2026, 6, 28, tzinfo=UTC),
        )

    assert result.status == "degraded"
    assert result.message == "Dagster live query HTTP 503"
    assert result.dagster_version == "1.13.11"
    assert result.repositories == []
    assert result.recent_runs == []


def _default_location_name() -> str:
    default = Settings.model_fields["pinvi_dagster_location_name"].default
    assert isinstance(default, str)
    return default


def test_the_location_name_is_the_one_the_etl_workspace_serves() -> None:
    """location 이름의 정본은 `apps/etl/workspace.yaml`이다 — 둘이 갈라지면 조회가 빈다."""
    workspace = yaml.safe_load(_ETL_WORKSPACE.read_text(encoding="utf-8"))
    locations = [entry["grpc_server"]["location_name"] for entry in workspace["load_from"]]
    assert locations == [_default_location_name()]


def test_the_location_name_is_the_module_the_code_server_loads() -> None:
    """location 이름은 code-server가 싣는 모듈 이름과 같다(Dagster `-m` 로드의 기본 이름).

    그 모듈의 정본은 `pyproject.toml [tool.dagster].module_name`이고, 이미지 기본 CMD의
    `-m`도 같은 모듈을 싣는다. 셋 중 하나만 바뀌면 조회가 빈 repository를 본다.
    """
    pyproject = tomllib.loads(_ETL_PYPROJECT.read_text(encoding="utf-8"))
    assert pyproject["tool"]["dagster"]["module_name"] == _default_location_name()

    cmd = re.search(r"^CMD (\[.*\])$", _ETL_DOCKERFILE.read_text(encoding="utf-8"), re.MULTILINE)
    assert cmd is not None, "ETL Dockerfile에 exec-form CMD가 없다"
    argv = json.loads(cmd.group(1))
    assert argv[argv.index("-m") + 1] == _default_location_name()


def test_the_location_setting_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PINVI_DAGSTER_LOCATION_NAME", "other.location")
    assert Settings(_env_file=None).pinvi_dagster_location_name == "other.location"


@pytest.mark.parametrize(
    "value", ["", " ", "\t", " pinvi.etl.definitions", "pinvi.etl.definitions "]
)
def test_an_empty_or_padded_location_setting_refuses_to_boot(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """compose의 `${VAR:-}`는 미설정을 빈 문자열로 주입한다 — 빈 이름으로 조용히 빈 조회를 하지 않는다."""
    monkeypatch.setenv("PINVI_DAGSTER_LOCATION_NAME", value)
    with pytest.raises(ValidationError, match="PINVI_DAGSTER_LOCATION_NAME"):
        Settings(_env_file=None)


def test_the_live_query_follows_the_location_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """상수가 아니라 설정을 읽는다 — 다른 location으로 옮기면 두 조회가 함께 따라간다."""
    monkeypatch.setattr(admin_etl.settings, "pinvi_dagster_location_name", "other.location")
    variables = admin_etl._pinvi_dagster_live_variables()
    assert variables["repositorySelector"]["repositoryLocationName"] == "other.location"
    assert variables["runsFilter"]["tags"][0]["value"] == "__repository__@other.location"


async def test_pinvi_dagster_probe_scopes_repository_and_runs_to_the_pinvi_location() -> None:
    """공유 Dagster webserver에서도 PinVi 것만 보도록 두 조회를 모두 좁힌다."""
    seen: list[httpx.Request] = []
    async with _client(
        {
            "/server_info": httpx.Response(200, json={"dagster_version": "1.13.24"}),
            "/graphql": httpx.Response(200, json=_graphql_payload()),
        },
        seen,
    ) as client:
        await admin_etl._fetch_pinvi_dagster_snapshot(
            client,
            base_url="http://dagster.test",
            start=0.0,
            checked_at=datetime(2026, 9, 29, tzinfo=UTC),
        )

    (graphql_request,) = [req for req in seen if req.url.path == "/graphql"]
    body = json.loads(graphql_request.content)
    query = body["query"]
    assert "repositoriesOrError" not in query
    assert "repositoryOrError(repositorySelector: $repositorySelector)" in query
    assert "runsOrError(filter: $runsFilter, limit: $runLimit)" in query
    variables = body["variables"]
    assert variables["repositorySelector"] == {
        "repositoryLocationName": "pinvi.etl.definitions",
        "repositoryName": "__repository__",
    }
    assert variables["runsFilter"] == {
        "tags": [
            {
                "key": ".dagster/repository",
                "value": "__repository__@pinvi.etl.definitions",
            }
        ]
    }
    assert variables["runLimit"] == admin_etl.PINVI_DAGSTER_RECENT_RUN_LIMIT


async def test_every_tick_selection_is_bounded_to_a_recent_window() -> None:
    """`ticks(limit: N)`에 `afterTimestamp`가 없으면 Dagster는 instigator의 **전체** tick 이력을
    읽고 정렬한 뒤 N건만 남긴다 — 공유 `job_ticks`가 커지자 webserver statement timeout(15초)과
    probe timeout(당시 2초)을 모두 넘겨 summary가 항상 degraded였다(2026-10-13). 모든 tick 선택은
    창 변수를 실어야 하고, 그 값은 호출 시각에서 창만큼 뺀 epoch여야 한다.
    """
    seen: list[httpx.Request] = []
    started = time.time()
    async with _client(
        {
            "/server_info": httpx.Response(200, json={"dagster_version": "1.13.24"}),
            "/graphql": httpx.Response(200, json=_graphql_payload()),
        },
        seen,
    ) as client:
        await admin_etl._fetch_pinvi_dagster_snapshot(
            client,
            base_url="http://dagster.test",
            start=0.0,
            checked_at=datetime.now(UTC),
        )
    finished = time.time()

    (graphql_request,) = [req for req in seen if req.url.path == "/graphql"]
    body = json.loads(graphql_request.content)
    query, variables = body["query"], body["variables"]
    windows = {
        "scheduleState": admin_etl.PINVI_DAGSTER_SCHEDULE_TICK_WINDOW_SECONDS,
        "sensorState": admin_etl.PINVI_DAGSTER_SENSOR_TICK_WINDOW_SECONDS,
    }
    selections = re.findall(r"(scheduleState|sensorState)\s*\{\s*status\s*ticks\(([^)]*)\)", query)
    assert {state for state, _ in selections} == set(windows)
    assert query.count("ticks(") == len(selections), "창 없는 tick 선택이 남아 있다"
    for state, arguments in selections:
        reference = re.search(r"afterTimestamp:\s*\$(\w+)", arguments)
        assert reference is not None, f"{state}의 ticks에 afterTimestamp 변수가 없다: {arguments}"
        value = variables[reference.group(1)]
        assert isinstance(value, float)
        assert started - windows[state] <= value <= finished - windows[state]


async def test_live_query_timeout_is_reported_as_a_timeout() -> None:
    """2026-10-13의 statement timeout은 '연결 실패'로 보였다 — 시간 초과는 따로 이름 붙인다.

    재시도 한 번까지 넘기면(두 번 모두 시간 초과) 그제야 degraded다.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/server_info":
            return httpx.Response(200, json={"dagster_version": "1.13.24"})
        raise httpx.ReadTimeout("fixture", request=request)

    async with httpx.AsyncClient(
        base_url="http://dagster.test", transport=httpx.MockTransport(handler)
    ) as client:
        result = await admin_etl._fetch_pinvi_dagster_snapshot(
            client,
            base_url="http://dagster.test",
            start=0.0,
            checked_at=datetime.now(UTC),
            deadline=time.perf_counter() + 10.0,
        )

    assert [req.url.path for req in seen] == ["/server_info", "/graphql", "/graphql"]
    assert result.status == "degraded"
    assert result.message == "Dagster live query 시간 초과"
    assert result.dagster_version == "1.13.24"
    assert result.job_count is None


async def test_a_timed_out_live_query_is_retried_once_within_the_remaining_budget() -> None:
    """cold cache에서 끊긴 첫 시도가 storage 페이지를 데우므로(n150 7.96초 → 0.21초) 남은 예산으로
    한 번 더 보낸다. 재시도의 소켓·전체 상한은 남은 예산이고, 변수는 첫 시도와 같다.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/server_info":
            return httpx.Response(200, json={"dagster_version": "1.13.24"})
        if len([req for req in seen if req.url.path == "/graphql"]) == 1:
            raise httpx.ReadTimeout("fixture", request=request)
        return httpx.Response(200, json=_graphql_payload())

    budget = 10.0
    started = time.perf_counter()
    async with httpx.AsyncClient(
        base_url="http://dagster.test",
        transport=httpx.MockTransport(handler),
        timeout=admin_etl.PINVI_DAGSTER_PROBE_TIMEOUT_SECONDS,
    ) as client:
        result = await admin_etl._fetch_pinvi_dagster_snapshot(
            client,
            base_url="http://dagster.test",
            start=started,
            checked_at=datetime.now(UTC),
            deadline=started + budget,
        )
    elapsed = time.perf_counter() - started

    assert result.status == "ok", result.message
    assert result.job_count == 2
    first, second = [req for req in seen if req.url.path == "/graphql"]
    assert json.loads(first.content) == json.loads(second.content)
    retry_timeout = second.extensions["timeout"]
    assert 0 < retry_timeout["read"] <= budget - elapsed + 0.5
    assert first.extensions["timeout"]["read"] == admin_etl.PINVI_DAGSTER_PROBE_TIMEOUT_SECONDS


async def test_a_timed_out_live_query_is_not_retried_without_budget() -> None:
    """예산이 남지 않았으면 재시도 없이 첫 시간 초과를 그대로 보고한다."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/server_info":
            return httpx.Response(200, json={"dagster_version": "1.13.24"})
        raise httpx.ReadTimeout("fixture", request=request)

    async with httpx.AsyncClient(
        base_url="http://dagster.test", transport=httpx.MockTransport(handler)
    ) as client:
        result = await admin_etl._fetch_pinvi_dagster_snapshot(
            client,
            base_url="http://dagster.test",
            start=0.0,
            checked_at=datetime.now(UTC),
            deadline=time.perf_counter(),
        )

    assert [req.url.path for req in seen] == ["/server_info", "/graphql"]
    assert result.status == "degraded"
    assert result.message == "Dagster live query 시간 초과"


async def test_pinvi_dagster_probe_degrades_when_the_pinvi_location_is_absent() -> None:
    """공유 webserver에 PinVi location이 아직 없으면 다른 테넌트로 채우지 않고 degraded다."""
    payload = _graphql_payload()
    payload["data"]["repositoryOrError"] = {
        "__typename": "RepositoryNotFoundError",
        "message": "Could not find a repository",
    }
    payload["data"]["runsOrError"] = {"__typename": "Runs", "results": []}
    async with _client(
        {
            "/server_info": httpx.Response(200, json={"dagster_version": "1.13.24"}),
            "/graphql": httpx.Response(200, json=payload),
        }
    ) as client:
        result = await admin_etl._fetch_pinvi_dagster_snapshot(
            client,
            base_url="http://dagster.test",
            start=0.0,
            checked_at=datetime(2026, 9, 29, tzinfo=UTC),
        )

    assert result.status == "degraded"
    assert result.message == "Dagster repository 조회 실패: RepositoryNotFoundError"
    assert result.repositories == []


async def test_old_active_run_survives_recent_window_and_duplicates_are_removed() -> None:
    payload = _graphql_payload()
    recent = payload["data"]["runsOrError"]["results"][0]
    active = {
        **recent,
        "runId": "old-active",
        "status": "STARTED",
        "startTime": 1.0,
        "updateTime": 1.0,
        "endTime": None,
    }
    payload["data"]["activeRuns"]["results"] = [active, recent]
    async with _client(
        {
            "/server_info": httpx.Response(200, json={}),
            "/graphql": httpx.Response(200, json=payload),
        }
    ) as client:
        result = await admin_etl._fetch_pinvi_dagster_snapshot(
            client, base_url="http://dagster.test", start=0.0, checked_at=datetime.now(UTC)
        )
    assert result.status == "ok"
    assert {run.run_id for run in result.recent_runs} == {"run-1", "old-active"}
    variables = admin_etl._pinvi_dagster_live_variables()
    assert variables["activeRunsFilter"]["tags"] == variables["runsFilter"]["tags"]
    assert set(variables["activeRunsFilter"]["statuses"]) == {
        "NOT_STARTED",
        "QUEUED",
        "STARTING",
        "STARTED",
        "CANCELING",
    }


async def test_active_query_failure_and_cap_are_not_healthy_empty() -> None:
    for active in [
        {"__typename": "PythonError"},
        {
            "__typename": "Runs",
            "results": [{"runId": str(i), "status": "STARTED"} for i in range(1000)],
        },
    ]:
        payload = _graphql_payload()
        payload["data"]["activeRuns"] = active
        async with _client(
            {
                "/server_info": httpx.Response(200, json={}),
                "/graphql": httpx.Response(200, json=payload),
            }
        ) as client:
            result = await admin_etl._fetch_pinvi_dagster_snapshot(
                client, base_url="http://dagster.test", start=0.0, checked_at=datetime.now(UTC)
            )
        assert result.status == "degraded"
        assert result.job_count is None and result.repository_count is None


async def test_decoded_response_size_limit_and_nonobject_are_rejected() -> None:
    for response, expected_error in [
        (
            httpx.Response(200, content=b"x" * (admin_etl.PINVI_DAGSTER_RESPONSE_LIMIT + 1)),
            BoundedResponseError,
        ),
        (httpx.Response(200, json=[]), ValueError),
    ]:
        async with _client({"/large": response}) as client:
            with pytest.raises(expected_error):
                await admin_etl._bounded_dagster_request(client, "GET", "http://dagster.test/large")


def test_last_tick_chooses_timestamp_and_never_exposes_error_payload() -> None:
    tick = admin_etl._last_tick(
        {
            "ticks": [
                {"status": "STARTED", "timestamp": 1},
                {"status": "FAILURE", "timestamp": 2, "error": {"message": "secret"}},
            ]
        }
    )
    assert tick is not None
    assert tick.model_dump() == {"status": "FAILURE", "timestamp": 2.0}


def test_run_runtime_tag_is_allowlisted_without_exposing_other_tags() -> None:
    from app.services.admin_etl import _pinvi_runs_from_graphql

    result = _pinvi_runs_from_graphql(
        {
            "__typename": "Runs",
            "results": [
                {
                    "runId": "run",
                    "status": "NOT_STARTED",
                    "tags": [
                        {"key": "dagster/max_runtime", "value": "120"},
                        {"key": "secret", "value": "never-export"},
                    ],
                }
            ],
        }
    )
    assert result[0].tags == {"dagster/max_runtime": "120"}


@pytest.mark.asyncio
async def test_compressed_response_is_rejected_before_any_decompression() -> None:
    class NeverRead(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError("compressed body must never be consumed")
            yield b"unreachable"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, headers={"content-encoding": "gzip"}, stream=NeverRead())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BoundedResponseError, match="압축"):
            await admin_etl._bounded_dagster_request(
                client, "GET", "http://dagster.test/compressed"
            )


@pytest.mark.parametrize(
    "rows",
    [
        None,
        {},
        [{"runId": "", "status": "STARTED"}],
        [{"runId": "x", "status": "unknown"}],
        [{"runId": "x", "status": []}],
        [{"runId": "x", "status": {}}],
        [{"runId": "x", "status": True}],
        [{"runId": "x", "status": 1}],
    ],
)
async def test_malformed_active_results_never_claim_healthy(rows) -> None:
    payload = _graphql_payload()
    payload["data"]["activeRuns"]["results"] = rows
    async with _client(
        {
            "/server_info": httpx.Response(200, json={}),
            "/graphql": httpx.Response(200, json=payload),
        }
    ) as client:
        result = await admin_etl._fetch_pinvi_dagster_snapshot(
            client, base_url="http://dagster.test", start=0.0, checked_at=datetime.now(UTC)
        )
    assert result.status == "degraded"
    assert result.job_count is None


@pytest.mark.parametrize("outcome", ["ok", "timeout", "error", "cancel"])
async def test_probe_disposes_client_with_separate_budget_and_preserves_cancel(
    monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    entered = asyncio.Event()
    close_cancelled = asyncio.Event()

    class SlowCloseTransport(httpx.MockTransport):
        async def aclose(self) -> None:
            try:
                await asyncio.sleep(0.25)
            except asyncio.CancelledError:
                close_cancelled.set()
                raise

    client = httpx.AsyncClient(transport=SlowCloseTransport(lambda _: httpx.Response(200)))
    monkeypatch.setattr(admin_etl.httpx, "AsyncClient", lambda **_: client)
    monkeypatch.setattr(admin_etl.settings, "pinvi_dagster_base_url", "http://dagster.test")
    monkeypatch.setattr(admin_etl, "PINVI_DAGSTER_TOTAL_TIMEOUT_SECONDS", 0.02)

    async def fetch(*args: Any, **kwargs: Any) -> admin_etl._PinviDagsterProbeResult:
        entered.set()
        if outcome in {"timeout", "cancel"}:
            await asyncio.sleep(1)
        if outcome == "error":
            raise httpx.ConnectError("fixture")
        return admin_etl._PinviDagsterProbeResult(
            status="ok", message="fixture", latency_ms=0, checked_at=datetime.now(UTC)
        )

    monkeypatch.setattr(admin_etl, "_fetch_pinvi_dagster_snapshot", fetch)
    started = time.perf_counter()
    task = asyncio.create_task(admin_etl._probe_pinvi_dagster())
    await entered.wait()
    if outcome == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await task
        assert result.status == ("ok" if outcome == "ok" else "down")
        if outcome == "timeout":
            # 바깥 전체 예산이 끊은 것은 연결 실패가 아니다 — 시간 초과로 이름 붙인다.
            assert result.message == "Dagster probe 전체 예산 초과"
    assert time.perf_counter() - started < 0.2
    assert close_cancelled.is_set()
    assert client.is_closed


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "collections_missing",
        "collections_null",
        "foreign_name",
        "foreign_location",
        "bad_row",
        "valid_empty",
    ],
)
async def test_pinvi_repository_requires_complete_owned_metadata(case: str) -> None:
    payload = _graphql_payload()
    repository = payload["data"]["repositoryOrError"]
    if case == "missing":
        repository = {"__typename": "Repository"}
    elif case == "collections_missing":
        repository = {key: repository[key] for key in ("__typename", "name", "location")}
    elif case == "collections_null":
        repository["assetNodes"] = None
    elif case == "foreign_name":
        repository["name"] = "geo_repository"
    elif case == "foreign_location":
        repository["location"] = {"name": "geo_location"}
    elif case == "bad_row":
        repository["jobs"] = [None]
    else:
        for key in ("jobs", "schedules", "sensors", "assetNodes"):
            repository[key] = []
    payload["data"]["repositoryOrError"] = repository
    async with _client(
        {
            "/server_info": httpx.Response(200, json={"dagster_version": "1.13.24"}),
            "/graphql": httpx.Response(200, json=payload),
        }
    ) as client:
        result = await admin_etl._fetch_pinvi_dagster_snapshot(
            client,
            base_url="http://dagster.test",
            start=0,
            checked_at=datetime.now(UTC),
        )
    assert result.status == ("ok" if case == "valid_empty" else "degraded")
    assert result.repository_count == (1 if case == "valid_empty" else None)
    if case != "valid_empty":
        assert result.repositories == []
        assert result.job_count is None
