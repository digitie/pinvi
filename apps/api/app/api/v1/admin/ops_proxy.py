"""kor-travel-map ops/admin proxy helpers for Admin read surfaces."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import HTTPException, status

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapError,
    KorTravelMapRateLimited,
    KorTravelMapUnavailable,
)


@contextmanager
def map_ops_errors(*, message_subject: str = "kor_travel_map ops") -> Iterator[None]:
    try:
        yield
    except KorTravelMapRateLimited as exc:
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds is not None
            else None
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMITED",
                "message": f"{message_subject} 요청이 많아 잠시 후 다시 시도하세요.",
            },
            headers=headers,
        ) from exc
    except KorTravelMapBadRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": exc.code or "VALIDATION_ERROR",
                "message": f"{message_subject} 요청을 kor_travel_map가 거절했습니다.",
            },
        ) from exc
    except KorTravelMapUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "FEATURE_SERVICE_UNAVAILABLE",
                "message": f"{message_subject} 서비스가 일시적으로 사용 불가합니다.",
            },
        ) from exc
    except KorTravelMapError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": f"{message_subject} 응답 형식이 올바르지 않습니다.",
            },
        ) from exc


def next_cursor(meta: dict[str, Any]) -> str | None:
    page = meta.get("page")
    if not isinstance(page, dict):
        return None
    value = page.get("next_cursor")
    return value if isinstance(value, str) and value else None
