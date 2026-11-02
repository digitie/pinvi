"""`app.core.redaction` 규칙 — stdout 로그 필터와 api_call_log endpoint가 함께 쓴다."""

from __future__ import annotations

import logging

from app.core.redaction import SecretRedactingFilter, redact_secrets, sanitize_url

SECRET = "SECRET-GEO-KEY-1234"


def test_redact_secrets_rules() -> None:
    assert redact_secrets("GET /x?key=abc&lon=1") == "GET /x?key=***&lon=1"
    assert redact_secrets("a?apiKey=abc b&ACCESS_TOKEN=xyz") == "a?apiKey=*** b&ACCESS_TOKEN=***"
    assert redact_secrets("/bot123456:AAH-abc_def/getChat") == "/bot123456:***/getChat"
    # 비밀이 아닌 이름은 그대로(접미사 일치 금지: monkey=, sig_cd=)
    assert redact_secrets("?monkey=1&sig_cd=11110") == "?monkey=1&sig_cd=11110"
    assert redact_secrets("no secrets here") == "no secrets here"


def test_redact_secrets_path_tokens() -> None:
    trip = "11111111-1111-4111-8111-111111111111"
    assert (
        redact_secrets(f'"GET /api/v1/trips/{trip}/shared/tok_abc HTTP/1.1"')
        == f'"GET /api/v1/trips/{trip}/shared/*** HTTP/1.1"'
    )
    assert redact_secrets("PUT /api/v1/storage/uploads/up.tok?x=1") == (
        "PUT /api/v1/storage/uploads/***?x=1"
    )
    # 다른 path의 같은 이름은 건드리지 않는다
    assert redact_secrets("/api/v1/trips/shared/list") == "/api/v1/trips/shared/list"


def test_filter_redacts_secret_inside_format_string() -> None:
    record = logging.LogRecord(
        "app.x", logging.WARNING, __file__, 1, f"GET %s?key={SECRET}", ("/v2/geocode",), None
    )
    assert SecretRedactingFilter().filter(record) is True
    assert record.getMessage() == "GET /v2/geocode?key=***"


def test_filter_leaves_clean_record_untouched() -> None:
    args = ("/v2/geocode", 200)
    record = logging.LogRecord("app.x", logging.INFO, __file__, 1, "GET %s %d", args, None)
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
