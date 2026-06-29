"""Resend REST client with `api_call_log` provider tracking."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from app.core.config import settings
from app.db import session as db_session
from app.middleware.api_call_logging import api_call_event_hooks


class ResendClient:
    """Small async wrapper over Resend REST endpoints Pinvi uses."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def send_email(self, payload: dict[str, Any]) -> str | None:
        response = await self._http.post("/emails", json=payload)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            return None
        resend_id = body.get("id")
        return str(resend_id) if resend_id is not None else None

    async def list_domains(self) -> list[dict[str, Any]]:
        response = await self._http.get("/domains")
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict):
            data = body.get("data", [])
        else:
            data = body
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]


@asynccontextmanager
async def create_resend_client(
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncIterator[ResendClient]:
    headers = {"Authorization": f"Bearer {settings.pinvi_resend_api_key}"}
    async with httpx.AsyncClient(
        base_url=settings.pinvi_resend_api_base_url,
        headers=headers,
        timeout=settings.pinvi_resend_timeout_seconds,
        transport=transport,
        event_hooks=api_call_event_hooks(db_session.async_session_factory, provider="resend"),
    ) as http:
        yield ResendClient(http)
