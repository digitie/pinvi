"""Map admin·ops HTTP client.

Feature 읽기는 별도 service read principal, 운영 관측은 ops principal을 사용한다.
직접 수정·폐쇄는 admin proxy 인증·If-Match·Idempotency-Key와 현재 commit receipt를
사용하며 폐기된 change-requests 큐는 호출하지 않는다. 신규 장소는 별도 service 큐가 소유한다.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal, cast
from urllib.parse import quote

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError

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

_OPS_OBSERVABILITY_READ_PATHS = frozenset(
    {
        "/v1/ops/dedup-reviews",
        "/v1/ops/consistency/issues",
        "/v1/ops/consistency/reports",
        "/v1/ops/system-logs",
        "/v1/ops/api-call-logs",
    }
)

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


class FeatureOverrideReceipt(BaseModel):
    feature_id: str = Field(min_length=1)
    row_revision: int = Field(ge=1, strict=True)
    command_id: int = Field(ge=1, strict=True)
    applied_field_count: int = Field(ge=1, strict=True)


class FeatureStateReceipt(BaseModel):
    feature_id: str = Field(min_length=1)
    lifecycle_state: Literal["active", "retired"]
    publication_state: Literal["draft", "published", "suppressed"]
    quality_state: Literal["valid", "quarantined"]
    row_revision: int = Field(ge=1, strict=True)
    audit_transition_id: int = Field(ge=1, strict=True)


class KorTravelMapAdminClient:
    """kor-travel-map admin + canonical ops HTTP client(transport-only)."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        service_token: str = "",
        admin_proxy_secret: str = "",
        admin_actor: str = "pinvi-admin",
        admin_features_read_token: str = "",
        ops_read_token: str = "",
        ops_cancel_token: str = "",
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.2,
        request_id: str | None = None,
    ) -> None:
        self._http = http
        self._service_token = service_token.strip()
        if admin_features_read_token and (
            len(admin_features_read_token) < 32
            or any(character.isspace() for character in admin_features_read_token)
        ):
            raise ValueError(
                "admin features read token must contain 32+ characters without whitespace"
            )
        if admin_features_read_token and admin_features_read_token in {
            service_token.strip(),
            admin_proxy_secret.strip(),
            ops_read_token.strip(),
            ops_cancel_token.strip(),
        }:
            raise ValueError(
                "admin features read token must not reuse another trust-boundary credential"
            )
        self._admin_features_read_token = admin_features_read_token
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

    def _feature_read_headers(self) -> dict[str, str]:
        """목록·상세 전용 자격만 보낸다. 다른 인증 경계로 fallback하지 않는다."""
        if not self._admin_features_read_token:
            raise KorTravelMapUnavailable(
                "kor-travel-map 관리자 Feature 조회 자격이 설정되지 않았습니다."
            )
        headers = {_SERVICE_TOKEN_HEADER: self._admin_features_read_token}
        if self._request_id:
            headers[_REQUEST_ID_HEADER] = self._request_id
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
            admin_features_read_token=self._admin_features_read_token,
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
        feature_read: bool = False,
        retry_transient: bool = True,
    ) -> httpx.Response:
        """허용된 요청만 transient(타임아웃/연결/5xx) 지수 백오프로 재시도."""
        if feature_read and (
            method != "GET"
            or ops_scope is not None
            or re.fullmatch(r"/v1/service/admin-features(?:/[^/?#]+)?", path) is None
            or path.rsplit("/", 1)[-1] in {".", ".."}
            or headers is not None
        ):
            raise ValueError("등록된 Feature 목록·상세 GET만 전용 읽기 자격을 사용할 수 있습니다.")
        last: KorTravelMapUnavailable | None = None
        max_attempts = self._max_attempts if retry_transient else 1
        for attempt in range(max_attempts):
            try:
                if feature_read:
                    request_headers = self._feature_read_headers()
                elif ops_scope is not None:
                    request_headers = self._ops_headers(ops_scope)
                else:
                    request_headers = self._headers()
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
                if feature_read and resp.status_code in {401, 403}:
                    # upstream 자격 오류를 사용자의 입력 오류로 바꾸거나 재시도하지 않는다.
                    raise KorTravelMapUnavailable(
                        "kor-travel-map 관리자 Feature 조회 권한을 확인할 수 없습니다."
                    )
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

    async def _send_ops_observability_read(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        """등록된 관측 GET만 `ops:read` principal로 보낸다."""

        if path not in _OPS_OBSERVABILITY_READ_PATHS:
            raise ValueError(f"등록되지 않은 kor-travel-map 관측 read 경로: {path}")
        return await self._send("GET", path, params=params, ops_scope="ops:read")

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
        if sc in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
            raise KorTravelMapUnavailable(
                "Map 관리자 인증을 확인할 수 없습니다.", code="MAP_ADMIN_AUTH_UNAVAILABLE"
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
            return {"request_id": self._request_id}
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
        values: Sequence[str] | None,
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
        lifecycle_states: Sequence[str] | None = None,
        publication_states: Sequence[str] | None = None,
        quality_states: Sequence[str] | None = None,
        provider_dataset_id: int | None = None,
        has_coord: bool | None = None,
        has_issue: bool | None = None,
        issue_types: list[str] | None = None,
        updated_from: str | None = None,
        updated_to: str | None = None,
        include_ended: bool | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/service/admin-features — admin feature 목록 envelope 반환.

        이름·주소·ID 검색은 `search_scope=feature`로 원천 JSON 검색을 제외한다.
        query 이름은 Map `GET /v1/admin/features`가 실제로 선언한 것만 보낸다:
        `[q, search_scope, kind, category, lifecycle_state, publication_state, quality_state,
        provider_dataset_id, has_coord, has_issue, issue_type, updated_from,
        updated_to, include_ended, page_size, cursor, sort, order]`.
        FastAPI는 모르는 query를 조용히 버리므로, 여기서 legacy 이름
        (`status`/`provider`/`dataset_key`)을 보내면 필터가 걸린 척하면서 전량이
        돌아온다 — 그래서 3축 cutover(`1f2bdc3a`) 이름으로 갈아탄다.
        """
        params: dict[str, Any] = {
            "search_scope": "feature",
        }
        if q:
            params["q"] = q
        self._put_sequence_params(params, "kind", kinds)
        self._put_sequence_params(params, "category", categories)
        self._put_sequence_params(params, "lifecycle_state", lifecycle_states)
        self._put_sequence_params(params, "publication_state", publication_states)
        self._put_sequence_params(params, "quality_state", quality_states)
        self._put_sequence_params(params, "issue_type", issue_types)
        if provider_dataset_id is not None:
            params["provider_dataset_id"] = provider_dataset_id
        if has_coord is not None:
            params["has_coord"] = has_coord
        if has_issue is not None:
            params["has_issue"] = has_issue
        if updated_from:
            params["updated_from"] = updated_from
        if updated_to:
            params["updated_to"] = updated_to
        if include_ended is not None:
            params["include_ended"] = include_ended
        if page_size is not None:
            params["page_size"] = page_size
        if cursor:
            params["cursor"] = cursor
        if sort:
            params["sort"] = sort
        if order:
            params["order"] = order
        return self._payload(
            await self._send("GET", "/v1/service/admin-features", params=params, feature_read=True)
        )

    async def get_feature_detail(self, feature_id: str) -> dict[str, Any]:
        """GET /v1/service/admin-features/{id} — admin feature 상세 data 반환."""
        return self._data(
            await self._send(
                "GET", f"/v1/service/admin-features/{quote(feature_id, safe='')}", feature_read=True
            )
        )

    async def get_feature_revision_etag(self, feature_id: str) -> str:
        """stable revision GET의 canonical ETag를 mutation precondition으로 보존한다."""
        resp = await self._send("GET", f"/v1/admin/features/{feature_id}/revision")
        self._data(resp)
        entity_tag = cast(str | None, resp.headers.get("ETag"))
        if entity_tag is None or _REVISION_ETAG_PATTERN.fullmatch(entity_tag) is None:
            raise KorTravelMapError("admin feature revision 응답에 canonical ETag가 없습니다.")
        return entity_tag

    def _command_receipt(self, resp: httpx.Response, schema: type[BaseModel]) -> dict[str, Any]:
        """직접 수정의 commit receipt만 수용하고 폐기된 요청 큐 shape는 거절한다."""
        data = self._data(resp)
        try:
            return schema.model_validate(data).model_dump(mode="json")
        except ValidationError as exc:
            raise KorTravelMapError("Map 직접 수정 receipt 형식이 올바르지 않습니다.") from exc

    async def patch_feature(
        self,
        feature_id: str,
        payload: Mapping[str, Any],
        *,
        expected_revision: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._command_receipt(
            await self._send(
                "PATCH",
                f"/v1/admin/features/{quote(feature_id, safe='')}",
                json=dict(payload),
                headers={"If-Match": expected_revision, "Idempotency-Key": idempotency_key},
            ),
            FeatureOverrideReceipt,
        )

    async def delete_feature(
        self,
        feature_id: str,
        *,
        reason: str,
        expected_revision: str,
        idempotency_key: str,
        operator: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"reason": reason}
        if operator is not None:
            body["operator"] = operator
        return self._command_receipt(
            await self._send(
                "DELETE",
                f"/v1/admin/features/{quote(feature_id, safe='')}",
                json=body,
                headers={"If-Match": expected_revision, "Idempotency-Key": idempotency_key},
            ),
            FeatureStateReceipt,
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
        """GET /v1/ops/dedup-reviews — 읽기 전용 principal로 후보 목록 조회."""
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
        return self._payload(
            await self._send_ops_observability_read("/v1/ops/dedup-reviews", params=params)
        )

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
        return self._payload(
            await self._send_ops_observability_read(
                "/v1/ops/consistency/issues",
                params=params,
            )
        )

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
        return self._payload(
            await self._send_ops_observability_read(
                "/v1/ops/consistency/reports",
                params=params,
            )
        )

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
        return self._payload(
            await self._send_ops_observability_read(
                "/v1/ops/system-logs",
                params=params,
            )
        )

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
        return self._payload(
            await self._send_ops_observability_read(
                "/v1/ops/api-call-logs",
                params=params,
            )
        )


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
        admin_features_read_token=(
            app_settings.pinvi_kor_travel_map_admin_features_read_token.get_secret_value()
            if app_settings.pinvi_kor_travel_map_admin_features_read_token is not None
            else ""
        ),
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
