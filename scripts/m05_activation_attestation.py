#!/usr/bin/env python3
"""M05 live UI와 paired runtime의 원격 상태를 독립적으로 검증한다.

``live`` 명령은 다음 순서를 고정한다.

1. Map case detail과 PinVi local receipt를 읽는다.
2. 호출자가 넘긴 실제 Playwright 명령을 실행한다.
3. 같은 두 snapshot을 다시 읽고, read-only UI 흐름 중 drift가 없었는지 확인한다.
4. 컨테이너 image ID/OCI label과 vendored Map OpenAPI를 확인한다.
5. 검증 결과를 signer가 확인할 수 있는 signed attestation으로 봉인한다.

운영에서는 명령행에 secret을 넣지 않는다. Map proxy secret과 PinVi admin 자격은
각각 ``M05_MAP_ADMIN_PROXY_SECRET``, ``M05_PINVI_EMAIL``,
``M05_PINVI_PASSWORD`` 환경변수로만 받는다.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import subprocess
import time
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PAIR_PATH = Path(__file__).resolve().parents[1] / (
    "contracts/kor-travel-map-m05-pair-provenance-v1.json"
)


class AttestationError(ValueError):
    """원격 live evidence가 attestation 계약을 위반했다."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AttestationError("duplicate JSON key")
        result[key] = value
    return result


