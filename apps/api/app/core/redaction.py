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

# query parameter 이름(소문자 비교). 값은 `***`로 바꾼다.
SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "client_secret",
        "id_token",
        "key",
        "password",
        "refresh_token",
        "secret",
        "service_key",
        "servicekey",
        "token",
    }
)
REDACTED = "***"

_TELEGRAM_BOT_TOKEN_RE = re.compile(r"/bot(\d+):[A-Za-z0-9_-]+")
# path에 실린 PinVi 자체 자격 증명: 여행 공유 링크, 서명된 업로드·다운로드 토큰(uvicorn access 줄).
_PATH_TOKEN_RE = re.compile(
    r"(?P<prefix>/trips/[0-9A-Fa-f-]{36}/shared/|/storage/(?:uploads|downloads)/)"
    r"(?P<token>[^/?\s\"'<>#]+)"
)
# 자유 텍스트 속 URL query의 `이름=값`. 값은 query 구분자·공백·따옴표·꺾쇠에서 끝난다.
_QUERY_SECRET_RE = re.compile(
    r"(?P<prefix>[?&;](?P<name>[A-Za-z_]+)=)(?P<value>[^&;\s\"'<>#]+)",
)


def _replace_query_secret(match: re.Match[str]) -> str:
    if match.group("name").lower() not in SENSITIVE_QUERY_KEYS:
        return match.group(0)
    return f"{match.group('prefix')}{REDACTED}"


def _redact_path_tokens(text: str) -> str:
    text = _TELEGRAM_BOT_TOKEN_RE.sub(rf"/bot\1:{REDACTED}", text)
    return _PATH_TOKEN_RE.sub(rf"\g<prefix>{REDACTED}", text)


def redact_secrets(text: str) -> str:
    """자유 텍스트(로그 줄·예외 메시지)에서 URL query 비밀값과 path 토큰을 가린다."""

    if "=" not in text and "/" not in text:
        return text
    text = _redact_path_tokens(text)
    return _QUERY_SECRET_RE.sub(_replace_query_secret, text)


def sanitize_url(url: object) -> str:
    """URL 하나를 구조적으로 가린다(api_call_log endpoint 기록용)."""

    raw = str(url)
    parts = urlsplit(raw)
    path = _redact_path_tokens(parts.path)
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
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


class SecretRedactingFilter(logging.Filter):
    """LogRecord의 msg·args·예외 문자열에서 비밀값을 가린다.

    args는 모양을 유지한 채 원소만 바꾼다 — uvicorn AccessFormatter처럼 args를 튜플로
    풀어 쓰는 formatter가 있어서다. httpx는 URL을 `httpx.URL` 객체로 넘기므로 문자열이
    아닌 원소도 문자열로 바꿔 검사한다(가릴 것이 있을 때만 교체).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args: Any = record.args
        if isinstance(args, tuple):
            record.args = tuple(_redact_arg(arg) for arg in args)
        elif isinstance(args, Mapping):
            record.args = {key: _redact_arg(value) for key, value in args.items()}
        # 비밀값이 format 문자열 자체(또는 msg 객체)에 있으면 완성된 메시지로 바꿔 끼운다.
        # args 원소만 고친 경우(uvicorn access 줄)는 여기서 바뀌는 것이 없어 모양이 유지된다.
        try:
            message = record.getMessage()
        except Exception:
            # 깨진 format은 handler의 logging 자체 오류 처리(handleError)에 맡긴다.
            message = None
        if message is not None:
            redacted = redact_secrets(message)
            if redacted != message:
                record.msg = redacted
                record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact_secrets(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_secrets(record.stack_info)
        return True
