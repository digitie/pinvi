"""User consent / profile complete — `docs/api/auth.md` §4."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ConsentType = Literal[
    "tos",
    "privacy",
    "lbs_tos",
    "location_collection",
    "demographic_use",
    "marketing",
]

REQUIRED_CONSENTS: set[str] = {"tos", "privacy", "lbs_tos", "location_collection"}

# 서버가 인정하는 약관 버전. 클라이언트가 보내는 임의 문자열을 그대로 저장하면 "무엇에 동의했는가"라는
# 법적 증빙이 클라이언트 입력에 달리게 된다(T-327). 프런트의 정본은
# `packages/domain/src/locationConsent.ts`의 `CONSENT_VERSION`이며 이 목록과 같아야 한다.
# 약관을 개정하면 새 버전을 여기 **추가**한다 — 기존 값을 지우면 그 버전으로 동의한 이력이
# 소급해서 무효처럼 보인다.
ACCEPTED_CONSENT_VERSIONS: tuple[str, ...] = ("v1.0",)


class ConsentItem(BaseModel):
    consent_type: ConsentType
    version: str = Field(min_length=1, max_length=32)

    @field_validator("version")
    @classmethod
    def _known_version(cls, value: str) -> str:
        if value not in ACCEPTED_CONSENT_VERSIONS:
            raise ValueError(
                f"알 수 없는 약관 버전입니다: {value}. 허용: {', '.join(ACCEPTED_CONSENT_VERSIONS)}"
            )
        return value


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
            raise ValueError("성별 / 생년월 / 거주지 입력 시 demographic_use 동의가 필요합니다.")
        return self


class ConsentResponse(BaseModel):
    consent_type: ConsentType
    version: str
    agreed_at: datetime
    withdrawn_at: datetime | None


class ConsentWithdrawRequest(BaseModel):
    consent_type: ConsentType
