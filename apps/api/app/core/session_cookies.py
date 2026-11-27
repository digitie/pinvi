"""Auth session cookie helpers."""

from __future__ import annotations

from datetime import datetime

from fastapi import Response

from app.core.config import settings
from app.core.time import utc_now


def set_session_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    refresh_expires_at: datetime,
) -> None:
    """두 cookie 설정. refresh cookie Max-Age는 서버 refresh session 만료까지만 둔다.

    로그인 유지 세션은 그 만료가 최대 `pinvi_remember_me_days`(365일), 유지하지 않은 세션은
    `pinvi_refresh_token_days`(7일)다 — cookie가 서버 세션보다 오래 남지 않는다.
    """
    secure = settings.pinvi_environment == "production"
    response.set_cookie(
        key="pinvi_access",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.pinvi_access_token_minutes * 60,
    )
    refresh_max_age = max(0, int((refresh_expires_at - utc_now()).total_seconds()))
    response.set_cookie(
        key="pinvi_refresh",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=refresh_max_age,
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie("pinvi_access")
    response.delete_cookie("pinvi_refresh")
