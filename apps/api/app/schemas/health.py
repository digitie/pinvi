from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["pinvi-api"] = "pinvi-api"
    version: str | None = None
    git_sha: str | None = None


class HealthDbResponse(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"
    latency_ms: int = 0


class CacheTargetSyncHealthResponse(BaseModel):
    enabled: bool
    ready: bool
    disabled_reason: str | None
    restore_epoch: int | None
    local_applied_cursor: str | None
    remote_acked_cursor: str | None
    pending_applied_gap: int
    pending_commands: int
    dead_letter_commands: int
    snapshot_id: str | None
    snapshot_count: int | None
    snapshot_merkle_root: str | None
    reconcile_status: str
    last_error: str | None
