"""`app.core.redaction` 규칙 — stdout 로그 필터와 api_call_log endpoint가 함께 쓴다."""

from __future__ import annotations

import json
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
    assert redact_secrets(f"telegram error token={TG_TOKEN[:3]} raw {TG_TOKEN}") == (
        "telegram error token=*** raw 123456789:***"
    )
    # JSON 문자열 안의 escape를 먹지 않는다(로그 줄이 JSON으로 남아야 한다)
    assert redact_secrets('{"href": "https://w/reset?token=ABC\\"x"}') == (
        '{"href": "https://w/reset?token=***\\"x"}'
    )


def test_redact_secrets_review_620_round3() -> None:
    """재리뷰 #620: 비밀이 아닌 쌍의 값이 뒤의 비밀 쌍을 삼키지 않는다, 따옴표 값, JSON escape 뒤."""

    cases = {
        # 비밀이 아닌 쌍의 값 안에 든 비밀 쌍
        f"redirect_uri=https://pinvi/cb?token={SECRET}": "redirect_uri=https://pinvi/cb?token=***",
        f"?url=https://geo.test/v2?key={SECRET}": "?url=https://geo.test/v2?key=***",
        f"foo=a,key={SECRET}": "foo=a,key=***",
        # 따옴표 없는 값은 공백·구분자까지 가린다 — `)`도 비밀의 일부일 수 있다(재리뷰 #620 M2)
        f"q=f(key={SECRET})": "q=f(key=***",
        # 따옴표 값(repr·kwargs)
        f"GeoConfig(base_url='http://g', api_key='{SECRET}')": (
            "GeoConfig(base_url='http://g', api_key='***')"
        ),
        f'call(serviceKey="{SECRET}")': 'call(serviceKey="***")',
        # 이름 앞 문자가 무엇이든(이름 문자만 아니면)
        f"[key={SECRET} {{token={SECRET} opts:key={SECRET} x|token={SECRET}": (
            "[key=*** {token=*** opts:key=*** x|token=***"
        ),
        # JSON 렌더 뒤: 줄바꿈·탭 escape 다음, escape된 따옴표 값
        f'{{"exc": "bad\\nkey={SECRET}", "kw": "token=\\"{SECRET}\\""}}': (
            '{"exc": "bad\\nkey=***", "kw": "token=\\"***\\""}'
        ),
        # Telegram: 슬래시 없는 bot 접두, 인코딩된 콜론
        f"bot{TG_TOKEN}": "bot123456789:***",
        TG_TOKEN.replace(":", "%3A"): "123456789%3A***",
        # OAuth callback 끝 슬래시
        "/api/v1/auth/oauth/google/callback/?code=S1&state=S2": (
            "/api/v1/auth/oauth/google/callback/?code=***&state=***"
        ),
        # URL userinfo의 password
        f"https://pinvi:{SECRET}@files.test/p": "https://pinvi:***@files.test/p",
    }
    for raw, expected in cases.items():
        assert redact_secrets(raw) == expected, raw
    # 이름 문자 뒤에 붙은 것은 비밀 이름이 아니다
    assert redact_secrets("monkey=1 sig_cd=2 sido_code=3 hotkey=4") == (
        "monkey=1 sig_cd=2 sido_code=3 hotkey=4"
    )


