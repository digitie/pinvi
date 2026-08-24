"""M05 root watcher runtime lease verifier 회귀."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.m05_runtime_lease import (
    M05RuntimeLeaseBinding,
    M05RuntimeLeaseError,
    M05RuntimeLeaseVerifier,
)

_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
_OTHER_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
_BINDING = M05RuntimeLeaseBinding(
    scope="production",
    activation_generation=7,
    activation_nonce="22222222-2222-4222-8222-222222222222",
    receipt_sha256="a" * 64,
    runtime_attestation_sha256="b" * 64,
    dependency_snapshot_sha256="c" * 64,
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(_canonical_json(value))
    path.chmod(0o600)


def _payload(*, sequence: int = 1, expires_at: int | None = None) -> dict[str, object]:
    public = _PRIVATE_KEY.public_key().public_bytes_raw()
    now = int(time.time())
    return {
        "activation_generation": _BINDING.activation_generation,
        "activation_nonce": _BINDING.activation_nonce,
        "dependency_snapshot_sha256": _BINDING.dependency_snapshot_sha256,
        "expires_at": expires_at if expires_at is not None else now + 60,
        "issued_at": now - 1,
        "key_id": hashlib.sha256(public).hexdigest(),
        "receipt_sha256": _BINDING.receipt_sha256,
        "runtime_attestation_sha256": _BINDING.runtime_attestation_sha256,
        "scope": _BINDING.scope,
        "sequence": sequence,
        "version": 1,
    }


def _write_lease(
    directory: Path,
    *,
    payload: dict[str, object] | None = None,
    signer: Ed25519PrivateKey = _PRIVATE_KEY,
    atomic: bool = False,
) -> None:
    value = payload if payload is not None else _payload()
    target = directory / "current.json"
    candidate = directory / ".current.json.tmp" if atomic else target
    _write_json(
        candidate,
        {
            "payload": value,
            "signature": base64.urlsafe_b64encode(signer.sign(_canonical_json(value)))
            .decode("ascii")
            .rstrip("="),
        },
    )
    if atomic:
        with candidate.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(candidate, target)
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _directory(tmp_path: Path) -> Path:
    directory = tmp_path / "runtime-lease"
    directory.mkdir(mode=0o700)
    public = _PRIVATE_KEY.public_key().public_bytes_raw()
    _write_json(
        directory / "trust.json",
        {
            "key_id": hashlib.sha256(public).hexdigest(),
            "public_key": base64.urlsafe_b64encode(public).decode("ascii").rstrip("="),
            "version": 1,
        },
    )
    _write_lease(directory)
    return directory


def _verifier(directory: Path) -> M05RuntimeLeaseVerifier:
    return M05RuntimeLeaseVerifier(
        directory=directory,
        binding=_BINDING,
        max_lifetime_seconds=120,
    )


def test_valid_lease_can_be_rechecked_and_atomically_renewed(tmp_path: Path) -> None:
    directory = _directory(tmp_path)
    verifier = _verifier(directory)

    verifier.validate()
    verifier.validate()
    _write_lease(
        directory,
        payload=_payload(sequence=2, expires_at=int(time.time()) + 59),
        atomic=True,
    )
    verifier.validate()


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda directory: (directory / "current.json").unlink(), "unavailable"),
        (
            lambda directory: _write_lease(
                directory,
                payload=_payload(expires_at=int(time.time()) - 1),
            ),
            "expired",
        ),
        (
            lambda directory: _write_lease(
                directory,
                payload={**_payload(), "receipt_sha256": "d" * 64},
            ),
            "not bound",
        ),
        (lambda directory: _write_lease(directory, signer=_OTHER_PRIVATE_KEY), "signature"),
        (lambda directory: (directory / "current.json").chmod(0o644), "permissions"),
    ],
)
def test_invalid_lease_is_fail_closed(tmp_path: Path, mutate, match: str) -> None:  # type: ignore[no-untyped-def]
    directory = _directory(tmp_path)
    mutate(directory)

    with pytest.raises(M05RuntimeLeaseError, match=match):
        _verifier(directory).validate()


def test_duplicate_symlink_and_oversized_documents_are_rejected(tmp_path: Path) -> None:
    directory = _directory(tmp_path)
    current = directory / "current.json"
    current.write_text('{"payload":{},"payload":{},"signature":"x"}', encoding="utf-8")
    current.chmod(0o600)
    with pytest.raises(M05RuntimeLeaseError, match="invalid JSON"):
        _verifier(directory).validate()

    current.unlink()
    current.symlink_to(directory / "trust.json")
    with pytest.raises(M05RuntimeLeaseError, match="unavailable"):
        _verifier(directory).validate()

    current.unlink()
    current.write_bytes(b"{" + b"x" * (64 * 1024) + b"}")
    current.chmod(0o600)
    with pytest.raises(M05RuntimeLeaseError, match="permissions"):
        _verifier(directory).validate()


def test_sequence_regression_and_equivocation_are_rejected(tmp_path: Path) -> None:
    directory = _directory(tmp_path)
    verifier = _verifier(directory)
    verifier.validate()
    _write_lease(directory, payload=_payload(sequence=2), atomic=True)
    verifier.validate()

    _write_lease(directory, payload=_payload(sequence=1), atomic=True)
    with pytest.raises(M05RuntimeLeaseError, match="regressed"):
        verifier.validate()

    _write_lease(
        directory,
        payload=_payload(sequence=2, expires_at=int(time.time()) + 59),
        atomic=True,
    )
    with pytest.raises(M05RuntimeLeaseError, match="reused"):
        verifier.validate()
