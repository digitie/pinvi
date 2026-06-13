"""Prometheus metrics middleware tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.middleware.prometheus import PrometheusMetricsMiddleware, prometheus_metrics


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(PrometheusMetricsMiddleware)

    @app.get("/items/{item_id}")
    async def read_item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    app.add_api_route("/metrics", prometheus_metrics, methods=["GET"], include_in_schema=False)
    return TestClient(app)


def test_prometheus_metrics_endpoint_emits_route_template_labels(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "pinvi_prometheus_metrics_enabled", True)
    monkeypatch.setattr(settings, "pinvi_prometheus_exclude_paths", ["/metrics"])
    client = _client()

    response = client.get("/items/abc")
    assert response.status_code == 200

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    assert "pinvi_api_http_requests_total" in metrics.text
    assert 'route="/items/{item_id}"' in metrics.text
    assert 'status_code="200"' in metrics.text
    assert "pinvi_api_http_request_duration_seconds_bucket" in metrics.text


def test_prometheus_metrics_endpoint_can_be_disabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "pinvi_prometheus_metrics_enabled", False)
    client = _client()

    response = client.get("/metrics")

    assert response.status_code == 404