def test_redact_secrets_review_620_round4() -> None:
    """세 번째 리뷰 #620: 완전히 인코딩된 중첩 URL, 따옴표 값의 꼬리, 헤더 꼴, 빈 사용자 userinfo."""

    cases = {
        # 완전히 percent-encoding된 중첩 URL(httpx·urlencode가 쓰는 모양)
        f"?next=https%3A%2F%2Fpinvi%2Fcb%3Ftoken%3D{SECRET}": (
            "?next=https%3A%2F%2Fpinvi%2Fcb%3Ftoken%3D***"
        ),
        f"redirect_uri=https%3A%2F%2Fx%2Fcb%3Fa%3D1%26key%3D{SECRET}": (
            "redirect_uri=https%3A%2F%2Fx%2Fcb%3Fa%3D1%26key%3D***"
        ),
        # 따옴표 값은 닫는 따옴표까지(쉼표·공백·괄호가 들어 있어도 꼬리가 새지 않는다)
        f"password='ab,cd{SECRET}'": "password='***'",
        f'password="ab cd{SECRET}"': 'password="***"',
        f"password=p){SECRET}": "password=***",
        # 헤더 꼴
        f"Authorization: Bearer {SECRET}": "Authorization: Bearer ***",
        f"{{'authorization': 'Basic {SECRET}'}}": "{'authorization': 'Basic ***'}",
        # 빈 사용자 userinfo
        f"redis://:{SECRET}@redis:6379/0": "redis://:***@redis:6379/0",
    }
    for raw, expected in cases.items():
        assert redact_secrets(raw) == expected, raw
    # 비밀 이름이 아닌 것은 그대로(하이픈·점 뒤 이름, uuid, 포트 뒤 query의 이메일)
    untouched = [
        "Idempotency-Key=abc cache-key=x obj.key=z",
        "trip:123456:11111111-1111-4111-8111-111111111111",
        "http://host:8080?email=a@b.com",
    ]
    for raw in untouched:
        assert redact_secrets(raw) == raw, raw


def test_redact_secrets_review_620_round5() -> None:
    """네 번째 리뷰 #620: 빈 값이 JSON을 깨지 않는다, 따옴표 종류별 끝, 다음 비밀 이름 앞에서 멈춤, 이중 인코딩."""

    cases = {
        # 빈 값 뒤 JSON 구조 — 따옴표를 열지 않는다(JSON이 깨지지 않게)
        '{"url": "https://x/?serviceKey=", "event": "e"}': (
            '{"url": "https://x/?serviceKey=", "event": "e"}'
        ),
        '{"detail": "token="}': '{"detail": "token="}',
        # 메시지 안에서 escape된 따옴표로 감싼 Authorization
        f'{{"event": "sent \\"Authorization: Bearer {SECRET}\\" upstream"}}': (
            '{"event": "sent \\"Authorization: Bearer ***\\" upstream"}'
        ),
        # 큰따옴표 값 안의 작은따옴표, 값 안의 escape된 백슬래시
        f"api_key=\"ab'cd{SECRET}\"": 'api_key="***"',
        f"password='ab\\\\cd{SECRET}'": "password='***'",
        # 이중 인코딩된 중첩 URL
        f"?next=https%253A%252F%252Fx%252Fcb%253Ftoken%253D{SECRET}": (
            "?next=https%253A%252F%252Fx%252Fcb%253Ftoken%253D***"
        ),
        # Authorization 변형(PinVi가 직접 보내는 KakaoAK 포함)
        f"Authorization: KakaoAK {SECRET}": "Authorization: KakaoAK ***",
        f"authorization=Bearer%20{SECRET}": "authorization=Bearer%20***",
        # JSON escape 뒤 이름: \uXXXX(비 ASCII), \r
        f'{{"event": "\\u00e9key={SECRET}", "e2": "bad\\rtoken={SECRET}"}}': (
            '{"event": "\\u00e9key=***", "e2": "bad\\rtoken=***"}'
        ),
        # 따옴표 값 안의 \uXXXX
        f"token='\\u00e9{SECRET}'": "token='***'",
    }
    for raw, expected in cases.items():
        assert redact_secrets(raw) == expected, raw
    # 따옴표 없는 값은 다음 비밀 이름 앞에서 멈춘다(그 비밀의 따옴표 값까지 가려진다)
    for raw in (f"key=abc,password='{SECRET}'", f'f(token=abc)(api_key="{SECRET}")'):
        redacted = redact_secrets(raw)
        assert SECRET not in redacted, raw
        assert "='***'" in redacted or '="***"' in redacted, redacted


