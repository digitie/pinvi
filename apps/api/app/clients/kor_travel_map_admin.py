"""kor-travel-map admin OpenAPI HTTP client — feature change relay (T-180).

Pinvi Admin이 1차 검토·승인한 사용자 feature 제안을 kor_travel_map `/v1/admin/features*`
(POST/PATCH/DELETE + change-requests approve/reject)로 전송하는 admin-path client다.
API base는 **:12701 `/v1/admin/*`** 이다. 사용자 토큰을 전달하지 않고
설정된 admin service token(`X-Kor-Travel-Map-Service-Token`)과, 운영에서 kor_travel_map
admin proxy gate가 켜진 경우 `X-Kor-Travel-Map-Admin-Proxy-Secret`/actor 헤더를 보낸다.

§7 합의 5건 **확정** (kor_travel_map T-217c, 2026-06-11):
- admin 인증 = 인프라 계층(SSO/IP allowlist, ADR-005 모델). 코드 인증은 kor_travel_map 측
  `admin_destructive_enabled` kill-switch뿐 — `X-Kor-Travel-Map-Service-Token`은 선택 pass-through.
- review_mode = kor_travel_map `KOR_TRAVEL_MAP_ADMIN_FEATURE_CHANGE_REVIEW_MODE`(기본 require_review 2단 검토).
- closure = soft `DELETE`(`user_deleted_*`, provider 재적재 부활 차단) / deactivate는 일시 비활성.
- idempotency/출처 태깅은 호출부(T-179 `feature_requests.py`)에서 적용.

계약: `docs/integrations/kor-travel-map-rest-api.md` §2.9 + kor_travel_map `openapi.json`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Annotated, Any, cast

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapError,
    KorTravelMapFeatureNotFound,
    KorTravelMapRateLimited,
    KorTravelMapUnavailable,
    _error_code,
)
from app.core.config import Settings, settings

logger = logging.getLogger(__name__)

_SERVICE_TOKEN_HEADER = "X-Kor-Travel-Map-Service-Token"  # noqa: S105 - 헤더 이름(비밀 아님)
_ADMIN_PROXY_SECRET_HEADER = "X-Kor-Travel-Map-Admin-Proxy-Secret"  # noqa: S105
_ADMIN_ACTOR_HEADER = "X-Kor-Travel-Map-Actor"


def _retry_after(resp: httpx.Response) -> int | None:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


class KorTravelMapAdminClient:
    """kor-travel-map admin(`/v1/admin/features*`) HTTP client (transport-only)."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        service_token: str = "",
        admin_proxy_secret: str = "",
        admin_actor: str = "pinvi-admin",
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.2,
    ) -> None:
        self._http = http
        self._service_token = service_token.strip()
        self._admin_proxy_secret = admin_proxy_secret.strip()
        self._admin_actor = admin_actor.strip() or "pinvi-admin"
        self._max_attempts = max(1, max_attempts)
        self._backoff_base_seconds = backoff_base_seconds

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._service_token:
            headers[_SERVICE_TOKEN_HEADER] = self._service_token
        if self._admin_proxy_secret:
            headers[_ADMIN_PROXY_SECRET_HEADER] = self._admin_proxy_secret
            headers[_ADMIN_ACTOR_HEADER] = self._admin_actor
        return headers

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        """transient(타임아웃/연결/5xx) 시 지수 백오프 재시도."""
        last: KorTravelMapUnavailable | None = None
        for attempt in range(self._max_attempts):
            try:
                resp = await self._http.request(
                    method, path, json=json, params=params, headers=self._headers()
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = KorTravelMapUnavailable(f"kor-travel-map admin 요청 실패({path}): {exc!r}")
            else:
                if resp.status_code >= 500:
                    last = KorTravelMapUnavailable(
                        f"kor-travel-map admin {resp.status_code} ({path})"
                    )
                else:
                    return resp
            if attempt + 1 < self._max_attempts:
                await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
        logger.warning("kor_travel_map_admin.unavailable", extra={"path": path})
        raise last or KorTravelMapUnavailable(f"kor-travel-map admin 요청 실패({path})")

    def _payload(self, resp: httpx.Response) -> dict[str, Any]:
        """성공 응답 envelope 추출. 오류 status는 도메인 예외로 변환."""
        sc = resp.status_code
        if sc == status.HTTP_404_NOT_FOUND:
            raise KorTravelMapFeatureNotFound("feature 를 찾을 수 없습니다.")
        if sc in (status.HTTP_429_TOO_MANY_REQUESTS, status.HTTP_409_CONFLICT):
            raise KorTravelMapRateLimited(
                f"kor-travel-map admin {sc}", retry_after_seconds=_retry_after(resp)
            )
        if sc >= status.HTTP_400_BAD_REQUEST:
            raise KorTravelMapBadRequest(f"kor-travel-map admin {sc}", code=_error_code(resp))
        payload = resp.json()
        data = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(data, dict):
            raise KorTravelMapError(f"예상치 못한 admin 응답 셰입({resp.request.url.path})")
        meta = payload.get("meta") if isinstance(payload, Mapping) else None
        if meta is not None and not isinstance(meta, dict):
            raise KorTravelMapError(f"예상치 못한 admin meta 셰입({resp.request.url.path})")
        return {"data": data, "meta": meta or {}}

    def _data(self, resp: httpx.Response) -> dict[str, Any]:
        """성공 응답 `data` 추출. 오류 status는 도메인 예외로 변환."""
        return cast(dict[str, Any], self._payload(resp)["data"])

    @staticmethod
    def _put_sequence_params(
        params: dict[str, Any],
        key: str,
        values: list[str] | tuple[str, ...] | None,
    ) -> None:
        cleaned = [value for value in values or [] if value]
        if cleaned:
            params[key] = cleaned

    async def list_features(
        self,
        *,
        q: str | None = None,
        kinds: list[str] | None = None,
        categories: list[str] | None = None,
        statuses: list[str] | None = None,
        providers: list[str] | None = None,
        dataset_keys: list[str] | None = None,
        has_coord: bool | None = None,
        has_issue: bool | None = None,
        issue_types: list[str] | None = None,
        updated_from: str | None = None,
        updated_to: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/admin/features — admin feature 목록(read-only) envelope 반환."""
        params: dict[str, Any] = {}
        if q:
            params["q"] = q
        self._put_sequence_params(params, "kind", kinds)
        self._put_sequence_params(params, "category", categories)
        self._put_sequence_params(params, "status", statuses)
        self._put_sequence_params(params, "provider", providers)
        self._put_sequence_params(params, "dataset_key", dataset_keys)
        self._put_sequence_params(params, "issue_type", issue_types)
        if has_coord is not None:
            params["has_coord"] = has_coord
        if has_issue is not None:
            params["has_issue"] = has_issue
        if updated_from:
            params["updated_from"] = updated_from
        if updated_to:
            params["updated_to"] = updated_to
        if page_size is not None:
            params["page_size"] = page_size
        if cursor:
            params["cursor"] = cursor
        if sort:
            params["sort"] = sort
        if order:
            params["order"] = order
        return self._payload(await self._send("GET", "/v1/admin/features", params=params))

    async def get_feature_detail(self, feature_id: str) -> dict[str, Any]:
        """GET /v1/admin/features/{id} — admin feature 상세 data 반환."""
        return self._data(await self._send("GET", f"/v1/admin/features/{feature_id}"))

    def _change_record(self, resp: httpx.Response) -> dict[str, Any]:
        """feature change 응답에서 `data.request`(AdminFeatureChangeRequestRecord) 추출.

        record = {feature_id, request_id, action, status, review_mode, payload,
        reason?, requested_by?, applied_at?, reviewed_at/by?, created_at}.
        """
        data = self._data(resp)
        record = data.get("request")
        if not isinstance(record, dict):
            raise KorTravelMapError("admin change 응답에 data.request 가 없습니다.")
        return record

    # ── feature change (T-179 승인 시 호출) ─────────────────────────────────

    async def create_feature(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """POST /v1/admin/features — 신규 feature(place/event) 생성 요청. `data.request` 반환."""
        return self._change_record(
            await self._send("POST", "/v1/admin/features", json=dict(payload))
        )

    async def patch_feature(self, feature_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """PATCH /v1/admin/features/{id} — 정보 수정(correction). `reason` 필수."""
        return self._change_record(
            await self._send("PATCH", f"/v1/admin/features/{feature_id}", json=dict(payload))
        )

    async def delete_feature(
        self, feature_id: str, *, reason: str, operator: str | None = None
    ) -> dict[str, Any]:
        """DELETE /v1/admin/features/{id} — 폐업(closure, soft). 문서 기본값=DELETE(§7)."""
        body: dict[str, Any] = {"reason": reason}
        if operator is not None:
            body["operator"] = operator
        return self._change_record(
            await self._send("DELETE", f"/v1/admin/features/{feature_id}", json=body)
        )

    # ── change-requests 큐 (kor_travel_map 운영자 검수 추적) ───────────────────────

    async def list_change_requests(
        self, *, page_size: int | None = None, cursor: str | None = None
    ) -> dict[str, Any]:
        """GET /v1/admin/features/change-requests — data = {items, review_mode}."""
        params: dict[str, Any] = {}
        if page_size is not None:
            params["page_size"] = page_size
        if cursor is not None:
            params["cursor"] = cursor
        return self._data(
            await self._send("GET", "/v1/admin/features/change-requests", params=params)
        )

    async def approve_change_request(
        self, request_id: str, *, operator: str | None = None, reason: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if operator is not None:
            body["operator"] = operator
        if reason is not None:
            body["reason"] = reason
        return self._change_record(
            await self._send(
                "POST", f"/v1/admin/features/change-requests/{request_id}/approve", json=body
            )
        )

    async def reject_change_request(
        self, request_id: str, *, operator: str | None = None, reason: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if operator is not None:
            body["operator"] = operator
        if reason is not None:
            body["reason"] = reason
        return self._change_record(
            await self._send(
                "POST", f"/v1/admin/features/change-requests/{request_id}/reject", json=body
            )
        )

    # ── curated feature import (ADR-049) ───────────────────────────────────────

    async def get_curated_detail_snapshot(self, curated_feature_id: str) -> dict[str, Any]:
        """GET /v1/admin/curated-features/{id}/detail-snapshot — 큐레이션 import용 snapshot.

        data = {curated_feature_id, version, etag, updated_at, theme, content, source, items}.
        kor-travel-map PR #533이 public `/v1/curated-features/{id}/pinvi-copy`를 폐지하고
        item 포함 snapshot을 admin 표면(서비스 토큰 필요)으로 옮겼다(ADR-049). plan-level 객체
        키는 `plan`에서 `content`로 개명됐다.
        """
        return self._data(
            await self._send(
                "GET", f"/v1/admin/curated-features/{curated_feature_id}/detail-snapshot"
            )
        )


def create_kor_travel_map_admin_client(app_settings: Settings) -> KorTravelMapAdminClient:
    """설정 기반 admin client 생성. admin token 미설정 시 공용 service token으로 fallback."""
    token = (
        app_settings.pinvi_kor_travel_map_admin_service_token
        or app_settings.pinvi_kor_travel_map_service_token
    )
    http = httpx.AsyncClient(
        base_url=app_settings.pinvi_kor_travel_map_admin_base_url,
        timeout=app_settings.pinvi_kor_travel_map_timeout_seconds,
    )
    return KorTravelMapAdminClient(
        http,
        service_token=token,
        admin_proxy_secret=app_settings.pinvi_kor_travel_map_admin_proxy_secret,
        admin_actor=app_settings.pinvi_kor_travel_map_admin_actor,
        max_attempts=app_settings.pinvi_kor_travel_map_max_attempts,
    )


@asynccontextmanager
async def kor_travel_map_admin_client_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — admin httpx client 1개 생성 후 `app.state`에 보관."""
    client = create_kor_travel_map_admin_client(settings)
    app.state.kor_travel_map_admin_client = client
    logger.info(
        "kor_travel_map_admin.client_ready",
        extra={"base_url": settings.pinvi_kor_travel_map_admin_base_url},
    )
    try:
        yield
    finally:
        await client.aclose()
        app.state.kor_travel_map_admin_client = None


def get_kor_travel_map_admin_client(request: Request) -> KorTravelMapAdminClient:
    """FastAPI 의존성 — `app.state`의 admin client. 미주입 시 503."""
    client = getattr(request.app.state, "kor_travel_map_admin_client", None)
    if not isinstance(client, KorTravelMapAdminClient):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "FEATURE_SERVICE_UNAVAILABLE",
                "message": "지도 admin 서비스가 일시적으로 사용 불가합니다.",
            },
        )
    return client


KorTravelMapAdminClientDep = Annotated[
    KorTravelMapAdminClient, Depends(get_kor_travel_map_admin_client)
]
