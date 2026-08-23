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
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PLAYWRIGHT_IMAGE_RE = re.compile(
    r"mcr\.microsoft\.com/playwright:[A-Za-z0-9][A-Za-z0-9._-]*@sha256:[0-9a-f]{64}\Z"
)
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
    if set(envelope) != {"map", "runtime_image_digests", "version"} or envelope["version"] != 1:
        raise AttestationError("Map pair provenance envelope is invalid")
    map_value = _object(envelope["map"], name="Map pair provenance map")
    if set(map_value) != {"admin", "full", "service", "user"}:
        raise AttestationError("Map pair provenance inventory is invalid")
    runtime_images = _object(
        envelope["runtime_image_digests"], name="Map runtime image digests"
    )
    if set(runtime_images) != {"admin", "api", "frontend"}:
        raise AttestationError("Map runtime image digest inventory is invalid")
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
    result["runtime_image_digests"] = {}
    for name in ("admin", "api", "frontend"):
        digest = _string(
            runtime_images[name], name=f"runtime_image_digests.{name}"
        )
        if _DIGEST_RE.fullmatch(digest) is None:
            raise AttestationError(f"runtime_image_digests.{name} is invalid")
        result["runtime_image_digests"][name] = digest
    return result


def _url(base: str, path: str) -> str:
    base = _string(base.rstrip("/"), name="URL")
    if not base.startswith(("http://", "https://")):
        raise AttestationError("URL must use http or https")
    return f"{base}{path}"


def _assert_clean_checkout(
    root: Path, *, expected_revision: str, label: str, allowed_revisions: set[str] | None = None
) -> None:
    """producer가 dirty/임의 checkout에서 실행되지 않도록 source identity를 고정한다."""

    if root.is_symlink() or not root.is_dir():
        raise AttestationError(f"{label} must be a regular directory")
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
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
        raise AttestationError(f"{label} git identity could not be verified") from exc
    if Path(top).resolve() != root.resolve() or status:
        raise AttestationError(f"{label} checkout must be clean and canonical")
    if allowed_revisions is not None:
        if revision not in allowed_revisions:
            raise AttestationError(f"{label} HEAD is not one of the pinned revisions")
    elif revision != expected_revision:
        raise AttestationError(f"{label} HEAD does not match the pinned revision")


def _assert_docker_endpoint(
    item: dict[str, object], *, container: str, endpoint_url: str, container_port: int
) -> None:
    """HTTP 대상이 caller가 고른 임의 서버가 아니라 지정 container의 host binding인지 확인한다."""

    try:
        parsed = urlsplit(endpoint_url)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise AttestationError(f"service endpoint is invalid for {container}") from exc
    if (
        parsed.scheme != "http"
        or host not in {"127.0.0.1", "localhost"}
        or port is None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise AttestationError(
            f"service endpoint must be a loopback HTTP root for {container}"
        )
    network = _object(item.get("NetworkSettings"), name=f"docker network {container}")
    ports = network.get("Ports")
    if not isinstance(ports, dict):
        raise AttestationError(f"docker endpoint binding is missing for {container}")
    bindings = ports.get(f"{container_port}/tcp")
    if not isinstance(bindings, list) or not any(
        isinstance(binding, dict)
        and str(binding.get("HostPort")) == str(port)
        and binding.get("HostIp") == "127.0.0.1"
        for binding in bindings
    ):
        raise AttestationError(f"service endpoint is not bound to {container}")


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
) -> tuple[dict[str, object], str, str]:
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
    receipt_sha = _string(receipt.get("receipt_sha256"), name="Pinvi receipt hash")
    if _SHA256_RE.fullmatch(receipt_sha) is None:
        raise AttestationError("Pinvi receipt hash is invalid")
    attempts = data.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise AttestationError("Pinvi M05 delivery attempts are missing")
    latest = _object(attempts[0], name="Pinvi latest attempt")
    if latest.get("status") != "applied" or latest.get("event_sha256") != event_sha:
        raise AttestationError("Pinvi latest attempt is not the applied event")
    impacts = data.get("impacts")
    if not isinstance(impacts, list) or len(impacts) != receipt.get("impact_count"):
        raise AttestationError("Pinvi impact count does not match its terminal receipt")
    return data, _sha256(_canonical_json(data)), receipt_sha


