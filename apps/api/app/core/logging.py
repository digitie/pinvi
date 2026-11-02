"""structlog 설정 — JSON 출력 + KST timestamp.

`docs/integrations/loki.md` §3.

외부 호출 URL의 비밀값(kor-travel-geo `?key=`, Telegram `/bot<token>/` 등)이 stdout 로그에
남지 않게 한다(2026-11-02 prod 점검에서 httpx INFO 줄이 geo key를 찍은 것을 확인):

- httpx·httpcore 로거는 WARNING부터만 낸다(요청마다 URL을 찍는 INFO·DEBUG 줄 차단).
- 방어선 2: root·uvicorn handler와 httpx·uvicorn 로거에 `SecretRedactingFilter`를 단다.
- structlog 예외 렌더러는 프레임 지역 변수를 찍지 않는다(`show_locals=False`).
"""

from __future__ import annotations

import logging
import sys
from typing import cast

import structlog
from structlog.tracebacks import ExceptionDictTransformer

from app.core.redaction import SecretRedactingFilter

# 요청마다 전체 URL을 INFO/DEBUG로 찍는 HTTP client 로거.
_QUIET_HTTP_LOGGERS = ("httpx", "httpcore")
# 레코드를 직접 내는 로거(로거 단위 filter는 자식 로거에서 전파된 레코드에는 걸리지 않는다).
_FILTERED_LOGGERS = ("httpx", "httpcore", "uvicorn", "uvicorn.access", "uvicorn.error")


def _attach_redaction(target: logging.Logger | logging.Handler) -> None:
    if not any(isinstance(existing, SecretRedactingFilter) for existing in target.filters):
        target.addFilter(SecretRedactingFilter())


def install_secret_redaction() -> None:
    """root·uvicorn의 현재 handler와 직접 내는 로거에 비밀값 필터를 단다(멱등)."""

    for handler in logging.getLogger().handlers:
        _attach_redaction(handler)
    for name in _FILTERED_LOGGERS:
        named = logging.getLogger(name)
        _attach_redaction(named)
        for handler in named.handlers:
            _attach_redaction(handler)


def configure_logging(level: str = "INFO") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            # `dict_tracebacks`와 같되 프레임 지역 변수는 찍지 않는다 — 지역 변수 repr
            # (`"api_key": "'…'"`, DB 접속 인자의 password)는 URL 모양이 아니라 필터가 못 가린다.
            structlog.processors.ExceptionRenderer(ExceptionDictTransformer(show_locals=False)),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stdout,
    )
    for name in _QUIET_HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    install_secret_redaction()


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
