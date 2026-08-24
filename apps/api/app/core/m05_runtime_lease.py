"""M05 runtime lease의 read-only 검증 경계.

activation receipt와 runtime attestation은 배포 시점 증명이다. ordinary API는 Docker
Engine 권한이나 발급 private key 없이 root host watcher의 짧은 lease만 재검증한다.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_MAX_DOCUMENT_BYTES: Final = 64 * 1024
_BASE64URL_32_BYTES_RE: Final = re.compile(r"[A-Za-z0-9_-]{43}")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
_UUID_RE: Final = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


class M05RuntimeLeaseError(RuntimeError):
    """root watcher가 보증하지 않는 M05 실행 상태."""


class _DuplicateJsonKeyError(ValueError):
    """JSON ambiguity를 허용하지 않는다."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError
        result[key] = value
    return result


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _decode_public_key(value: object) -> bytes | None:
    if not isinstance(value, str) or _BASE64URL_32_BYTES_RE.fullmatch(value) is None:
        return None
    try:
        decoded = base64.urlsafe_b64decode(value + "=")
    except (binascii.Error, ValueError):
        return None
    if (
        len(decoded) != 32
        or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value
    ):
        return None
    try:
        Ed25519PublicKey.from_public_bytes(decoded)
    except ValueError:
        return None
    return decoded


def _decode_signature(value: object) -> bytes | None:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{86}", value) is None:
        return None
    try:
        decoded = base64.urlsafe_b64decode(value + "==")
    except (binascii.Error, ValueError):
        return None
    if (
        len(decoded) != 64
        or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value
    ):
        return None
    return decoded


@dataclass(frozen=True)
class M05RuntimeLeaseBinding:
    """lease가 반드시 묶어야 하는 activation/runtime identity."""

    scope: Literal["staging", "production"]
    activation_generation: int
    activation_nonce: str
    receipt_sha256: str
    runtime_attestation_sha256: str
    dependency_snapshot_sha256: str


