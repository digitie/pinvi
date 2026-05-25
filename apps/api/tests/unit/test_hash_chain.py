"""content_hash chain 단위 테스트."""

from __future__ import annotations

from app.services.hash_chain import GENESIS_HASH, compute_content_hash, sha256_hex


def test_hash_chain_links() -> None:
    payload_a = {"user_id": "u-1", "endpoint": "/x", "lat": "1.0", "lng": "2.0"}
    payload_b = {"user_id": "u-1", "endpoint": "/y", "lat": "1.0", "lng": "2.0"}

    h1 = compute_content_hash(GENESIS_HASH, payload_a)
    h2 = compute_content_hash(h1, payload_b)

    assert h1 != h2
    # 동일 입력은 동일 결과
    assert compute_content_hash(GENESIS_HASH, payload_a) == h1


def test_sha256_hex_consistent() -> None:
    assert sha256_hex("1.2.3.4") == sha256_hex("1.2.3.4")
    assert sha256_hex("a") != sha256_hex("b")


def test_genesis_hash_format() -> None:
    assert len(GENESIS_HASH) == 64
    assert set(GENESIS_HASH) == {"0"}
