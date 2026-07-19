"""kor-travel-map admin OpenAPI HTTP client — feature change relay (T-180).

Pinvi Admin이 1차 검토·승인한 사용자 feature 제안을 kor_travel_map `/v1/admin/features*`
(POST/PATCH/DELETE + change-requests approve/reject)로 전송하는 admin-path client다.
API base는 **:12701 `/v1/admin/*`** 이다. 사용자 토큰을 전달하지 않고
설정된 admin service token(`X-Kor-Travel-Map-Service-Token`)과, 운영에서 kor_travel_map
admin proxy gate가 켜진 경우 `X-Kor-Travel-Map-Admin-Proxy-Secret`/actor 헤더를 보낸다.
`/v1/ops/datasets*`·`/v1/ops/pipeline*`는 별도 server principal token/scope만 보내며
frontend BFF 자격은 전송하지 않는다(T-ADM-C6c).

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
import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal, cast

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapConflict,
    KorTravelMapError,
    KorTravelMapFeatureNotFound,
    KorTravelMapPreconditionFailed,
    KorTravelMapRateLimited,
    KorTravelMapUnavailable,
    _error_code,
)
from app.core.config import Settings, settings
from app.db import session as db_session
from app.middleware.api_call_logging import api_call_event_hooks
from app.services.kor_travel_map_ops_projection import (
    KorTravelMapOpsContractError,
    validate_pipeline_cancellation_detail,
    validate_pipeline_cancellation_root_without_attempt,
)

logger = logging.getLogger(__name__)

_SERVICE_TOKEN_HEADER = "X-Kor-Travel-Map-Service-Token"  # noqa: S105 - 헤더 이름(비밀 아님)
_ADMIN_PROXY_SECRET_HEADER = "X-Kor-Travel-Map-Admin-Proxy-Secret"  # noqa: S105
_ADMIN_ACTOR_HEADER = "X-Kor-Travel-Map-Actor"
_OPS_TOKEN_HEADER = "X-Kor-Travel-Map-Ops-Token"  # noqa: S105 - 헤더 이름(비밀 아님)
_OPS_SCOPE_HEADER = "X-Kor-Travel-Map-Ops-Scope"
_REQUEST_ID_HEADER = "X-Request-Id"
_REVISION_ETAG_PATTERN = re.compile(r'^"[1-9][0-9]*"$')

OpsScope = Literal["ops:read", "ops:cancel"]

_SENSITIVE_DETAIL_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "password",
        "secret",
        "service_key",
        "token",
    }
)
_CANCELLATION_TYPED_CODES_BY_STATUS: dict[int, frozenset[str]] = {
    status.HTTP_409_CONFLICT: frozenset(
        {
            "PIPELINE_CANCELLATION_IN_PROGRESS",
            "PIPELINE_CANCELLATION_UNSAFE",
        }
    ),
    status.HTTP_502_BAD_GATEWAY: frozenset({"DAGSTER_TERMINATE_FAILED"}),
    status.HTTP_503_SERVICE_UNAVAILABLE: frozenset(
        {"DAGSTER_UNAVAILABLE", "DAGSTER_TERMINATION_TIMEOUT"}
    ),
}


def _parse_retry_after(raw: str | None) -> int | None:
    if raw is None or not raw.isascii() or not raw.isdigit():
        return None
    value = int(raw)
    return value if 1 <= value <= 300 else None


def _retry_after(resp: httpx.Response) -> int | None:
    return _parse_retry_after(resp.headers.get("Retry-After"))


def _safe_detail_value(value: Any, *, key: str = "") -> Any:
    """canonical error detail에서 자격 증명 이름을 재귀적으로 마스킹한다."""

    normalized_key = key.casefold().replace("-", "_")
    if any(fragment in normalized_key for fragment in _SENSITIVE_DETAIL_KEYS):
        return "***"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_safe_detail_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(item_key): _safe_detail_value(item, key=str(item_key))
            for item_key, item in value.items()
        }
    return None


def _cancellation_problem_details(resp: httpx.Response) -> dict[str, Any] | None:
    """pipeline cancellation problem의 전체 canonical detail을 안전하게 보존한다."""

    try:
        problem = resp.json()
    except ValueError:
        return None
    if not isinstance(problem, dict):
        return None
    raw_details = problem.get("details")
    if not isinstance(raw_details, dict):
        return None
    return {key: _safe_detail_value(value, key=key) for key, value in raw_details.items()}


def pipeline_cancellation_outcome_uncertain(
    job_id: str,
) -> KorTravelMapUnavailable:
    """dispatch 뒤 결과를 확정할 수 없을 때 재조정 가능한 표준 오류를 만든다."""

    reconciliation_path = f"/v1/ops/pipeline/executions/import_job/{job_id}"
    return KorTravelMapUnavailable(
        "kor-travel-map pipeline cancellation outcome is uncertain",
        code="PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN",
        details={
            "outcome_certainty": "uncertain",
            "reconciliation": {
                "method": "GET",
                "path": reconciliation_path,
                "scope": "ops:read",
            },
        },
    )


def _validated_typed_cancellation_details(
    *,
    status_code: int,
    code: str,
    details: dict[str, Any] | None,
    retry_after_raw: str | None,
) -> dict[str, Any] | None:
    """status/code별 Map typed problem의 허용 detail shape를 strict 검증한다."""

    if code == "PIPELINE_CANCELLATION_UNSAFE":
        if retry_after_raw is not None:
            raise KorTravelMapOpsContractError("unsafe cancellation cannot carry Retry-After")
    elif code == "PIPELINE_CANCELLATION_IN_PROGRESS" or status_code in {
        status.HTTP_502_BAD_GATEWAY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    }:
        if _parse_retry_after(retry_after_raw) is None:
            raise KorTravelMapOpsContractError(
                "retryable cancellation requires canonical Retry-After"
            )
    if status_code == status.HTTP_409_CONFLICT:
        if details is None:
            if code == "PIPELINE_CANCELLATION_UNSAFE":
                return None
            raise KorTravelMapOpsContractError(
                "in-progress cancellation requires canonical root or detail"
            )
        if set(details) == {"root", "cancellation"}:
            return validate_pipeline_cancellation_root_without_attempt(details)
    if details is None:
        raise KorTravelMapOpsContractError("typed cancellation failure requires canonical detail")
    canonical = validate_pipeline_cancellation_detail(details)
    if status_code == status.HTTP_409_CONFLICT:
        expected_status = {
            "PIPELINE_CANCELLATION_IN_PROGRESS": "in_progress",
            "PIPELINE_CANCELLATION_UNSAFE": "failed",
        }[code]
        if canonical["status"] != expected_status:
            raise KorTravelMapOpsContractError(
                "typed cancellation status does not match its 409 code"
            )
    elif status_code in {
        status.HTTP_502_BAD_GATEWAY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    }:
        error = canonical["error"]
        if (
            canonical["status"] != "retryable"
            or not isinstance(error, dict)
            or error.get("code") != code
        ):
            raise KorTravelMapOpsContractError(
                "typed Dagster failure must match retryable attempt evidence"
            )
    return canonical


class KorTravelMapAdminClient:
    """kor-travel-map admin + canonical ops HTTP client(transport-only)."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        service_token: str = "",
        admin_proxy_secret: str = "",
        admin_actor: str = "pinvi-admin",
        ops_read_token: str = "",
        ops_cancel_token: str = "",
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.2,
        request_id: str | None = None,
    ) -> None:
        self._http = http
        self._service_token = service_token.strip()
        self._admin_proxy_secret = admin_proxy_secret.strip()
        self._admin_actor = admin_actor.strip() or "pinvi-admin"
        self._ops_tokens: dict[OpsScope, str] = {
            "ops:read": ops_read_token.strip(),
            "ops:cancel": ops_cancel_token.strip(),
        }
        self._max_attempts = max(1, max_attempts)
        self._backoff_base_seconds = backoff_base_seconds
        self._request_id = (request_id or "").strip()

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._request_id:
            headers[_REQUEST_ID_HEADER] = self._request_id
        if self._service_token:
            headers[_SERVICE_TOKEN_HEADER] = self._service_token
        if self._admin_proxy_secret:
            headers[_ADMIN_PROXY_SECRET_HEADER] = self._admin_proxy_secret
            headers[_ADMIN_ACTOR_HEADER] = self._admin_actor
        return headers

    def _ops_headers(self, scope: OpsScope) -> dict[str, str]:
        """canonical ops용 server principal 헤더만 반환한다.

        frontend BFF secret/actor와 public service token은 이 경계로 전달하지 않는다.
        """

        headers: dict[str, str] = {_OPS_SCOPE_HEADER: scope}
        if self._request_id:
            headers[_REQUEST_ID_HEADER] = self._request_id
        token = self._ops_tokens[scope]
        if token:
            headers[_OPS_TOKEN_HEADER] = token
        return headers

    def with_request_id(self, request_id: str | None) -> KorTravelMapAdminClient:
        return KorTravelMapAdminClient(
            self._http,
            service_token=self._service_token,
            admin_proxy_secret=self._admin_proxy_secret,
            admin_actor=self._admin_actor,
            ops_read_token=self._ops_tokens["ops:read"],
            ops_cancel_token=self._ops_tokens["ops:cancel"],
            max_attempts=self._max_attempts,
            backoff_base_seconds=self._backoff_base_seconds,
            request_id=request_id,
        )

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        ops_scope: OpsScope | None = None,
        retry_transient: bool = True,
    ) -> httpx.Response:
        """허용된 요청만 transient(타임아웃/연결/5xx) 지수 백오프로 재시도."""
        last: KorTravelMapUnavailable | None = None
        max_attempts = self._max_attempts if retry_transient else 1
        for attempt in range(max_attempts):
            try:
                request_headers = (
                    self._ops_headers(ops_scope)
                    if ops_scope is not None
                    else self._headers()
                )
                if headers is not None:
                    request_headers.update(headers)
                resp = await self._http.request(
                    method,
                    path,
                    json=json,
                    params=params,
                    headers=request_headers,
                    extensions=self._extensions(),
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = KorTravelMapUnavailable(f"kor-travel-map admin 요청 실패({path}): {exc!r}")
            else:
                if resp.status_code >= 500:
                    if not retry_transient:
                        return resp
                    last = KorTravelMapUnavailable(
                        f"kor-travel-map admin {resp.status_code} ({path})"
                    )
                else:
                    return resp
            if attempt + 1 < max_attempts:
                await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
        logger.warning("kor_travel_map_admin.unavailable", extra={"path": path})
        raise last or KorTravelMapUnavailable(f"kor-travel-map admin 요청 실패({path})")

    def _payload(
        self,
        resp: httpx.Response,
        *,
        require_meta: bool = False,
    ) -> dict[str, Any]:
        """성공 응답 envelope 추출. 오류 status는 도메인 예외로 변환."""
        sc = resp.status_code
        if sc == status.HTTP_404_NOT_FOUND:
            raise KorTravelMapFeatureNotFound(
                "feature 를 찾을 수 없습니다.",
                code=_error_code(resp),
                details=_cancellation_problem_details(resp),
            )
        error_code = _error_code(resp)
        if sc >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise KorTravelMapUnavailable(
                f"kor-travel-map admin {sc}",
                code=error_code,
                details=_cancellation_problem_details(resp),
                retry_after_seconds=_retry_after(resp),
                status_code=(
                    sc
                    if sc
                    in {
                        status.HTTP_502_BAD_GATEWAY,
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                    }
                    else status.HTTP_503_SERVICE_UNAVAILABLE
                ),
            )
        if sc == status.HTTP_409_CONFLICT:
            raise KorTravelMapConflict(
                f"kor-travel-map admin {sc}",
                code=error_code,
                details=_cancellation_problem_details(resp),
                retry_after_seconds=_retry_after(resp),
            )
        if sc == status.HTTP_412_PRECONDITION_FAILED:
            raise KorTravelMapPreconditionFailed(
                f"kor-travel-map admin {sc}",
                code=error_code,
            )
        if sc == status.HTTP_429_TOO_MANY_REQUESTS:
            raise KorTravelMapRateLimited(
                f"kor-travel-map admin {sc}", retry_after_seconds=_retry_after(resp)
            )
        if sc >= status.HTTP_400_BAD_REQUEST:
            raise KorTravelMapBadRequest(f"kor-travel-map admin {sc}", code=error_code)
        payload = resp.json()
        data = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(data, dict):
            raise KorTravelMapError(f"예상치 못한 admin 응답 셰입({resp.request.url.path})")
        meta = payload.get("meta") if isinstance(payload, Mapping) else None
        if require_meta and not isinstance(meta, Mapping):
            raise KorTravelMapError(f"canonical ops meta가 없습니다({resp.request.url.path})")
        if meta is not None and not isinstance(meta, Mapping):
            raise KorTravelMapError(f"예상치 못한 admin meta 셰입({resp.request.url.path})")
        if require_meta and isinstance(meta, Mapping):
            duration_ms = meta.get("duration_ms")
            meta_request_id = meta.get("request_id")
            if (
                not isinstance(duration_ms, int)
                or isinstance(duration_ms, bool)
                or duration_ms < 0
                or not isinstance(meta_request_id, str)
                or (bool(self._request_id) and meta_request_id != self._request_id)
            ):
                raise KorTravelMapError(
                    f"canonical ops meta provenance가 다릅니다({resp.request.url.path})"
                )
        return {"data": data, "meta": dict(meta) if isinstance(meta, Mapping) else {}}

    def _extensions(self) -> dict[str, str]:
        if self._request_id:
            return {"pinvi_request_id": self._request_id}
        return {}

    def _data(
        self,
        resp: httpx.Response,
        *,
        require_meta: bool = False,
    ) -> dict[str, Any]:
        """성공 응답 `data` 추출. 오류 status는 도메인 예외로 변환."""
        return cast(
            dict[str, Any],
            self._payload(resp, require_meta=require_meta)["data"],
        )

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

    async def _feature_revision_etag(self, feature_id: str) -> str:
        """stable revision GET의 canonical ETag를 mutation precondition으로 보존한다."""
        resp = await self._send("GET", f"/v1/admin/features/{feature_id}/revision")
        self._data(resp)
        entity_tag = cast(str | None, resp.headers.get("ETag"))
        if entity_tag is None or _REVISION_ETAG_PATTERN.fullmatch(entity_tag) is None:
            raise KorTravelMapError("admin feature revision 응답에 canonical ETag가 없습니다.")
        return entity_tag

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
        entity_tag = await self._feature_revision_etag(feature_id)
        return self._change_record(
            await self._send(
                "PATCH",
                f"/v1/admin/features/{feature_id}",
                json=dict(payload),
                headers={"If-Match": entity_tag},
            )
        )

    async def delete_feature(
        self, feature_id: str, *, reason: str, operator: str | None = None
    ) -> dict[str, Any]:
        """DELETE /v1/admin/features/{id} — 폐업(closure, soft). 문서 기본값=DELETE(§7)."""
        body: dict[str, Any] = {"reason": reason}
        if operator is not None:
            body["operator"] = operator
        entity_tag = await self._feature_revision_etag(feature_id)
        return self._change_record(
            await self._send(
                "DELETE",
                f"/v1/admin/features/{feature_id}",
                json=body,
                headers={"If-Match": entity_tag},
            )
        )

    # ── change-requests 큐 (kor_travel_map 운영자 검수 추적) ───────────────────────

    async def list_change_requests(
        self,
        *,
        statuses: list[str] | None = None,
        actions: list[str] | None = None,
        q: str | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """GET /v1/admin/features/change-requests — data = {items, review_mode}."""
        params: dict[str, Any] = {}
        self._put_sequence_params(params, "status", statuses)
        self._put_sequence_params(params, "action", actions)
        if q:
            params["q"] = q
        if page_size is not None:
            params["page_size"] = page_size
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

    # ── ops/provider ETL read proxy (kor_travel_map admin 운영 화면) ────────────────

    async def get_ops_pipeline_overview(self, *, run_limit: int = 10) -> dict[str, Any]:
        """canonical pipeline/Dagster 상태 strip을 반환한다."""
        return self._data(
            await self._send(
                "GET",
                "/v1/ops/pipeline/overview",
                params={"run_limit": run_limit},
                ops_scope="ops:read",
            ),
            require_meta=True,
        )

    async def list_ops_datasets(self) -> dict[str, Any]:
        """canonical provider x dataset x sync_scope grid를 반환한다."""
        return self._data(
            await self._send(
                "GET",
                "/v1/ops/datasets",
                ops_scope="ops:read",
            ),
            require_meta=True,
        )

    async def list_ops_pipeline_executions(
        self,
        *,
        status_filter: str | None = None,
        load_batch_id: str | None = None,
        parent_job_id: str | None = None,
        page_size: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """canonical import-job root timeline envelope를 반환한다."""
        params: dict[str, Any] = {"kind": "import_job", "page_size": page_size}
        if status_filter:
            params["status"] = status_filter
        if load_batch_id:
            params["load_batch_id"] = load_batch_id
        if parent_job_id:
            params["parent_job_id"] = parent_job_id
        if cursor:
            params["cursor"] = cursor
        return self._payload(
            await self._send(
                "GET",
                "/v1/ops/pipeline/executions",
                params=params,
                ops_scope="ops:read",
            ),
            require_meta=True,
        )

    async def cancel_ops_pipeline_execution(
        self,
        job_id: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """canonical import-job 계층 취소 결과를 반환한다."""
        body: dict[str, Any] = {}
        if reason is not None:
            body["reason"] = reason
        reconciliation_path = f"/v1/ops/pipeline/executions/import_job/{job_id}"
        try:
            response = await self._send(
                "POST",
                f"{reconciliation_path}/cancel",
                json=body,
                ops_scope="ops:cancel",
                retry_transient=False,
            )
        except KorTravelMapUnavailable as exc:
            raise pipeline_cancellation_outcome_uncertain(job_id) from exc

        # Map이 명시적으로 정의한 502/503 problem은 보존한다. 그 외 5xx는
        # dispatch 이후의 알 수 없는 서버 실패이므로 취소 결과를 단정하지 않는다.
        if response.status_code >= 500 and response.status_code not in {502, 503}:
            raise pipeline_cancellation_outcome_uncertain(job_id)
        try:
            return self._data(response, require_meta=True)
        except KorTravelMapConflict as exc:
            if exc.code in _CANCELLATION_TYPED_CODES_BY_STATUS.get(
                response.status_code, frozenset()
            ):
                try:
                    exc.details = _validated_typed_cancellation_details(
                        status_code=response.status_code,
                        code=exc.code,
                        details=exc.details,
                        retry_after_raw=response.headers.get("Retry-After"),
                    )
                except KorTravelMapOpsContractError as contract_exc:
                    raise pipeline_cancellation_outcome_uncertain(job_id) from contract_exc
                raise
            raise pipeline_cancellation_outcome_uncertain(job_id) from exc
        except KorTravelMapUnavailable as exc:
            if exc.code in _CANCELLATION_TYPED_CODES_BY_STATUS.get(
                response.status_code, frozenset()
            ):
                try:
                    exc.details = _validated_typed_cancellation_details(
                        status_code=response.status_code,
                        code=exc.code,
                        details=exc.details,
                        retry_after_raw=response.headers.get("Retry-After"),
                    )
                except KorTravelMapOpsContractError as contract_exc:
                    raise pipeline_cancellation_outcome_uncertain(job_id) from contract_exc
                raise
            raise pipeline_cancellation_outcome_uncertain(job_id) from exc
        except KorTravelMapFeatureNotFound as exc:
            if exc.code == "PIPELINE_EXECUTION_NOT_FOUND":
                raise
            raise pipeline_cancellation_outcome_uncertain(job_id) from exc
        except (KorTravelMapBadRequest, KorTravelMapRateLimited):
            raise
        except (KorTravelMapError, TypeError, ValueError) as exc:
            # 2xx라도 JSON/envelope를 해석할 수 없으면 upstream 적용 여부는 불확실하다.
            raise pipeline_cancellation_outcome_uncertain(job_id) from exc

    async def get_ops_pipeline_execution(self, job_id: str) -> dict[str, Any]:
        """취소 응답 유실 시 current cancellation overlay를 재조회한다."""

        return self._data(
            await self._send(
                "GET",
                f"/v1/ops/pipeline/executions/import_job/{job_id}",
                ops_scope="ops:read",
            ),
            require_meta=True,
        )

    async def list_dedup_reviews(
        self,
        *,
        statuses: list[str] | None = None,
        providers: list[str] | None = None,
        dataset_keys: list[str] | None = None,
        kinds: list[str] | None = None,
        categories: list[str] | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        q: str | None = None,
        page_size: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/admin/dedup-reviews — dedup review queue 목록 envelope 반환."""
        params: dict[str, Any] = {"page_size": page_size}
        self._put_sequence_params(params, "status", statuses)
        self._put_sequence_params(params, "provider", providers)
        self._put_sequence_params(params, "dataset_key", dataset_keys)
        self._put_sequence_params(params, "kind", kinds)
        self._put_sequence_params(params, "category", categories)
        if min_score is not None:
            params["min_score"] = min_score
        if max_score is not None:
            params["max_score"] = max_score
        if q:
            params["q"] = q
        if cursor:
            params["cursor"] = cursor
        return self._payload(await self._send("GET", "/v1/admin/dedup-reviews", params=params))

    async def decide_dedup_review(
        self,
        review_id: str,
        *,
        decision: str,
        decision_reason: str | None = None,
        master_feature_id: str | None = None,
        reviewed_by: str | None = None,
    ) -> dict[str, Any]:
        """PATCH /v1/admin/dedup-reviews/{review_id} — dedup verdict data 반환."""
        body: dict[str, Any] = {"decision": decision}
        if decision_reason is not None:
            body["decision_reason"] = decision_reason
        if master_feature_id is not None:
            body["master_feature_id"] = master_feature_id
        if reviewed_by is not None:
            body["reviewed_by"] = reviewed_by
        return self._data(
            await self._send("PATCH", f"/v1/admin/dedup-reviews/{review_id}", json=body)
        )

    async def list_integrity_issues(
        self,
        *,
        status_filter: str | None = "open",
        severity: str | None = None,
        violation_type: str | None = None,
        provider: str | None = None,
        dataset_key: str | None = None,
        feature_id: str | None = None,
        page_size: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/ops/consistency/issues — integrity issue 목록 envelope 반환."""
        params: dict[str, Any] = {"page_size": page_size}
        if status_filter:
            params["status"] = status_filter
        if severity:
            params["severity"] = severity
        if violation_type:
            params["violation_type"] = violation_type
        if provider:
            params["provider"] = provider
        if dataset_key:
            params["dataset_key"] = dataset_key
        if feature_id:
            params["feature_id"] = feature_id
        if cursor:
            params["cursor"] = cursor
        return self._payload(await self._send("GET", "/v1/ops/consistency/issues", params=params))

    async def patch_admin_issue(
        self,
        issue_id: str,
        *,
        action: str,
        reason: str | None = None,
        operator: str | None = None,
    ) -> dict[str, Any]:
        """PATCH /v1/admin/issues/{id} — integrity issue 상태 조치 envelope 반환."""
        body: dict[str, Any] = {"action": action}
        if reason is not None:
            body["reason"] = reason
        if operator is not None:
            body["operator"] = operator
        return self._payload(await self._send("PATCH", f"/v1/admin/issues/{issue_id}", json=body))

    async def list_consistency_reports(
        self,
        *,
        severity_max: str | None = None,
        page_size: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/ops/consistency/reports — consistency report 목록 envelope 반환."""
        params: dict[str, Any] = {"page_size": page_size}
        if severity_max:
            params["severity_max"] = severity_max
        if cursor:
            params["cursor"] = cursor
        return self._payload(await self._send("GET", "/v1/ops/consistency/reports", params=params))

    async def list_system_logs(
        self,
        *,
        level: str | None = None,
        source: str | None = None,
        q: str | None = None,
        request_id: str | None = None,
        page_size: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/ops/system-logs — sanitized system log 목록 envelope 반환."""
        params: dict[str, Any] = {"page_size": page_size}
        if level:
            params["level"] = level
        if source:
            params["source"] = source
        if q:
            params["q"] = q
        if request_id:
            params["request_id"] = request_id
        if cursor:
            params["cursor"] = cursor
        return self._payload(await self._send("GET", "/v1/ops/system-logs", params=params))

    async def list_ops_api_call_logs(
        self,
        *,
        method: str | None = None,
        min_status: int | None = None,
        path: str | None = None,
        request_id: str | None = None,
        page_size: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/ops/api-call-logs — upstream API call log 목록 envelope 반환."""
        params: dict[str, Any] = {"page_size": page_size}
        if method:
            params["method"] = method
        if min_status is not None:
            params["min_status"] = min_status
        if path:
            params["path"] = path
        if request_id:
            params["request_id"] = request_id
        if cursor:
            params["cursor"] = cursor
        return self._payload(await self._send("GET", "/v1/ops/api-call-logs", params=params))


def create_kor_travel_map_admin_client(app_settings: Settings) -> KorTravelMapAdminClient:
    """admin 자격과 canonical ops principal을 분리해 client를 생성한다."""
    token = (
        app_settings.pinvi_kor_travel_map_admin_service_token
        or app_settings.pinvi_kor_travel_map_service_token
    )
    http = httpx.AsyncClient(
        base_url=app_settings.pinvi_kor_travel_map_admin_base_url,
        timeout=app_settings.pinvi_kor_travel_map_timeout_seconds,
        event_hooks=api_call_event_hooks(
            db_session.async_session_factory,
            provider="kor_travel_map_admin",
        ),
    )
    return KorTravelMapAdminClient(
        http,
        service_token=token,
        admin_proxy_secret=app_settings.pinvi_kor_travel_map_admin_proxy_secret,
        admin_actor=app_settings.pinvi_kor_travel_map_admin_actor,
        ops_read_token=(
            app_settings.pinvi_kor_travel_map_ops_read_token.get_secret_value()
            if app_settings.pinvi_kor_travel_map_ops_read_token is not None
            else ""
        ),
        ops_cancel_token=(
            app_settings.pinvi_kor_travel_map_ops_cancel_token.get_secret_value()
            if app_settings.pinvi_kor_travel_map_ops_cancel_token is not None
            else ""
        ),
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
    return client.with_request_id(getattr(request.state, "request_id", None))


KorTravelMapAdminClientDep = Annotated[
    KorTravelMapAdminClient, Depends(get_kor_travel_map_admin_client)
]
