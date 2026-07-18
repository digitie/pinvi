"""Shared helpers for dev-only admin safety routes."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.core.config import settings


def is_dev_safety_route_enabled() -> bool:
    return settings.pinvi_environment != "production"


def ensure_dev_safety_route_enabled() -> None:
    if not is_dev_safety_route_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Not found."},
        )


def reject_non_dry_run() -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "DRY_RUN_ONLY",
            "message": "현재 seed/reset route는 dry_run만 지원합니다.",
        },
    )


def reject_confirmation() -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "CONFIRMATION_MISMATCH",
            "message": "확인 문구가 일치하지 않습니다.",
        },
    )
