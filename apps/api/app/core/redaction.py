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

# 값·토큰이 끝나는 문자: query 구분자, 공백, 따옴표, 꺾쇠, fragment, JSON escape(`\`), 닫는 괄호·쉼표.
_VALUE_END = "&;\\s\"'<>#\\\\,)\\]}"
_TELEGRAM_BOT_PATH_RE = re.compile(r"/bot(\d+):[A-Za-z0-9_-]+")
# `/bot/` 경로 밖에 나타나는 Telegram bot token(`<bot id>:<35자>`, 콜론이 `%3A`로 인코딩된 것 포함).
# `clients/telegram.py`의 `mask_token`과 같은 모양이되 숫자 자리수를 좁혀 시각(`13:26`)과 겹치지 않게 한다.
_TELEGRAM_TOKEN_RE = re.compile(r"(?<!\d)(?P<id>\d{6,12})(?P<sep>:|%3[Aa])[A-Za-z0-9_-]{30,}")
# path에 실린 PinVi 자체 자격 증명: 여행 공유 링크, 서명된 업로드·다운로드 토큰(uvicorn access 줄).
_PATH_TOKEN_RE = re.compile(
    r"(?P<prefix>/trips/[^/?\s\"'<>#\\]+/shared/|/storage/(?:uploads|downloads)/)"
    rf"(?P<token>[^/?{_VALUE_END}]+)"
)
# OAuth callback의 `code`·`state`(callback path에서만 — `code=`는 다른 곳에서 지역 코드 등이다).
_OAUTH_CALLBACK_RE = re.compile(
    rf"(?P<path>/oauth/[^/?{_VALUE_END}]+/callback/?\?)(?P<query>[^\s\"'<>#\\]*)"
)
_OAUTH_PARAM_RE = re.compile(rf"(?P<lead>^|&)(?P<name>code|state)=[^{_VALUE_END}]*")
# URL userinfo의 password(`scheme://user:password@host`).
_USERINFO_RE = re.compile(r"(?P<prefix>://[^/@\s:\"']+):[^/@\s\"']+@")
# 비밀 **이름만** 맞춘다 — 비밀이 아닌 `이름=값`의 값(`redirect_uri=…?token=…`)이 뒤의 비밀 쌍을
# 삼키지 않게. 이름 앞은 이름 문자가 아니어야 한다(`monkey=`·`sig_cd=` 제외). JSON으로 렌더된 줄에서는
# 줄바꿈·탭이 `\n`·`\t`로 남으므로 그 escape 뒤도 이름의 시작으로 본다. 값은 따옴표(escape 포함)로
# 감싸여 있을 수 있고(`api_key='…'`, `token=\"…\"`), `=`가 `%3D`로 인코딩됐을 수 있다.
_SENSITIVE_NAMES = "|".join(
    sorted((re.escape(name) for name in SENSITIVE_QUERY_KEYS), key=len, reverse=True)
)
_QUERY_SECRET_RE = re.compile(
    rf"(?:(?<![A-Za-z0-9_])|(?<=\\[nrt]))(?P<name>{_SENSITIVE_NAMES})"
    rf"(?P<eq>(?:=|%3[Dd])\\?[\"']?)(?P<value>[^{_VALUE_END}]+)",
    re.IGNORECASE,
)


def _replace_query_secret(match: re.Match[str]) -> str:
    return f"{match.group('name')}{match.group('eq')}{REDACTED}"


def _replace_oauth_callback(match: re.Match[str]) -> str:
    query = _OAUTH_PARAM_RE.sub(rf"\g<lead>\g<name>={REDACTED}", match.group("query"))
    return f"{match.group('path')}{query}"


def redact_secrets(text: str) -> str:
    """자유 텍스트(로그 줄·예외 메시지·URL)에서 비밀값을 가린다.

    가리는 것: 비밀 이름의 query·kwargs 값, path 토큰(Telegram `/bot…/`, 공유 링크, 저장소 토큰),
    `/bot/` 밖 Telegram token, OAuth callback의 code·state, URL userinfo password.
    """

    if not any(marker in text for marker in ("=", "/", ":", "%")):
        return text
    text = _TELEGRAM_BOT_PATH_RE.sub(rf"/bot\1:{REDACTED}", text)
    text = _PATH_TOKEN_RE.sub(rf"\g<prefix>{REDACTED}", text)
    text = _TELEGRAM_TOKEN_RE.sub(rf"\g<id>\g<sep>{REDACTED}", text)
    text = _OAUTH_CALLBACK_RE.sub(_replace_oauth_callback, text)
    text = _USERINFO_RE.sub(rf"\g<prefix>:{REDACTED}@", text)
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
