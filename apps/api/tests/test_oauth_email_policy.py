from __future__ import annotations

from app.models.mixins import kst_now
from app.models.user import User
from app.services.oauth_email_policy import decide_oauth_email_match


def test_google_unverified_email_is_rejected() -> None:
    decision = decide_oauth_email_match(
        provider="google",
        provider_email="Planner@Example.com",
        provider_email_verified=False,
        existing_user=None,
    )

    assert decision.action == "reject"
    assert decision.reason == "google_email_not_verified"
    assert decision.normalized_email == "planner@example.com"


def test_existing_verified_email_still_requires_explicit_link() -> None:
    existing_user = User(
        email="planner@example.com",
        email_verified=True,
        email_verified_at=kst_now(),
        account_status="active",
        status="active",
        system_role="planner",
        is_active=True,
    )

    decision = decide_oauth_email_match(
        provider="google",
        provider_email="PLANNER@example.com",
        provider_email_verified=True,
        existing_user=existing_user,
    )

    assert decision.action == "require_explicit_account_link"
    assert decision.reason == "verified_email_match_requires_user_link"
    assert decision.normalized_email == "planner@example.com"


def test_unverified_non_google_provider_new_email_requires_tripmate_verification() -> None:
    decision = decide_oauth_email_match(
        provider="naver",
        provider_email="new@example.com",
        provider_email_verified=False,
        existing_user=None,
    )

    assert decision.action == "create_pending_email_verification_user"
    assert decision.reason == "provider_email_needs_tripmate_verification"
