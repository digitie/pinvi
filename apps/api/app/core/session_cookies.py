"""Auth session cookie helpers."""

from __future__ import annotations

from fastapi import Response

from app.core.config import settings


def set_session_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
) -> None:
    secure = settings.pinvi_environment == "production"
    response.set_cookie(
        key="pinvi_access",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.pinvi_access_token_minutes * 60,
    )
    response.set_cookie(
        key="pinvi_refresh",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.pinvi_refresh_token_days * 24 * 60 * 60,
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie("pinvi_access")
    response.delete_cookie("pinvi_refresh")
