from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models.user import User
from app.services.admin_auth import normalize_email

OAuthEmailAction = Literal[
    "create_active_user",
    "create_pending_email_verification_user",
    "require_explicit_account_link",
    "reject",
]


@dataclass(frozen=True)
class OAuthEmailMatchDecision:
    action: OAuthEmailAction
    reason: str
    normalized_email: str | None


def decide_oauth_email_match(
    *,
    provider: str,
    provider_email: str | None,
    provider_email_verified: bool,
    existing_user: User | None,
) -> OAuthEmailMatchDecision:
    if provider_email is None or not provider_email.strip():
        return OAuthEmailMatchDecision(
            action="reject",
            reason="email_required",
            normalized_email=None,
        )

    normalized = normalize_email(provider_email)
    if provider == "google" and not provider_email_verified:
        return OAuthEmailMatchDecision(
            action="reject",
            reason="google_email_not_verified",
            normalized_email=normalized,
        )

    if existing_user is None:
        if provider_email_verified:
            return OAuthEmailMatchDecision(
                action="create_active_user",
                reason="provider_verified_new_email",
                normalized_email=normalized,
            )
        return OAuthEmailMatchDecision(
            action="create_pending_email_verification_user",
            reason="provider_email_needs_tripmate_verification",
            normalized_email=normalized,
        )

    if not provider_email_verified:
        return OAuthEmailMatchDecision(
            action="require_explicit_account_link",
            reason="provider_email_not_verified",
            normalized_email=normalized,
        )
    if not existing_user.email_verified:
        return OAuthEmailMatchDecision(
            action="require_explicit_account_link",
            reason="tripmate_email_not_verified",
            normalized_email=normalized,
        )
    return OAuthEmailMatchDecision(
        action="require_explicit_account_link",
        reason="verified_email_match_requires_user_link",
        normalized_email=normalized,
    )
