"""Admin ETL Pinvi Dagster live probe 단위 테스트."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.services import admin_etl


_ROOT = Path(__file__).resolve().parents[4]
_ETL_WORKSPACE = _ROOT / "apps" / "etl" / "workspace.yaml"


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


def test_the_location_name_is_the_one_the_etl_workspace_serves() -> None:
    """location 이름의 정본은 `apps/etl/workspace.yaml`이다 — 둘이 갈라지면 조회가 빈다."""
    workspace = yaml.safe_load(_ETL_WORKSPACE.read_text(encoding="utf-8"))
    locations = [entry["grpc_server"]["location_name"] for entry in workspace["load_from"]]
    assert locations == [admin_etl.PINVI_DAGSTER_LOCATION_NAME]


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
