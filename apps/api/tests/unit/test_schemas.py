"""Pydantic schema 단위 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest, VerifyEmailRequest
from app.schemas.storage import AttachmentResponse


def _register_consents() -> list[dict[str, str]]:
    return [
        {"consent_type": "tos", "version": "v1.0"},
        {"consent_type": "privacy", "version": "v1.0"},
        {"consent_type": "lbs_tos", "version": "v1.0"},
        {"consent_type": "location_collection", "version": "v1.0"},
    ]


def test_register_request_valid() -> None:
    req = RegisterRequest(
        email="user@example.com",
        password="secret-pw-12345",
        nickname="user",
        consents=_register_consents(),
    )
    assert req.email == "user@example.com"


def test_register_request_short_password() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="user@example.com",
            password="short",
            nickname="user",
            consents=_register_consents(),
        )


def test_register_request_invalid_email() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="not-an-email",
            password="secret-pw-12345",
            nickname="user",
            consents=_register_consents(),
        )


def test_register_request_requires_all_consents() -> None:
    with pytest.raises(ValidationError) as exc:
        RegisterRequest(
            email="user@example.com",
            password="secret-pw-12345",
            nickname="user",
            consents=[{"consent_type": "tos", "version": "v1.0"}],
        )
    assert "필수 동의 누락" in str(exc.value)


def test_register_request_rejects_duplicate_consent() -> None:
    with pytest.raises(ValidationError) as exc:
        RegisterRequest(
            email="user@example.com",
            password="secret-pw-12345",
            nickname="user",
            consents=[*_register_consents(), {"consent_type": "tos", "version": "v1.0"}],
        )
    assert "동의 항목 중복" in str(exc.value)


def test_verify_email_request_token_length() -> None:
    with pytest.raises(ValidationError):
        VerifyEmailRequest(token="short")


def test_login_request_valid() -> None:
    req = LoginRequest(email="user@example.com", password="x")
    assert req.password == "x"


def test_attachment_response_syncs_notice_aliases() -> None:
    plan_id = uuid.uuid4()
    poi_id = uuid.uuid4()
    response = AttachmentResponse(
        attachment_id=uuid.uuid4(),
        trip_id=None,
        trip_poi_id=None,
        curated_plan_id=plan_id,
        curated_poi_id=poi_id,
        source_attachment_id=None,
        bucket="tripmate-media",
        storage_key="curated/plan/image.jpg",
        original_filename="image.jpg",
        content_type="image/jpeg",
        byte_size=1024,
        public_url=None,
        role="image",
        description=None,
        sort_order=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    assert response.notice_plan_id == plan_id
    assert response.notice_poi_id == poi_id
    dumped = response.model_dump(mode="json")
    assert dumped["notice_plan_id"] == str(plan_id)
    assert dumped["notice_poi_id"] == str(poi_id)


def test_attachment_response_accepts_legacy_notice_aliases() -> None:
    plan_id = uuid.uuid4()
    response = AttachmentResponse(
        attachment_id=uuid.uuid4(),
        trip_id=None,
        trip_poi_id=None,
        notice_plan_id=plan_id,
        notice_poi_id=None,
        source_attachment_id=None,
        bucket="tripmate-media",
        storage_key="curated/plan/image.jpg",
        original_filename="image.jpg",
        content_type="image/jpeg",
        byte_size=1024,
        public_url=None,
        role="image",
        description=None,
        sort_order=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    assert response.curated_plan_id == plan_id
    assert response.notice_plan_id == plan_id


def test_attachment_response_rejects_mismatched_notice_aliases() -> None:
    with pytest.raises(ValidationError):
        AttachmentResponse(
            attachment_id=uuid.uuid4(),
            trip_id=None,
            trip_poi_id=None,
            curated_plan_id=uuid.uuid4(),
            curated_poi_id=None,
            notice_plan_id=uuid.uuid4(),
            notice_poi_id=None,
            source_attachment_id=None,
            bucket="tripmate-media",
            storage_key="curated/plan/image.jpg",
            original_filename="image.jpg",
            content_type="image/jpeg",
            byte_size=1024,
            public_url=None,
            role="image",
            description=None,
            sort_order=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
