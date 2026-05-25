"""User consent / profile complete — `docs/api/auth.md` §4."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ConsentType = Literal[
    "tos",
    "privacy",
    "lbs_tos",
    "location_collection",
    "demographic_use",
    "marketing",
]

REQUIRED_CONSENTS: set[str] = {"tos", "privacy", "lbs_tos", "location_collection"}


class ConsentItem(BaseModel):
    consent_type: ConsentType
    version: str = Field(min_length=1, max_length=32)


class ProfileCompleteRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=80)
    avatar_kind: Literal["default", "upload"] = "default"
    avatar_attachment_id: str | None = None
    gender: Literal["female", "male", "non_binary", "no_answer"] | None = None
    birth_year_month: str | None = Field(default=None, pattern=r"^\d{6}$")
    residence_sigungu_code: str | None = Field(default=None, pattern=r"^\d{5}$")
    consents: list[ConsentItem]

    @model_validator(mode="after")
    def _check_required(self) -> ProfileCompleteRequest:
        provided = {item.consent_type for item in self.consents}
        missing = REQUIRED_CONSENTS - provided
        if missing:
            raise ValueError(f"필수 동의 누락: {sorted(missing)}")

        demographic = "demographic_use" in provided
        if not demographic and (
            self.gender is not None
            or self.birth_year_month is not None
            or self.residence_sigungu_code is not None
        ):
            raise ValueError(
                "성별 / 생년월 / 거주지 입력 시 demographic_use 동의가 필요합니다."
            )
        return self


class ConsentResponse(BaseModel):
    consent_type: ConsentType
    version: str
    agreed_at: datetime
    withdrawn_at: datetime | None


class ConsentWithdrawRequest(BaseModel):
    consent_type: ConsentType
