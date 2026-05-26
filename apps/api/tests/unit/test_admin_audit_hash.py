"""admin_audit chain — payload 직렬화 안정성."""

from __future__ import annotations

from app.services.hash_chain import GENESIS_HASH, compute_content_hash


def test_admin_audit_payload_canonical() -> None:
    """admin_audit 페이로드는 키 정렬 후 hash. 동일 입력 → 동일 해시."""
    payload = {
        "actor_user_id": "00000000-0000-0000-0000-000000000001",
        "action": "user.force_verify",
        "resource_type": "user",
        "resource_id": "00000000-0000-0000-0000-000000000002",
        "before_state": {"status": "pending_verification"},
        "after_state": {"status": "pending_profile", "email_verified_at": "2026-05-26T00:00:00+00:00"},
        "access_reason": "테스트",
        "target_pii_fields": ["email"],
        "ip_hash": "a" * 64,
        "user_agent": "pytest",
        "request_id": "00000000-0000-0000-0000-0000000000aa",
        "occurred_at": "2026-05-26T00:00:00+00:00",
    }
    h1 = compute_content_hash(GENESIS_HASH, payload)
    h2 = compute_content_hash(GENESIS_HASH, payload)
    assert h1 == h2
    assert len(h1) == 64


def test_admin_audit_chain_links() -> None:
    """이전 hash가 바뀌면 다음 hash도 다르다 — chain 동작."""
    payload = {"action": "x", "request_id": "r"}
    h1 = compute_content_hash(GENESIS_HASH, payload)
    h2 = compute_content_hash(h1, payload)
    assert h1 != h2
