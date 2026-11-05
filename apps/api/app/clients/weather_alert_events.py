"""병합된 Weather201 공개 발표 관측 DTO. provider 원천을 해석하지 않는다."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, StrictBool


class ScopedAlertEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    announcement_id: str = Field(min_length=1, max_length=128)
    area_code: str = Field(min_length=1, max_length=64)
    area_name: str = Field(max_length=200)
    warning_name: str | None
    stress_name: str | None
    action: Literal[
        "issued",
        "released",
        "extended",
        "corrected",
        "changed_issue",
        "changed_release",
        "cancelled",
        "unknown",
    ]
    issued_at: AwareDatetime | None
    starts_at: AwareDatetime | None
    ends_at: AwareDatetime | None
    all_ends_at: AwareDatetime | None
    occurrence_id: None = None
    correlation_status: Literal["unresolved"]
    first_seen_at: AwareDatetime
    scope_status: Literal["verified"]
    bjd_prefixes: list[str] = Field(max_length=1000)


class RegionalAlertEvents(BaseModel):
    namespace: Literal["kr_bjd"]
    bjd_code: str
    region_status: Literal["known", "unknown"]
    mapping_version: str
    mapping_valid_from: AwareDatetime
    mapping_coverage: Literal["partial"]
    unverified_scope_count: int = Field(ge=0, strict=True)
    collection_status: str
    last_attempt_at: AwareDatetime | None
    last_success_at: AwareDatetime | None
    last_error_code: str | None
    fresh: StrictBool
    events_complete: StrictBool
    retained_since: AwareDatetime
    history_available_since: AwareDatetime | None
    queried_since: AwareDatetime
    absence_is_clear: StrictBool
    events: list[ScopedAlertEvent] = Field(max_length=5000)
