from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["tripmate-api"] = "tripmate-api"
    version: str | None = None
    git_sha: str | None = None


class HealthDbResponse(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"
    latency_ms: int = 0
