"""Telegram Bot API client (사용자/Admin 알림) — `docs/integrations/telegram.md`.

T-106. Telegram Bot API(`getChat`/`sendMessage`) 전송 전용 client. bot token 원본은
DB에 저장하지 않고(§1), 로그에는 `mask_token`으로만 남긴다(§9). PII/좌표는 호출자 책임.

실패는 §5 표대로 `TelegramError.code`로 분류한다:
`missing_chat_id` | `bot_forbidden` | `invalid_chat` | `invalid_topic` |
`rate_limited` | `network_error` | `unknown_error`.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, ClassVar

import httpx

from app.clients._resilience import BULKHEAD_REJECTIONS

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
        if type(candidate) is int and candidate > 0:
            return candidate
    header = response.headers.get("retry-after")
    if header and header.isascii() and header.isdigit():
        try:
            seconds = int(header)
        except ValueError:
            return None
        return seconds if seconds > 0 else None
    return None


def _classify(response: httpx.Response, *, token: str | None = None) -> TelegramError:
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
    # 설정된 값은 길이/형식과 무관하게 숨긴다. provider가 credential을 되비춰도
    # UI 오류·outbox 기록에 원문이 남지 않는다.
    safe = mask_token(description.replace(token, "***") if token else description)
    safe = safe or f"telegram error {status}"

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

    #: 상한을 건 client(요청 경로)의 worker(프로세스) 전체 Telegram 동시 호출 수(#621). client는 요청마다
    #: 새로 만들므로 수는 인스턴스가 아니라 클래스에 둔다. 이벤트 루프에 묶이지 않는 정수이고 await 없이
    #: 세고 되돌린다 — 한 프로세스에 루프 하나(uvicorn worker)라는 전제다. 스레드 안전하지 않다.
    _in_flight: ClassVar[int] = 0

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        timeout_seconds: float = 5.0,
        max_concurrent_requests: int | None = None,
    ) -> None:
        """``max_concurrent_requests``가 None이면 상한이 없다.

        알림 drain worker는 상한을 걸지 않는다 — 로컬 거부가 `network_error`로 재시도 횟수를 태우고
        target을 실패로 표시하면 안 된다. 그쪽은 lease 뒤 잠금 없이 보내고 worker가 순차라 자체로 묶인다.
        """
        self._http = http
        self._timeout = timeout_seconds
        if max_concurrent_requests is not None and max_concurrent_requests < 1:
            raise ValueError("max_concurrent_requests는 양수여야 합니다.")
        self._max_concurrent = max_concurrent_requests

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _call(
        self, method: str, telegram_method: str, token: str, **kwargs: Any
    ) -> dict[str, Any]:
        path = f"/bot{token}/{telegram_method}"
        if self._max_concurrent is None:
            return await self._send(method, path, token, **kwargs)
        # 꽉 차면 기다리지 않는다. target 등록·검증은 쓰기 트랜잭션 안에서 부르므로, Telegram 정지가
        # 이 상한보다 많은 DB 연결을 붙잡지 못하게 한다. 공개 분류는 기존 재시도 가능 `network_error`다.
        if TelegramClient._in_flight >= self._max_concurrent:
            BULKHEAD_REJECTIONS.labels(provider="telegram", scope="interactive").inc()
            raise TelegramError("telegram 동시 호출 상한 — 호출하지 않음", code="network_error")
        TelegramClient._in_flight += 1
        try:
            return await self._send(method, path, token, **kwargs)
        finally:
            TelegramClient._in_flight -= 1

    async def _send(self, method: str, path: str, token: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with asyncio.timeout(self._timeout):
                response = await self._http.request(method, path, timeout=self._timeout, **kwargs)
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise TelegramError("telegram timeout", code="network_error") from exc
        except httpx.TransportError as exc:
            raise TelegramError("telegram connection error", code="network_error") from exc

        if response.status_code != 200:
            raise _classify(response, token=token)
        try:
            body = response.json()
        except ValueError:
            raise TelegramError(
                "Telegram 응답 형식이 올바르지 않습니다.",
                code="unknown_error",
                status_code=response.status_code,
            ) from None
        if not isinstance(body, dict) or body.get("ok") is not True:
            # 200 + ok:false (희귀) — 분류 시도 후 unknown fallback.
            raise _classify(response, token=token)
        result = body.get("result")
        return result if isinstance(result, dict) else {}

    async def verify_target(self, token: str, chat_id: str) -> dict[str, Any]:
        """`getChat`로 chat 존재/타입/봇 접근권을 확인하고 타입·제목 스냅샷을 반환한다."""
        if not chat_id:
            raise TelegramError("chat_id required", code="missing_chat_id")
        result = await self._call("GET", "getChat", token, params={"chat_id": chat_id})
        if result.get("type") not in {"private", "group", "supergroup", "channel"}:
            raise TelegramError(
                "Telegram 대상 확인 응답 형식이 올바르지 않습니다.",
                code="unknown_error",
                status_code=200,
            )
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
        parse_mode: str | None = "MarkdownV2",
    ) -> dict[str, Any]:
        """`sendMessage`로 메시지를 보낸다. 성공 시 Telegram message 객체를 반환한다.

        `parse_mode=None`이면 plain text — MarkdownV2 escape가 필요 없는 시스템 알림에 사용.
        """
        if not chat_id:
            raise TelegramError("chat_id required", code="missing_chat_id")
        payload: dict[str, Any] = {"chat_id": chat_id, "text": message}
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        result = await self._call("POST", "sendMessage", token, json=payload)
        message_id = result.get("message_id")
        if type(message_id) is not int or message_id <= 0:
            raise TelegramError(
                "Telegram 전송 확인 응답 형식이 올바르지 않습니다.",
                code="unknown_error",
                status_code=200,
            )
        return result