def _docker_inspect(
    container: str,
    *,
    expected_revision: str,
    expected_environment: str,
    require_environment_label: bool = True,
    expected_image_digest: str | None = None,
    endpoint_url: str | None = None,
    endpoint_container_port: int = 8000,
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
    container_id = item.get("Id")
    if not isinstance(container_id, str) or re.fullmatch(r"[0-9a-f]{64}\Z", container_id) is None:
        raise AttestationError(f"runtime container ID is invalid for {container}")
    state = _object(item.get("State"), name=f"docker state {container}")
    if state.get("Running") is not True:
        raise AttestationError(f"runtime container is not running for {container}")
    started_at = _string(
        state.get("StartedAt"), name=f"{container}.state.started_at"
    )
    image_id = item.get("Image")
    if not isinstance(image_id, str) or _DIGEST_RE.fullmatch(image_id) is None:
        raise AttestationError(f"runtime image ID is not immutable for {container}")
    if expected_image_digest is not None and image_id != expected_image_digest:
        raise AttestationError(f"runtime image digest mismatch for {container}")
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
    if endpoint_url is not None:
        _assert_docker_endpoint(
            item,
            container=container,
            endpoint_url=endpoint_url,
            container_port=endpoint_container_port,
        )
    return {
        "container_id": container_id,
        "digest": image_id,
        "image_id": image_id,
        "environment": expected_environment,
        "source_revision": expected_revision,
        "revision_label": revision,
        "started_at": started_at,
    }


def _docker_image_identity(image_ref: str) -> dict[str, str]:
    """M05 browser는 공식 이미지의 immutable registry digest만 허용한다."""

    if _PLAYWRIGHT_IMAGE_RE.fullmatch(image_ref) is None:
        raise AttestationError(
            "M05 Playwright runner image must be an immutable official digest reference"
        )
    repository, expected_digest = image_ref.rsplit("@", 1)
    try:
        completed = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{json .}}", image_ref],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AttestationError("M05 Playwright runner image inspect failed") from exc
    try:
        item = _object(json.loads(completed.stdout), name="Playwright runner image")
    except json.JSONDecodeError as exc:
        raise AttestationError("M05 Playwright runner image inspect output is invalid") from exc
    image_id = item.get("Id")
    if not isinstance(image_id, str) or _DIGEST_RE.fullmatch(image_id) is None:
        raise AttestationError("M05 Playwright runner image ID is not immutable")
    repo_digests = item.get("RepoDigests")
    if not isinstance(repo_digests, list) or f"{repository.split(':', 1)[0]}@{expected_digest}" not in repo_digests:
        raise AttestationError(
            "M05 Playwright runner image is not attested by the official registry digest"
        )
    return {"image_id": image_id, "image_ref": image_ref}


def _assert_runtime_identity(
    before: dict[str, str], after: dict[str, str], *, label: str
) -> None:
    for field in (
        "container_id",
        "digest",
        "image_id",
        "environment",
        "source_revision",
        "revision_label",
        "started_at",
    ):
        if before[field] != after[field]:
            raise AttestationError(f"runtime identity changed during live verification: {label}")


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