def test_redacted_json_line_stays_valid_json() -> None:
    """가린 뒤에도 structlog JSON 줄은 JSON이다(escape를 먹지 않는다)."""

    payload = {
        "event": f"token=é{SECRET} key={SECRET}\nnext line",
        "url": f"https://g/?key={SECRET}&q=하회",
        "kw": f'call(api_key="{SECRET}")',
        "empty": "https://x/?serviceKey=",
        "empty2": "token=",
        "auth": f'sent "Authorization: Bearer {SECRET}" upstream',
    }
    for ensure_ascii in (True, False):
        line = json.dumps(payload, ensure_ascii=ensure_ascii)
        redacted = redact_secrets(line)
        assert SECRET not in redacted, line
        json.loads(redacted)


def test_structlog_event_dict_secret_keys_are_masked() -> None:
    """`log.info("x", api_key=…)`처럼 이름=값 꼴이 아닌 event-dict 키도 가린다(JSON에선 `"api_key": "…"`)."""

    from app.core.logging import redact_event_dict

    event = redact_event_dict(
        None, "info", {"event": "x", "api_key": SECRET, "Token": SECRET, "region_key": "11"}
    )
    assert event == {"event": "x", "api_key": "***", "Token": "***", "region_key": "11"}


def test_structlog_event_dict_nested_secret_keys_and_processor_is_installed() -> None:
    import structlog

    from app.core.logging import configure_logging, redact_event_dict

    event = redact_event_dict(
        None, "info", {"event": "x", "params": {"serviceKey": SECRET, "page": 1}}
    )
    assert event == {"event": "x", "params": {"serviceKey": "***", "page": 1}}

    configure_logging("WARNING")
    assert redact_event_dict in structlog.get_config()["processors"]


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
    line = (
        '"GET /api/v1/auth/oauth/google/callback?code=4/0Ab-xyz&state=st_123&scope=email HTTP/1.1"'
    )
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

    record = _record(f"GET %s %s?key={SECRET}", (f"?token={SECRET}",))
    assert SecretRedactingFilter().filter(record) is True
    # handleError가 찍는 `Message: %r`와 `Arguments: %s` 둘 다
    assert SECRET not in str(record.msg)
    assert SECRET not in str(record.args)


def test_filter_never_raises_into_the_caller() -> None:
    class Exploding:
        def __str__(self) -> str:
            raise RuntimeError("boom")

    record = _record(f"value %s ?key={SECRET}", (Exploding(),))
    assert SecretRedactingFilter().filter(record) is True
    message = record.getMessage()
    assert SECRET not in message
    assert "redaction failed" in message


def test_filter_fails_closed_when_exception_text_cannot_be_formatted() -> None:
    record = _record("boom")
    record.exc_info = (ValueError, ValueError(f"?key={SECRET}"), "not-a-traceback")  # type: ignore[assignment]
    assert SecretRedactingFilter().filter(record) is True
    assert record.exc_info is None
    assert SECRET not in str(record.exc_text)


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
    # 가린 URL도 다시 인코딩하지 않는다(stdout과 같은 모양)
    assert sanitize_url(f"http://geo.test/v2/geocode?key={SECRET}&ids=a,b&flag") == (
        "http://geo.test/v2/geocode?key=***&ids=a,b&flag"
    )


def test_sanitize_url_covers_what_parse_qsl_misses() -> None:
    """재리뷰 #620: `;` 구분자, fragment, userinfo password, /bot 밖 Telegram token, 인코딩된 이름."""

    assert SECRET not in sanitize_url(f"http://h/p?a=1;key={SECRET}")
    assert SECRET not in sanitize_url(f"http://h/p#access_token={SECRET}")
    assert sanitize_url(f"http://u:{SECRET}@h/p") == "http://u:***@h/p"
    assert SECRET not in sanitize_url(f"http://h/p?next=/x?token%3D{SECRET}&t={TG_TOKEN}")
    assert TG_TOKEN not in sanitize_url(f"http://h/p?t={TG_TOKEN}")
    assert SECRET not in sanitize_url(f"http://h/p?%6Bey={SECRET}")


def test_sanitize_url_leaves_clean_url_byte_identical() -> None:
    """리뷰 #620: 가릴 것이 없으면 다시 인코딩하지 않는다(MCP 기록의 `,`·공백·`?flag` 보존)."""

    raw = "/mcp/v1/features?ids=a,b&q=하회 마을&flag"
    assert sanitize_url(raw) == raw
