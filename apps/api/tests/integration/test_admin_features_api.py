"""Admin feature read proxy 통합 테스트 (T-209)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.clients.kor_travel_map import (
    KorTravelMapConflict,
    KorTravelMapFeatureNotFound,
    KorTravelMapPreconditionFailed,
    KorTravelMapUnavailable,
    get_kor_travel_map_client,
)
from app.clients.kor_travel_map_admin import get_kor_travel_map_admin_client
from app.main import app
from app.models.audit import AdminAuditLog
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory: Any,
    *,
    email: str,
    roles: list[str] | None = None,
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=email,
            password_hash="x",
            status="active",
            roles=roles or ["user"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


def _feature_record() -> dict[str, Any]:
    """Map 현행 릴리스의 `AdminFeatureRecord` 그대로 — 합성 `status`가 **없다**.

    Map 3축 cutover(`1f2bdc3a`)로 admin 목록 item은
    `lifecycle_state`/`publication_state`/`quality_state`만 준다. 이 fake에 `status`를
    되살리면(=Pinvi 스키마가 다시 요구하면) 아래 회귀 테스트가 red가 된다.
    """
    return {
        "feature_id": "f_place_1",
        "feature_uuid": "f_place_1",
        "kind": "place",
        "name": "해운대 카페",
        "category": "01070100",
        "lifecycle_state": "active",
        "publication_state": "published",
        "quality_state": "valid",
        "lon": 129.163,
        "lat": 35.158,
        "address_label": "부산 해운대구",
        "primary_provider": "visitkorea",
        "primary_dataset_key": "places",
        "issue_count": 1,
        "issues": [
            {
                "issue_id": "iss-1",
                "violation_type": "missing_source",
                "severity": "warning",
                "message": "source 보강 필요",
                "detected_at": "2026-06-12T00:00:00+09:00",
            }
        ],
        "created_at": "2026-06-11T00:00:00+09:00",
        "updated_at": "2026-06-12T00:00:00+09:00",
    }


def _detail() -> dict[str, Any]:
    """Map 현행 릴리스의 `AdminFeatureDetailData` 그대로.

    - `feature`는 3축만 준다(합성 `status` 없음, `row_revision` 추가).
    - `sources`는 `is_primary_source`/`source_version`/`raw_*` 없이 `source_entity_key`·
      `observed_at`을 준다 — primary 여부는 `source_role`이 표현한다.
    - `versions`/`change_requests`는 애초에 오지 않고, 대신 `state_transitions`·
      `curations`가 온다(Pinvi 스키마에서는 optional이라 빈 목록으로 남는다).
    """
    return {
        "feature": {
            "feature_id": "f_place_1",
            "feature_uuid": "f_place_1",
            "kind": "place",
            "name": "해운대 카페",
            "category": "01070100",
            "lifecycle_state": "active",
            "publication_state": "published",
            "quality_state": "valid",
            "lon": 129.163,
            "lat": 35.158,
            "address": {"road": "해운대해변로"},
            "detail": {"phone": "051-000-0000"},
            "urls": {"homepage": "https://example.com/place"},
            "raw_refs": [{"provider": "visitkorea"}],
            "sido_code": "26",
            "sigungu_code": "26350",
            "marker_icon": "cafe",
            "marker_color": "P-07",
            "row_revision": 3,
            "created_at": "2026-06-11T00:00:00+09:00",
            "updated_at": "2026-06-12T00:00:00+09:00",
        },
        "sources": [
            {
                "source_entity_key": "visitkorea:places:content:1",
                "source_record_key": "visitkorea:places:1",
                "provider": "visitkorea",
                "dataset_key": "places",
                "source_entity_type": "content",
                "source_entity_id": "1",
                "source_role": "primary",
                "match_method": "natural_key",
                "confidence": 100,
                "raw_payload_hash": "sha256:abc",
                "raw_data": {"name": "해운대 카페"},
                "fetched_at": "2026-06-11T00:00:00+09:00",
                "imported_at": "2026-06-11T00:01:00+09:00",
                "observed_at": "2026-06-11T00:00:30+09:00",
                "linked_at": "2026-06-11T00:02:00+09:00",
            }
        ],
        "issues": [],
        "overrides": [
            {
                "override_id": "ovr-1",
                "source_record_key": "visitkorea:places:1",
                "field_path": "detail.phone",
                "source_value": "051-111-1111",
                "override_value": "051-000-0000",
                "prevent_provider_reactivation": True,
                "status": "active",
                "reason": "운영 검수",
                "created_by": "pinvi-admin",
                "created_at": "2026-06-12T00:10:00+09:00",
            }
        ],
        "state_transitions": [
            {
                "transition_id": 1,
                "from_lifecycle_state": None,
                "from_publication_state": None,
                "from_quality_state": None,
                "to_lifecycle_state": "active",
                "to_publication_state": "published",
                "to_quality_state": "valid",
                "transition_kind": "provider_import",
                "reason_code": "initial_load",
                "principal": "service:kortravelmap",
                "occurred_at": "2026-06-11T00:00:00+09:00",
                "row_revision": 1,
            }
        ],
        "files": [],
        "curations": [],
    }


class _FakeAdminClient:
    def __init__(
        self,
        *,
        not_found: bool = False,
        approve_conflict: bool = False,
        approve_precondition: bool = False,
    ) -> None:
        self.list_kwargs: dict[str, Any] | None = None
        self.detail_id: str | None = None
        self.change_request_kwargs: dict[str, Any] | None = None
        self.approved: dict[str, str | None] | None = None
        self.rejected: dict[str, str | None] | None = None
        self.not_found = not_found
        self.approve_conflict = approve_conflict
        self.approve_precondition = approve_precondition

    async def list_features(self, **kwargs: Any) -> dict[str, Any]:
        self.list_kwargs = kwargs
        return {
            "data": {"items": [_feature_record()]},
            "meta": {"page": {"next_cursor": "cursor-2"}, "duration_ms": 7},
        }

    async def get_feature_detail(self, feature_id: str) -> dict[str, Any]:
        self.detail_id = feature_id
        if self.not_found:
            raise KorTravelMapFeatureNotFound("not found")
        return _detail()

    async def list_change_requests(self, **kwargs: Any) -> dict[str, Any]:
        self.change_request_kwargs = kwargs
        return {
            "items": [
                {
                    "request_id": "krq-1",
                    "feature_id": "f_place_1",
                    "action": "add",
                    "status": "pending",
                    "review_mode": "require_review",
                    "payload": {"name": "해운대 카페"},
                    "reason": "사용자 제안",
                    "requested_by": "pinvi-admin",
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "applied_at": None,
                    "created_at": "2026-06-12T00:00:00+09:00",
                }
            ],
            "review_mode": "require_review",
        }

    async def approve_change_request(
        self, request_id: str, *, operator: str | None = None, reason: str | None = None
    ) -> dict[str, Any]:
        if self.approve_conflict:
            raise KorTravelMapConflict("already reviewed", code="INVALID_STATE")
        if self.approve_precondition:
            raise KorTravelMapPreconditionFailed(
                "stale feature",
                code="PRECONDITION_FAILED",
            )
        self.approved = {"request_id": request_id, "operator": operator, "reason": reason}
        return {
            "request_id": request_id,
            "feature_id": "f_place_1",
            "action": "add",
            "status": "applied",
            "review_mode": "require_review",
            "payload": {"name": "해운대 카페"},
            "reason": reason,
            "requested_by": "pinvi-admin",
            "reviewed_by": operator,
            "reviewed_at": "2026-06-12T01:00:00+09:00",
            "applied_at": "2026-06-12T01:00:01+09:00",
            "created_at": "2026-06-12T00:00:00+09:00",
        }

    async def reject_change_request(
        self, request_id: str, *, operator: str | None = None, reason: str | None = None
    ) -> dict[str, Any]:
        self.rejected = {"request_id": request_id, "operator": operator, "reason": reason}
        return {
            "request_id": request_id,
            "feature_id": "f_place_1",
            "action": "update",
            "status": "rejected",
            "review_mode": "require_review",
            "payload": {"name": "해운대 카페"},
            "reason": reason,
            "requested_by": "pinvi-admin",
            "reviewed_by": operator,
            "reviewed_at": "2026-06-12T01:00:00+09:00",
            "applied_at": None,
            "created_at": "2026-06-12T00:00:00+09:00",
        }


class _FakeWeatherClient:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.calls: dict[str, Any] = {}
        self.unavailable = unavailable

    async def feature_weather(
        self, feature_id: str, *, asof: Any = None, known_at: Any = None
    ) -> dict[str, Any]:
        # 시그니처는 실제 client(`clients/kor_travel_map.py feature_weather`)와 같아야 한다 —
        # kwarg가 빠져 있으면 라우터가 새 인자를 넘기기 시작해도 fake에서만 TypeError로 늦게 터진다.
        self.calls["feature_weather"] = {
            "feature_id": feature_id,
            "asof": asof,
            "known_at": known_at,
        }
        # 실제 transport의 단일 시간대 정책을 그대로 흉내낸다(`_require_aware_datetime`).
        # 이게 없으면 라우터가 `normalize_asof_query()`를 다시 빼먹어도 fake는 naive를 받아
        # 200을 돌려주고, 실제 배포에서만 500이 난다.
        for field, value in (("asof", asof), ("known_at", known_at)):
            if isinstance(value, datetime) and value.utcoffset() is None:
                raise ValueError(f"{field}에는 UTC offset이 필요합니다.")
        if self.unavailable:
            raise KorTravelMapUnavailable("kor-travel-map weather down")
        # admin weather-values는 **user** 표면 카드를 투영한다 — Map bitemporal
        # cutover(`6650aa71`)로 `asof` → `selected_at`. (Map admin profile에도
        # `GET /v1/admin/features/{id}/weather`가 있지만 Pinvi는 아직 쓰지 않는다;
        # `api/v1/admin/features.py` `_weather_values_from_payload` 주석의 후속 과제.)
        return {
            "feature_id": feature_id,
            "selected_at": "2026-06-12T10:00:00+09:00",
            "refresh_after": "2026-06-12T11:00:00+09:00",
            "latest_at": "2026-06-12T09:30:00+09:00",
            "is_stale": False,
            "source_styles": ["nowcast", "short"],
            "metrics": [
                {
                    "metric_key": "T1H",
                    "metric_name": "기온",
                    "forecast_style": "nowcast",
                    "timeline_bucket": "current",
                    "valid_at": "2026-06-12T10:00:00+09:00",
                    "value_number": 24.5,
                    "unit": "℃",
                }
            ],
        }


def _override(fake: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_admin_client] = lambda: fake


def _override_weather(fake: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_client] = lambda: fake


def _clear() -> None:
    app.dependency_overrides.pop(get_kor_travel_map_admin_client, None)
    app.dependency_overrides.pop(get_kor_travel_map_client, None)


async def test_list_admin_features_proxies_filters(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "operator"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/features",
            params=[
                ("q", "해운대"),
                ("kind", "place"),
                ("kind", "event"),
                ("lifecycle_state", "active"),
                ("publication_state", "published"),
                ("publication_state", "suppressed"),
                ("quality_state", "quarantined"),
                ("provider_dataset_id", "42"),
                ("category", "01070100"),
                ("has_issue", "true"),
                ("page_size", "100"),
                ("cursor", "cursor-1"),
                ("sort", "updated_at"),
                ("order", "desc"),
            ],
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["items"][0]["feature_id"] == "f_place_1"
    assert data["items"][0]["issues"][0]["violation_type"] == "missing_source"
    assert data["next_cursor"] == "cursor-2"
    assert data["duration_ms"] == 7
    assert fake.list_kwargs is not None
    assert fake.list_kwargs["q"] == "해운대"
    assert fake.list_kwargs["kinds"] == ["place", "event"]
    assert fake.list_kwargs["lifecycle_states"] == ["active"]
    assert fake.list_kwargs["publication_states"] == ["published", "suppressed"]
    assert fake.list_kwargs["quality_states"] == ["quarantined"]
    assert fake.list_kwargs["provider_dataset_id"] == 42
    assert fake.list_kwargs["categories"] == ["01070100"]
    assert fake.list_kwargs["has_issue"] is True
    assert fake.list_kwargs["page_size"] == 100
    assert fake.list_kwargs["cursor"] == "cursor-1"
    assert fake.list_kwargs["sort"] == "updated_at"
    assert fake.list_kwargs["order"] == "desc"
    # Map에 없는 legacy 필터 이름은 client 호출 인자로도 남으면 안 된다.
    assert not {"statuses", "providers", "dataset_keys"} & set(fake.list_kwargs)


async def test_list_admin_features_drops_legacy_status_provider_dataset_filters(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    """3축 cutover 전 이름(`status`/`provider`/`dataset_key`)은 upstream에 도달하지 않는다.

    Map `GET /v1/admin/features`에는 셋 다 없어 보내봐야 조용히 버려진다 —
    "필터가 걸린 척"하는 회귀를 여기서 red로 만든다.
    """
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "operator"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/features",
            params=[
                ("status", "active"),
                ("provider", "visitkorea"),
                ("dataset_key", "places"),
            ],
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert fake.list_kwargs is not None
    forwarded = {key: value for key, value in fake.list_kwargs.items() if value is not None}
    # 라우터가 legacy 이름을 다시 받으면 여기에 값이 실려 red가 된다.
    assert forwarded == {"page_size": 50, "sort": "name", "order": "asc"}


async def test_list_admin_features_rejects_retired_status_sort_key(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    """`sort=status`는 Map enum에서 사라졌다 — 여기서 막지 않으면 upstream 422가 된다."""
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "operator"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/features",
            params=[("sort", "status")],
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 422, resp.text
    assert fake.list_kwargs is None


async def test_list_admin_features_exposes_three_state_axes_without_status(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    """Map이 `status`를 안 주는 페이로드로도 목록이 200이고, 3축이 그대로 나온다."""
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "operator"]
    )
    assert "status" not in _feature_record()
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.get("/admin/features", cookies=auth_cookies(str(admin_id)))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["items"][0]
    assert item["lifecycle_state"] == "active"
    assert item["publication_state"] == "published"
    assert item["quality_state"] == "valid"
    # `status`를 되살리면(스키마 필드 복원) 이 단언이 red가 된다.
    assert "status" not in item


async def test_get_admin_feature_returns_detail(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/features/f_place_1",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert fake.detail_id == "f_place_1"
    assert data["feature"]["name"] == "해운대 카페"
    assert data["sources"][0]["provider"] == "visitkorea"
    # Map은 상세 source에 `is_primary_source`를 주지 않는다(필수로 되돌리면 502).
    assert data["sources"][0]["is_primary_source"] is None
    assert data["sources"][0]["source_role"] == "primary"
    # 3축이 상세에도 그대로 실린다.
    assert data["feature"]["lifecycle_state"] == "active"
    assert data["feature"]["publication_state"] == "published"
    assert data["feature"]["quality_state"] == "valid"
    # `status`를 되살리면 이 단언이 red가 된다.
    assert "status" not in data["feature"]
    assert "status" not in _detail()["feature"]
    # Map 현행 상세에는 `versions`/`change_requests`가 없다 — 항상 빈 목록으로 남는다
    # (후속: 두 필드를 Pinvi 상세 계약에서 걷어낼지 결정).
    assert data["versions"] == []
    assert data["change_requests"] == []


async def test_get_admin_feature_sources_and_overrides_return_projections(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "operator"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        sources_resp = await client.get(
            "/admin/features/f_place_1/sources",
            cookies=auth_cookies(str(admin_id)),
        )
        overrides_resp = await client.get(
            "/admin/features/f_place_1/overrides",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert sources_resp.status_code == 200, sources_resp.text
    assert overrides_resp.status_code == 200, overrides_resp.text
    sources = sources_resp.json()["data"]
    overrides = overrides_resp.json()["data"]
    assert sources["feature_id"] == "f_place_1"
    assert sources["items"][0]["source_record_key"] == "visitkorea:places:1"
    assert overrides["feature_id"] == "f_place_1"
    assert overrides["items"][0]["field_path"] == "detail.phone"
    assert overrides["items"][0]["prevent_provider_reactivation"] is True


async def test_get_admin_feature_weather_values_proxies_weather_card(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    fake = _FakeWeatherClient()
    _override_weather(fake)
    try:
        resp = await client.get(
            "/admin/features/f_weather_1/weather-values",
            params={"asof": "2026-06-12T10:00:00+09:00"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert fake.calls["feature_weather"]["feature_id"] == "f_weather_1"
    assert fake.calls["feature_weather"]["asof"] == datetime.fromisoformat(
        "2026-06-12T10:00:00+09:00"
    )
    assert data["feature_id"] == "f_weather_1"
    assert data["asof"] == "2026-06-12T10:00:00+09:00"
    assert data["source_styles"] == ["nowcast", "short"]
    assert data["items"][0]["metric_key"] == "T1H"


async def test_get_admin_feature_weather_values_reads_naive_asof_as_kst(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    """offset 없는 `?asof=`도 200이고, client에는 **aware**(KST)로 전달된다.

    회귀 방어: 이 핸들러가 `normalize_asof_query()`를 건너뛰고 raw query를 넘기던 동안
    naive 입력은 transport `ValueError`가 됐고, 그 예외는 KorTravelMap* 계열만 잡는
    `_map_admin_errors()`를 뚫어 **500**이 됐다(직전 릴리스에서는 200). user weather 라우터
    (`test_features_api.py test_weather_naive_asof_is_read_as_kst_not_utc`)와 같은 해석을
    쓰는지도 함께 고정한다 — 두 경계가 갈라지면 같은 query가 9시간 다른 시점을 조회한다.
    """
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "operator"]
    )
    fake = _FakeWeatherClient()
    _override_weather(fake)
    try:
        resp = await client.get(
            "/admin/features/f_weather_1/weather-values",
            params={"asof": "2026-06-12T10:00:00"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    passed = fake.calls["feature_weather"]["asof"]
    assert passed.utcoffset() == timedelta(hours=9)
    assert passed.isoformat() == "2026-06-12T10:00:00+09:00"
    # knowledge time은 라우터가 넘기지 않는다 — client가 "지금"을 채운다.
    assert fake.calls["feature_weather"]["known_at"] is None


async def test_get_admin_feature_weather_values_maps_upstream_unavailable(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "operator"]
    )
    fake = _FakeWeatherClient(unavailable=True)
    _override_weather(fake)
    try:
        resp = await client.get(
            "/admin/features/f_weather_1/weather-values",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "FEATURE_SERVICE_UNAVAILABLE"


async def test_get_admin_feature_maps_upstream_404(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    fake = _FakeAdminClient(not_found=True)
    _override(fake)
    try:
        resp = await client.get(
            "/admin/features/missing",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_list_admin_feature_change_requests_proxies_filters(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "operator"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/features/change-requests",
            params=[
                ("status", "pending"),
                ("status", "applied"),
                ("action", "add"),
                ("q", "해운대"),
                ("page_size", "10"),
            ],
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["items"][0]["request_id"] == "krq-1"
    assert data["items"][0]["payload"] == {"name": "해운대 카페"}
    assert data["review_mode"] == "require_review"
    assert data["page_size"] == 10
    assert fake.change_request_kwargs == {
        "statuses": ["pending", "applied"],
        "actions": ["add"],
        "q": "해운대",
        "page_size": 10,
    }


async def test_approve_admin_feature_change_request_appends_audit(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.post(
            "/admin/features/change-requests/krq-1/approve",
            json={
                "access_reason": "Pinvi 운영 검수 완료",
                "kor_travel_map_reason": "원천 검수 완료",
            },
            headers={"X-Request-Id": str(uuid.uuid4())},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "applied"
    assert fake.approved == {
        "request_id": "krq-1",
        "operator": "pinvi-admin",
        "reason": "원천 검수 완료",
    }
    async with session_factory() as db:
        audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.action == "feature_change_request.approve")
        )
    assert audit is not None
    assert audit.resource_id == "krq-1"
    assert audit.access_reason == "Pinvi 운영 검수 완료"


async def test_reject_admin_feature_change_request_appends_audit(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.post(
            "/admin/features/change-requests/krq-2/reject",
            json={"access_reason": "중복 변경 요청"},
            headers={"X-Request-Id": str(uuid.uuid4())},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "rejected"
    assert fake.rejected == {
        "request_id": "krq-2",
        "operator": "pinvi-admin",
        "reason": "중복 변경 요청",
    }
    async with session_factory() as db:
        audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.action == "feature_change_request.reject")
        )
    assert audit is not None
    assert audit.resource_id == "krq-2"


async def test_change_request_conflict_maps_409_without_audit(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    fake = _FakeAdminClient(approve_conflict=True)
    _override(fake)
    try:
        resp = await client.post(
            "/admin/features/change-requests/krq-1/approve",
            json={"access_reason": "재승인 시도"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE"
    async with session_factory() as db:
        audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.action == "feature_change_request.approve")
        )
    assert audit is None


async def test_change_request_stale_revision_maps_412_without_audit(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-stale@example.com", roles=["user", "admin"]
    )
    fake = _FakeAdminClient(approve_precondition=True)
    _override(fake)
    try:
        resp = await client.post(
            "/admin/features/change-requests/krq-stale/approve",
            json={"access_reason": "stale 승인 시도"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 412
    assert resp.json()["error"]["code"] == "PRECONDITION_FAILED"
    async with session_factory() as db:
        audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.action == "feature_change_request.approve")
        )
    assert audit is None


async def test_non_admin_features_route_is_hidden(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    user_id = await _create_user(session_factory, email="plain@example.com")
    resp = await client.get("/admin/features", cookies=auth_cookies(str(user_id)))
    assert resp.status_code == 404