def _openapi_operations(value: object, *, name: str) -> dict[str, set[str]]:
    document = _object(value, name=name)
    paths = _object(document.get("paths"), name=f"{name}.paths")
    operations: dict[str, set[str]] = {}
    for path, raw_operations in paths.items():
        if not isinstance(path, str):
            raise AttestationError(f"{name} contains an invalid path")
        operation_object = _object(raw_operations, name=f"{name}.paths.{path}")
        operations[path] = {
            method
            for method in operation_object
            if method in {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
        }
    return operations


def _openapi_surface_sha256(operations: dict[str, set[str]]) -> str:
    return _sha256(
        _canonical_json(
            {path: sorted(methods) for path, methods in sorted(operations.items())}
        )
    )


def _assert_openapi_surface_covered(
    runtime_value: object, *, expected_value: object
) -> str:
    runtime_operations = _openapi_operations(runtime_value, name="runtime Map OpenAPI")
    expected_operations = _openapi_operations(expected_value, name="full Map OpenAPI")
    runtime_paths = _object(
        _object(runtime_value, name="runtime Map OpenAPI").get("paths"),
        name="runtime Map OpenAPI.paths",
    )
    expected_paths = _object(
        _object(expected_value, name="full Map OpenAPI").get("paths"),
        name="full Map OpenAPI.paths",
    )
    for path, methods in expected_operations.items():
        if path not in runtime_operations or not methods.issubset(runtime_operations[path]):
            raise AttestationError(
                f"live Map OpenAPI does not cover the pinned full surface: {path}"
            )
        expected_path = _object(expected_paths[path], name=f"full Map OpenAPI.paths.{path}")
        runtime_path = _object(runtime_paths[path], name=f"runtime Map OpenAPI.paths.{path}")
        for method in methods:
            expected_operation = _object(
                expected_path[method], name=f"full Map OpenAPI operation {path} {method}"
            )
            runtime_operation = _object(
                runtime_path[method], name=f"runtime Map OpenAPI operation {path} {method}"
            )
            if expected_operation.get("operationId") != runtime_operation.get("operationId"):
                raise AttestationError(
                    f"live Map OpenAPI operation identity differs from the pinned full surface: {path}"
                )
    return _sha256(
        _canonical_json(
            {
                "expected": {
                    path: sorted(methods)
                    for path, methods in sorted(expected_operations.items())
                },
                "runtime": {
                    path: sorted(methods)
                    for path, methods in sorted(runtime_operations.items())
                },
            }
        )
    )


def _runtime_map_openapi(
    *, map_admin_url: str, source_root: Path, expected: dict[str, dict[str, str]]
) -> dict[str, dict[str, str]]:
    """실행 중 full/admin과 source-bound service/user surface를 대조한다.

    Map API는 service/user profile을 별도 HTTP route로 제공하지 않고, 같은 full
    application에서 생성한 vendored artifact로 관리한다. 따라서 HTTP proof는
    실제 ``/openapi.json``에만 적용하고, service/user는 pinned Git blob을
    ``source-artifact`` transport로 봉인한다.
    """

    runtime_value, runtime_raw = _http_json(
        _url(map_admin_url, "/openapi.json"),
        headers=_map_headers(),
    )
    runtime_source_raw = _git_blob(
        source_root,
        revision=expected["admin"]["source_revision"],
        relative_path="packages/kor-travel-map-api/openapi.json",
    )
    try:
        runtime_source_value = json.loads(
            runtime_source_raw, object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError, AttestationError) as exc:
        raise AttestationError("pinned Map admin OpenAPI is not valid JSON") from exc
    runtime_canonical = _sha256(_canonical_json(runtime_value))
    source_canonical = _sha256(_canonical_json(runtime_source_value))
    if runtime_canonical != source_canonical:
        raise AttestationError(
            "live Map admin OpenAPI does not match the pinned source artifact"
        )
    full_source_raw = _git_blob(
        source_root,
        revision=expected["full"]["source_revision"],
        relative_path="packages/kor-travel-map-api/openapi.json",
    )
    try:
        full_source_value = json.loads(
            full_source_raw, object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError, AttestationError) as exc:
        raise AttestationError("pinned Map full OpenAPI is not valid JSON") from exc
    full_surface_coverage_sha256 = _assert_openapi_surface_covered(
        runtime_value, expected_value=full_source_value
    )
    full_source_canonical = _sha256(_canonical_json(full_source_value))
    runtime_surface_sha256 = _openapi_surface_sha256(
        _openapi_operations(runtime_value, name="runtime Map OpenAPI")
    )

    result: dict[str, dict[str, str]] = {}
    result["admin_openapi"] = {
        "canonical_sha256": runtime_canonical,
        "source_canonical_sha256": source_canonical,
        "source_revision": expected["admin"]["source_revision"],
        "source_sha256": expected["admin"]["openapi_sha256"],
        "surface_coverage_sha256": runtime_surface_sha256,
        "transport": "http",
        "transport_sha256": _sha256(runtime_raw),
    }
    result["full_openapi"] = {
        "canonical_sha256": runtime_canonical,
        "source_canonical_sha256": full_source_canonical,
        "source_revision": expected["full"]["source_revision"],
        "source_sha256": expected["full"]["openapi_sha256"],
        "surface_coverage_sha256": full_surface_coverage_sha256,
        "transport": "http",
        "transport_sha256": _sha256(runtime_raw),
    }
    for name in ("service", "user"):
        source_raw = _git_blob(
            source_root,
            revision=expected[name]["source_revision"],
            relative_path=f"packages/kor-travel-map-api/openapi.{name}.json",
        )
        try:
            source_value = json.loads(
                source_raw, object_pairs_hook=_reject_duplicate_keys
            )
        except (UnicodeDecodeError, json.JSONDecodeError, AttestationError) as exc:
            raise AttestationError(f"pinned Map {name} OpenAPI is not valid JSON") from exc
        source_canonical = _sha256(_canonical_json(source_value))
        source_surface_sha256 = _openapi_surface_sha256(
            _openapi_operations(source_value, name=f"pinned Map {name} OpenAPI")
        )
        result[f"{name}_openapi"] = {
            "canonical_sha256": source_canonical,
            "source_canonical_sha256": source_canonical,
            "source_revision": expected[name]["source_revision"],
            "source_sha256": expected[name]["openapi_sha256"],
            "surface_coverage_sha256": source_surface_sha256,
            "transport": "source-artifact",
            "transport_sha256": _sha256(source_raw),
        }
    return result


def _validate_ui_marker(
    value: object,
    *,
    event_id: str,
    source_revision: str,
    verification_id: str,
    runner_image: dict[str, str],
    pinvi_detail: dict[str, object],
    pinvi_detail_sha256: str,
) -> None:
    marker = _object(value, name="UI evidence marker")
    expected = {
        "assertions",
        "event_id",
        "impact_count",
        "old_feature_id",
        "pinvi_detail_sha256",
        "replacement_feature_id",
        "source_revision",
        "status",
        "verification_id",
        "playwright_runner_image_id",
        "playwright_runner_image_ref",
    }
    if set(marker) != expected or marker.get("status") != "passed":
        raise AttestationError("UI evidence marker schema/status is invalid")
    if _uuid(marker.get("event_id"), name="UI marker event ID") != event_id:
        raise AttestationError("UI marker event does not match the requested event")
    if _commit(marker.get("source_revision"), name="UI marker source revision") != source_revision:
        raise AttestationError("UI marker source revision does not match the runtime")
    if _uuid(marker.get("verification_id"), name="UI marker verification ID") != verification_id:
        raise AttestationError("UI marker verification ID does not match this run")
    if marker.get("playwright_runner_image_ref") != runner_image["image_ref"]:
        raise AttestationError("UI marker Playwright image reference does not match this run")
    if marker.get("playwright_runner_image_id") != runner_image["image_id"]:
        raise AttestationError("UI marker Playwright image ID does not match this run")
    if not isinstance(marker["assertions"], list) or not marker["assertions"]:
        raise AttestationError("UI marker assertions are missing")
    if not isinstance(marker["impact_count"], int) or marker["impact_count"] < 0:
        raise AttestationError("UI marker impact count is invalid")
    digest = marker["pinvi_detail_sha256"]
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise AttestationError("UI marker Pinvi detail hash is invalid")
    if digest != pinvi_detail_sha256:
        raise AttestationError("UI marker does not bind the after-run Pinvi detail response")
    receipt = _object(pinvi_detail.get("receipt"), name="UI marker Pinvi receipt")
    for marker_field, receipt_field in (
        ("old_feature_id", "old_feature_id"),
        ("replacement_feature_id", "replacement_feature_id"),
        ("impact_count", "impact_count"),
    ):
        if marker[marker_field] != receipt.get(receipt_field):
            raise AttestationError(
                f"UI marker does not bind Pinvi receipt field: {receipt_field}"
            )


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


def _runtime_snapshot(
    args: argparse.Namespace,
    *,
    pair: dict[str, dict[str, str]],
    source_revision: str,
) -> dict[str, dict[str, str]]:
    return {
        "map_admin": _docker_inspect(
            args.map_admin_container,
            expected_revision=pair["admin"]["source_revision"],
            expected_environment=args.scope,
            require_environment_label=False,
            expected_image_digest=pair["runtime_image_digests"]["admin"],
            endpoint_url=args.map_admin_url,
        ),
        "map_api": _docker_inspect(
            args.map_api_container,
            expected_revision=pair["admin"]["source_revision"],
            expected_environment=args.scope,
            require_environment_label=False,
            expected_image_digest=pair["runtime_image_digests"]["api"],
        ),
        "map_frontend": _docker_inspect(
            args.map_frontend_container,
            expected_revision=pair["admin"]["source_revision"],
            expected_environment=args.scope,
            require_environment_label=False,
            expected_image_digest=pair["runtime_image_digests"]["frontend"],
        ),
        "pinvi_api": _docker_inspect(
            args.pinvi_api_container,
            expected_revision=source_revision,
            expected_environment=args.scope,
            endpoint_url=args.pinvi_api_url,
        ),
        "pinvi_web": _docker_inspect(
            args.pinvi_web_container,
            expected_revision=source_revision,
            expected_environment=args.scope,
            endpoint_url=args.pinvi_web_url,
            endpoint_container_port=3000,
        ),
        "pinvi_dagster": _docker_inspect(
            args.pinvi_dagster_container,
            expected_revision=source_revision,
            expected_environment=args.scope,
        ),
    }


def _assert_runtime_snapshots_unchanged(
    before: dict[str, dict[str, str]],
    after: dict[str, dict[str, str]],
) -> None:
    for name, runtime in before.items():
        _assert_runtime_identity(runtime, after[name], label=name)


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

    pair = _load_pair()
    pinvi_source_root = Path(__file__).resolve().parents[1]
    _assert_clean_checkout(
        pinvi_source_root,
        expected_revision=source_revision,
        label="Pinvi source",
    )
    _assert_clean_checkout(
        args.map_source_root,
        expected_revision=pair["full"]["source_revision"],
        allowed_revisions={entry["source_revision"] for entry in pair.values()},
        label="Map source",
    )
    runtime_initial = _runtime_snapshot(
        args, pair=pair, source_revision=source_revision
    )

    before_map, before_ack, before_map_hash, _before_ack_hash = _map_case_snapshot(
        map_admin_url=args.map_admin_url,
        case_id=case_id,
        event_id=event_id,
    )
    before_pinvi, before_pinvi_hash, before_receipt_sha = _pinvi_case_snapshot(
        pinvi_api_url=args.pinvi_api_url,
        event_id=event_id,
        email=email,
        password=password,
    )
    before_local_receipt_sha = _string(
        before_ack.get("local_receipt_sha256"), name="Map local receipt hash"
    )
    if before_local_receipt_sha != before_receipt_sha:
        raise AttestationError(
            "Map ACK local receipt hash does not match the Pinvi terminal receipt"
        )
    runtime_before_ui = _runtime_snapshot(
        args, pair=pair, source_revision=source_revision
    )
    _assert_runtime_snapshots_unchanged(runtime_initial, runtime_before_ui)

    command = list(args.ui_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise AttestationError("a real Playwright command is required after --")
    runner_path = pinvi_source_root / "scripts/n150-playwright-runner.sh"
    if Path(command[0]).resolve() != runner_path.resolve():
        raise AttestationError("live UI must use the repository Playwright runner")
    command[0] = str(runner_path)
    expected_command = [
        str(runner_path),
        "--",
        "npm",
        "-w",
        "@pinvi/web",
        "run",
        "test:e2e:live-mutating",
        "--",
        "apps/web/e2e/admin-feature-reference-reconciliations-live-mutating.live.ts",
        "--workers=1",
    ]
    if command != expected_command:
        raise AttestationError("live UI command is not the pinned M05 Playwright test")
    runner_image = _docker_image_identity(args.playwright_runner_image)
    verification_id = str(uuid4())
    marker_path = evidence_dir / "ui-run.json"
    if marker_path.is_symlink() or marker_path.exists():
        raise AttestationError("UI evidence marker must not pre-exist the pinned run")
    child_env = os.environ.copy()
    child_env["PINVI_M05_UI_EVIDENCE_DIR"] = str(evidence_dir)
    child_env["PINVI_M05_LIVE_EVENT_ID"] = event_id
    child_env["PINVI_M05_UI_VERIFICATION_ID"] = verification_id
    child_env["PINVI_M05_PLAYWRIGHT_RUNNER_IMAGE_REF"] = runner_image["image_ref"]
    child_env["PINVI_M05_PLAYWRIGHT_RUNNER_IMAGE_ID"] = runner_image["image_id"]
    child_env["PINVI_PLAYWRIGHT_RUNNER_IMAGE"] = runner_image["image_ref"]
    child_env["PINVI_PLAYWRIGHT_RUNNER_NETWORK"] = "host"
    child_env["PINVI_PLAYWRIGHT_RUNNER_REPO_ROOT"] = str(pinvi_source_root)
    child_env["PINVI_PLAYWRIGHT_RUNNER_SKIP_NPM_CI"] = "0"
    child_env["PINVI_LIVE_WEB_URL"] = args.pinvi_web_url
    child_env["PINVI_LIVE_API_URL"] = args.pinvi_api_url
    child_env["PINVI_M05_UI_API_URL"] = args.pinvi_api_url
    completed = subprocess.run(command, check=False, env=child_env)
    if completed.returncode != 0:
        raise AttestationError(f"live UI command exited with {completed.returncode}")
    _assert_clean_checkout(
        pinvi_source_root,
        expected_revision=source_revision,
        label="Pinvi source after live UI",
    )
    marker, marker_raw_hash = _read_json(marker_path)

    after_map, after_ack, after_map_hash, after_ack_hash = _map_case_snapshot(
        map_admin_url=args.map_admin_url,
        case_id=case_id,
        event_id=event_id,
    )
    after_pinvi, after_pinvi_hash, after_receipt_sha = _pinvi_case_snapshot(
        pinvi_api_url=args.pinvi_api_url,
        event_id=event_id,
        email=email,
        password=password,
    )
    after_local_receipt_sha = _string(
        after_ack.get("local_receipt_sha256"), name="Map local receipt hash"
    )
    if after_local_receipt_sha != after_receipt_sha:
        raise AttestationError(
            "Map ACK local receipt hash does not match the Pinvi terminal receipt"
        )
    if before_map_hash != after_map_hash or before_pinvi_hash != after_pinvi_hash:
        raise AttestationError("M05 remote state drifted during the read-only UI flow")
    if before_map != after_map or before_pinvi != after_pinvi:
        raise AttestationError(
            "M05 remote snapshot is not byte-stable across the UI flow"
        )
    _validate_ui_marker(
        marker,
        event_id=event_id,
        source_revision=source_revision,
        verification_id=verification_id,
        runner_image=runner_image,
        pinvi_detail=after_pinvi,
        pinvi_detail_sha256=after_pinvi_hash,
    )
    runtime_after_ui = _runtime_snapshot(
        args, pair=pair, source_revision=source_revision
    )
    _assert_runtime_snapshots_unchanged(runtime_initial, runtime_after_ui)

    source_openapi = _hash_source_openapi(args.map_source_root)
    runtime_map_openapi = _runtime_map_openapi(
        map_admin_url=args.map_admin_url,
        source_root=args.map_source_root,
        expected=pair,
    )
    runtime_after_openapi = _runtime_snapshot(
        args, pair=pair, source_revision=source_revision
    )
    _assert_runtime_snapshots_unchanged(runtime_after_ui, runtime_after_openapi)
    map_pair = {
        "admin": pair["admin"],
        "full": pair["full"],
        "service": pair["service"],
        "user": pair["user"],
        "admin_image_digest": runtime_after_openapi["map_admin"]["digest"],
        "api_image_digest": runtime_after_openapi["map_api"]["digest"],
        "frontend_image_digest": runtime_after_openapi["map_frontend"]["digest"],
        "runtime": {
            **runtime_map_openapi,
            "admin": runtime_after_openapi["map_admin"],
            "api": runtime_after_openapi["map_api"],
            "frontend": runtime_after_openapi["map_frontend"],
            "full_openapi_sha256": source_openapi["full"],
        },
    }
    pinvi_images = {
        "api": runtime_after_openapi["pinvi_api"],
        "web": runtime_after_openapi["pinvi_web"],
        "dagster": runtime_after_openapi["pinvi_dagster"],
    }

    live_ui = {
        "event_id": event_id,
        "event_sha256": _string(
            _object(after_map["event"], name="Map event")["event_sha256"],
            name="event hash",
        ),
        "map_admin_endpoint": args.map_admin_url.rstrip("/"),
        "map_ack_sha256": after_ack_hash,
        "map_local_receipt_sha256": after_local_receipt_sha,
        "map_snapshot_before_sha256": before_map_hash,
        "map_snapshot_after_sha256": after_map_hash,
        "pinvi_snapshot_before_sha256": before_pinvi_hash,
        "pinvi_snapshot_after_sha256": after_pinvi_hash,
        "pinvi_source_revision": source_revision,
        "pinvi_api_endpoint": args.pinvi_api_url.rstrip("/"),
        "pinvi_web_endpoint": args.pinvi_web_url.rstrip("/"),
        "pinvi_receipt_sha256": after_receipt_sha,
        "playwright_runner_image_id": runner_image["image_id"],
        "playwright_runner_image_ref": runner_image["image_ref"],
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
        "local_receipt_sha256": after_receipt_sha,
        "map_admin_endpoint": args.map_admin_url.rstrip("/"),
        "map_snapshot_sha256": after_map_hash,
        "pinvi_snapshot_sha256": after_pinvi_hash,
        "pinvi_api_endpoint": args.pinvi_api_url.rstrip("/"),
        "pinvi_web_endpoint": args.pinvi_web_url.rstrip("/"),
        "pinvi_source_revision": source_revision,
        "playwright_runner_image_id": runner_image["image_id"],
        "playwright_runner_image_ref": runner_image["image_ref"],
        "scope": args.scope,
        "status": "passed",
        "verification_id": verification_id,
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
    live.add_argument("--map-admin-container", required=True)
    live.add_argument("--map-api-container", required=True)
    live.add_argument("--map-frontend-container", required=True)
    live.add_argument("--map-source-root", type=Path, required=True)
    live.add_argument("--pinvi-api-url", required=True)
    live.add_argument("--pinvi-api-container", required=True)
    live.add_argument("--pinvi-web-url", required=True)
    live.add_argument("--pinvi-web-container", required=True)
    live.add_argument("--pinvi-dagster-container", required=True)
    live.add_argument("--event-id", required=True)
    live.add_argument("--pinvi-source-revision", required=True)
    live.add_argument("--scope", choices=("staging", "production"), required=True)
    live.add_argument("--playwright-runner-image", required=True)
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
