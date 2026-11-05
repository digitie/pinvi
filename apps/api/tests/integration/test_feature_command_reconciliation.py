"""#668: 실제 Pinvi DB/auth와 Map HTTP 경계의 안전한 해제."""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.api.v1.admin import feature_requests as routes
from app.clients.kor_travel_map_admin import KorTravelMapAdminClient
from app.models.feature_suggestion import FeatureSuggestion
from tests.integration.test_admin_feature_requests_api import _create_suggestion, _create_user

pytestmark = pytest.mark.asyncio


async def _pending(session_factory):
    uid = await _create_user(
        session_factory, email=f"resolve-{uuid.uuid4().hex}@pinvi.test", roles=["user", "admin"]
    )
    target = str(uuid.uuid4())
    rid = await _create_suggestion(
        session_factory, requester_id=uid, suggestion_type="correction", target_feature_id=target
    )
    body = {"access_reason": "원래 승인 사유", "name": "원래 수정할 이름"}
    dispatch = {
        "input": body,
        "feature_id": target,
        "type": "correction",
        "payload": {
            "reason": f"[suggestion:{rid}] {body['access_reason']}",
            "operator": "pinvi-admin",
            "name": body["name"],
        },
        "expected_revision": '"7"',
        "actor": "pinvi-admin",
        "command_key": str(rid),
    }
    async with session_factory() as db:
        row = await db.get(FeatureSuggestion, rid)
        row.kor_travel_map_ref = {"dispatch": dispatch}
        await db.commit()
    return uid, rid, dispatch


async def test_verified_absence_clears_dispatch_and_preserves_a_new_attempt_key(
    client, auth_cookies, session_factory, monkeypatch
):
    uid, rid, dispatch = await _pending(session_factory)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "state": "abandoned",
                    "actor": dispatch["actor"],
                    "operation": "admin.feature.patch",
                    "idempotency_key": dispatch["command_key"],
                    "feature_id": dispatch["feature_id"],
                    "request_fingerprint": "a" * 64,
                    "command_id": 17,
                    "receipt": None,
                },
                "meta": {
                    "duration_ms": 1,
                    "request_id": request.headers.get("X-Request-ID", "fixture"),
                },
            },
        )

    http = httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler))
    sdk = KorTravelMapAdminClient(
        http, admin_actor="pinvi-admin", admin_proxy_secret="fixture-map-proxy", max_attempts=1
    )
    monkeypatch.setattr(routes, "get_kor_travel_map_admin_client", lambda request: sdk)
    try:
        response = await client.post(
            f"/admin/feature-requests/{rid}/reconcile-map-command",
            cookies=auth_cookies(str(uid)),
            json={"access_reason": "실행 기록을 안전하게 확인"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["resolution"] == "abandoned"
        async with session_factory() as db:
            row = await db.get(FeatureSuggestion, rid)
            ref = row.kor_travel_map_ref
            assert ref.get("dispatch") is None
            assert str(uuid.UUID(ref["next_command_key"])) != str(rid)
            assert row.status == "pending"
        again = await client.post(
            f"/admin/feature-requests/{rid}/reconcile-map-command",
            cookies=auth_cookies(str(uid)),
            json={"access_reason": "같은 결과를 다시 확인"},
        )
        assert again.status_code == 200, again.text
        assert again.json()["data"]["resolution"] == "abandoned"
        assert len(calls) == 1
    finally:
        await http.aclose()
