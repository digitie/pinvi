"""krtour-map admin OpenAPI HTTP client — feature change relay (T-180).

TripMate Admin이 1차 검토·승인한 사용자 feature 제안을 krtour `/v1/admin/features*`
(POST/PATCH/DELETE + change-requests approve/reject)로 전송하는 admin-path client다.
API base는 **:12301 `/v1/admin/*`** 이다. 사용자 토큰을 전달하지 않고
설정된 admin service token(`X-Krtour-Service-Token`)만 보낸다.

§7 합의 5건 **확정** (krtour T-217c, 2026-06-11):
- admin 인증 = 인프라 계층(SSO/IP allowlist, ADR-005 모델). 코드 인증은 krtour 측
  `admin_destructive_enabled` kill-switch뿐 — `X-Krtour-Service-Token`은 선택 pass-through.
- review_mode = krtour `KRTOUR_MAP_ADMIN_FEATURE_CHANGE_REVIEW_MODE`(기본 require_review 2단 검토).
- closure = soft `DELETE`(`user_deleted_*`, provider 재적재 부활 차단) / deactivate는 일시 비활성.
- idempotency/출처 태깅은 호출부(T-179 `feature_requests.py`)에서 적용.

계약: `docs/integrations/krtour-map-rest-api.md` §2.9 + krtour `openapi.json`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status

from app.clients.krtour_map import (
    KrtourMapBadRequest,
    KrtourMapError,
    KrtourMapFeatureNotFound,
    KrtourMapRateLimited,
    KrtourMapUnavailable,
    _error_code,
)
from app.core.config import Settings, settings

logger = logging.getLogger(__name__)

_SERVICE_TOKEN_HEADER = "X-Krtour-Service-Token"  # noqa: S105 - 헤더 이름(비밀 아님)


def _retry_after(resp: httpx.Response) -> int | None:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


class KrtourMapAdminClient:
    """krtour-map admin(`/v1/admin/features*`) HTTP client (transport-only)."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        service_token: str = "",
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.2,
    ) -> None:
        self._http = http
        self._service_token = service_token
        self._max_attempts = max(1, max_attempts)
        self._backoff_base_seconds = backoff_base_seconds

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        if self._service_token:
            return {_SERVICE_TOKEN_HEADER: self._service_token}
        return {}

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        """transient(타임아웃/연결/5xx) 시 지수 백오프 재시도."""
        last: KrtourMapUnavailable | None = None
        for attempt in range(self._max_attempts):
            try:
                resp = await self._http.request(
                    method, path, json=json, params=params, headers=self._headers()
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = KrtourMapUnavailable(f"krtour-map admin 요청 실패({path}): {exc!r}")
            else:
                if resp.status_code >= 500:
                    last = KrtourMapUnavailable(f"krtour-map admin {resp.status_code} ({path})")
                else:
                    return resp
            if attempt + 1 < self._max_attempts:
                await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
        logger.warning("krtour_map_admin.unavailable", extra={"path": path})
        raise last or KrtourMapUnavailable(f"krtour-map admin 요청 실패({path})")

    def _data(self, resp: httpx.Response) -> dict[str, Any]:
        """성공 응답 `data` 추출. 오류 status는 도메인 예외로 변환."""
        sc = resp.status_code
        if sc == status.HTTP_404_NOT_FOUND:
            raise KrtourMapFeatureNotFound("feature 를 찾을 수 없습니다.")
        if sc in (status.HTTP_429_TOO_MANY_REQUESTS, status.HTTP_409_CONFLICT):
            raise KrtourMapRateLimited(
                f"krtour-map admin {sc}", retry_after_seconds=_retry_after(resp)
            )
        if sc >= status.HTTP_400_BAD_REQUEST:
            raise KrtourMapBadRequest(f"krtour-map admin {sc}", code=_error_code(resp))
        payload = resp.json()
        data = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(data, dict):
            raise KrtourMapError(f"예상치 못한 admin 응답 셰입({resp.request.url.path})")
        return data

    def _change_record(self, resp: httpx.Response) -> dict[str, Any]:
        """feature change 응답에서 `data.request`(AdminFeatureChangeRequestRecord) 추출.

        record = {feature_id, request_id, action, status, review_mode, payload,
        reason?, requested_by?, applied_at?, reviewed_at/by?, created_at}.
        """
        data = self._data(resp)
        record = data.get("request")
        if not isinstance(record, dict):
            raise KrtourMapError("admin change 응답에 data.request 가 없습니다.")
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

    # ── change-requests 큐 (krtour 운영자 검수 추적) ───────────────────────

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


def create_krtour_map_admin_client(app_settings: Settings) -> KrtourMapAdminClient:
    """설정 기반 admin client 생성. admin token 미설정 시 공용 service token으로 fallback."""
    token = (
        app_settings.tripmate_krtour_map_admin_service_token
        or app_settings.tripmate_krtour_map_service_token
    )
    http = httpx.AsyncClient(
        base_url=app_settings.tripmate_krtour_map_admin_base_url,
        timeout=app_settings.tripmate_krtour_map_timeout_seconds,
    )
    return KrtourMapAdminClient(
        http,
        service_token=token,
        max_attempts=app_settings.tripmate_krtour_map_max_attempts,
    )


@asynccontextmanager
async def krtour_map_admin_client_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — admin httpx client 1개 생성 후 `app.state`에 보관."""
    client = create_krtour_map_admin_client(settings)
    app.state.krtour_map_admin_client = client
    logger.info(
        "krtour_map_admin.client_ready",
        extra={"base_url": settings.tripmate_krtour_map_admin_base_url},
    )
    try:
        yield
    finally:
        await client.aclose()
        app.state.krtour_map_admin_client = None


def get_krtour_map_admin_client(request: Request) -> KrtourMapAdminClient:
    """FastAPI 의존성 — `app.state`의 admin client. 미주입 시 503."""
    client = getattr(request.app.state, "krtour_map_admin_client", None)
    if not isinstance(client, KrtourMapAdminClient):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "FEATURE_SERVICE_UNAVAILABLE",
                "message": "지도 admin 서비스가 일시적으로 사용 불가합니다.",
            },
        )
    return client


KrtourMapAdminClientDep = Annotated[KrtourMapAdminClient, Depends(get_krtour_map_admin_client)]
