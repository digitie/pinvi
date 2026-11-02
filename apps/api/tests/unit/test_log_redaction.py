"""`app.core.redaction` 규칙 — stdout 로그 필터와 api_call_log endpoint가 함께 쓴다."""

from __future__ import annotations

import logging

from app.core.redaction import SecretRedactingFilter, redact_secrets, sanitize_url

SECRET = "SECRET-GEO-KEY-1234"
TG_TOKEN = "123456789:AAH" + "x" * 32


def _record(msg: object, args: tuple[object, ...] | None = None) -> logging.LogRecord:
    return logging.LogRecord("app.x", logging.WARNING, __file__, 1, msg, args, None)


def test_redact_secrets_rules() -> None:
    assert redact_secrets("GET /x?key=abc&lon=1") == "GET /x?key=***&lon=1"
    assert redact_secrets("a?apiKey=abc b&ACCESS_TOKEN=xyz") == "a?apiKey=*** b&ACCESS_TOKEN=***"
    assert redact_secrets("/bot123456:AAH-abc_def/getChat") == "/bot123456:***/getChat"
    # 비밀이 아닌 이름은 그대로(접미사 일치 금지: monkey=, sig_cd=, sido_code=)
    assert redact_secrets("?monkey=1&sig_cd=11110&sido_code=11") == (
        "?monkey=1&sig_cd=11110&sido_code=11"
    )
    assert redact_secrets("no secrets here") == "no secrets here"


def test_redact_secrets_review_620_gaps() -> None:
    # 문자열 첫머리·공백·따옴표 뒤의 `key=`(raw query string, form body)
    assert redact_secrets(f"key={SECRET}&a=1") == "key=***&a=1"
    assert redact_secrets(f"body: serviceKey={SECRET}") == "body: serviceKey=***"
    # 하이픈·숫자가 든 이름(서명 URL)
    assert redact_secrets(f"?X-Amz-Signature={SECRET}&X-Amz-Credential=AK/2026") == (
        "?X-Amz-Signature=***&X-Amz-Credential=***"
    )
    # `/bot` 접두가 없는 Telegram bot token
    assert TG_TOKEN not in redact_secrets(f"telegram error token={TG_TOKEN[:3]} raw {TG_TOKEN}")
    # JSON 문자열 안의 escape를 먹지 않는다(로그 줄이 JSON으로 남아야 한다)
    assert redact_secrets('{"href": "https://w/reset?token=ABC\\"x"}') == (
        '{"href": "https://w/reset?token=***\\"x"}'
    )


def test_redact_secrets_path_tokens() -> None:
    trip = "11111111-1111-4111-8111-111111111111"
    assert (
        redact_secrets(f'"GET /api/v1/trips/{trip}/shared/tok_abc HTTP/1.1"')
        == f'"GET /api/v1/trips/{trip}/shared/*** HTTP/1.1"'
    )
    # FastAPI uuid는 32자리 hex도 받는다
    assert redact_secrets(f"/api/v1/trips/{trip.replace('-', '')}/shared/tok_abc") == (
        f"/api/v1/trips/{trip.replace('-', '')}/shared/***"
    )
    assert redact_secrets("PUT /api/v1/storage/uploads/up.tok?x=1") == (
        "PUT /api/v1/storage/uploads/***?x=1"
    )
    # 다른 path의 같은 이름은 건드리지 않는다
    assert redact_secrets("/api/v1/trips/shared/list") == "/api/v1/trips/shared/list"


def test_redact_secrets_oauth_callback_code_and_state() -> None:
    line = '"GET /api/v1/auth/oauth/google/callback?code=4/0Ab-xyz&state=st_123&scope=email HTTP/1.1"'
    assert redact_secrets(line) == (
        '"GET /api/v1/auth/oauth/google/callback?code=***&state=***&scope=email HTTP/1.1"'
    )
    # callback 밖의 code= 는 그대로(지역 코드 등)
    assert redact_secrets("/v1/regions?code=11110") == "/v1/regions?code=11110"


def test_filter_redacts_secret_inside_format_string() -> None:
    record = _record(f"GET %s?key={SECRET}", ("/v2/geocode",))
    assert SecretRedactingFilter().filter(record) is True
    assert record.getMessage() == "GET /v2/geocode?key=***"


def test_filter_redacts_dict_args() -> None:
    record = _record("GET %(url)s", ({"url": f"http://g/?key={SECRET}"},))
    assert SecretRedactingFilter().filter(record) is True
    assert record.getMessage() == "GET http://g/?key=***"


def test_filter_redacts_broken_format_string_too() -> None:
    """getMessage가 깨지면 logging이 raw msg를 stderr로 찍는다 — 그 msg도 가린다."""

    record = _record(f"GET %s %s?key={SECRET}", ("only-one",))
    assert SecretRedactingFilter().filter(record) is True
    assert SECRET not in str(record.msg)


def test_filter_never_raises_into_the_caller() -> None:
    class Exploding:
        def __str__(self) -> str:
            raise RuntimeError("boom")

    record = _record("value %s", (Exploding(),))
    assert SecretRedactingFilter().filter(record) is True
    assert isinstance(record.getMessage(), str)


def test_filter_leaves_clean_record_untouched() -> None:
    args = ("/v2/geocode", 200)
    record = _record("GET %s %d", args)
    assert SecretRedactingFilter().filter(record) is True
    assert record.msg == "GET %s %d"
    assert record.args == args


def test_sanitize_url_masks_query_and_telegram_path() -> None:
    assert (
        sanitize_url(f"https://api.telegram.org/bot42:{SECRET}/sendMessage?chat_id=7")
        == "https://api.telegram.org/bot42:***/sendMessage?chat_id=7"
    )
    masked = sanitize_url(f"http://geo.test/v2/geocode?key={SECRET}&limit=5")
    assert SECRET not in masked
    assert masked.endswith("limit=5")


def test_sanitize_url_leaves_clean_url_byte_identical() -> None:
    """리뷰 #620: 가릴 것이 없으면 다시 인코딩하지 않는다(MCP 기록의 `,`·공백·`?flag` 보존)."""

    raw = "/mcp/v1/features?ids=a,b&q=하회 마을&flag"
    assert sanitize_url(raw) == raw
