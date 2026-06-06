"""회원가입 시 약관 동의 저장 흐름."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.user_consent import UserConsent

pytestmark = pytest.mark.asyncio


def _register_payload() -> dict[str, object]:
    return {
        "email": f"user-{uuid.uuid4()}@example.com",
        "password": "secret-pw-12345",
        "nickname": "약관사용자",
        "consents": [
            {"consent_type": "tos", "version": "v1.0"},
            {"consent_type": "privacy", "version": "v1.0"},
            {"consent_type": "lbs_tos", "version": "v1.0"},
            {"consent_type": "location_collection", "version": "v1.0"},
            {"consent_type": "marketing", "version": "v1.0"},
        ],
    }


async def test_register_records_signup_consents(client, session_factory) -> None:
    resp = await client.post("/auth/register", json=_register_payload())

    assert resp.status_code == 201
    user_id = uuid.UUID(resp.json()["data"]["user"]["user_id"])

    async with session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(UserConsent)
                    .where(UserConsent.user_id == user_id)
                    .order_by(UserConsent.consent_type)
                )
            ).scalars()
        )

    assert {row.consent_type for row in rows} == {
        "tos",
        "privacy",
        "lbs_tos",
        "location_collection",
        "marketing",
    }
    assert {row.version for row in rows} == {"v1.0"}
    assert all(row.withdrawn_at is None for row in rows)


async def test_register_rejects_missing_required_consent(client) -> None:
    payload = _register_payload()
    payload["consents"] = [{"consent_type": "tos", "version": "v1.0"}]

    resp = await client.post("/auth/register", json=payload)

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
