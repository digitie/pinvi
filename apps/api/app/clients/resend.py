"""Resend REST client with `api_call_log` provider tracking."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from app.core.config import settings
from app.db import session as db_session
from app.middleware.api_call_logging import ApiCallLoggingClient, api_call_event_hooks

# 4xx 중 같은 요청을 다시 보내면 성공할 수 있는 것: timeout·idempotency 동시 처리·rate limit/quota.
# 나머지 4xx(400 검증, 401 key, 403 미검증 발신 도메인, 422 from/to 형식 등)는 설정이나 payload를
# 고치기 전까지 몇 번을 보내도 같은 답이므로 영구 실패다(#720).
_RETRYABLE_CLIENT_STATUS = frozenset({408, 409, 429})
_ERROR_MESSAGE_MAX_CHARS = 200
_EMAIL_PATTERN = re.compile(r"[^\s<>\"'`@]+@[^\s<>\"'`@]+")
_API_KEY_PATTERN = re.compile(r"\bre_[A-Za-z0-9_]+")


class ResendPermanentError(Exception):
    """재시도해도 성공하지 않는 Resend 거절(대개 발신 도메인·key·payload 설정 오류).

    `summary`는 outbox `last_error`·로그에 그대로 남기는 값이다. 수신자 주소와 API key
    모양의 문자열은 가리고 길이를 자른다.
    """

    def __init__(self, *, status_code: int, error_name: str | None, message: str | None) -> None:
        self.status_code = status_code
        self.error_name = error_name
        self.message = message
        super().__init__(self.summary)

    @property
    def summary(self) -> str:
        parts = [f"resend_permanent:{self.status_code}"]
        if self.error_name:
            parts.append(self.error_name)
        if self.message:
            parts.append(self.message)
        return ":".join(parts)


def _redact_error_text(value: str) -> str:
    redacted = _EMAIL_PATTERN.sub("<email>", value)
    redacted = _API_KEY_PATTERN.sub("<redacted>", redacted)
    redacted = " ".join(redacted.split())
    return redacted[:_ERROR_MESSAGE_MAX_CHARS]


def _permanent_error_from_response(response: httpx.Response) -> ResendPermanentError:
    error_name: str | None = None
    message: str | None = None
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        raw_name = body.get("name")
        raw_message = body.get("message")
        if isinstance(raw_name, str) and raw_name.strip():
            error_name = _redact_error_text(raw_name)[:64]
        if isinstance(raw_message, str) and raw_message.strip():
            message = _redact_error_text(raw_message)
    return ResendPermanentError(
        status_code=response.status_code,
        error_name=error_name,
        message=message,
    )


def is_permanent_resend_status(status_code: int) -> bool:
    return 400 <= status_code < 500 and status_code not in _RETRYABLE_CLIENT_STATUS


class ResendClient:
    """Small async wrapper over Resend REST endpoints Pinvi uses."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def send_email(self, payload: dict[str, Any]) -> str | None:
        response = await self._http.post("/emails", json=payload)
        if is_permanent_resend_status(response.status_code):
            raise _permanent_error_from_response(response)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            return None
        resend_id = body.get("id")
        return str(resend_id) if resend_id is not None else None

    async def list_domains(self) -> list[dict[str, Any]]:
        response = await self._http.get("/domains")
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict):
            data = body.get("data", [])
        else:
            data = body
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]


@asynccontextmanager
async def create_resend_client(
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncIterator[ResendClient]:
    headers = {"Authorization": f"Bearer {settings.pinvi_resend_api_key}"}
    async with ApiCallLoggingClient(
        base_url=settings.pinvi_resend_api_base_url,
        headers=headers,
        timeout=settings.pinvi_resend_timeout_seconds,
        transport=transport,
        event_hooks=api_call_event_hooks(db_session.async_session_factory, provider="resend"),
    ) as http:
        yield ResendClient(http)
