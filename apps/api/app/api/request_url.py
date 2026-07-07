"""요청 헤더 기준 public URL helper."""

from __future__ import annotations

from fastapi import Request


def _first_forwarded_value(value: str | None) -> str | None:
    if not value:
        return None
    first = value.split(",", 1)[0].strip()
    return first or None


def public_api_base_url(request: Request) -> str:
    """Reverse proxy 뒤에서도 브라우저가 접근한 API origin을 복원한다."""
    scheme = _first_forwarded_value(request.headers.get("x-forwarded-proto"))
    host = _first_forwarded_value(request.headers.get("x-forwarded-host"))

    if scheme in {"http", "https"}:
        if host:
            return f"{scheme}://{host}".rstrip("/")
        return str(request.base_url.replace(scheme=scheme)).rstrip("/")

    return str(request.base_url).rstrip("/")
