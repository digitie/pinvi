"""Admin ETL Pinvi Dagster live probe 단위 테스트."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.services import admin_etl


def _client(payloads: dict[str, httpx.Response]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return payloads.get(request.url.path, httpx.Response(404, json={"detail": "not found"}))

    return httpx.AsyncClient(
        base_url="http://dagster.test",
        transport=httpx.MockTransport(handler),
    )


def _graphql_payload() -> dict[str, Any]:
    return {
        "data": {
            "version": "1.13.11",
            "repositoriesOrError": {
                "__typename": "RepositoryConnection",
                "nodes": [
                    {
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
                    }
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
