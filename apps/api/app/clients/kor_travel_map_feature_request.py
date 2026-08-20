"""kor-travel-map 범용 Feature 요청 큐 전용 service transport.

PinVi의 사용자 제안은 PinVi DB에 먼저 보존한다. 관리자 승인 뒤에만 이 client가
Map의 ``/v1/service/feature-requests``로 immutable 요청을 제출한다. admin/public/일반
service 자격을 재사용하지 않고, 제출 request UUID를 ``Idempotency-Key``와 body에 함께
결박한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.clients.kor_travel_map import _error_code
from app.core.config import Settings, settings
from app.db import session as db_session
from app.middleware.api_call_logging import api_call_event_hooks

logger = logging.getLogger(__name__)

_SERVICE_TOKEN_HEADER = "X-Kor-Travel-Map-Service-Token"  # noqa: S105 - header name
_IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
_SUBMIT_PATH = "/v1/service/feature-requests"


class FeatureRequestQueueError(RuntimeError):
    """Map Feature 요청 큐 호출/계약 오류의 공통 기반."""


class FeatureRequestQueueUnavailable(FeatureRequestQueueError):
    """network, timeout, 또는 Map 5xx로 제출 결과가 확정되지 않음."""


class FeatureRequestQueueContractError(FeatureRequestQueueError):
    """성공 응답이 vendored OpenAPI 계약과 다름."""


class FeatureRequestQueueProblem(FeatureRequestQueueError):
    """Map RFC7807 4xx를 status/code로 보존한다."""

    def __init__(self, *, status_code: int, code: str | None) -> None:
        super().__init__(f"kor-travel-map feature request problem: {status_code} {code}")
        self.status_code = status_code
        self.code = code


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FeatureRequestCoord(_ClosedModel):
    lon: float = Field(ge=124, le=132)
    lat: float = Field(ge=33, le=39.5)


class FeatureRequestReceipt(_ClosedModel):
    request_id: uuid.UUID
    status: Literal["pending", "approved", "rejected", "exact_conflict"]
    kind: Literal["place", "event"]
    name: str = Field(min_length=1, max_length=200)
    coord: FeatureRequestCoord
    categories: list[str] = Field(max_length=10)
    note: str | None = Field(default=None, max_length=2000)
    submitted_at: datetime
    resolved_at: datetime | None = None
    resolved_by_actor: str | None = None
    feature_id: str | None = None
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def validate_submit_receipt(self) -> FeatureRequestReceipt:
        # submit command의 stored response는 최초 제출 시점의 상태여야 한다. 이미 완료된 Map
        # queue row를 최신 상태로 읽어 PinVi local state를 잘못 전이시키지 않는다.
        if self.status not in {"pending", "exact_conflict"}:
            raise ValueError("submit response status must be pending or exact_conflict")
        if self.status == "pending" and self.feature_id is not None:
            raise ValueError("pending submit response cannot have feature_id")
        if self.status == "exact_conflict" and not self.feature_id:
            raise ValueError("exact_conflict submit response requires feature_id")
        return self


class FeatureRequestServiceClient:
    """``feature-request:submit`` principal에 고정된 idempotent writer."""

    def __init__(self, http: httpx.AsyncClient, *, token: str, max_attempts: int = 3) -> None:
        self._http = http
        self._token = token
        self._max_attempts = max(1, max_attempts)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def submit(
        self,
        *,
        request_id: uuid.UUID,
        kind: Literal["place", "event"],
        name: str,
        lon: float,
        lat: float,
        categories: list[str],
        note: str | None,
    ) -> FeatureRequestReceipt:
        """immutable PinVi request를 동일 UUID의 Map command로 정확히 한 번 제출한다."""

        payload = {
            "request_id": str(request_id),
            "kind": kind,
            "name": name,
            "coord": {"lon": lon, "lat": lat},
            "categories": categories,
            "note": note,
        }
        headers = {
            _SERVICE_TOKEN_HEADER: self._token,
            _IDEMPOTENCY_KEY_HEADER: str(request_id),
        }
        last_error: FeatureRequestQueueUnavailable | None = None
        for attempt in range(self._max_attempts):
            try:
                response = await self._http.post(_SUBMIT_PATH, json=payload, headers=headers)
            except httpx.RequestError as exc:
                last_error = FeatureRequestQueueUnavailable(
                    f"kor-travel-map feature request transport failed: {exc!r}"
                )
            else:
                if response.status_code >= 500:
                    last_error = FeatureRequestQueueUnavailable(
                        f"kor-travel-map feature request returned {response.status_code}"
                    )
                elif response.status_code != status.HTTP_201_CREATED:
                    raise FeatureRequestQueueProblem(
                        status_code=response.status_code,
                        code=_error_code(response),
                    )
                else:
                    return self._receipt(response, request_id=request_id)
            if attempt + 1 < self._max_attempts:
                await asyncio.sleep(0.2 * (2**attempt))
        raise last_error or FeatureRequestQueueUnavailable("feature request submission failed")

    @staticmethod
    def _receipt(response: httpx.Response, *, request_id: uuid.UUID) -> FeatureRequestReceipt:
        try:
            payload = json.loads(response.content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FeatureRequestQueueContractError("Map submit response is not valid JSON") from exc
        if not isinstance(payload, dict) or set(payload) != {"data", "meta"}:
            raise FeatureRequestQueueContractError("Map submit envelope shape is invalid")
        if not isinstance(payload["meta"], dict) or not isinstance(payload["data"], dict):
            raise FeatureRequestQueueContractError("Map submit envelope data/meta is invalid")
        try:
            receipt = FeatureRequestReceipt.model_validate(payload["data"])
        except ValueError as exc:
            raise FeatureRequestQueueContractError("Map submit data contract is invalid") from exc
        if receipt.request_id != request_id:
            raise FeatureRequestQueueContractError("Map submit response request_id differs from input")
        return receipt


def create_feature_request_service_client(app_settings: Settings) -> FeatureRequestServiceClient | None:
    token = app_settings.pinvi_kor_travel_map_feature_request_token
    if token is None:
        return None
    http = httpx.AsyncClient(
        base_url=app_settings.pinvi_kor_travel_map_api_base_url,
        timeout=app_settings.pinvi_kor_travel_map_timeout_seconds,
        event_hooks=api_call_event_hooks(
            db_session.async_session_factory,
            provider="kor_travel_map_feature_request",
        ),
    )
    return FeatureRequestServiceClient(
        http,
        token=token.get_secret_value(),
        max_attempts=app_settings.pinvi_kor_travel_map_max_attempts,
    )


@asynccontextmanager
async def feature_request_service_client_lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = create_feature_request_service_client(settings)
    app.state.feature_request_service_client = client
    if client is None:
        logger.info("kor_travel_map_feature_request.client_disabled")
    else:
        logger.info(
            "kor_travel_map_feature_request.client_ready",
            extra={"base_url": settings.pinvi_kor_travel_map_api_base_url},
        )
    try:
        yield
    finally:
        if client is not None:
            await client.aclose()
        app.state.feature_request_service_client = None


def get_feature_request_service_client(request: Request) -> FeatureRequestServiceClient:
    client = getattr(request.app.state, "feature_request_service_client", None)
    if not isinstance(client, FeatureRequestServiceClient):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "MAP_FEATURE_REQUEST_QUEUE_UNAVAILABLE",
                "message": "지도 Feature 요청 큐가 구성되지 않았습니다.",
            },
        )
    return client


FeatureRequestServiceClientDep = Annotated[
    FeatureRequestServiceClient,
    Depends(get_feature_request_service_client),
]
