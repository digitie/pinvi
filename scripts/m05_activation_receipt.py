#!/usr/bin/env python3
"""M05 paired live/restore/review evidence를 서명된 production receipt로 봉인한다."""

from __future__ import annotations

import argparse
import base64
import binascii
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import time
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PLAYWRIGHT_IMAGE_RE = re.compile(
    r"mcr\.microsoft\.com/playwright:[A-Za-z0-9][A-Za-z0-9._-]*@sha256:[0-9a-f]{64}\Z"
)
_REVIEW_PR_RE = re.compile(r"https://github\.com/digitie/pinvi/pull/[1-9][0-9]*\Z")
_M05_ACTIVATION_PR_URL = "https://github.com/digitie/pinvi/pull/466"
_PAIR_PROVENANCE = Path(__file__).resolve().parents[1] / (
    "contracts/kor-travel-map-m05-pair-provenance-v1.json"
)
_TRUST_ANCHOR = Path(__file__).resolve().parents[1] / (
    "contracts/pinvi-m05-activation-receipt-trust-v1.json"
)
_REVIEWER_ROSTER = Path(__file__).resolve().parents[1] / (
    "contracts/pinvi-m05-reviewer-roster-v1.json"
)
_EVIDENCE_FILES = (
    "attestation.json",
    "reviews.json",
    "live-ui.json",
    "restore.json",
    "map-pair.json",
    "pinvi-images.json",
)


