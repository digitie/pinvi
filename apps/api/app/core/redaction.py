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

# 값·토큰이 끝나는 문자: query 구분자, 공백, 따옴표, 꺾쇠, fragment, 그리고 JSON escape(`\`).
_VALUE_END = "&;\\s\"'<>#\\\\"
_TELEGRAM_BOT_PATH_RE = re.compile(r"/bot(\d+):[A-Za-z0-9_-]+")
# `/bot` 접두 없이 나타나는 Telegram bot token(`<bot id>:<35자>`). `clients/telegram.py`의
# `mask_token`과 같은 모양이되 숫자 자리수를 좁혀 시각(`13:26`) 같은 것과 겹치지 않게 한다.
_TELEGRAM_TOKEN_RE = re.compile(r"\b(\d{6,12}):[A-Za-z0-9_-]{30,}")
# path에 실린 PinVi 자체 자격 증명: 여행 공유 링크, 서명된 업로드·다운로드 토큰(uvicorn access 줄).
_PATH_TOKEN_RE = re.compile(
    r"(?P<prefix>/trips/[^/?\s\"'<>#\\]+/shared/|/storage/(?:uploads|downloads)/)"
    rf"(?P<token>[^/?{_VALUE_END}]+)"
)
# OAuth callback의 `code`·`state`(callback path에서만 — `code=`는 다른 곳에서 지역 코드 등이다).
_OAUTH_CALLBACK_RE = re.compile(rf"(?P<path>/oauth/[^/?{_VALUE_END}]+/callback\?)(?P<query>[^\s\"'<>#\\]*)")
_OAUTH_PARAM_RE = re.compile(rf"(?P<lead>^|&)(?P<name>code|state)=[^{_VALUE_END}]*")
# 자유 텍스트 속 `이름=값`. 이름 앞은 문자열 처음·query 구분자·공백·따옴표·괄호·쉼표.
_QUERY_SECRET_RE = re.compile(
    rf"(?P<lead>^|[?&;\s\"'(,])(?P<name>[A-Za-z0-9_-]+)=(?P<value>[^{_VALUE_END}]+)",
)


def _replace_query_secret(match: re.Match[str]) -> str:
    if match.group("name").lower() not in SENSITIVE_QUERY_KEYS:
        return match.group(0)
    return f"{match.group('lead')}{match.group('name')}={REDACTED}"


def _replace_oauth_callback(match: re.Match[str]) -> str:
    query = _OAUTH_PARAM_RE.sub(rf"\g<lead>\g<name>={REDACTED}", match.group("query"))
    return f"{match.group('path')}{query}"


def _redact_path_tokens(text: str) -> str:
    text = _TELEGRAM_BOT_PATH_RE.sub(rf"/bot\1:{REDACTED}", text)
    return _PATH_TOKEN_RE.sub(rf"\g<prefix>{REDACTED}", text)


def redact_secrets(text: str) -> str:
    """자유 텍스트(로그 줄·예외 메시지)에서 query 비밀값, path 토큰, Telegram token을 가린다."""

    if "=" not in text and "/" not in text and ":" not in text:
        return text
    text = _redact_path_tokens(text)
    text = _TELEGRAM_TOKEN_RE.sub(rf"\1:{REDACTED}", text)
    text = _OAUTH_CALLBACK_RE.sub(_replace_oauth_callback, text)
    return _QUERY_SECRET_RE.sub(_replace_query_secret, text)


def sanitize_url(url: object) -> str:
    """URL 하나를 구조적으로 가린다(api_call_log endpoint 기록용).

    가릴 것이 없으면 입력을 그대로 돌려준다 — 다시 인코딩하면 `,`·공백·값 없는 `?flag`가 바뀐다.
    """

    raw = str(url)
    parts = urlsplit(raw)
    path = _redact_path_tokens(parts.path)
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    if path == parts.path and not any(
        key.lower() in SENSITIVE_QUERY_KEYS for key, _value in query_pairs
    ):
        return raw
    query = urlencode(
        [
            (key, REDACTED if key.lower() in SENSITIVE_QUERY_KEYS else value)
            for key, value in query_pairs
        ],
        doseq=True,
    )
    return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


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
    로그를 남긴 앱 코드로 샌다. 그래서 실패하면 메시지를 고정 문구로 바꾸고 통과시킨다.
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
