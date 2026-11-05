"""Telegram Bot API client 계약 테스트 (httpx.MockTransport) — T-106."""

from __future__ import annotations

import json as _json
from collections.abc import Callable

import httpx
import pytest

from app.clients.telegram import TelegramClient, TelegramError, mask_token

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> TelegramClient:
    http = httpx.AsyncClient(
        base_url="https://api.telegram.test",
        transport=httpx.MockTransport(handler),
    )
    return TelegramClient(http, timeout_seconds=1.0)


# --- mask_token -------------------------------------------------------------


def test_mask_token_hides_secret_but_keeps_id() -> None:
    raw = "bot 123456789:AAEjQ_l0Nq7Rabcdefghijklmnopqrstuvwx failed"
    masked = mask_token(raw)
    assert "AAEjQ_l0Nq7Rabcdefghijklmnopqrstuvwx" not in masked
    assert "123456789:***" in masked


def test_mask_token_leaves_plain_text() -> None:
    assert mask_token("chat not found") == "chat not found"


# --- verify_target ----------------------------------------------------------


async def test_verify_target_returns_type_and_title() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["chat_id"] = request.url.params.get("chat_id")
        return httpx.Response(
            200, json={"ok": True, "result": {"type": "group", "title": "가족 단톡"}}
        )

    client = _client(handler)
    result = await client.verify_target("111:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "-100123")
    assert seen["path"] == "/bot111:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/getChat"
    assert seen["chat_id"] == "-100123"
    assert result == {"telegram_chat_type": "group", "title_snapshot": "가족 단톡"}


async def test_verify_target_private_uses_first_name() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"ok": True, "result": {"type": "private", "first_name": "지훈"}}
        )

    result = await _client(handler).verify_target("1:tok", "42")
    assert result == {"telegram_chat_type": "private", "title_snapshot": "지훈"}


async def test_verify_target_missing_chat_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - 호출 안 됨
        return httpx.Response(200, json={"ok": True, "result": {}})

    with pytest.raises(TelegramError) as exc:
        await _client(handler).verify_target("1:tok", "")
    assert exc.value.code == "missing_chat_id"


# --- send_to_target ---------------------------------------------------------


async def test_send_to_target_posts_payload() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    client = _client(handler)
    result = await client.send_to_target(
        "9:tok", "555", "안녕", thread_id="3", parse_mode="MarkdownV2"
    )
    assert seen["path"] == "/bot9:tok/sendMessage"
    assert seen["body"] == {
        "chat_id": "555",
        "text": "안녕",
        "parse_mode": "MarkdownV2",
        "message_thread_id": "3",
    }
    assert result == {"message_id": 7}


async def test_send_plain_text_omits_parse_mode() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 2}})

    await _client(handler).send_to_target("9:tok", "555", "plain", parse_mode=None)
    assert "parse_mode" not in seen["body"]


async def test_send_omits_thread_id_when_none() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    await _client(handler).send_to_target("9:tok", "555", "hi")
    assert "message_thread_id" not in seen["body"]


# --- failure classification (§5) -------------------------------------------


@pytest.mark.parametrize(
    ("status", "body", "expected_code"),
    [
        (
            403,
            {"ok": False, "description": "Forbidden: bot was blocked by the user"},
            "bot_forbidden",
        ),
        (400, {"ok": False, "description": "Bad Request: chat not found"}, "invalid_chat"),
        (
            400,
            {"ok": False, "description": "Bad Request: message thread not found"},
            "invalid_topic",
        ),
        (500, {"ok": False, "description": "Internal Server Error"}, "network_error"),
        (418, {"ok": False, "description": "teapot"}, "unknown_error"),
    ],
)
async def test_send_classifies_http_errors(
    status: int, body: dict[str, object], expected_code: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    with pytest.raises(TelegramError) as exc:
        await _client(handler).send_to_target("1:tok", "5", "x")
    assert exc.value.code == expected_code
    assert exc.value.status_code == status


async def test_rate_limited_extracts_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "ok": False,
                "description": "Too Many Requests",
                "parameters": {"retry_after": 12},
            },
        )

    with pytest.raises(TelegramError) as exc:
        await _client(handler).send_to_target("1:tok", "5", "x")
    assert exc.value.code == "rate_limited"
    assert exc.value.retry_after == 12


async def test_timeout_is_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom", request=request)

    with pytest.raises(TelegramError) as exc:
        await _client(handler).verify_target("1:tok", "5")
    assert exc.value.code == "network_error"


async def test_classify_does_not_leak_token_in_message() -> None:
    leaky = "Unauthorized for 123456789:AAEjQ_l0Nq7Rabcdefghijklmnopqrstuvwx token"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"ok": False, "description": leaky})

    with pytest.raises(TelegramError) as exc:
        await _client(handler).send_to_target("1:tok", "5", "x")
    assert "AAEjQ_l0Nq7Rabcdefghijklmnopqrstuvwx" not in str(exc.value)


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "12"])
async def test_retry_after_requires_positive_integer_seconds(value: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "ok": False,
                "description": "Too Many Requests",
                "parameters": {"retry_after": value},
            },
        )

    with pytest.raises(TelegramError) as raised:
        await _client(handler).send_to_target("1:tok", "5", "x")
    assert raised.value.retry_after is None


async def test_zero_retry_after_header_is_not_an_immediate_retry() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"ok": False}, headers={"Retry-After": "0"})

    with pytest.raises(TelegramError) as raised:
        await _client(handler).send_to_target("1:tok", "5", "x")
    assert raised.value.retry_after is None


async def test_success_with_invalid_json_has_a_safe_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>unexpected proxy response</html>")

    with pytest.raises(TelegramError) as raised:
        await _client(handler).send_to_target("1:tok", "5", "x")
    assert raised.value.code == "unknown_error"
    assert "proxy response" not in str(raised.value)


async def test_missing_chat_type_does_not_verify_an_invalid_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {}})

    with pytest.raises(TelegramError) as raised:
        await _client(handler).verify_target("1:tok", "5")
    assert raised.value.code == "unknown_error"


async def test_provider_error_never_echoes_the_configured_token() -> None:
    token = "1:short-fixture-token"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": f"invalid credential {token}"})

    with pytest.raises(TelegramError) as raised:
        await _client(handler).send_to_target(token, "5", "x")
    assert token not in str(raised.value)


@pytest.mark.parametrize(
    "body",
    [
        {"ok": 1, "result": {"message_id": 1}},
        {"ok": "true", "result": {"message_id": 1}},
        {"ok": True},
        {"ok": True, "result": {}},
        {"ok": True, "result": {"message_id": False}},
        {"ok": True, "result": {"message_id": 0}},
    ],
)
async def test_send_requires_positive_message_ack(body: dict[str, object]) -> None:
    with pytest.raises(TelegramError) as error:
        await _client(lambda request: httpx.Response(200, json=body)).send_to_target(
            "1:token", "42", "일정"
        )
    assert error.value.code == "unknown_error"


async def test_wall_clock_timeout_includes_response_hook() -> None:
    import asyncio

    async def hook(response: httpx.Response) -> None:
        await asyncio.sleep(0.05)

    http = httpx.AsyncClient(
        base_url="https://telegram.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        ),
        event_hooks={"response": [hook]},
    )
    async with http:
        with pytest.raises(TelegramError) as error:
            await TelegramClient(http, timeout_seconds=0.01).send_to_target("1:token", "42", "일정")
    assert error.value.code == "network_error"
