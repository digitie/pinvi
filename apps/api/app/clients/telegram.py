"""Telegram Bot API client (사용자/Admin 알림) — `docs/integrations/telegram.md`.

T-106. Telegram Bot API(`getChat`/`sendMessage`) 전송 전용 client. bot token 원본은
DB에 저장하지 않고(§1), 로그에는 `mask_token`으로만 남긴다(§9). PII/좌표는 호출자 책임.

실패는 §5 표대로 `TelegramError.code`로 분류한다:
`missing_chat_id` | `bot_forbidden` | `invalid_chat` | `invalid_topic` |
`rate_limited` | `network_error` | `unknown_error`.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# §9 — bot token 마스킹 (`\d+:[A-Za-z0-9_-]+`). 숫자 ID는 남기고 secret 부분만 가린다.
_TOKEN_RE = re.compile(r"(\d+):[A-Za-z0-9_-]{20,}")


def mask_token(text: str) -> str:
    """문자열 안의 Telegram bot token을 `<id>:***`로 마스킹한다."""
    return _TOKEN_RE.sub(lambda m: f"{m.group(1)}:***", text)


class TelegramError(Exception):
    """Telegram 호출 실패. `code`는 docs §5의 분류값."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        status_code: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(message)


def _retry_after_seconds(response: httpx.Response, body: dict[str, Any]) -> int | None:
    params = body.get("parameters")
    if isinstance(params, dict):
        candidate = params.get("retry_after")
        if isinstance(candidate, int):
            return candidate
    header = response.headers.get("retry-after")
    if header and header.isdigit():
        return int(header)
    return None


def _classify(response: httpx.Response) -> TelegramError:
    """HTTP 응답을 §5 실패 코드로 변환한다 (token은 노출하지 않음)."""
    status = response.status_code
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    description = str(body.get("description") or "").strip()
    desc_lower = description.lower()
    safe = mask_token(description) or f"telegram error {status}"

    if status == 429:
        return TelegramError(
            safe,
            code="rate_limited",
            status_code=status,
            retry_after=_retry_after_seconds(response, body),
        )
    if status == 403:
        return TelegramError(safe, code="bot_forbidden", status_code=status)
    if status == 400:
        if "thread" in desc_lower or "topic" in desc_lower:
            return TelegramError(safe, code="invalid_topic", status_code=status)
        return TelegramError(safe, code="invalid_chat", status_code=status)
    if status >= 500:
        return TelegramError(safe, code="network_error", status_code=status)
    return TelegramError(safe, code="unknown_error", status_code=status)


class TelegramClient:
    """Telegram Bot API 전송 전용 client (httpx.AsyncClient 주입)."""

    def __init__(self, http: httpx.AsyncClient, *, timeout_seconds: float = 5.0) -> None:
        self._http = http
        self._timeout = timeout_seconds

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _call(
        self, method: str, telegram_method: str, token: str, **kwargs: Any
    ) -> dict[str, Any]:
        path = f"/bot{token}/{telegram_method}"
        try:
            response = await self._http.request(method, path, timeout=self._timeout, **kwargs)
        except httpx.TimeoutException as exc:
            raise TelegramError("telegram timeout", code="network_error") from exc
        except httpx.TransportError as exc:
            raise TelegramError("telegram connection error", code="network_error") from exc

        if response.status_code != 200:
            raise _classify(response)
        body = response.json()
        if not isinstance(body, dict) or not body.get("ok"):
            # 200 + ok:false (희귀) — 분류 시도 후 unknown fallback.
            raise _classify(response)
        result = body.get("result")
        return result if isinstance(result, dict) else {}

    async def verify_target(self, token: str, chat_id: str) -> dict[str, Any]:
        """`getChat`로 chat 존재/타입/봇 접근권을 확인하고 타입·제목 스냅샷을 반환한다."""
        if not chat_id:
            raise TelegramError("chat_id required", code="missing_chat_id")
        result = await self._call("GET", "getChat", token, params={"chat_id": chat_id})
        return {
            "telegram_chat_type": result.get("type"),
            "title_snapshot": result.get("title")
            or result.get("first_name")
            or result.get("username"),
        }

    async def send_to_target(
        self,
        token: str,
        chat_id: str,
        message: str,
        *,
        thread_id: str | None = None,
        parse_mode: str = "MarkdownV2",
    ) -> dict[str, Any]:
        """`sendMessage`로 메시지를 보낸다. 성공 시 Telegram message 객체를 반환한다."""
        if not chat_id:
            raise TelegramError("chat_id required", code="missing_chat_id")
        payload: dict[str, Any] = {"chat_id": chat_id, "text": message, "parse_mode": parse_mode}
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        return await self._call("POST", "sendMessage", token, json=payload)
