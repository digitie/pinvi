#!/usr/bin/env python3
"""M05 paired live/restore/review evidence를 서명된 production receipt로 봉인한다."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import cast
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PAIR_PROVENANCE = Path(__file__).resolve().parents[1] / (
    "contracts/kor-travel-map-m05-pair-provenance-v1.json"
)
_EVIDENCE_FILES = (
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


def _read_json(path: Path, *, require_root_owned: bool) -> object:
    if path.is_symlink() or not path.is_file():
        raise ReceiptError(f"evidence file is not a regular file: {path.name}")
    file_stat = path.stat()
    if stat.S_IMODE(file_stat.st_mode) != 0o600:
        raise ReceiptError(f"evidence file mode is not 0600: {path.name}")
    if require_root_owned and file_stat.st_uid != 0:
        raise ReceiptError(f"evidence file is not root-owned: {path.name}")
    try:
        return json.loads(path.read_bytes(), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ReceiptError) as exc:
        raise ReceiptError(f"evidence JSON is invalid: {path.name}") from exc


def _write_new_json(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink():
        raise ReceiptError(f"output already exists: {path}")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    )
    os.chmod(path, 0o600)


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


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pair_provenance() -> dict[str, dict[str, str]]:
    try:
        raw = json.loads(
            _PAIR_PROVENANCE.read_bytes(), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ReceiptError) as exc:
        raise ReceiptError("pair provenance file is invalid") from exc
    payload = _object(raw, name="pair provenance")
    if set(payload) != {"map", "version"} or payload["version"] != 1:
        raise ReceiptError("pair provenance envelope is invalid")
    map_value = _object(payload["map"], name="pair provenance map")
    result: dict[str, dict[str, str]] = {}
    for name in ("admin", "full", "service", "user"):
        entry = _object(map_value.get(name), name=f"pair provenance {name}")
        if set(entry) != {"openapi_sha256", "source_revision"}:
            raise ReceiptError(f"pair provenance {name} schema is invalid")
        result[name] = {
            "openapi_sha256": _sha256(
                entry["openapi_sha256"], name=f"{name}.openapi_sha256"
            ),
            "source_revision": _commit(
                entry["source_revision"], name=f"{name}.source_revision"
            ),
        }
    return result


def _reviews(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) != 2:
        raise ReceiptError("reviews.json must contain exactly two reviews")
    result: list[dict[str, object]] = []
    for item in value:
        review = _object(item, name="review")
        if set(review) != {"commit", "p0_p1", "review_id", "reviewer_id"}:
            raise ReceiptError("review schema is invalid")
        if type(review["p0_p1"]) is not int or review["p0_p1"] != 0:
            raise ReceiptError("review P0/P1 count must be zero")
        result.append(
            {
                "commit": _commit(review["commit"], name="review.commit"),
                "p0_p1": 0,
                "review_id": _string(review["review_id"], name="review.review_id"),
                "reviewer_id": _string(
                    review["reviewer_id"], name="review.reviewer_id"
                ),
            }
        )
    return result


def _live_ui(value: object, *, pinvi_source_revision: str) -> dict[str, str]:
    live = _object(value, name="live-ui evidence")
    expected = {
        "event_id",
        "event_sha256",
        "map_ack_sha256",
        "pinvi_source_revision",
        "runner_exit_code",
        "server_side_ack_verified",
        "status",
    }
    if set(live) != expected or live["status"] != "passed":
        raise ReceiptError("live-ui evidence schema/status is invalid")
    if type(live["runner_exit_code"]) is not int or live["runner_exit_code"] != 0:
        raise ReceiptError("live-ui runner did not exit successfully")
    if live["server_side_ack_verified"] is not True:
        raise ReceiptError("live-ui server-side Map ACK was not verified")
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
        "pinvi_source_revision": pinvi_source_revision,
    }


def _restore(value: object) -> None:
    restore = _object(value, name="restore evidence")
    expected = {
        "dump_sha256",
        "no_owner_restore",
        "restore_command",
        "runtime_role_verified",
        "source_db_identity_sha256",
        "status",
        "target_db_identity_sha256",
        "trigger_guard_verified",
    }
    if set(restore) != expected or restore["status"] != "passed":
        raise ReceiptError("restore evidence schema/status is invalid")
    if restore["restore_command"] != "pg_restore --no-owner --no-privileges":
        raise ReceiptError("restore evidence is not a no-owner restore")
    for field in (
        "no_owner_restore",
        "runtime_role_verified",
        "trigger_guard_verified",
    ):
        if restore[field] is not True:
            raise ReceiptError(f"restore evidence flag is not true: {field}")
    for field in (
        "dump_sha256",
        "source_db_identity_sha256",
        "target_db_identity_sha256",
    ):
        _sha256(restore[field], name=f"restore.{field}")


def _map_pair(value: object, expected: dict[str, dict[str, str]]) -> dict[str, str]:
    pair = _object(value, name="Map pair evidence")
    if set(pair) != {
        "admin",
        "admin_image_digest",
        "api_image_digest",
        "frontend_image_digest",
        "full",
        "service",
        "user",
    }:
        raise ReceiptError("Map pair evidence schema is invalid")
    for name in ("admin", "full", "service", "user"):
        entry = _object(pair[name], name=f"Map pair {name}")
        if set(entry) != {"openapi_sha256", "source_revision"}:
            raise ReceiptError(f"Map pair {name} evidence schema is invalid")
        for field in ("openapi_sha256", "source_revision"):
            if entry[field] != expected[name][field]:
                raise ReceiptError(
                    f"Map pair {name} does not match the vendored provenance"
                )
    return {
        "admin_image_digest": _digest(
            pair["admin_image_digest"], name="Map admin image digest"
        ),
        "api_image_digest": _digest(
            pair["api_image_digest"], name="Map API image digest"
        ),
        "frontend_image_digest": _digest(
            pair["frontend_image_digest"], name="Map frontend image digest"
        ),
    }


def _pinvi_images(value: object, *, pinvi_source_revision: str) -> dict[str, str]:
    images = _object(value, name="Pinvi image evidence")
    if set(images) != {"api", "dagster", "web"}:
        raise ReceiptError("Pinvi image evidence schema is invalid")
    result: dict[str, str] = {}
    for name in ("api", "web", "dagster"):
        image = _object(images[name], name=f"Pinvi {name} image evidence")
        if set(image) != {"digest", "environment", "source_revision"}:
            raise ReceiptError(f"Pinvi {name} image evidence schema is invalid")
        if image["environment"] != "production":
            raise ReceiptError(f"Pinvi {name} image environment is not production")
        if (
            _commit(image["source_revision"], name=f"Pinvi {name}.source_revision")
            != pinvi_source_revision
        ):
            raise ReceiptError("Pinvi runtime images do not share one source revision")
        result[name] = _digest(image["digest"], name=f"Pinvi {name}.digest")
    return result


def _create(args: argparse.Namespace) -> int:
    evidence_dir = args.evidence_dir
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        raise ReceiptError("evidence directory must be a regular directory")
    evidence_dir = evidence_dir.resolve(strict=True)
    directory_stat = evidence_dir.stat()
    if stat.S_IMODE(directory_stat.st_mode) != 0o700:
        raise ReceiptError("evidence directory mode is not 0700")
    if args.require_root_owned and directory_stat.st_uid != 0:
        raise ReceiptError("evidence directory is not root-owned")

    source_revision = _commit(args.pinvi_source_revision, name="Pinvi source revision")
    paths = {
        name.removesuffix(".json").replace("-", "_"): evidence_dir / name
        for name in _EVIDENCE_FILES
    }
    evidence = {
        key: _read_json(path, require_root_owned=args.require_root_owned)
        for key, path in paths.items()
    }
    reviews = _reviews(evidence["reviews"])
    live_ui = _live_ui(evidence["live_ui"], pinvi_source_revision=source_revision)
    _restore(evidence["restore"])
    pair_expected = _pair_provenance()
    map_pair = _map_pair(evidence["map_pair"], pair_expected)
    pinvi_images = _pinvi_images(
        evidence["pinvi_images"], pinvi_source_revision=source_revision
    )

    private_key_path = args.private_key
    if (
        private_key_path.is_symlink()
        or stat.S_IMODE(private_key_path.stat().st_mode) != 0o600
    ):
        raise ReceiptError("private key must be a non-symlink 0600 file")
    private_key_path = private_key_path.resolve(strict=True)
    if args.require_root_owned and private_key_path.stat().st_uid != 0:
        raise ReceiptError("private key is not root-owned")
    try:
        private_key = serialization.load_pem_private_key(
            private_key_path.read_bytes(), password=None
        )
    except (ValueError, TypeError) as exc:
        raise ReceiptError("private key is not valid PEM") from exc
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ReceiptError("private key is not Ed25519")

    payload: dict[str, object] = {
        "adversarial_reviews": reviews,
        "live_ui_e2e": "passed",
        "live_ui_event_id": live_ui["event_id"],
        "live_ui_evidence_sha256": _file_sha256(paths["live_ui"]),
        "live_ui_map_ack_sha256": live_ui["map_ack_sha256"],
        "map_admin_openapi_sha256": pair_expected["admin"]["openapi_sha256"],
        "map_admin_source_revision": pair_expected["admin"]["source_revision"],
        "map_admin_image_digest": map_pair["admin_image_digest"],
        "map_api_image_digest": map_pair["api_image_digest"],
        "map_frontend_image_digest": map_pair["frontend_image_digest"],
        "map_full_openapi_sha256": pair_expected["full"]["openapi_sha256"],
        "map_full_source_revision": pair_expected["full"]["source_revision"],
        "map_pair_evidence_sha256": _file_sha256(paths["map_pair"]),
        "map_service_openapi_sha256": pair_expected["service"]["openapi_sha256"],
        "map_service_source_revision": pair_expected["service"]["source_revision"],
        "map_user_openapi_sha256": pair_expected["user"]["openapi_sha256"],
        "map_user_source_revision": pair_expected["user"]["source_revision"],
        "pinvi_api_image_digest": pinvi_images["api"],
        "pinvi_dagster_image_digest": pinvi_images["dagster"],
        "pinvi_image_evidence_sha256": _file_sha256(paths["pinvi_images"]),
        "pinvi_source_revision": source_revision,
        "pinvi_web_image_digest": pinvi_images["web"],
        "restore_drill": "passed",
        "restore_evidence_sha256": _file_sha256(paths["restore"]),
        "review_evidence_sha256": _file_sha256(paths["reviews"]),
        "scope": "production",
        "version": 1,
    }
    signed = {
        "payload": payload,
        "signature": _base64url(private_key.sign(_canonical_json(payload))),
    }
    _write_new_json(args.output.resolve(), signed)
    print(f"receipt_sha256={_file_sha256(args.output)}")
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
    create.add_argument("--require-root-owned", action="store_true")
    create.set_defaults(handler=_create)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, ReceiptError, binascii.Error) as exc:
        raise SystemExit(f"M05 activation receipt failed: {exc}") from None


if __name__ == "__main__":
    raise SystemExit(main())
