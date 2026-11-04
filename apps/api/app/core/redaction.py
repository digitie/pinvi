"""URL·로그의 비밀값 가리기 — 외부 API key·토큰이 로그나 api_call_log에 남지 않게.

2026-11-02 prod 점검: httpx의 INFO 줄(`HTTP Request: POST http://…/v2/geocode?key=…`)이 컨테이너
stdout에 kor-travel-geo 공개 API key를 그대로 찍었다. `api_call_log` 테이블은 이미 가리고
있었지만 stdout 로그는 아니었다. 이 모듈이 두 경로가 함께 쓰는 단일 규칙이다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# query parameter 이름(소문자 비교, 정확히 일치). 값은 `***`로 바꾼다.
SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "appkey",
        "authkey",
        "client_secret",
        "confmkey",
        "crtfc_key",
        "id_token",
        "key",
        "password",
        "refresh_token",
        "secret",
        "service_key",
        "servicekey",
        "sig",
        "signature",
        "token",
        "x-amz-credential",
        "x-amz-security-token",
        "x-amz-signature",
        "x-api-key",
    }
)
REDACTED = "***"

# 따옴표 없는 값·토큰이 끝나는 문자: query 구분자, 공백, 따옴표, 꺾쇠, fragment, JSON escape(`\`).
# 닫는 괄호·쉼표는 넣지 않는다 — 비밀값의 일부일 수 있어 꼬리가 샌다(괄호를 하나 더 가리는 편이 낫다).
_VALUE_END = "&;\\s\"'<>#\\\\"
_TELEGRAM_BOT_PATH_RE = re.compile(r"/bot(\d+):[A-Za-z0-9_-]+")
# `/bot/` 경로 밖에 나타나는 Telegram bot token(`<bot id>:<35자>`, 콜론이 `%3A`로 인코딩된 것 포함).
# `clients/telegram.py`의 `mask_token`과 같은 모양이되 숫자 자리수를 좁혀 시각(`13:26`)과 겹치지 않게 하고,
# 대문자가 하나는 있어야 한다(소문자 hex인 uuid·해시 `trip:123456:<uuid>`를 건드리지 않게).
_TELEGRAM_TOKEN_RE = re.compile(
    r"(?<!\d)(?P<id>\d{6,12})(?P<sep>:|%3[Aa])(?=[A-Za-z0-9_-]*[A-Z])[A-Za-z0-9_-]{30,}"
)
# `Authorization: Bearer …`·`{'authorization': 'Basic …'}` 꼴 자격 증명.
#: 스킴은 선택(`Bearer`·`Basic`·`Token`·PinVi가 보내는 `KakaoAK`), 구분은 공백·`%20`·`+`. 따옴표가 escape돼
#: 있어도(JSON 안) 잡고, 값은 escape(`\`) 앞에서 끝나 JSON을 깨지 않는다.
#: 값이 JSON 비문자열(`null`·`true`·숫자·`{`·`[`)이면 건드리지 않는다 — `"authorization": null`을
#: 가리면 JSON 줄이 깨진다.
_AUTH_HEADER_RE = re.compile(
    r"(?P<prefix>authorization\\?[\"']?\s*[:=]\s*\\?[\"']?"
    r"(?:(?:bearer|basic|token|kakaoak)(?:\s+|%20|\+))?)"
    r"(?![{\[]|(?:null|true|false|-?\d[\d.eE+-]*)(?:[\s,}\]]|$))"
    r"[^\s\"',\\]+",
    re.IGNORECASE,
)
# path에 실린 PinVi 자체 자격 증명: 여행 공유 링크, 서명된 업로드·다운로드 토큰(uvicorn access 줄).
# `/`가 `%2F`(이중 `%252F`)로 인코딩된 꼴(`/login?next=%2Fshared%2F…`)도 잡는다(#671). 인코딩된 꼴에서는
# 토큰 뒤 하위 경로(`%2Fcomments`)까지 함께 가려진다 — 덜 가리는 것보다 낫다.
_SLASH = "(?:/|%2[Ff]|%252[Ff])"
_PATH_TOKEN_RE = re.compile(
    rf"(?P<prefix>{_SLASH}trips{_SLASH}[^/?%\s\"'<>#\\]+{_SLASH}shared{_SLASH}"
    rf"|{_SLASH}storage{_SLASH}(?:uploads|downloads){_SLASH})"
    rf"(?P<token>[^/?{_VALUE_END}]+)"
)
# 웹 공유 화면 `/shared/{tripId}/{token}` — 접근 로그·`next=`·OAuth `return_to`에 실린다(#671).
# API 꼴 `/trips/{id}/shared/{token}/…`은 위 규칙이 먼저 `***`로 바꾸므로 id 자리가 `***`이면 건너뛴다.
_WEB_SHARED_RE = re.compile(
    rf"(?P<prefix>{_SLASH}shared{_SLASH}(?!\*\*\*)[^/?%{_VALUE_END}]+{_SLASH})"
    rf"(?P<token>[^/?%{_VALUE_END}]+)"
)
# OAuth callback의 `code`·`state`(callback path에서만 — `code=`는 다른 곳에서 지역 코드 등이다).
_OAUTH_CALLBACK_RE = re.compile(
    rf"(?P<path>/oauth/[^/?{_VALUE_END}]+/callback/?\?)(?P<query>[^\s\"'<>#\\]*)"
)
_OAUTH_PARAM_RE = re.compile(rf"(?P<lead>^|&)(?P<name>code|state)=[^{_VALUE_END}]*")
# URL userinfo의 password(`scheme://user:password@host`, 빈 사용자 `redis://:pw@` 포함). password에 `?`·`#`이
# 있으면 query·fragment로 본다(`http://host:8080?email=a@b.com`을 건드리지 않게).
_USERINFO_RE = re.compile(r"(?P<prefix>://[^/@\s:\"']*):[^/@\s\"'?#]+@")
# 비밀 **이름만** 맞춘다 — 비밀이 아닌 `이름=값`의 값(`redirect_uri=…?token=…`)이 뒤의 비밀 쌍을
# 삼키지 않게. 이름 앞: 이름 문자·점·하이픈이 아니거나(`monkey=`·`obj.key=`·`Idempotency-Key=` 제외),
# JSON escape(`\n`·`\t`·`\r`·`\uXXXX`) 뒤이거나, percent-encoding(`%3F`·`%26`, 이중 `%253F`) 뒤다.
# `=`는 `%3D`·`%253D`로 인코딩됐을 수 있다. 값:
# - 작은따옴표로 열었으면 작은따옴표까지(값 안의 `\"`·`\\`·`\uXXXX` 허용, 날 큰따옴표에서는 멈춘다 — JSON 보호).
# - 큰따옴표로 열었으면(`\"` 또는, 바로 뒤가 JSON 구조 `,:}]`가 아닌 날 `"`) 큰따옴표까지. 빈 값 뒤의
#   JSON 구조(`"serviceKey=", "x"`)에서 따옴표를 열면 JSON이 깨진다.
# - 따옴표가 없으면 `_VALUE_END` 또는 다음 비밀 이름 앞까지(`key=abc,password='…'`의 뒤 비밀을 삼키지 않게).
_SENSITIVE_NAMES = "|".join(
    sorted((re.escape(name) for name in SENSITIVE_QUERY_KEYS), key=len, reverse=True)
)
_QUERY_SECRET_RE = re.compile(
    r"(?:(?<![A-Za-z0-9_.-])|(?<=\\[nrt])|(?<=%[0-9A-Fa-f]{2})|(?<=%25[0-9A-Fa-f]{2})"
    r"|(?<=\\u[0-9A-Fa-f]{4}))"
    rf"(?P<name>{_SENSITIVE_NAMES})(?P<eq>=|%3[Dd]|%253[Dd])"
    r"(?:(?P<q>\\?')(?:\\u[0-9A-Fa-f]{4}|\\\\|\\\"|[^'\"\\\n])+"
    r"|(?P<q2>\\\"|\"(?![,:}\]]))(?:\\u[0-9A-Fa-f]{4}|\\\\|[^\"\\\n])+"
    rf"|(?:(?!(?<![A-Za-z0-9_.-])(?:{_SENSITIVE_NAMES})(?:=|%3[Dd]))"
    rf"(?:\\u[0-9A-Fa-f]{{4}}|\\\\|[^{_VALUE_END}]))+)",
    re.IGNORECASE,
)


def _replace_query_secret(match: re.Match[str]) -> str:
    quote = match.group("q") or match.group("q2") or ""
    return f"{match.group('name')}{match.group('eq')}{quote}{REDACTED}"


def _replace_oauth_callback(match: re.Match[str]) -> str:
    query = _OAUTH_PARAM_RE.sub(rf"\g<lead>\g<name>={REDACTED}", match.group("query"))
    return f"{match.group('path')}{query}"


def redact_secrets(text: str) -> str:
    """자유 텍스트(로그 줄·예외 메시지·URL)에서 비밀값을 가린다.

    가리는 것: 비밀 이름의 query·kwargs 값, path 토큰(Telegram `/bot…/`, 공유 링크 API·웹 화면, 저장소 토큰),
    `/bot/` 밖 Telegram token, OAuth callback의 code·state, URL userinfo password,
    `Authorization: Bearer|Basic|Token …`.

    못 가리는 꼴(남는 한계): `이름: 값`·`이름 = 값`처럼 `=`가 바로 붙지 않은 것(dict repr `{'password': …}`,
    SQLAlchemy 오류의 parameters, 헤더 `x-api-key: …`), 접미사가 붙은 이름(`db_password=`, `bot_token=`).
    structlog event-dict의 비밀 이름 키는 `app.core.logging.redact_event_dict`가 따로 가린다.
    """

    if not any(marker in text for marker in ("=", "/", ":", "%")):
        return text
    text = _TELEGRAM_BOT_PATH_RE.sub(rf"/bot\1:{REDACTED}", text)
    text = _PATH_TOKEN_RE.sub(rf"\g<prefix>{REDACTED}", text)
    text = _WEB_SHARED_RE.sub(rf"\g<prefix>{REDACTED}", text)
    text = _TELEGRAM_TOKEN_RE.sub(rf"\g<id>\g<sep>{REDACTED}", text)
    text = _OAUTH_CALLBACK_RE.sub(_replace_oauth_callback, text)
    text = _USERINFO_RE.sub(rf"\g<prefix>:{REDACTED}@", text)
    text = _AUTH_HEADER_RE.sub(rf"\g<prefix>{REDACTED}", text)
    return _QUERY_SECRET_RE.sub(_replace_query_secret, text)


def sanitize_url(url: object) -> str:
    """URL 하나를 가린다(api_call_log endpoint 기록용) — stdout 로그와 같은 규칙, 같은 모양.

    문자열 규칙(`redact_secrets`)으로 가리고 나머지 인코딩은 그대로 둔다. 문자열 규칙이 못 보는
    인코딩된 이름(`%6Bey=…`)이 남아 있을 때만 query를 구조적으로 다시 쓴다.
    """

    text = redact_secrets(str(url))
    parts = urlsplit(text)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if not any(key.lower() in SENSITIVE_QUERY_KEYS and value != REDACTED for key, value in pairs):
        return text
    query = urlencode(
        [(key, REDACTED if key.lower() in SENSITIVE_QUERY_KEYS else value) for key, value in pairs],
        doseq=True,
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _redact_arg(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    redacted = redact_secrets(text)
    return redacted if redacted != text else value


_UNREDACTABLE = "[log message dropped: secret redaction failed]"


class SecretRedactingFilter(logging.Filter):
    """LogRecord의 msg·args·예외 문자열에서 비밀값을 가린다.

    args는 모양을 유지한 채 원소만 바꾼다 — uvicorn AccessFormatter처럼 args를 튜플로
    풀어 쓰는 formatter가 있어서다. httpx는 URL을 `httpx.URL` 객체로 넘기므로 문자열이
    아닌 원소도 문자열로 바꿔 검사한다(가릴 것이 있을 때만 교체).

    filter는 logging이 예외를 잡아 주지 않는 자리다(`Filterer.filter`) — 여기서 난 예외는
    로그를 남긴 앱 코드로 샌다. 그래서 실패하면 **fail-closed**로 통과시킨다:
    - 메시지 단계 실패: msg를 고정 문구로, args를 None으로. uvicorn access 레코드라면
      AccessFormatter가 튜플을 풀지 못해 그 한 줄은 logging 오류로 바뀐다(비밀은 새지 않는다).
    - 예외 단계 실패: exc_info를 지우고 exc_text를 고정 문구로. 로거 단위 filter라면 뒤의 모든
      handler가 traceback 없이 받는다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            self._redact_message(record)
        except Exception:
            record.msg = _UNREDACTABLE
            record.args = None
        try:
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = redact_secrets(record.exc_text)
            if record.stack_info:
                record.stack_info = redact_secrets(record.stack_info)
        except Exception:
            record.exc_info = None
            record.exc_text = _UNREDACTABLE
            record.stack_info = None
        return True

    @staticmethod
    def _redact_message(record: logging.LogRecord) -> None:
        args: Any = record.args
        if isinstance(args, tuple):
            record.args = tuple(_redact_arg(arg) for arg in args)
        elif isinstance(args, Mapping):
            record.args = {key: _redact_arg(value) for key, value in args.items()}
        # 비밀값이 format 문자열 자체(또는 msg 객체)에 있으면 완성된 메시지로 바꿔 끼운다.
        # args 원소만 고친 경우(uvicorn access 줄)는 여기서 바뀌는 것이 없어 모양이 유지된다.
        try:
            message = record.getMessage()
        except (TypeError, ValueError, KeyError):
            # 깨진 format — logging은 handleError에서 raw msg를 stderr로 찍으므로 그것도 가린다.
            raw = str(record.msg)
            redacted_raw = redact_secrets(raw)
            if redacted_raw != raw:
                record.msg = redacted_raw
            return
        redacted = redact_secrets(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
