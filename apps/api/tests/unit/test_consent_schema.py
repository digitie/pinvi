"""Profile complete + consent schema 검증."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.consent import ConsentItem, ProfileCompleteRequest


def _consents(extra: list[str] | None = None) -> list[ConsentItem]:
    items = [
        ConsentItem(consent_type="tos", version="v1.0"),
        ConsentItem(consent_type="privacy", version="v1.0"),
        ConsentItem(consent_type="lbs_tos", version="v1.0"),
        ConsentItem(consent_type="location_collection", version="v1.0"),
    ]
    if extra:
        items.extend(ConsentItem(consent_type=t, version="v1.0") for t in extra)  # type: ignore[arg-type]
    return items


def test_profile_complete_requires_all_four() -> None:
    with pytest.raises(ValidationError) as exc:
        ProfileCompleteRequest(
            nickname="x",
            avatar_kind="default",
            consents=[ConsentItem(consent_type="tos", version="v1.0")],
        )
    assert "필수 동의 누락" in str(exc.value)


def test_demographic_fields_require_consent() -> None:
    with pytest.raises(ValidationError) as exc:
        ProfileCompleteRequest(
            nickname="x",
            avatar_kind="default",
            gender="male",
            birth_year_month="199003",
            consents=_consents(),
        )
    assert "demographic_use" in str(exc.value)


def test_profile_complete_with_demographic_ok() -> None:
    req = ProfileCompleteRequest(
        nickname="x",
        avatar_kind="default",
        gender="male",
        birth_year_month="199003",
        residence_sigungu_code="11680",
        consents=_consents(extra=["demographic_use"]),
    )
    assert req.gender == "male"
    assert req.birth_year_month == "199003"


def test_birth_year_month_format() -> None:
    with pytest.raises(ValidationError):
        ProfileCompleteRequest(
            nickname="x",
            avatar_kind="default",
            birth_year_month="19990303",  # YYYYMMDD 형식 거부
            consents=_consents(extra=["demographic_use"]),
        )
