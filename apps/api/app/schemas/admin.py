from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.json_types import JsonValue


class AdminLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1)


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    is_admin: bool
    is_privileged: bool


class AdminLoginResponse(BaseModel):
    user: AdminUserResponse


class AdminDatasetColumn(BaseModel):
    name: str
    type: str
    nullable: bool
    searchable: bool
    filterable: bool
    sortable: bool


class AdminDatasetSummary(BaseModel):
    table_name: str
    row_count: int
    columns: list[AdminDatasetColumn]


class AdminDatasetListResponse(BaseModel):
    datasets: list[AdminDatasetSummary]
    page_size_options: list[int]
    default_page_size: int


class AdminDatasetRowsResponse(BaseModel):
    table_name: str
    page: int
    limit: int
    total: int
    columns: list[AdminDatasetColumn]
    rows: list[dict[str, JsonValue]]


class AdminManagedUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    nickname: str | None
    name: str | None
    account_status: str
    system_role: str
    birth_year_month: str | None
    gender: str | None
    residence_sigungu_code: str | None
    email_verified_at: datetime | None
    is_active: bool
    is_admin: bool
    is_privileged: bool
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    users: list[AdminManagedUserResponse]
    page: int
    limit: int
    total: int


class AdminUpdateUserRequest(BaseModel):
    account_status: str | None = Field(
        default=None,
        pattern=r"^(pending_email_verification|invited|active|disabled|deleted)$",
    )
    system_role: str | None = Field(default=None, pattern=r"^(admin|planner|participant)$")
    nickname: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    email_verified: bool | None = None
