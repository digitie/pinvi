"""#668: 실제 Pinvi DB/auth와 Map HTTP 경계의 안전한 해제."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
from sqlalchemy import select

from app.api.v1.admin import feature_requests as routes
from app.clients.kor_travel_map_admin import KorTravelMapAdminClient
from app.models.audit import AdminAuditLog
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
            json={"access_reason": "실행 기록을 안전하게 확인", "expected_command_key": str(rid)},
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
            json={"access_reason": "같은 결과를 다시 확인", "expected_command_key": str(rid)},
        )
        assert again.status_code == 200, again.text
        assert again.json()["data"]["resolution"] == "abandoned"
        assert len(calls) == 1
    finally:
        await http.aclose()


def _wire(dispatch, state="abandoned", **updates):
    data = {
        "state": state,
        "actor": dispatch["actor"],
        "operation": "admin.feature.patch",
        "idempotency_key": dispatch["command_key"],
        "feature_id": dispatch["feature_id"],
        "request_fingerprint": "a" * 64,
        "command_id": 17,
        "receipt": None,
    }
    if state == "completed":
        data["receipt"] = {
            "data": {
                "feature_id": dispatch["feature_id"],
                "row_revision": 8,
                "command_id": 17,
                "applied_field_count": 1,
            },
            "meta": {"request_id": str(uuid.uuid4()), "duration_ms": 1},
        }
    return {
        "data": {**data, **updates},
        "meta": {"request_id": str(uuid.uuid4()), "duration_ms": 1},
    }


async def _stored(session_factory, rid):
    async with session_factory() as db:
        row = await db.get(FeatureSuggestion, rid)
        return row.status, row.kor_travel_map_ref, row.resolved_at


@asynccontextmanager
async def _sdk(monkeypatch, handler):
    async with httpx.AsyncClient(
        base_url="http://map.test", transport=httpx.MockTransport(handler)
    ) as http:
        sdk = KorTravelMapAdminClient(
            http, admin_actor="pinvi-admin", admin_proxy_secret="fixture-map-proxy", max_attempts=1
        )
        monkeypatch.setattr(routes, "get_kor_travel_map_admin_client", lambda request: sdk)
        yield sdk


async def _resolve(client, auth_cookies, uid, rid, **body):
    return await client.post(
        f"/admin/feature-requests/{rid}/reconcile-map-command",
        cookies=auth_cookies(str(uid)),
        json={
            "access_reason": "실행 기록을 안전하게 확인",
            "expected_command_key": str(rid),
            **body,
        },
    )


@pytest.mark.parametrize("state", ["pending", "completed"])
async def test_pending_preserves_dispatch_completed_recovers_once_and_audits(
    client, auth_cookies, session_factory, monkeypatch, state
):
    uid, rid, dispatch = await _pending(session_factory)
    before = await _stored(session_factory, rid)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=_wire(dispatch, state))

    async with _sdk(monkeypatch, handler):
        response = await _resolve(client, auth_cookies, uid, rid)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["resolution"] == state
        after = await _stored(session_factory, rid)
        if state == "pending":
            assert after == before
        else:
            assert after[0] == "added"
            assert after[1].get("dispatch") is None
            assert after[1]["feature_id"] == dispatch["feature_id"]
            assert after[1]["last_resolution"]["command_key"] == dispatch["command_key"]
            again = await _resolve(client, auth_cookies, uid, rid)
            assert again.status_code == 200, again.text
            assert len(calls) == 1
            assert await _stored(session_factory, rid) == after
        async with session_factory() as db:
            actions = list(
                await db.scalars(
                    select(AdminAuditLog.action).where(AdminAuditLog.resource_id == str(rid))
                )
            )
        assert sorted(actions) == sorted(
            [
                "feature_request.command_reconcile_requested",
                f"feature_request.command_reconcile_{state}",
            ]
        )


@pytest.mark.parametrize(
    ("case", "status"),
    [
        ("actor", 502),
        ("operation", 502),
        ("key", 502),
        ("feature", 502),
        ("missing_receipt", 502),
        ("receipt_command", 502),
        ("receipt_feature", 502),
        ("unresolved_receipt", 502),
        ("metadata", 502),
        ("legacy", 409),
        ("unavailable", 503),
        ("timeout", 503),
        ("auth", 503),
    ],
)
async def test_unverifiable_or_failed_map_result_never_unlocks_or_changes_dispatch(
    client, auth_cookies, session_factory, monkeypatch, case, status
):
    uid, rid, dispatch = await _pending(session_factory)
    before = await _stored(session_factory, rid)

    def handler(request):
        if case == "timeout":
            raise httpx.ReadTimeout("fixture lost response", request=request)
        if case in {"legacy", "unavailable", "auth"}:
            code = {
                "legacy": "LEGACY_FINGERPRINT_UNVERIFIABLE",
                "unavailable": "SERVICE_UNAVAILABLE",
                "auth": "FORBIDDEN",
            }[case]
            return httpx.Response(
                {"legacy": 409, "unavailable": 503, "auth": 403}[case],
                json={"type": "about:blank", "code": code, "detail": "fixture"},
            )
        wire = _wire(dispatch, "completed")
        data = wire["data"]
        if case == "actor":
            data["actor"] = "other-actor"
        elif case == "operation":
            data["operation"] = "admin.feature.delete"
        elif case == "key":
            data["idempotency_key"] = str(uuid.uuid4())
        elif case == "feature":
            data["feature_id"] = str(uuid.uuid4())
        elif case == "missing_receipt":
            data["receipt"] = None
        elif case == "receipt_command":
            data["receipt"]["data"]["command_id"] += 1
        elif case == "receipt_feature":
            data["receipt"]["data"]["feature_id"] = str(uuid.uuid4())
        elif case == "unresolved_receipt":
            data["state"] = "abandoned"
        elif case == "metadata":
            wire.pop("meta")
        return httpx.Response(200, json=wire)

    async with _sdk(monkeypatch, handler):
        response = await _resolve(client, auth_cookies, uid, rid)
    assert response.status_code == status, response.text
    assert await _stored(session_factory, rid) == before
    if case == "legacy":
        assert response.json()["error"]["code"] == "LEGACY_FINGERPRINT_UNVERIFIABLE"
    async with session_factory() as db:
        actions = list(
            await db.scalars(
                select(AdminAuditLog.action).where(AdminAuditLog.resource_id == str(rid))
            )
        )
    assert actions == ["feature_request.command_reconcile_requested"]


@pytest.mark.parametrize(
    "corruption", ["missing_actor", "actor_changed", "payload_changed", "missing_key"]
)
async def test_legacy_or_changed_identity_is_refused_before_map(
    client, auth_cookies, session_factory, monkeypatch, corruption
):
    uid, rid, dispatch = await _pending(session_factory)
    if corruption == "missing_actor":
        dispatch.pop("actor")
    elif corruption == "actor_changed":
        dispatch["actor"] = "other-actor"
    elif corruption == "payload_changed":
        dispatch["payload"]["name"] = "corrupted-name"
    else:
        dispatch.pop("command_key")
    async with session_factory() as db:
        row = await db.get(FeatureSuggestion, rid)
        row.kor_travel_map_ref = {"dispatch": dispatch}
        await db.commit()
    before = await _stored(session_factory, rid)

    def forbidden(request):
        raise AssertionError("identity must be verified before sending to Map")

    async with _sdk(monkeypatch, forbidden):
        response = await _resolve(client, auth_cookies, uid, rid)
    assert response.status_code == 409, response.text
    assert await _stored(session_factory, rid) == before


async def test_abandoned_new_approval_uses_new_persistent_key_then_retries_same_key(
    client, auth_cookies, session_factory, monkeypatch
):
    uid, rid, dispatch = await _pending(session_factory)
    patches = []

    def handler(request):
        if request.url.path.endswith("/reconcile"):
            return httpx.Response(200, json=_wire(dispatch))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"data": {"feature_id": dispatch["feature_id"]}},
                headers={"ETag": '"9"'},
            )
        assert request.method == "PATCH"
        patches.append(request)
        return httpx.Response(503, json={"code": "SERVICE_UNAVAILABLE"})

    async with _sdk(monkeypatch, handler):
        resolved = await _resolve(client, auth_cookies, uid, rid)
        assert resolved.status_code == 200, resolved.text
        new_key = (await _stored(session_factory, rid))[1]["next_command_key"]
        for _ in range(2):
            response = await client.post(
                f"/admin/feature-requests/{rid}/approve",
                cookies=auth_cookies(str(uid)),
                json={
                    "access_reason": "새 승인 사유",
                    "name": "새 이름",
                    "expected_command_key": new_key,
                },
            )
            assert response.status_code == 503, response.text
        assert len(patches) == 2
        assert {r.headers["Idempotency-Key"] for r in patches} == {new_key}
        assert new_key != dispatch["command_key"]
        assert {r.headers["If-Match"] for r in patches} == {'"9"'}
        after = (await _stored(session_factory, rid))[1]
        assert after["dispatch"]["command_key"] == new_key
        assert after["dispatch"]["actor"] == "pinvi-admin"


async def test_non_admin_and_invalid_confirmation_reason_cannot_reconcile(
    client, auth_cookies, session_factory, monkeypatch
):
    uid, rid, _ = await _pending(session_factory)
    user = await _create_user(
        session_factory, email=f"ordinary-{uuid.uuid4().hex}@pinvi.test", roles=["user"]
    )
    before = await _stored(session_factory, rid)

    def forbidden(request):
        raise AssertionError("authorization/input must fail before Map")

    async with _sdk(monkeypatch, forbidden):
        hidden = await _resolve(client, auth_cookies, user, rid)
        assert hidden.status_code == 404, hidden.text
        short = await _resolve(client, auth_cookies, uid, rid, access_reason=" ")
        assert short.status_code == 422, short.text
    assert await _stored(session_factory, rid) == before


async def test_stale_approval_and_resolution_cannot_target_the_new_attempt(
    client, auth_cookies, session_factory, monkeypatch
):
    uid, rid, dispatch = await _pending(session_factory)
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/reconcile"):
            return httpx.Response(200, json=_wire(dispatch))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"data": {"feature_id": dispatch["feature_id"]}},
                headers={"ETag": '"9"'},
            )
        return httpx.Response(503, json={"code": "SERVICE_UNAVAILABLE"})

    async with _sdk(monkeypatch, handler):
        resolved = await _resolve(client, auth_cookies, uid, rid)
        assert resolved.status_code == 200, resolved.text
        new_key = (await _stored(session_factory, rid))[1]["next_command_key"]
        count = len(calls)
        for key in (str(rid), None):
            stale_body = {**dispatch["input"]}
            if key is not None:
                stale_body["expected_command_key"] = key
            stale = await client.post(
                f"/admin/feature-requests/{rid}/approve",
                cookies=auth_cookies(str(uid)),
                json=stale_body,
            )
            assert stale.status_code == 409, stale.text
            assert stale.json()["error"]["code"] == "MAP_COMMAND_ATTEMPT_CHANGED"
        assert len(calls) == count
        # Current generation may dispatch, but delayed old reconcile must not seal it.
        current = await client.post(
            f"/admin/feature-requests/{rid}/approve",
            cookies=auth_cookies(str(uid)),
            json={**dispatch["input"], "expected_command_key": new_key},
        )
        assert current.status_code == 503, current.text
        before = await _stored(session_factory, rid)
        count = len(calls)
        stale_resolution = await _resolve(client, auth_cookies, uid, rid)
        assert stale_resolution.status_code == 409, stale_resolution.text
        assert stale_resolution.json()["error"]["code"] == "MAP_COMMAND_ATTEMPT_CHANGED"
        assert await _stored(session_factory, rid) == before
        assert len(calls) == count


async def test_new_attempt_precondition_failure_never_resurrects_original_sealed_key(
    client, auth_cookies, session_factory, monkeypatch
):
    uid, rid, dispatch = await _pending(session_factory)
    patches = []
    revision = 9

    def handler(request):
        if request.url.path.endswith("/reconcile"):
            return httpx.Response(200, json=_wire(dispatch))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"data": {"feature_id": dispatch["feature_id"]}},
                headers={"ETag": f'"{revision}"'},
            )
        patches.append(request)
        if len(patches) == 1:
            return httpx.Response(412, json={"code": "PRECONDITION_FAILED"})
        return httpx.Response(503, json={"code": "SERVICE_UNAVAILABLE"})

    async with _sdk(monkeypatch, handler):
        assert (await _resolve(client, auth_cookies, uid, rid)).status_code == 200
        new_key = (await _stored(session_factory, rid))[1]["next_command_key"]
        first = await client.post(
            f"/admin/feature-requests/{rid}/approve",
            cookies=auth_cookies(str(uid)),
            json={**dispatch["input"], "expected_command_key": new_key},
        )
        assert first.status_code == 412, first.text
        ref = (await _stored(session_factory, rid))[1]
        assert ref is not None and ref.get("dispatch") is None
        assert ref["next_command_key"] != str(rid)
        assert ref["last_resolution"]["command_key"] == str(rid)
        revision = 10
        again = await client.post(
            f"/admin/feature-requests/{rid}/approve",
            cookies=auth_cookies(str(uid)),
            json={**dispatch["input"], "expected_command_key": ref["next_command_key"]},
        )
        assert again.status_code == 503, again.text
        assert patches[-1].headers["Idempotency-Key"] != str(rid)
        assert patches[-1].headers["If-Match"] == '"10"'


async def test_approval_waiting_behind_reconciliation_cannot_execute_a_fresh_generation(
    client, auth_cookies, session_factory, monkeypatch
):
    import asyncio

    uid, rid, dispatch = await _pending(session_factory)
    map_waiting = asyncio.Event()
    approval_waiting = asyncio.Event()
    release_map = asyncio.Event()
    calls = []
    original_load = routes._load_pending

    async def observed_load(db, request_id):
        approval_waiting.set()
        return await original_load(db, request_id)

    monkeypatch.setattr(routes, "_load_pending", observed_load)

    async def handler(request):
        calls.append(request)
        assert request.url.path.endswith("/reconcile"), "stale approval must never reach Map"
        async with session_factory() as db:
            assert (
                await db.scalar(
                    select(AdminAuditLog.log_id).where(
                        AdminAuditLog.resource_id == str(rid),
                        AdminAuditLog.action == "feature_request.command_reconcile_requested",
                    )
                )
                is not None
            ), "requested audit must be committed before external command"
        map_waiting.set()
        await asyncio.wait_for(release_map.wait(), timeout=10)
        return httpx.Response(200, json=_wire(dispatch))

    async with _sdk(monkeypatch, handler):
        reconciliation = asyncio.create_task(_resolve(client, auth_cookies, uid, rid))
        approval = None
        try:
            await asyncio.wait_for(map_waiting.wait(), timeout=10)
            approval = asyncio.create_task(
                client.post(
                    f"/admin/feature-requests/{rid}/approve",
                    cookies=auth_cookies(str(uid)),
                    json={**dispatch["input"], "expected_command_key": str(rid)},
                )
            )
            await asyncio.wait_for(approval_waiting.wait(), timeout=10)
            release_map.set()
            result, stale = await asyncio.gather(reconciliation, approval)
            assert result.status_code == 200, result.text
            assert stale.status_code == 409, stale.text
            assert stale.json()["error"]["code"] == "MAP_COMMAND_ATTEMPT_CHANGED"
            assert len(calls) == 1
            status, ref, _ = await _stored(session_factory, rid)
            assert status == "pending" and ref.get("dispatch") is None
            assert ref["next_command_key"] != str(rid)
        finally:
            release_map.set()
            await asyncio.gather(
                reconciliation, *([approval] if approval else []), return_exceptions=True
            )