def _object(value: object, *, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AttestationError(f"{name} must be an object")
    return cast(dict[str, object], value)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _string(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        raise AttestationError(f"{name} must be a non-empty token-free string")
    return value


def _commit(value: object, *, name: str) -> str:
    value = _string(value, name=name)
    if _COMMIT_RE.fullmatch(value) is None:
        raise AttestationError(f"{name} must be a full lowercase commit")
    return value


def _uuid(value: object, *, name: str) -> str:
    value = _string(value, name=name)
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except ValueError as exc:
        raise AttestationError(f"{name} must be a canonical UUID") from exc
    return value


def _read_json(path: Path) -> tuple[object, str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttestationError) as exc:
        raise AttestationError(f"invalid JSON evidence: {path.name}") from exc
    return value, _sha256(raw)


def _secure_read(path: Path, *, require_root_owned: bool, label: str) -> bytes:
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise AttestationError(f"{label} is not readable") from exc
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise AttestationError(f"{label} must be a 0600 regular file")
        if require_root_owned and metadata.st_uid != 0:
            raise AttestationError(f"{label} must be root-owned")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            return stream.read()
    finally:
        if fd != -1:
            os.close(fd)


def _write_json(path: Path, value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode(
        "utf-8"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise AttestationError(
            f"evidence output already exists or is unsafe: {path.name}"
        ) from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd != -1:
            os.close(fd)
    return _sha256(raw)


def _load_pair() -> dict[str, dict[str, str]]:
    raw, _ = _read_json(_PAIR_PATH)
    envelope = _object(raw, name="Map pair provenance")
    if set(envelope) != {"map", "version"} or envelope["version"] != 1:
        raise AttestationError("Map pair provenance envelope is invalid")
    map_value = _object(envelope["map"], name="Map pair provenance map")
    if set(map_value) != {"admin", "full", "service", "user"}:
        raise AttestationError("Map pair provenance inventory is invalid")
    result: dict[str, dict[str, str]] = {}
    for name in ("admin", "full", "service", "user"):
        entry = _object(map_value[name], name=f"Map pair {name}")
        if set(entry) != {"openapi_sha256", "source_revision"}:
            raise AttestationError(f"Map pair {name} schema is invalid")
        digest = _string(entry["openapi_sha256"], name=f"{name}.openapi_sha256")
        if _SHA256_RE.fullmatch(digest) is None:
            raise AttestationError(f"{name}.openapi_sha256 is invalid")
        result[name] = {
            "openapi_sha256": digest,
            "source_revision": _commit(
                entry["source_revision"], name=f"{name}.source_revision"
            ),
        }
    return result


def _url(base: str, path: str) -> str:
    base = _string(base.rstrip("/"), name="URL")
    if not base.startswith(("http://", "https://")):
        raise AttestationError("URL must use http or https")
    return f"{base}{path}"


def _http_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    opener: Any | None = None,
    method: str = "GET",
    body: object | None = None,
) -> tuple[object, bytes]:
    request = Request(
        url,
        data=None if body is None else _canonical_json(body),
        headers={"Accept": "application/json", **(headers or {})},
        method=method,
    )
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with (opener or build_opener()).open(request, timeout=30) as response:
            raw = response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise AttestationError(f"live HTTP verification failed: {url}") from exc
    try:
        return json.loads(raw, object_pairs_hook=_reject_duplicate_keys), raw
    except (UnicodeDecodeError, json.JSONDecodeError, AttestationError) as exc:
        raise AttestationError(f"live HTTP response is not valid JSON: {url}") from exc


def _data(value: object, *, name: str) -> dict[str, object]:
    envelope = _object(value, name=name)
    data = envelope.get("data")
    return _object(data, name=f"{name}.data")


def _map_headers() -> dict[str, str]:
    secret = os.environ.get("M05_MAP_ADMIN_PROXY_SECRET", "")
    actor = os.environ.get("M05_MAP_ADMIN_ACTOR", "pinvi-m05-attestation")
    if not secret or any(char.isspace() for char in secret):
        raise AttestationError(
            "M05_MAP_ADMIN_PROXY_SECRET must be supplied via environment"
        )
    return {
        "X-Kor-Travel-Map-Admin-Proxy-Secret": secret,
        "X-Kor-Travel-Map-Actor": _string(actor, name="M05_MAP_ADMIN_ACTOR"),
    }


def _map_case_snapshot(
    *,
    map_admin_url: str,
    case_id: str,
    event_id: str,
) -> tuple[dict[str, object], dict[str, object], str, str]:
    value, _ = _http_json(
        _url(map_admin_url, f"/v1/admin/manual-provider-dedup-cases/{case_id}"),
        headers=_map_headers(),
    )
    data = _data(value, name="Map case detail")
    if data.get("status") != "terminal":
        raise AttestationError("Map M05 case is not terminal")
    event = _object(data.get("event"), name="Map case event")
    if _uuid(event.get("event_id"), name="Map event ID") != event_id:
        raise AttestationError("Map case event does not match the requested event")
    event_sha = _string(event.get("event_sha256"), name="Map event hash")
    if _SHA256_RE.fullmatch(event_sha) is None:
        raise AttestationError("Map event hash is invalid")
    sequence = event.get("event_sequence")
    if type(sequence) is not int or sequence < 1:
        raise AttestationError("Map event sequence is invalid")
    subscriptions = data.get("subscriptions")
    if not isinstance(subscriptions, list):
        raise AttestationError("Map subscription delivery evidence is missing")
    expected_principal = "service:feature-reference-reconciliation"
    matching = [
        _object(item, name="Map subscription")
        for item in subscriptions
        if isinstance(item, dict) and item.get("principal_id") == expected_principal
    ]
    if len(matching) != 1:
        raise AttestationError("Map M05 service subscription is not unique")
    subscription = matching[0]
    acked = subscription.get("acked_through_sequence")
    if type(acked) is not int or acked < sequence:
        raise AttestationError("Map ACK cursor has not reached the event")
    ack = _object(subscription.get("ack"), name="Map ACK")
    if (
        _uuid(ack.get("event_id"), name="Map ACK event ID") != event_id
        or ack.get("event_sha256") != event_sha
    ):
        raise AttestationError("Map ACK does not bind to the event")
    local_receipt_sha = _string(
        ack.get("local_receipt_sha256"), name="Map local receipt hash"
    )
    if _SHA256_RE.fullmatch(local_receipt_sha) is None:
        raise AttestationError("Map local receipt hash is invalid")
    map_data_hash = _sha256(_canonical_json(data))
    ack_hash = _sha256(_canonical_json(ack))
    return data, ack, map_data_hash, ack_hash


def _pinvi_case_snapshot(
    *,
    pinvi_api_url: str,
    event_id: str,
    email: str,
    password: str,
) -> tuple[dict[str, object], str]:
    if not email or not password:
        raise AttestationError("M05_PINVI_EMAIL and M05_PINVI_PASSWORD are required")
    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    login, _ = _http_json(
        _url(pinvi_api_url, "/auth/login"),
        opener=opener,
        method="POST",
        body={"email": email, "password": password},
    )
    login_data = _data(login, name="Pinvi login")
    roles = login_data.get("roles")
    if not isinstance(roles, list) or not any(
        role in {"admin", "operator", "cpo"} for role in roles
    ):
        raise AttestationError("Pinvi live account is not an admin role")
    value, _ = _http_json(
        _url(pinvi_api_url, f"/admin/feature-reference-reconciliations/{event_id}"),
        opener=opener,
    )
    data = _data(value, name="Pinvi M05 detail")
    if data.get("status") != "applied":
        raise AttestationError("Pinvi M05 local receipt is not applied")
    receipt = _object(data.get("receipt"), name="Pinvi local receipt")
    if _uuid(receipt.get("event_id"), name="Pinvi receipt event ID") != event_id:
        raise AttestationError("Pinvi receipt does not match the requested event")
    event_sha = _string(receipt.get("event_sha256"), name="Pinvi receipt event hash")
    if _SHA256_RE.fullmatch(event_sha) is None:
        raise AttestationError("Pinvi receipt event hash is invalid")
    attempts = data.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise AttestationError("Pinvi M05 delivery attempts are missing")
    latest = _object(attempts[0], name="Pinvi latest attempt")
    if latest.get("status") != "applied" or latest.get("event_sha256") != event_sha:
        raise AttestationError("Pinvi latest attempt is not the applied event")
    impacts = data.get("impacts")
    if not isinstance(impacts, list) or len(impacts) != receipt.get("impact_count"):
        raise AttestationError("Pinvi impact count does not match its terminal receipt")
    return data, _sha256(_canonical_json(data))


def _docker_inspect(
    container: str,
    *,
    expected_revision: str,
    expected_environment: str,
    require_environment_label: bool = True,
) -> dict[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", container):
        raise AttestationError("container name is invalid")
    try:
        completed = subprocess.run(
            ["docker", "inspect", "--format", "{{json .}}", container],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AttestationError(f"docker inspect failed for {container}") from exc
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AttestationError(
            f"docker inspect output is invalid for {container}"
        ) from exc
    item = _object(value, name=f"docker inspect {container}")
    image_id = item.get("Image")
    if not isinstance(image_id, str) or _DIGEST_RE.fullmatch(image_id) is None:
        raise AttestationError(f"runtime image ID is not immutable for {container}")
    config = _object(item.get("Config"), name=f"docker config {container}")
    labels = config.get("Labels")
    labels = (
        _object(labels, name=f"docker labels {container}") if labels is not None else {}
    )
    revision = _string(
        labels.get("org.opencontainers.image.revision"),
        name=f"{container}.org.opencontainers.image.revision",
    )
    if revision != expected_revision:
        raise AttestationError(f"runtime source revision mismatch for {container}")
    environment_label = labels.get("io.pinvi.build.environment")
    if require_environment_label and environment_label is None:
        raise AttestationError(
            f"runtime build environment label is missing for {container}"
        )
    if (
        environment_label is not None
        and _string(environment_label, name=f"{container}.io.pinvi.build.environment")
        != expected_environment
    ):
        raise AttestationError(f"runtime build environment mismatch for {container}")
    return {
        "digest": image_id,
        "image_id": image_id,
        "environment": expected_environment,
        "source_revision": expected_revision,
        "revision_label": revision,
    }


def _git_blob(source_root: Path, *, revision: str, relative_path: str) -> bytes:
    if source_root.is_symlink() or not source_root.is_dir():
        raise AttestationError("Map source root must be a regular directory")
    try:
        completed = subprocess.run(
            ["git", "-C", str(source_root), "show", f"{revision}:{relative_path}"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AttestationError(
            f"Map source revision does not contain the pinned artifact: {revision}:{relative_path}"
        ) from exc
    return completed.stdout


def _hash_source_openapi(source_root: Path) -> dict[str, str]:
    expected = _load_pair()
    paths = {
        "admin": "packages/kor-travel-map-api/openapi.json",
        "full": "packages/kor-travel-map-api/openapi.json",
        "service": "packages/kor-travel-map-api/openapi.service.json",
        "user": "packages/kor-travel-map-api/openapi.user.json",
    }
    actual: dict[str, str] = {}
    for name, relative_path in paths.items():
        revision = _commit(
            expected[name]["source_revision"], name=f"{name}.source_revision"
        )
        digest = _sha256(
            _git_blob(source_root, revision=revision, relative_path=relative_path)
        )
        if digest != expected[name]["openapi_sha256"]:
            raise AttestationError(
                f"Map source OpenAPI does not match the tracked pair: {name}"
            )
        actual[name] = digest
    return actual


def _validate_ui_marker(value: object, *, event_id: str) -> None:
    marker = _object(value, name="UI evidence marker")
    expected = {
        "assertions",
        "event_id",
        "impact_count",
        "old_feature_id",
        "pinvi_detail_sha256",
        "replacement_feature_id",
        "status",
    }
    if set(marker) != expected or marker.get("status") != "passed":
        raise AttestationError("UI evidence marker schema/status is invalid")
    if _uuid(marker.get("event_id"), name="UI marker event ID") != event_id:
        raise AttestationError("UI marker event does not match the requested event")
    if not isinstance(marker["assertions"], list) or not marker["assertions"]:
        raise AttestationError("UI marker assertions are missing")
    if not isinstance(marker["impact_count"], int) or marker["impact_count"] < 0:
        raise AttestationError("UI marker impact count is invalid")
    digest = marker["pinvi_detail_sha256"]
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise AttestationError("UI marker Pinvi detail hash is invalid")


def _load_private_key(path: Path, *, require_root_owned: bool) -> Ed25519PrivateKey:
    raw = _secure_read(
        path, require_root_owned=require_root_owned, label="M05 private key"
    )
    try:
        value = serialization.load_pem_private_key(raw, password=None)
    except (TypeError, ValueError) as exc:
        raise AttestationError("M05 private key is invalid") from exc
    if not isinstance(value, Ed25519PrivateKey):
        raise AttestationError("M05 private key is not Ed25519")
    return value


def _live(args: argparse.Namespace) -> int:
    evidence_dir: Path = args.evidence_dir
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        raise AttestationError("evidence directory must already exist")
    metadata = evidence_dir.stat()
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise AttestationError("evidence directory mode must be 0700")
    if args.require_root_owned and metadata.st_uid != 0:
        raise AttestationError("evidence directory must be root-owned")

    event_id = _uuid(args.event_id, name="M05 event ID")
    case_id = _uuid(args.map_case_id, name="Map case ID")
    source_revision = _commit(args.pinvi_source_revision, name="Pinvi source revision")
    if args.scope not in {"staging", "production"}:
        raise AttestationError("attestation scope must be staging or production")
    email = os.environ.get("M05_PINVI_EMAIL", "")
    password = os.environ.get("M05_PINVI_PASSWORD", "")

    before_map, _before_ack, before_map_hash, _before_ack_hash = _map_case_snapshot(
        map_admin_url=args.map_admin_url,
        case_id=case_id,
        event_id=event_id,
    )
    before_pinvi, before_pinvi_hash = _pinvi_case_snapshot(
        pinvi_api_url=args.pinvi_api_url,
        event_id=event_id,
        email=email,
        password=password,
    )

    command = list(args.ui_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise AttestationError("a real Playwright command is required after --")
    child_env = os.environ.copy()
    child_env["PINVI_M05_UI_EVIDENCE_DIR"] = str(evidence_dir)
    child_env["PINVI_M05_LIVE_EVENT_ID"] = event_id
    completed = subprocess.run(command, check=False, env=child_env)
    if completed.returncode != 0:
        raise AttestationError(f"live UI command exited with {completed.returncode}")
    marker_path = evidence_dir / "ui-run.json"
    marker, marker_raw_hash = _read_json(marker_path)
    _validate_ui_marker(marker, event_id=event_id)

    after_map, _after_ack, after_map_hash, after_ack_hash = _map_case_snapshot(
        map_admin_url=args.map_admin_url,
        case_id=case_id,
        event_id=event_id,
    )
    after_pinvi, after_pinvi_hash = _pinvi_case_snapshot(
        pinvi_api_url=args.pinvi_api_url,
        event_id=event_id,
        email=email,
        password=password,
    )
    if before_map_hash != after_map_hash or before_pinvi_hash != after_pinvi_hash:
        raise AttestationError("M05 remote state drifted during the read-only UI flow")
    if before_map != after_map or before_pinvi != after_pinvi:
        raise AttestationError(
            "M05 remote snapshot is not byte-stable across the UI flow"
        )

    pair = _load_pair()
    source_openapi = _hash_source_openapi(args.map_source_root)
    runtime_map_api = _docker_inspect(
        args.map_api_container,
        expected_revision=pair["admin"]["source_revision"],
        expected_environment=args.scope,
        require_environment_label=False,
    )
    runtime_map_frontend = _docker_inspect(
        args.map_frontend_container,
        expected_revision=pair["admin"]["source_revision"],
        expected_environment=args.scope,
        require_environment_label=False,
    )
    map_pair = {
        "admin": pair["admin"],
        "full": pair["full"],
        "service": pair["service"],
        "user": pair["user"],
        "admin_image_digest": runtime_map_frontend["digest"],
        "api_image_digest": runtime_map_api["digest"],
        "frontend_image_digest": runtime_map_frontend["digest"],
        "runtime": {
            "api": runtime_map_api,
            "frontend": runtime_map_frontend,
            "full_openapi_sha256": source_openapi["full"],
        },
    }
    pinvi_images = {
        name: _docker_inspect(
            container,
            expected_revision=source_revision,
            expected_environment=args.scope,
        )
        for name, container in (
            ("api", args.pinvi_api_container),
            ("web", args.pinvi_web_container),
            ("dagster", args.pinvi_dagster_container),
        )
    }

    live_ui = {
        "event_id": event_id,
        "event_sha256": _string(
            _object(after_map["event"], name="Map event")["event_sha256"],
            name="event hash",
        ),
        "map_ack_sha256": after_ack_hash,
        "map_snapshot_before_sha256": before_map_hash,
        "map_snapshot_after_sha256": after_map_hash,
        "pinvi_snapshot_before_sha256": before_pinvi_hash,
        "pinvi_snapshot_after_sha256": after_pinvi_hash,
        "pinvi_source_revision": source_revision,
        "runner_exit_code": completed.returncode,
        "server_side_ack_verified": True,
        "status": "passed",
        "ui_evidence_sha256": marker_raw_hash,
    }
    output_hashes = {
        "live-ui": _write_json(evidence_dir / "live-ui.json", live_ui),
        "map-pair": _write_json(evidence_dir / "map-pair.json", map_pair),
        "pinvi-images": _write_json(evidence_dir / "pinvi-images.json", pinvi_images),
    }
    for name in ("reviews", "restore"):
        path = evidence_dir / f"{name}.json"
        _value, output_hashes[name] = _read_json(path)

    private_key = _load_private_key(
        args.private_key, require_root_owned=args.require_root_owned
    )
    attestation_payload = {
        "created_at": int(time.time()),
        "event_id": event_id,
        "evidence_sha256": output_hashes,
        "map_ack_sha256": after_ack_hash,
        "map_snapshot_sha256": after_map_hash,
        "pinvi_snapshot_sha256": after_pinvi_hash,
        "pinvi_source_revision": source_revision,
        "scope": args.scope,
        "status": "passed",
        "verification_id": str(uuid4()),
        "version": 1,
    }
    attestation = {
        "payload": attestation_payload,
        "signature": base64.urlsafe_b64encode(
            private_key.sign(_canonical_json(attestation_payload))
        )
        .decode("ascii")
        .rstrip("="),
    }
    attestation_hash = _write_json(evidence_dir / "attestation.json", attestation)
    print(f"attestation_sha256={attestation_hash}")
    print(f"event_id={event_id}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    live = subparsers.add_parser("live")
    live.add_argument("--evidence-dir", type=Path, required=True)
    live.add_argument("--private-key", type=Path, required=True)
    live.add_argument("--map-admin-url", required=True)
    live.add_argument("--map-case-id", required=True)
    live.add_argument("--map-api-container", required=True)
    live.add_argument("--map-frontend-container", required=True)
    live.add_argument("--map-source-root", type=Path, required=True)
    live.add_argument("--pinvi-api-url", required=True)
    live.add_argument("--pinvi-api-container", required=True)
    live.add_argument("--pinvi-web-container", required=True)
    live.add_argument("--pinvi-dagster-container", required=True)
    live.add_argument("--event-id", required=True)
    live.add_argument("--pinvi-source-revision", required=True)
    live.add_argument("--scope", choices=("staging", "production"), required=True)
    live.add_argument("--require-root-owned", action="store_true")
    live.add_argument("ui_command", nargs=argparse.REMAINDER)
    live.set_defaults(handler=_live)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return cast(int, args.handler(args))
    except (AttestationError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"M05 live attestation failed: {exc}") from None


if __name__ == "__main__":
    raise SystemExit(main())
