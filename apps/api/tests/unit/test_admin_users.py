"""admin_users 서비스 단위 테스트 — mask_email + 비즈니스 룰."""

from __future__ import annotations

from app.services.admin_users import mask_email


def test_mask_email_normal() -> None:
    assert mask_email("hong@example.com") == "h***@example.com"


def test_mask_email_one_char_local() -> None:
    assert mask_email("a@x.com") == "a***@x.com"


def test_mask_email_no_at_passthrough() -> None:
    """`@` 없으면 그대로 (방어적)."""
    assert mask_email("invalid") == "invalid"


def test_mask_email_long_local() -> None:
    """첫 글자만 노출."""
    assert mask_email("verylonglocal@example.com") == "v***@example.com"