class M05RuntimeLeaseVerifier:
    """root-owned mounted directory의 trust/current lease를 fail-closed로 검증한다."""

    def __init__(
        self,
        *,
        directory: Path,
        binding: M05RuntimeLeaseBinding,
        max_lifetime_seconds: int,
    ) -> None:
        self._directory = directory
        self._binding = binding
        self._max_lifetime_seconds = max_lifetime_seconds
        self._last_sequence = 0
        self._last_lease_sha256: str | None = None

    def _open_directory(self) -> int:
        if not self._directory.is_absolute():
            raise M05RuntimeLeaseError("runtime lease directory is invalid")
        try:
            descriptor = os.open(
                self._directory,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
        except OSError as exc:
            raise M05RuntimeLeaseError("runtime lease directory is unavailable") from exc
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700
            ):
                raise M05RuntimeLeaseError("runtime lease directory permissions are invalid")
        except Exception:
            os.close(descriptor)
            raise
        return descriptor

    @staticmethod
    def _read_document(directory_descriptor: int, name: str) -> bytes:
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=directory_descriptor,
            )
        except OSError as exc:
            raise M05RuntimeLeaseError("runtime lease document is unavailable") from exc
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_size < 1
                or before.st_size > _MAX_DOCUMENT_BYTES
            ):
                raise M05RuntimeLeaseError("runtime lease document permissions are invalid")
            raw = bytearray()
            while len(raw) <= _MAX_DOCUMENT_BYTES:
                chunk = os.read(descriptor, min(8192, _MAX_DOCUMENT_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            after = os.fstat(descriptor)
            if (
                len(raw) > _MAX_DOCUMENT_BYTES
                or len(raw) != before.st_size
                or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            ):
                raise M05RuntimeLeaseError("runtime lease document changed while reading")
            return bytes(raw)
        finally:
            os.close(descriptor)

    @staticmethod
    def _parse_document(raw: bytes) -> dict[str, object]:
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
        except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKeyError) as exc:
            raise M05RuntimeLeaseError("runtime lease document is invalid JSON") from exc
        if not isinstance(value, dict):
            raise M05RuntimeLeaseError("runtime lease document is not an object")
        return cast(dict[str, object], value)

    def validate(self) -> None:
        """현재 lease가 process가 이미 승인한 sequence를 후퇴시키지 않는지 확인한다."""

        directory_descriptor = self._open_directory()
        try:
            trust_raw = self._read_document(directory_descriptor, "trust.json")
            lease_raw = self._read_document(directory_descriptor, "current.json")
        finally:
            os.close(directory_descriptor)
        public_key, key_id = self._validate_trust(self._parse_document(trust_raw))
        sequence = self._validate_lease(
            self._parse_document(lease_raw), public_key=public_key, key_id=key_id
        )
        lease_sha256 = hashlib.sha256(lease_raw).hexdigest()
        if sequence < self._last_sequence:
            raise M05RuntimeLeaseError("runtime lease sequence regressed")
        if sequence == self._last_sequence:
            if self._last_lease_sha256 is None or not hmac.compare_digest(
                lease_sha256, self._last_lease_sha256
            ):
                raise M05RuntimeLeaseError("runtime lease sequence was reused")
            return
        self._last_sequence = sequence
        self._last_lease_sha256 = lease_sha256

    @staticmethod
    def _validate_trust(trust: dict[str, object]) -> tuple[bytes, str]:
        if set(trust) != {"key_id", "public_key", "version"} or trust.get("version") != 1:
            raise M05RuntimeLeaseError("runtime lease trust schema is invalid")
        public_key = _decode_public_key(trust.get("public_key"))
        key_id = trust.get("key_id")
        if (
            public_key is None
            or not isinstance(key_id, str)
            or _SHA256_RE.fullmatch(key_id) is None
            or not hmac.compare_digest(hashlib.sha256(public_key).hexdigest(), key_id)
        ):
            raise M05RuntimeLeaseError("runtime lease trust key is invalid")
        return public_key, key_id

    def _validate_lease(
        self,
        envelope: dict[str, object],
        *,
        public_key: bytes,
        key_id: str,
    ) -> int:
        if set(envelope) != {"payload", "signature"}:
            raise M05RuntimeLeaseError("runtime lease envelope is invalid")
        payload = envelope.get("payload")
        signature = _decode_signature(envelope.get("signature"))
        if not isinstance(payload, dict) or signature is None:
            raise M05RuntimeLeaseError("runtime lease signature encoding is invalid")
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                signature, _canonical_json(payload)
            )
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise M05RuntimeLeaseError("runtime lease signature is invalid") from exc
        fields = {
            "activation_generation",
            "activation_nonce",
            "dependency_snapshot_sha256",
            "expires_at",
            "issued_at",
            "key_id",
            "receipt_sha256",
            "runtime_attestation_sha256",
            "scope",
            "sequence",
            "version",
        }
        if set(payload) != fields or payload.get("version") != 1:
            raise M05RuntimeLeaseError("runtime lease payload schema is invalid")
        issued_at, expires_at, sequence = (
            payload.get("issued_at"),
            payload.get("expires_at"),
            payload.get("sequence"),
        )
        if (
            type(issued_at) is not int
            or type(expires_at) is not int
            or type(sequence) is not int
            or sequence < 1
        ):
            raise M05RuntimeLeaseError("runtime lease time or sequence is invalid")
        now = int(time.time())
        if (
            issued_at > now + 5
            or expires_at <= now
            or expires_at <= issued_at
            or expires_at - issued_at > self._max_lifetime_seconds
        ):
            raise M05RuntimeLeaseError("runtime lease is expired or too long-lived")
        binding = self._binding
        string_bindings = (
            ("scope", binding.scope),
            ("activation_nonce", binding.activation_nonce),
            ("receipt_sha256", binding.receipt_sha256),
            ("runtime_attestation_sha256", binding.runtime_attestation_sha256),
            ("dependency_snapshot_sha256", binding.dependency_snapshot_sha256),
            ("key_id", key_id),
        )
        sha_fields = {
            "receipt_sha256",
            "runtime_attestation_sha256",
            "dependency_snapshot_sha256",
            "key_id",
        }
        if (
            payload.get("activation_generation") != binding.activation_generation
            or any(
                not isinstance(payload.get(name), str)
                or not hmac.compare_digest(cast(str, payload[name]), expected)
                for name, expected in string_bindings
            )
            or not isinstance(payload.get("activation_nonce"), str)
            or _UUID_RE.fullmatch(cast(str, payload["activation_nonce"])) is None
            or any(
                not isinstance(payload.get(name), str)
                or _SHA256_RE.fullmatch(cast(str, payload[name])) is None
                for name in sha_fields
            )
        ):
            raise M05RuntimeLeaseError("runtime lease is not bound to the active pair")
        return sequence