class ReceiptError(ValueError):
    """M05 evidence가 canonical receipt 계약을 위반했다."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError("duplicate JSON key")
        result[key] = value
    return result


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_base64url(value: object, *, expected_length: int) -> bytes | None:
    if not isinstance(value, str) or not value or "=" in value:
        return None
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error):
        return None
    if len(decoded) != expected_length or _base64url(decoded) != value:
        return None
    return decoded


def _open_secure_directory(path: Path, *, require_root_owned: bool) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ReceiptError("evidence directory must be a regular directory") from exc
    directory_stat = os.fstat(fd)
    if not stat.S_ISDIR(directory_stat.st_mode):
        os.close(fd)
        raise ReceiptError("evidence directory must be a regular directory")
    if stat.S_IMODE(directory_stat.st_mode) != 0o700:
        os.close(fd)
        raise ReceiptError("evidence directory mode is not 0700")
    if require_root_owned and directory_stat.st_uid != 0:
        os.close(fd)
        raise ReceiptError("evidence directory is not root-owned")
    return fd


def _read_secure_bytes(
    path: Path,
    *,
    require_root_owned: bool,
    directory_fd: int | None = None,
    label: str,
) -> bytes:
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        if directory_fd is None:
            fd = os.open(path, flags)
        else:
            fd = os.open(path.name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise ReceiptError(
            f"{label} is not a readable regular file: {path.name}"
        ) from exc
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ReceiptError(f"{label} is not a regular file: {path.name}")
        if stat.S_IMODE(file_stat.st_mode) != 0o600:
            raise ReceiptError(f"{label} mode is not 0600: {path.name}")
        if require_root_owned and file_stat.st_uid != 0:
            raise ReceiptError(f"{label} is not root-owned: {path.name}")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            return stream.read()
    finally:
        if fd != -1:
            os.close(fd)


def _read_json(
    path: Path,
    *,
    require_root_owned: bool,
    directory_fd: int | None = None,
) -> tuple[object, str]:
    raw = _read_secure_bytes(
        path,
        require_root_owned=require_root_owned,
        directory_fd=directory_fd,
        label="evidence file",
    )
    try:
        return (
            json.loads(raw, object_pairs_hook=_reject_duplicate_keys),
            hashlib.sha256(raw).hexdigest(),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ReceiptError) as exc:
        raise ReceiptError(f"evidence JSON is invalid: {path.name}") from exc


def _write_new_json(path: Path, value: object) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ReceiptError("output parent must be a regular directory")
    parent_stat = path.parent.stat()
    if stat.S_IMODE(parent_stat.st_mode) & 0o022:
        raise ReceiptError("output parent must not be group/world writable")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise ReceiptError(f"output already exists: {path}") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode(
                    "utf-8"
                )
            )
    finally:
        if fd != -1:
            os.close(fd)


def _object(value: object, *, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ReceiptError(f"{name} must be an object")
    return cast(dict[str, object], value)


def _string(value: object, *, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(character.isspace() for character in value)
    ):
        raise ReceiptError(f"{name} must be a non-empty token-free string")
    return value


def _sha256(value: object, *, name: str) -> str:
    value = _string(value, name=name)
    if _SHA256_RE.fullmatch(value) is None:
        raise ReceiptError(f"{name} must be lowercase SHA-256")
    return value


def _digest(value: object, *, name: str) -> str:
    value = _string(value, name=name)
    if _DIGEST_RE.fullmatch(value) is None:
        raise ReceiptError(f"{name} must be an immutable image digest")
    return value


def _commit(value: object, *, name: str) -> str:
    value = _string(value, name=name)
    if _COMMIT_RE.fullmatch(value) is None:
        raise ReceiptError(f"{name} must be a full lowercase commit")
    return value


def _uuid(value: object, *, name: str) -> str:
    value = _string(value, name=name)
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except ValueError as exc:
        raise ReceiptError(f"{name} must be a canonical UUID") from exc
    return value


def _ledger_record_hash(record: dict[str, object]) -> str:
    unsigned = {key: value for key, value in record.items() if key != "record_sha256"}
    return hashlib.sha256(_canonical_json(unsigned)).hexdigest()


def _trust_anchor() -> str:
    try:
        raw = json.loads(
            _TRUST_ANCHOR.read_bytes(), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ReceiptError) as exc:
        raise ReceiptError("M05 activation trust anchor is invalid") from exc
    payload = _object(raw, name="M05 activation trust anchor")
    if (
        set(payload) != {"public_key_sha256", "version"}
        or type(payload["version"]) is not int
        or payload["version"] != 1
    ):
        raise ReceiptError("M05 activation trust anchor schema is invalid")
    return _sha256(
        payload["public_key_sha256"], name="M05 activation public key fingerprint"
    )


def _reviewer_roster() -> set[str]:
    try:
        raw = json.loads(
            _REVIEWER_ROSTER.read_bytes(), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ReceiptError) as exc:
        raise ReceiptError("M05 reviewer roster is invalid") from exc
    payload = _object(raw, name="M05 reviewer roster")
    if set(payload) != {"agent_ids", "version"} or payload["version"] != 1:
        raise ReceiptError("M05 reviewer roster schema is invalid")
    agents = payload["agent_ids"]
    if not isinstance(agents, list) or len(agents) != 2:
        raise ReceiptError("M05 reviewer roster must contain exactly two agents")
    result = {_uuid(agent, name="M05 reviewer roster agent") for agent in agents}
    if len(result) != 2:
        raise ReceiptError("M05 reviewer roster agents must be distinct")
    return result


def _assert_source_checkout(source_revision: str) -> None:
    """receipt signer가 인자로 받은 revision의 clean checkout에서만 동작하게 한다."""

    root = Path(__file__).resolve().parents[1]
    try:
        revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReceiptError(
            "receipt producer source revision could not be verified"
        ) from exc
    if revision != source_revision or status:
        raise ReceiptError(
            "receipt producer checkout must be clean at the signed revision"
        )


def _ledger_records(path: Path, *, require_root_owned: bool) -> list[dict[str, object]]:
    if not path.is_file() or path.is_symlink():
        return []
    raw = _read_secure_bytes(
        path,
        require_root_owned=require_root_owned,
        label="activation ledger",
    )
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ReceiptError("activation ledger is not valid UTF-8") from exc
    records: list[dict[str, object]] = []
    previous_generation: int | None = None
    activation_nonces: set[str] = set()
    for line in lines:
        try:
            record = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        except (json.JSONDecodeError, ReceiptError) as exc:
            raise ReceiptError("activation ledger contains invalid JSON") from exc
        record_object = _object(record, name="activation ledger record")
        if set(record_object) != {
            "activation_expires_at",
            "activation_generation",
            "activation_issued_at",
            "activation_nonce",
            "previous_record_sha256",
            "record_sha256",
            "receipt_sha256",
            "scope",
            "source_revision",
        }:
            raise ReceiptError("activation ledger record schema is invalid")
        generation = record_object["activation_generation"]
        issued_at = record_object["activation_issued_at"]
        expires_at = record_object["activation_expires_at"]
        scope = record_object["scope"]
        if (
            type(generation) is not int
            or generation < 1
            or (previous_generation is not None and generation <= previous_generation)
            or type(issued_at) is not int
            or type(expires_at) is not int
            or expires_at <= issued_at
            or expires_at - issued_at > 7 * 24 * 60 * 60
            or not isinstance(scope, str)
            or scope not in {"staging", "production"}
        ):
            raise ReceiptError("activation ledger record fields are invalid")
        activation_nonce = _uuid(
            record_object["activation_nonce"], name="ledger activation nonce"
        )
        if activation_nonce in activation_nonces:
            raise ReceiptError("activation ledger contains a replayed nonce")
        activation_nonces.add(activation_nonce)
        previous_record_sha = _sha256(
            record_object["previous_record_sha256"],
            name="ledger previous record hash",
        )
        if previous_record_sha != (
            records[-1]["record_sha256"] if records else "0" * 64
        ):
            raise ReceiptError("activation ledger hash chain is broken")
        _sha256(record_object["receipt_sha256"], name="ledger receipt hash")
        _commit(record_object["source_revision"], name="ledger source revision")
        if record_object["record_sha256"] != _ledger_record_hash(record_object):
            raise ReceiptError("activation ledger record hash is invalid")
        previous_generation = generation
        records.append(record_object)
    return records


def _read_high_watermark(
    path: Path, *, require_root_owned: bool
) -> tuple[int, str] | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ReceiptError("activation high-watermark is not a regular file")
    raw = _read_secure_bytes(
        path,
        require_root_owned=require_root_owned,
        label="activation high-watermark",
    )
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ReceiptError) as exc:
        raise ReceiptError("activation high-watermark is invalid JSON") from exc
    payload = _object(value, name="activation high-watermark")
    if set(payload) != {"generation", "receipt_sha256"}:
        raise ReceiptError("activation high-watermark schema is invalid")
    generation = payload["generation"]
    receipt_sha256 = _sha256(
        payload["receipt_sha256"], name="activation high-watermark receipt hash"
    )
    if type(generation) is not int or generation < 1:
        raise ReceiptError("activation high-watermark generation is invalid")
    metadata = path.stat()
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ReceiptError("activation high-watermark mode is not 0600")
    if require_root_owned and metadata.st_uid != 0:
        raise ReceiptError("activation high-watermark is not root-owned")
    return generation, receipt_sha256


def _write_high_watermark(
    path: Path,
    *,
    generation: int,
    receipt_sha256: str,
    require_root_owned: bool,
) -> None:
    if type(generation) is not int or generation < 1:
        raise ReceiptError("activation high-watermark generation is invalid")
    receipt_sha256 = _sha256(
        receipt_sha256, name="activation high-watermark receipt hash"
    )
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ReceiptError(
            "activation high-watermark parent must be a regular directory"
        )
    parent_stat = path.parent.stat()
    if stat.S_IMODE(parent_stat.st_mode) & 0o022:
        raise ReceiptError(
            "activation high-watermark parent must not be group/world writable"
        )
    if require_root_owned and parent_stat.st_uid != 0:
        raise ReceiptError("activation high-watermark parent is not root-owned")
    existing = _read_high_watermark(path, require_root_owned=require_root_owned)
    if existing is not None:
        existing_generation, existing_receipt_sha256 = existing
        if existing_generation > generation:
            raise ReceiptError(
                "activation high-watermark generation cannot move backwards"
            )
        if (
            existing_generation == generation
            and existing_receipt_sha256 != receipt_sha256
        ):
            raise ReceiptError(
                "activation high-watermark conflicts at the same generation"
            )
        if existing_generation == generation:
            return

    temporary = path.parent / f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    value = {"generation": generation, "receipt_sha256": receipt_sha256}
    fd = -1
    try:
        fd = os.open(temporary, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(_canonical_json(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(
            path.parent,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise ReceiptError("activation high-watermark could not be updated") from exc
    finally:
        if fd != -1:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    written = _read_high_watermark(path, require_root_owned=require_root_owned)
    if written != (generation, receipt_sha256):
        raise ReceiptError("activation high-watermark update could not be verified")


def _ledger(args: argparse.Namespace) -> int:
    receipt_bytes = _read_secure_bytes(
        args.receipt,
        require_root_owned=args.require_root_owned,
        label="receipt",
    )
    try:
        envelope = json.loads(receipt_bytes, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ReceiptError) as exc:
        raise ReceiptError("receipt is not valid JSON") from exc
    envelope_object = _object(envelope, name="receipt")
    if set(envelope_object) != {"payload", "signature"}:
        raise ReceiptError("receipt envelope schema is invalid")
    payload = _object(envelope_object["payload"], name="receipt payload")
    required = {
        "activation_expires_at",
        "activation_generation",
        "activation_issued_at",
        "activation_nonce",
        "pinvi_source_revision",
        "scope",
    }
    if not required.issubset(payload):
        raise ReceiptError("receipt does not contain ledger fields")
    generation = payload["activation_generation"]
    issued_at = payload["activation_issued_at"]
    expires_at = payload["activation_expires_at"]
    if (
        type(generation) is not int
        or generation < 1
        or type(issued_at) is not int
        or type(expires_at) is not int
        or expires_at <= issued_at
        or not isinstance(payload["scope"], str)
        or payload["scope"] not in {"staging", "production"}
    ):
        raise ReceiptError("receipt ledger fields are invalid")
    nonce = _uuid(payload["activation_nonce"], name="receipt activation nonce")
    source_revision = _commit(
        payload["pinvi_source_revision"], name="receipt source revision"
    )
    record = {
        "activation_expires_at": expires_at,
        "activation_generation": generation,
        "activation_issued_at": issued_at,
        "activation_nonce": nonce,
        "previous_record_sha256": "0" * 64,
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "scope": payload["scope"],
        "source_revision": source_revision,
    }
    args.ledger.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.ledger.parent.is_symlink() or not args.ledger.parent.is_dir():
        raise ReceiptError("activation ledger parent must be a regular directory")
    if args.ledger.parent.stat().st_mode & 0o022:
        raise ReceiptError("activation ledger parent must not be group/world writable")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_CLOEXEC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(args.ledger, flags, 0o600)
    except OSError as exc:
        raise ReceiptError("activation ledger cannot be opened") from exc
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        ledger_stat = os.fstat(fd)
        if (
            not stat.S_ISREG(ledger_stat.st_mode)
            or stat.S_IMODE(ledger_stat.st_mode) != 0o600
        ):
            raise ReceiptError("activation ledger mode is not 0600")
        if args.require_root_owned and ledger_stat.st_uid != 0:
            raise ReceiptError("activation ledger is not root-owned")
        records = _ledger_records(
            args.ledger, require_root_owned=args.require_root_owned
        )
        if any(record["activation_nonce"] == nonce for record in records):
            raise ReceiptError("activation nonce has already been recorded")
        if records:
            record["previous_record_sha256"] = records[-1]["record_sha256"]
            previous_generation = records[-1]["activation_generation"]
            if (
                type(previous_generation) is not int
                or generation <= previous_generation
            ):
                raise ReceiptError(
                    "activation ledger generation must increase monotonically"
                )
        record["record_sha256"] = _ledger_record_hash(record)
        with os.fdopen(fd, "ab") as stream:
            fd = -1
            stream.write(_canonical_json(record) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd != -1:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    _write_high_watermark(
        args.high_watermark,
        generation=generation,
        receipt_sha256=cast(str, record["receipt_sha256"]),
        require_root_owned=args.require_root_owned,
    )
    print(f"ledger_generation={generation}")
    print(f"ledger_receipt_sha256={record['receipt_sha256']}")
    return 0


def _pair_provenance() -> dict[str, dict[str, str]]:
    try:
        raw = json.loads(
            _PAIR_PROVENANCE.read_bytes(), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ReceiptError) as exc:
        raise ReceiptError("pair provenance file is invalid") from exc
    payload = _object(raw, name="pair provenance")
    if (
        set(payload) != {"map", "runtime_image_digests", "version"}
        or type(payload["version"]) is not int
        or payload["version"] != 1
    ):
        raise ReceiptError("pair provenance envelope is invalid")
    map_value = _object(payload["map"], name="pair provenance map")
    if set(map_value) != {"admin", "full", "service", "user"}:
        raise ReceiptError("pair provenance map inventory is invalid")
    runtime_images = _object(
        payload["runtime_image_digests"], name="pair provenance runtime image digests"
    )
    if set(runtime_images) != {"admin", "api", "frontend"}:
        raise ReceiptError("pair provenance runtime image digest inventory is invalid")
    result: dict[str, dict[str, str]] = {}
    for name in ("admin", "full", "service", "user"):
        entry = _object(map_value.get(name), name=f"pair provenance {name}")
        if set(entry) != {
            "openapi_sha256",
            "runtime_operation_contract_sha256",
            "source_canonical_sha256",
            "source_operation_contract_sha256",
            "source_revision",
        }:
            raise ReceiptError(f"pair provenance {name} schema is invalid")
        result[name] = {
            "openapi_sha256": _sha256(
                entry["openapi_sha256"], name=f"{name}.openapi_sha256"
            ),
            "runtime_operation_contract_sha256": _sha256(
                entry["runtime_operation_contract_sha256"],
                name=f"{name}.runtime_operation_contract_sha256",
            ),
            "source_canonical_sha256": _sha256(
                entry["source_canonical_sha256"],
                name=f"{name}.source_canonical_sha256",
            ),
            "source_operation_contract_sha256": _sha256(
                entry["source_operation_contract_sha256"],
                name=f"{name}.source_operation_contract_sha256",
            ),
            "source_revision": _commit(
                entry["source_revision"], name=f"{name}.source_revision"
            ),
        }
    result["runtime_image_digests"] = {
        name: _digest(runtime_images[name], name=f"runtime_image_digests.{name}")
        for name in ("admin", "api", "frontend")
    }
    return result


def _reviews(
    value: object, *, pinvi_source_revision: str, expected_pr_url: str
) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) != 2:
        raise ReceiptError("reviews.json must contain exactly two reviews")
    result: list[dict[str, object]] = []
    review_keys: set[tuple[str, str, str]] = set()
    reviewer_ids: set[str] = set()
    review_ids: set[str] = set()
    agent_ids: set[str] = set()
    allowed_agent_ids = _reviewer_roster()
    for item in value:
        review = _object(item, name="review")
        if set(review) != {
            "agent_id",
            "commit",
            "p0_p1",
            "pr_url",
            "review_id",
            "reviewer_id",
            "summary",
            "summary_sha256",
            "verdict",
        }:
            raise ReceiptError("review schema is invalid")
        if type(review["p0_p1"]) is not int or review["p0_p1"] != 0:
            raise ReceiptError("review P0/P1 count must be zero")
        commit = _commit(review["commit"], name="review.commit")
        if commit != pinvi_source_revision:
            raise ReceiptError(
                "review commit does not match the signed Pinvi source revision"
            )
        review_id = _uuid(review["review_id"], name="review.review_id")
        reviewer_id = _uuid(review["reviewer_id"], name="review.reviewer_id")
        agent_id = _uuid(review["agent_id"], name="review.agent_id")
        if reviewer_id != agent_id:
            raise ReceiptError("review.reviewer_id must bind to review.agent_id")
        pr_url = _string(review["pr_url"], name="review.pr_url")
        if pr_url != expected_pr_url or _REVIEW_PR_RE.fullmatch(pr_url) is None:
            raise ReceiptError(
                "review.pr_url must identify the exact Pinvi pull request"
            )
        if agent_id not in allowed_agent_ids:
            raise ReceiptError("review.agent_id is not in the pinned reviewer roster")
        if review["verdict"] != "GO":
            raise ReceiptError("review verdict must be GO")
        summary = review["summary"]
        if (
            not isinstance(summary, str)
            or not summary
            or any(character in "\r\n" for character in summary)
        ):
            raise ReceiptError("review.summary must be a non-empty one-line string")
        summary_sha256 = _sha256(review["summary_sha256"], name="review.summary_sha256")
        if hashlib.sha256(summary.encode("utf-8")).hexdigest() != summary_sha256:
            raise ReceiptError("review summary hash is invalid")
        if (
            reviewer_id in reviewer_ids
            or review_id in review_ids
            or agent_id in agent_ids
        ):
            raise ReceiptError(
                "reviews.json must contain distinct reviewers and review IDs"
            )
        reviewer_ids.add(reviewer_id)
        review_ids.add(review_id)
        agent_ids.add(agent_id)
        normalized = {
            "commit": commit,
            "p0_p1": 0,
            "agent_id": agent_id,
            "pr_url": pr_url,
            "review_id": review_id,
            "reviewer_id": reviewer_id,
            "summary": summary,
            "summary_sha256": summary_sha256,
            "verdict": "GO",
        }
        key = (reviewer_id, review_id, commit)
        if key in review_keys:
            raise ReceiptError("reviews.json must contain two distinct reviews")
        review_keys.add(key)
        result.append(normalized)
    return result


def _live_ui(value: object, *, pinvi_source_revision: str) -> dict[str, str]:
    live = _object(value, name="live-ui evidence")
    expected = {
        "event_id",
        "event_sha256",
        "map_admin_endpoint",
        "map_ack_sha256",
        "map_local_receipt_sha256",
        "map_snapshot_after_sha256",
        "map_snapshot_before_sha256",
        "pinvi_api_endpoint",
        "pinvi_web_endpoint",
        "pinvi_receipt_sha256",
        "pinvi_source_revision",
        "pinvi_snapshot_after_sha256",
        "pinvi_snapshot_before_sha256",
        "runner_exit_code",
        "server_side_ack_verified",
        "status",
        "ui_evidence_sha256",
        "verification_id",
        "playwright_runner_image_id",
        "playwright_runner_image_ref",
    }
    if set(live) != expected or live["status"] != "passed":
        raise ReceiptError("live-ui evidence schema/status is invalid")
    if type(live["runner_exit_code"]) is not int or live["runner_exit_code"] != 0:
        raise ReceiptError("live-ui runner did not exit successfully")
    if live["server_side_ack_verified"] is not True:
        raise ReceiptError("live-ui server-side Map ACK was not verified")
    _uuid(live["verification_id"], name="live-ui.verification_id")
    _digest(
        live["playwright_runner_image_id"],
        name="live-ui.playwright_runner_image_id",
    )
    if (
        not isinstance(live["playwright_runner_image_ref"], str)
        or _PLAYWRIGHT_IMAGE_RE.fullmatch(live["playwright_runner_image_ref"]) is None
    ):
        raise ReceiptError("live-ui Playwright runner image reference is invalid")
    for field in ("map_admin_endpoint", "pinvi_api_endpoint", "pinvi_web_endpoint"):
        endpoint = live[field]
        if (
            not isinstance(endpoint, str)
            or not endpoint.startswith("http://127.0.0.1:")
            or any(character.isspace() for character in endpoint)
        ):
            raise ReceiptError(
                f"live-ui endpoint is not a canonical loopback URL: {field}"
            )
    local_receipt_sha = _sha256(
        live["map_local_receipt_sha256"], name="live-ui.map_local_receipt_sha256"
    )
    pinvi_receipt_sha = _sha256(
        live["pinvi_receipt_sha256"], name="live-ui.pinvi_receipt_sha256"
    )
    if local_receipt_sha != pinvi_receipt_sha:
        raise ReceiptError("live-ui Map ACK and Pinvi receipt hashes differ")
    if (
        live["map_snapshot_before_sha256"] != live["map_snapshot_after_sha256"]
        or live["pinvi_snapshot_before_sha256"] != live["pinvi_snapshot_after_sha256"]
    ):
        raise ReceiptError("live-ui remote snapshot drifted during the UI flow")
    if (
        _commit(live["pinvi_source_revision"], name="live-ui.pinvi_source_revision")
        != pinvi_source_revision
    ):
        raise ReceiptError(
            "live-ui source revision does not match the signed Pinvi pair"
        )
    return {
        "event_id": _uuid(live["event_id"], name="live-ui.event_id"),
        "event_sha256": _sha256(live["event_sha256"], name="live-ui.event_sha256"),
        "map_ack_sha256": _sha256(
            live["map_ack_sha256"], name="live-ui.map_ack_sha256"
        ),
        "map_admin_endpoint": _string(
            live["map_admin_endpoint"], name="live-ui.map_admin_endpoint"
        ),
        "map_local_receipt_sha256": local_receipt_sha,
        "map_snapshot_after_sha256": _sha256(
            live["map_snapshot_after_sha256"], name="live-ui.map_snapshot_after_sha256"
        ),
        "map_snapshot_before_sha256": _sha256(
            live["map_snapshot_before_sha256"],
            name="live-ui.map_snapshot_before_sha256",
        ),
        "pinvi_source_revision": pinvi_source_revision,
        "pinvi_api_endpoint": _string(
            live["pinvi_api_endpoint"], name="live-ui.pinvi_api_endpoint"
        ),
        "pinvi_web_endpoint": _string(
            live["pinvi_web_endpoint"], name="live-ui.pinvi_web_endpoint"
        ),
        "pinvi_receipt_sha256": pinvi_receipt_sha,
        "playwright_runner_image_id": _digest(
            live["playwright_runner_image_id"],
            name="live-ui.playwright_runner_image_id",
        ),
        "playwright_runner_image_ref": _string(
            live["playwright_runner_image_ref"],
            name="live-ui.playwright_runner_image_ref",
        ),
        "pinvi_snapshot_after_sha256": _sha256(
            live["pinvi_snapshot_after_sha256"],
            name="live-ui.pinvi_snapshot_after_sha256",
        ),
        "pinvi_snapshot_before_sha256": _sha256(
            live["pinvi_snapshot_before_sha256"],
            name="live-ui.pinvi_snapshot_before_sha256",
        ),
        "verification_id": _uuid(
            live["verification_id"], name="live-ui.verification_id"
        ),
        "ui_evidence_sha256": _sha256(
            live["ui_evidence_sha256"], name="live-ui.ui_evidence_sha256"
        ),
    }


def _restore(value: object, *, pinvi_source_revision: str) -> None:
    restore = _object(value, name="restore evidence")
    expected = {
        "backup_runner_sha256",
        "dump_sha256",
        "execution_id",
        "no_owner_restore",
        "restore_command",
        "restore_output_sha256",
        "restore_runner_sha256",
        "runtime_db_identity",
        "runtime_role",
        "runtime_role_verified",
        "source_db_identity",
        "source_db_identity_after_backup",
        "source_db_identity_after_backup_sha256",
        "source_db_identity_sha256",
        "source_revision",
        "staging_role",
        "staging_role_verified",
        "status",
        "target_db_identity",
        "target_db_identity_before_restore",
        "target_db_identity_before_restore_sha256",
        "target_db_identity_sha256",
        "trigger_guard_verified",
        "runtime_db_identity_sha256",
    }
    if set(restore) != expected or restore["status"] != "passed":
        raise ReceiptError("restore evidence schema/status is invalid")
    if restore["restore_command"] != (
        "pg_restore --clean --if-exists --exit-on-error --no-owner --no-privileges"
    ):
        raise ReceiptError("restore evidence is not a no-owner restore")
    for field in (
        "no_owner_restore",
        "runtime_role_verified",
        "staging_role_verified",
        "trigger_guard_verified",
    ):
        if restore[field] is not True:
            raise ReceiptError(f"restore evidence flag is not true: {field}")
    for field in (
        "backup_runner_sha256",
        "dump_sha256",
        "restore_output_sha256",
        "restore_runner_sha256",
        "runtime_db_identity_sha256",
        "source_db_identity_after_backup_sha256",
        "source_db_identity_sha256",
        "target_db_identity_before_restore_sha256",
        "target_db_identity_sha256",
    ):
        _sha256(restore[field], name=f"restore.{field}")
    repository_root = Path(__file__).resolve().parents[1]
    for evidence_field, script_path in (
        ("backup_runner_sha256", repository_root / "scripts/backup-db.sh"),
        ("restore_runner_sha256", repository_root / "scripts/restore-staging-drill.sh"),
    ):
        try:
            expected_script_sha256 = hashlib.sha256(
                script_path.read_bytes()
            ).hexdigest()
        except OSError as exc:
            raise ReceiptError("restore runner source is missing") from exc
        if restore[evidence_field] != expected_script_sha256:
            raise ReceiptError(
                f"restore runner hash is not bound to {script_path.name}"
            )
    for field in (
        "source_db_identity",
        "source_db_identity_after_backup",
        "target_db_identity_before_restore",
        "target_db_identity",
        "runtime_db_identity",
    ):
        identity = _object(restore[field], name=f"restore.{field}")
        if set(identity) != {
            "database",
            "database_oid",
            "schema_exists",
            "server_version_num",
            "system_identifier",
            "user",
        }:
            raise ReceiptError(f"restore.{field} identity schema is invalid")
    for identity_field, digest_field in (
        ("source_db_identity", "source_db_identity_sha256"),
        ("source_db_identity_after_backup", "source_db_identity_after_backup_sha256"),
        (
            "target_db_identity_before_restore",
            "target_db_identity_before_restore_sha256",
        ),
        ("target_db_identity", "target_db_identity_sha256"),
        ("runtime_db_identity", "runtime_db_identity_sha256"),
    ):
        expected_identity_sha256 = hashlib.sha256(
            _canonical_json(restore[identity_field])
        ).hexdigest()
        if restore[digest_field] != expected_identity_sha256:
            raise ReceiptError(f"restore identity hash is not bound: {identity_field}")
    if (
        restore["source_db_identity"]["database"]
        != restore["source_db_identity_after_backup"]["database"]
        or restore["source_db_identity"]["database_oid"]
        != restore["source_db_identity_after_backup"]["database_oid"]
        or restore["source_db_identity"]["system_identifier"]
        != restore["source_db_identity_after_backup"]["system_identifier"]
        or restore["target_db_identity_before_restore"]["database"]
        != restore["target_db_identity"]["database"]
        or restore["target_db_identity_before_restore"]["database_oid"]
        != restore["target_db_identity"]["database_oid"]
        or restore["target_db_identity_before_restore"]["system_identifier"]
        != restore["target_db_identity"]["system_identifier"]
        or restore["target_db_identity"]["database"]
        != restore["runtime_db_identity"]["database"]
        or restore["target_db_identity"]["database_oid"]
        != restore["runtime_db_identity"]["database_oid"]
        or restore["target_db_identity"]["system_identifier"]
        != restore["runtime_db_identity"]["system_identifier"]
        or restore["runtime_db_identity"]["user"] != restore["runtime_role"]
        or restore["target_db_identity_before_restore"]["user"]
        != restore["staging_role"]
        or restore["source_db_identity"]["schema_exists"] is not True
        or restore["source_db_identity_after_backup"]["schema_exists"] is not True
        or restore["target_db_identity_before_restore"]["schema_exists"] is not False
        or restore["target_db_identity"]["schema_exists"] is not True
        or restore["runtime_db_identity"]["schema_exists"] is not True
        or restore["source_db_identity"]["database"]
        == restore["target_db_identity_before_restore"]["database"]
        or restore["source_db_identity"]["database_oid"]
        == restore["target_db_identity_before_restore"]["database_oid"]
    ):
        raise ReceiptError("restore database identities or roles are not bound")
    _string(restore["runtime_role"], name="restore.runtime_role")
    _string(restore["staging_role"], name="restore.staging_role")
    _uuid(restore["execution_id"], name="restore.execution_id")
    if (
        _commit(restore["source_revision"], name="restore.source_revision")
        != pinvi_source_revision
    ):
        raise ReceiptError("restore producer source revision does not match Pinvi")


def _map_pair(
    value: object,
    expected: dict[str, dict[str, str]],
    *,
    environment: str,
) -> dict[str, str]:
    pair = _object(value, name="Map pair evidence")
    if set(pair) != {
        "admin",
        "admin_image_digest",
        "api_image_digest",
        "frontend_image_digest",
        "full",
        "runtime",
        "service",
        "user",
    }:
        raise ReceiptError("Map pair evidence schema is invalid")
    for name in ("admin", "full", "service", "user"):
        entry = _object(pair[name], name=f"Map pair {name}")
        if set(entry) != {
            "openapi_sha256",
            "runtime_operation_contract_sha256",
            "source_canonical_sha256",
            "source_operation_contract_sha256",
            "source_revision",
        }:
            raise ReceiptError(f"Map pair {name} evidence schema is invalid")
        for field in ("openapi_sha256", "source_revision"):
            if entry[field] != expected[name][field]:
                raise ReceiptError(
                    f"Map pair {name} does not match the vendored provenance"
                )
        if (
            entry["runtime_operation_contract_sha256"]
            != expected[name]["runtime_operation_contract_sha256"]
            or entry["source_canonical_sha256"]
            != expected[name]["source_canonical_sha256"]
            or entry["source_operation_contract_sha256"]
            != expected[name]["source_operation_contract_sha256"]
        ):
            raise ReceiptError(f"Map pair {name} hashes are not pinned to provenance")
    runtime = _object(pair["runtime"], name="Map pair runtime evidence")
    if set(runtime) != {
        "admin_openapi",
        "admin",
        "api",
        "frontend",
        "full_openapi",
        "full_openapi_sha256",
        "service_openapi",
        "user_openapi",
    }:
        raise ReceiptError("Map pair runtime evidence schema is invalid")
    if runtime["full_openapi_sha256"] != expected["full"]["openapi_sha256"]:
        raise ReceiptError("Map runtime OpenAPI does not match the vendored provenance")
    runtime_openapi: dict[str, dict[str, object]] = {}
    for surface, provenance_name in (
        ("admin_openapi", "admin"),
        ("full_openapi", "full"),
        ("service_openapi", "service"),
        ("user_openapi", "user"),
    ):
        artifact = _object(
            runtime[surface], name=f"Map runtime {provenance_name} OpenAPI evidence"
        )
        if set(artifact) != {
            "canonical_sha256",
            "source_canonical_sha256",
            "source_revision",
            "source_sha256",
            "surface_coverage_sha256",
            "transport",
            "transport_sha256",
        }:
            raise ReceiptError(
                f"Map runtime {provenance_name} OpenAPI evidence schema is invalid"
            )
        expected_transport = (
            "http" if provenance_name in {"admin", "full"} else "source-artifact"
        )
        if artifact["transport"] != expected_transport:
            raise ReceiptError(
                f"Map runtime {provenance_name} OpenAPI transport is invalid"
            )
        for field in (
            "canonical_sha256",
            "source_canonical_sha256",
            "surface_coverage_sha256",
            "transport_sha256",
        ):
            _sha256(
                artifact[field],
                name=f"Map runtime {provenance_name} OpenAPI.{field}",
            )
        if (
            (
                provenance_name != "full"
                and artifact["canonical_sha256"] != artifact["source_canonical_sha256"]
            )
            or artifact["source_sha256"] != expected[provenance_name]["openapi_sha256"]
            or artifact["source_canonical_sha256"]
            != expected[provenance_name]["source_canonical_sha256"]
            or artifact["surface_coverage_sha256"]
            != expected[provenance_name]["runtime_operation_contract_sha256"]
            or artifact["source_revision"]
            != expected[provenance_name]["source_revision"]
        ):
            raise ReceiptError(
                f"Map runtime {provenance_name} OpenAPI is not bound to the pair"
            )
        _commit(
            artifact["source_revision"],
            name=f"Map runtime {provenance_name} OpenAPI.source_revision",
        )
        runtime_openapi[surface] = artifact
    if (
        runtime_openapi["full_openapi"]["canonical_sha256"]
        != runtime_openapi["admin_openapi"]["canonical_sha256"]
        or runtime_openapi["full_openapi"]["transport_sha256"]
        != runtime_openapi["admin_openapi"]["transport_sha256"]
    ):
        raise ReceiptError("Map full/admin runtime OpenAPI HTTP proofs do not match")
    for name in ("admin", "api", "frontend"):
        runtime_image = _object(runtime[name], name=f"Map runtime {name}")
        if set(runtime_image) != {
            "container_id",
            "digest",
            "environment",
            "image_id",
            "revision_label",
            "source_revision",
            "started_at",
        }:
            raise ReceiptError(f"Map runtime {name} evidence schema is invalid")
        if runtime_image["digest"] != runtime_image["image_id"]:
            raise ReceiptError(
                f"Map runtime {name} image ID is not bound to its digest"
            )
        if runtime_image["revision_label"] != runtime_image["source_revision"]:
            raise ReceiptError(
                f"Map runtime {name} source label is not self-consistent"
            )
        if runtime_image["environment"] != environment:
            raise ReceiptError(
                f"Map runtime {name} environment does not match receipt scope"
            )
        if runtime_image["source_revision"] != expected["admin"]["source_revision"]:
            raise ReceiptError(
                f"Map runtime {name} source revision does not match the pair"
            )
        _digest(runtime_image["digest"], name=f"Map runtime {name}.digest")
        _commit(
            runtime_image["source_revision"], name=f"Map runtime {name}.source_revision"
        )
        _string(runtime_image["environment"], name=f"Map runtime {name}.environment")
        if (
            not isinstance(runtime_image["container_id"], str)
            or re.fullmatch(r"[0-9a-f]{64}\Z", runtime_image["container_id"]) is None
            or not isinstance(runtime_image["started_at"], str)
            or not runtime_image["started_at"]
        ):
            raise ReceiptError(f"Map runtime {name} container identity is invalid")
    image_digests = {
        "admin": _digest(pair["admin_image_digest"], name="Map admin image digest"),
        "api": _digest(pair["api_image_digest"], name="Map API image digest"),
        "frontend": _digest(
            pair["frontend_image_digest"], name="Map frontend image digest"
        ),
    }
    expected_image_digests = _object(
        expected["runtime_image_digests"], name="Map expected runtime image digests"
    )
    for name, digest in image_digests.items():
        if digest != _digest(
            expected_image_digests[name], name=f"Map expected {name} image digest"
        ):
            raise ReceiptError(
                f"Map {name} image digest does not match the pinned runtime"
            )
        runtime_image = _object(runtime[name], name=f"Map runtime {name}")
        if digest != _digest(
            runtime_image["digest"], name=f"Map runtime {name} digest"
        ):
            raise ReceiptError(f"Map {name} image digest is not bound to its runtime")
    return {
        "admin_image_digest": image_digests["admin"],
        "map_admin_container_id": runtime["admin"]["container_id"],
        "admin_runtime_openapi_sha256": _sha256(
            runtime_openapi["admin_openapi"]["transport_sha256"],
            name="Map runtime admin OpenAPI.transport_sha256",
        ),
        "admin_runtime_operation_contract_sha256": expected["admin"][
            "runtime_operation_contract_sha256"
        ],
        "full_runtime_openapi_sha256": _sha256(
            runtime_openapi["full_openapi"]["transport_sha256"],
            name="Map runtime full OpenAPI.transport_sha256",
        ),
        "full_runtime_operation_contract_sha256": expected["full"][
            "runtime_operation_contract_sha256"
        ],
        "api_image_digest": image_digests["api"],
        "map_api_container_id": runtime["api"]["container_id"],
        "frontend_image_digest": image_digests["frontend"],
        "map_frontend_container_id": runtime["frontend"]["container_id"],
        "service_runtime_openapi_sha256": _sha256(
            runtime_openapi["service_openapi"]["transport_sha256"],
            name="Map runtime service OpenAPI.transport_sha256",
        ),
        "service_runtime_operation_contract_sha256": expected["service"][
            "runtime_operation_contract_sha256"
        ],
        "user_runtime_openapi_sha256": _sha256(
            runtime_openapi["user_openapi"]["transport_sha256"],
            name="Map runtime user OpenAPI.transport_sha256",
        ),
        "user_runtime_operation_contract_sha256": expected["user"][
            "runtime_operation_contract_sha256"
        ],
    }


def _pinvi_images(
    value: object, *, pinvi_source_revision: str, environment: str
) -> dict[str, str]:
    images = _object(value, name="Pinvi image evidence")
    if set(images) != {"api", "dagster", "web"}:
        raise ReceiptError("Pinvi image evidence schema is invalid")
    result: dict[str, str] = {}
    for name in ("api", "web", "dagster"):
        image = _object(images[name], name=f"Pinvi {name} image evidence")
        if set(image) != {
            "container_id",
            "digest",
            "environment",
            "image_id",
            "revision_label",
            "source_revision",
            "started_at",
        }:
            raise ReceiptError(f"Pinvi {name} image evidence schema is invalid")
        if image["environment"] != environment:
            raise ReceiptError(
                f"Pinvi {name} image environment does not match receipt scope"
            )
        if image["digest"] != image["image_id"]:
            raise ReceiptError(f"Pinvi {name} image ID is not bound to its digest")
        if image["revision_label"] != image["source_revision"]:
            raise ReceiptError(
                f"Pinvi {name} image source label is not self-consistent"
            )
        if (
            _commit(image["source_revision"], name=f"Pinvi {name}.source_revision")
            != pinvi_source_revision
        ):
            raise ReceiptError("Pinvi runtime images do not share one source revision")
        if (
            not isinstance(image["container_id"], str)
            or re.fullmatch(r"[0-9a-f]{64}\Z", image["container_id"]) is None
            or not isinstance(image["started_at"], str)
            or not image["started_at"]
        ):
            raise ReceiptError(f"Pinvi {name} container identity is invalid")
        result[name] = _digest(image["digest"], name=f"Pinvi {name}.digest")
        result[f"{name}_container_id"] = image["container_id"]
    return result


def _attestation(
    value: object,
    *,
    evidence_hashes: dict[str, str],
    live_ui: dict[str, str],
    pinvi_source_revision: str,
    scope: str,
    public_key_bytes: bytes,
    issued_at: int,
    expires_at: int,
    activation_nonce: str,
) -> str:
    envelope = _object(value, name="M05 live attestation")
    if set(envelope) != {"payload", "signature"} or not isinstance(
        envelope["signature"], str
    ):
        raise ReceiptError("M05 live attestation envelope is invalid")
    payload = _object(envelope["payload"], name="M05 live attestation payload")
    expected = {
        "created_at",
        "event_id",
        "evidence_sha256",
        "local_receipt_sha256",
        "map_admin_endpoint",
        "map_ack_sha256",
        "map_snapshot_sha256",
        "pinvi_snapshot_sha256",
        "pinvi_api_endpoint",
        "pinvi_web_endpoint",
        "pinvi_source_revision",
        "playwright_runner_image_id",
        "playwright_runner_image_ref",
        "scope",
        "status",
        "verification_id",
        "version",
    }
    if set(payload) != expected:
        raise ReceiptError("M05 live attestation payload schema is invalid")
    if (
        type(payload["version"]) is not int
        or payload["version"] != 1
        or payload["status"] != "passed"
        or payload["scope"] != scope
        or _commit(payload["pinvi_source_revision"], name="attestation source revision")
        != pinvi_source_revision
        or _uuid(payload["event_id"], name="attestation event ID")
        != live_ui["event_id"]
        or type(payload["created_at"]) is not int
        or payload["created_at"] < issued_at - 60
        or payload["created_at"] > issued_at + 15 * 60
        or payload["created_at"] > int(time.time()) + 60
    ):
        raise ReceiptError("M05 live attestation identity/status is invalid")
    verification_id = _uuid(
        payload["verification_id"], name="attestation verification ID"
    )
    if (
        verification_id != activation_nonce
        or verification_id != live_ui["verification_id"]
    ):
        raise ReceiptError(
            "M05 live attestation verification ID is not bound to the receipt nonce"
        )
    if (
        payload["playwright_runner_image_id"] != live_ui["playwright_runner_image_id"]
        or payload["playwright_runner_image_ref"]
        != live_ui["playwright_runner_image_ref"]
    ):
        raise ReceiptError("M05 live attestation does not bind the Playwright runner")
    _digest(
        payload["playwright_runner_image_id"],
        name="attestation.playwright_runner_image_id",
    )
    if _PLAYWRIGHT_IMAGE_RE.fullmatch(payload["playwright_runner_image_ref"]) is None:
        raise ReceiptError("M05 live attestation Playwright image reference is invalid")
    if payload["created_at"] > expires_at:
        raise ReceiptError("M05 live attestation is newer than the receipt expiry")
    for field, expected_endpoint in (
        ("map_admin_endpoint", live_ui["map_admin_endpoint"]),
        ("pinvi_api_endpoint", live_ui["pinvi_api_endpoint"]),
        ("pinvi_web_endpoint", live_ui["pinvi_web_endpoint"]),
    ):
        if payload[field] != expected_endpoint:
            raise ReceiptError(f"M05 live attestation does not bind {field}")
    if (
        _sha256(
            payload["local_receipt_sha256"], name="attestation.local_receipt_sha256"
        )
        != live_ui["map_local_receipt_sha256"]
        or live_ui["map_local_receipt_sha256"] != live_ui["pinvi_receipt_sha256"]
    ):
        raise ReceiptError(
            "M05 live attestation does not bind the terminal receipt hash"
        )
    for field, expected_value in (
        ("map_ack_sha256", live_ui["map_ack_sha256"]),
        ("map_snapshot_sha256", live_ui["map_snapshot_after_sha256"]),
        ("pinvi_snapshot_sha256", live_ui["pinvi_snapshot_after_sha256"]),
    ):
        if _sha256(payload[field], name=f"attestation.{field}") != expected_value:
            raise ReceiptError(f"M05 live attestation does not bind {field}")
    attested_hashes = _object(
        payload["evidence_sha256"], name="attestation evidence hashes"
    )
    if set(attested_hashes) != {
        "live-ui",
        "map-pair",
        "pinvi-images",
        "restore",
        "reviews",
    }:
        raise ReceiptError("M05 live attestation evidence inventory is invalid")
    for name in ("live-ui", "map-pair", "pinvi-images", "restore", "reviews"):
        if (
            _sha256(attested_hashes[name], name=f"attestation.{name}")
            != evidence_hashes[name]
        ):
            raise ReceiptError(f"M05 live attestation does not bind {name} evidence")
    signature_bytes = _decode_base64url(envelope["signature"], expected_length=64)
    if signature_bytes is None:
        raise ReceiptError("M05 live attestation signature encoding is invalid")
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes, _canonical_json(payload)
        )
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ReceiptError("M05 live attestation signature is invalid") from exc
    return verification_id


def _create(args: argparse.Namespace) -> int:
    evidence_dir = args.evidence_dir
    evidence_directory_fd = _open_secure_directory(
        evidence_dir, require_root_owned=args.require_root_owned
    )

    source_revision = _commit(args.pinvi_source_revision, name="Pinvi source revision")
    _assert_source_checkout(source_revision)
    if args.pr_url != _M05_ACTIVATION_PR_URL:
        raise ReceiptError("M05 activation receipt is pinned to PR #466")
    scope = _string(args.scope, name="receipt scope")
    if scope not in {"staging", "production"}:
        raise ReceiptError("receipt scope must be staging or production")
    now = int(time.time())
    issued_at = (
        args.activation_issued_at if args.activation_issued_at is not None else now
    )
    expires_at = (
        args.activation_expires_at
        if args.activation_expires_at is not None
        else now + 24 * 60 * 60
    )
    if type(issued_at) is not int or type(expires_at) is not int:
        raise ReceiptError("activation timestamps must be integers")
    if issued_at > now + 60 or expires_at <= now or expires_at <= issued_at:
        raise ReceiptError("activation receipt freshness window is invalid")
    if expires_at - issued_at > 7 * 24 * 60 * 60:
        raise ReceiptError("activation receipt lifetime exceeds seven days")
    paths = {
        name.removesuffix(".json").replace("-", "_"): Path(name)
        for name in _EVIDENCE_FILES
    }
    try:
        evidence: dict[str, object] = {}
        evidence_hashes: dict[str, str] = {}
        for key, path in paths.items():
            value, digest = _read_json(
                path,
                require_root_owned=args.require_root_owned,
                directory_fd=evidence_directory_fd,
            )
            evidence[key] = value
            evidence_hashes[key] = digest

        attestation_envelope = _object(
            evidence["attestation"], name="M05 live attestation"
        )
        attestation_payload = _object(
            attestation_envelope.get("payload"), name="M05 live attestation payload"
        )
        attestation_nonce = _uuid(
            attestation_payload.get("verification_id"),
            name="M05 attestation verification ID",
        )
        activation_nonce = _uuid(
            args.activation_nonce or attestation_nonce, name="activation nonce"
        )
        if activation_nonce != attestation_nonce:
            raise ReceiptError(
                "activation nonce must match the live attestation verification ID"
            )
        reviews = _reviews(
            evidence["reviews"],
            pinvi_source_revision=source_revision,
            expected_pr_url=args.pr_url,
        )
        live_ui = _live_ui(evidence["live_ui"], pinvi_source_revision=source_revision)
        _restore(evidence["restore"], pinvi_source_revision=source_revision)
        pair_expected = _pair_provenance()
        map_pair = _map_pair(evidence["map_pair"], pair_expected, environment=scope)
        pinvi_images = _pinvi_images(
            evidence["pinvi_images"],
            pinvi_source_revision=source_revision,
            environment=scope,
        )
    finally:
        os.close(evidence_directory_fd)

    private_key_bytes = _read_secure_bytes(
        args.private_key,
        require_root_owned=args.require_root_owned,
        label="private key",
    )
    try:
        private_key = serialization.load_pem_private_key(
            private_key_bytes, password=None
        )
    except (ValueError, TypeError) as exc:
        raise ReceiptError("private key is not valid PEM") from exc
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ReceiptError("private key is not Ed25519")
    public_key_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    if (
        args.require_root_owned
        and hashlib.sha256(public_key_raw).hexdigest() != _trust_anchor()
    ):
        raise ReceiptError("private key does not match the vendored M05 trust anchor")
    _attestation(
        evidence["attestation"],
        evidence_hashes={
            "live-ui": evidence_hashes["live_ui"],
            "map-pair": evidence_hashes["map_pair"],
            "pinvi-images": evidence_hashes["pinvi_images"],
            "restore": evidence_hashes["restore"],
            "reviews": evidence_hashes["reviews"],
        },
        live_ui=live_ui,
        pinvi_source_revision=source_revision,
        scope=scope,
        public_key_bytes=public_key_raw,
        issued_at=issued_at,
        expires_at=expires_at,
        activation_nonce=activation_nonce,
    )

    payload: dict[str, object] = {
        "activation_expires_at": expires_at,
        "activation_generation": args.activation_generation,
        "activation_issued_at": issued_at,
        "activation_nonce": activation_nonce,
        "activation_attestation_sha256": evidence_hashes["attestation"],
        "adversarial_reviews": reviews,
        "live_ui_e2e": "passed",
        "live_ui_event_id": live_ui["event_id"],
        "live_ui_evidence_sha256": evidence_hashes["live_ui"],
        "live_ui_map_ack_sha256": live_ui["map_ack_sha256"],
        "live_ui_local_receipt_sha256": live_ui["map_local_receipt_sha256"],
        "live_ui_map_admin_endpoint": live_ui["map_admin_endpoint"],
        "live_ui_map_snapshot_sha256": live_ui["map_snapshot_after_sha256"],
        "live_ui_pinvi_api_endpoint": live_ui["pinvi_api_endpoint"],
        "live_ui_pinvi_snapshot_sha256": live_ui["pinvi_snapshot_after_sha256"],
        "live_ui_pinvi_web_endpoint": live_ui["pinvi_web_endpoint"],
        "live_ui_playwright_runner_image_id": live_ui["playwright_runner_image_id"],
        "live_ui_playwright_runner_image_ref": live_ui["playwright_runner_image_ref"],
        "live_ui_verification_id": live_ui["verification_id"],
        "map_admin_openapi_sha256": pair_expected["admin"]["openapi_sha256"],
        "map_admin_runtime_openapi_sha256": map_pair["admin_runtime_openapi_sha256"],
        "map_admin_runtime_operation_contract_sha256": map_pair[
            "admin_runtime_operation_contract_sha256"
        ],
        "map_admin_source_operation_contract_sha256": pair_expected["admin"][
            "source_operation_contract_sha256"
        ],
        "map_admin_source_revision": pair_expected["admin"]["source_revision"],
        "map_admin_image_digest": map_pair["admin_image_digest"],
        "map_admin_container_id": map_pair["map_admin_container_id"],
        "map_api_image_digest": map_pair["api_image_digest"],
        "map_api_container_id": map_pair["map_api_container_id"],
        "map_frontend_image_digest": map_pair["frontend_image_digest"],
        "map_frontend_container_id": map_pair["map_frontend_container_id"],
        "map_full_openapi_sha256": pair_expected["full"]["openapi_sha256"],
        "map_full_runtime_openapi_sha256": map_pair["full_runtime_openapi_sha256"],
        "map_full_runtime_operation_contract_sha256": map_pair[
            "full_runtime_operation_contract_sha256"
        ],
        "map_full_source_operation_contract_sha256": pair_expected["full"][
            "source_operation_contract_sha256"
        ],
        "map_full_source_revision": pair_expected["full"]["source_revision"],
        "map_pair_evidence_sha256": evidence_hashes["map_pair"],
        "map_service_openapi_sha256": pair_expected["service"]["openapi_sha256"],
        "map_service_runtime_openapi_sha256": map_pair[
            "service_runtime_openapi_sha256"
        ],
        "map_service_runtime_operation_contract_sha256": map_pair[
            "service_runtime_operation_contract_sha256"
        ],
        "map_service_source_operation_contract_sha256": pair_expected["service"][
            "source_operation_contract_sha256"
        ],
        "map_service_source_revision": pair_expected["service"]["source_revision"],
        "map_user_openapi_sha256": pair_expected["user"]["openapi_sha256"],
        "map_user_runtime_openapi_sha256": map_pair["user_runtime_openapi_sha256"],
        "map_user_runtime_operation_contract_sha256": map_pair[
            "user_runtime_operation_contract_sha256"
        ],
        "map_user_source_operation_contract_sha256": pair_expected["user"][
            "source_operation_contract_sha256"
        ],
        "map_user_source_revision": pair_expected["user"]["source_revision"],
        "pinvi_api_image_digest": pinvi_images["api"],
        "pinvi_api_container_id": pinvi_images["api_container_id"],
        "pinvi_dagster_image_digest": pinvi_images["dagster"],
        "pinvi_dagster_container_id": pinvi_images["dagster_container_id"],
        "pinvi_image_evidence_sha256": evidence_hashes["pinvi_images"],
        "pinvi_source_revision": source_revision,
        "pinvi_web_container_id": pinvi_images["web_container_id"],
        "pinvi_web_image_digest": pinvi_images["web"],
        "restore_drill": "passed",
        "restore_evidence_sha256": evidence_hashes["restore"],
        "review_evidence_sha256": evidence_hashes["reviews"],
        "scope": scope,
        "version": 1,
    }
    signed = {
        "payload": payload,
        "signature": _base64url(private_key.sign(_canonical_json(payload))),
    }
    _write_new_json(args.output, signed)
    print(f"receipt_sha256={hashlib.sha256(args.output.read_bytes()).hexdigest()}")
    print(
        f"public_key={_base64url(private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))}"
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--evidence-dir", type=Path, required=True)
    create.add_argument("--private-key", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument(
        "--pinvi-source-revision", default=os.environ.get("PINVI_SOURCE_REVISION", "")
    )
    create.add_argument(
        "--scope", choices=("staging", "production"), default="production"
    )
    create.add_argument("--pr-url", default=_M05_ACTIVATION_PR_URL)
    create.add_argument("--activation-generation", type=int, required=True)
    create.add_argument("--activation-nonce")
    create.add_argument("--activation-issued-at", type=int)
    create.add_argument("--activation-expires-at", type=int)
    create.add_argument("--require-root-owned", action="store_true")
    create.set_defaults(handler=_create)
    ledger = subparsers.add_parser("ledger")
    ledger.add_argument("--receipt", type=Path, required=True)
    ledger.add_argument("--ledger", type=Path, required=True)
    ledger.add_argument("--high-watermark", type=Path, required=True)
    ledger.add_argument("--require-root-owned", action="store_true")
    ledger.set_defaults(handler=_ledger)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return cast(int, args.handler(args))
    except (OSError, ReceiptError, binascii.Error) as exc:
        raise SystemExit(f"M05 activation receipt failed: {exc}") from None


if __name__ == "__main__":
    raise SystemExit(main())
