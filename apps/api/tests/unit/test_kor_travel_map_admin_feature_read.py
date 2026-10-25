"""관리자 Feature 두 조회의 전용 자격·오류 분류 경계."""
from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from app.clients.kor_travel_map import KorTravelMapBadRequest, KorTravelMapUnavailable
from app.clients.kor_travel_map_admin import (
    KorTravelMapAdminClient,
    create_kor_travel_map_admin_client,
)
from app.core.config import Settings

_TOKEN = "feature-read-" + "r" * 32


def _client(handler, *, token=_TOKEN):
    return KorTravelMapAdminClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        admin_features_read_token=token,
        service_token="legacy-service",
        admin_proxy_secret="admin-proxy",
        ops_read_token="ops-read",
        ops_cancel_token="ops-cancel",
        max_attempts=3,
        backoff_base_seconds=0,
    )


@pytest.mark.parametrize("detail", [False, True])
async def test_feature_reads_use_only_dedicated_credential_and_keep_request_id(detail):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"data": {"items": [], "feature_id": "f_1"}})

    client = _client(handler)
    try:
        bound = client.with_request_id("request-feature-read")
        if detail:
            result = await bound.get_feature_detail("f_1")
        else:
            result = await bound.list_features(page_size=25, publication_states=["draft"])
        request = seen[0]
        assert len(seen) == 1
        assert request.method == "GET"
        assert request.url.path == "/v1/service/admin-features" + ("/f_1" if detail else "")
        assert request.headers["X-Kor-Travel-Map-Service-Token"] == _TOKEN
        assert request.headers["X-Request-Id"] == "request-feature-read"
        assert not any(k in request.headers for k in (
            "X-Kor-Travel-Map-Admin-Proxy-Secret", "X-Kor-Travel-Map-Actor",
            "X-Kor-Travel-Map-Ops-Token", "X-Kor-Travel-Map-Ops-Scope",
        ))
        assert result
        if not detail:
            assert request.url.params["page_size"] == "25"
            assert request.url.params["publication_state"] == "draft"
    finally:
        await client.aclose()


@pytest.mark.parametrize("detail", [False, True])
async def test_missing_read_token_cannot_fallback_or_make_http_request(detail):
    seen = []
    client = _client(lambda request: seen.append(request), token="")
    try:
        with pytest.raises(KorTravelMapUnavailable) as error:
            if detail:
                await client.get_feature_detail("f_1")
            else:
                await client.list_features()
        assert error.value.status_code == 503
        assert seen == []
    finally:
        await client.aclose()


@pytest.mark.parametrize("code", [401, 403])
@pytest.mark.parametrize("detail", [False, True])
async def test_read_auth_failure_is_unavailable_without_retry_or_upstream_body(code, detail):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(code, json={"detail": _TOKEN})

    client = _client(handler)
    try:
        with pytest.raises(KorTravelMapUnavailable) as error:
            if detail:
                await client.get_feature_detail("f_1")
            else:
                await client.list_features()
        assert error.value.status_code == 503
        assert _TOKEN not in str(error.value)
        assert len(seen) == 1
    finally:
        await client.aclose()


async def test_real_query_validation_remains_bad_request():
    client = _client(lambda request: httpx.Response(422, json={"detail": "invalid cursor"}))
    try:
        with pytest.raises(KorTravelMapBadRequest):
            await client.list_features(cursor="invalid")
    finally:
        await client.aclose()


async def test_read_credential_never_reaches_mutation_or_ops():
    seen = []
    client = _client(lambda request: seen.append(request) or httpx.Response(200, json={"data": {}}))
    try:
        await client._send("PATCH", "/v1/admin/features/f_1", json={})
        await client._send_ops_observability_read("/v1/ops/system-logs")
        assert seen[0].headers["X-Kor-Travel-Map-Service-Token"] == "legacy-service"
        assert seen[0].headers["X-Kor-Travel-Map-Admin-Proxy-Secret"] == "admin-proxy"
        assert seen[1].headers["X-Kor-Travel-Map-Ops-Token"] == "ops-read"
        assert all(_TOKEN not in r.headers.values() for r in seen)
        for method, path in [("POST", "/v1/service/admin-features"), ("GET", "/v1/admin/features"), ("GET", "/v1/service/admin-features/.."), ("GET", "/v1/service/admin-features/.")]:
            with pytest.raises(ValueError):
                await client._send(method, path, feature_read=True)
        assert len(seen) == 2
    finally:
        await client.aclose()


async def test_factory_preserves_secret_setting_and_clone():
    config = Settings(_env_file=None, pinvi_kor_travel_map_admin_features_read_token=_TOKEN)
    assert _TOKEN not in repr(config)
    client = create_kor_travel_map_admin_client(config)
    try:
        assert client.with_request_id("factory")._feature_read_headers()["X-Kor-Travel-Map-Service-Token"] == _TOKEN
    finally:
        await client.aclose()


@pytest.mark.parametrize("token", ["", "short", "r" * 31, "r" * 32 + " ", "r" * 16 + "\u2003" + "r" * 16])
def test_settings_reject_invalid_read_credential(token):
    with pytest.raises(ValidationError, match="ADMIN_FEATURES_READ_TOKEN"):
        Settings(_env_file=None, pinvi_kor_travel_map_admin_features_read_token=token)


def test_settings_reject_legacy_credential_reuse():
    with pytest.raises(ValidationError, match="must not reuse"):
        Settings(_env_file=None, pinvi_kor_travel_map_admin_features_read_token=_TOKEN,
                 pinvi_kor_travel_map_service_token=_TOKEN)
