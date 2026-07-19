#!/usr/bin/env python3
"""PinVi API Docker image의 source revision build 계약을 검증한다."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn, Sequence

_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_ENVIRONMENTS = {"development", "test", "smoke", "staging", "production"}
_IMMUTABLE_ENVIRONMENTS = {"staging", "production"}


class ProvenanceError(ValueError):
    """빌드 provenance 입력이 안전 계약을 위반했다."""


def _run_git(repo_root: Path, args: Sequence[str]) -> str:
    try:
        completed = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo_root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise ProvenanceError(
            "Git repository provenance를 확인할 수 없습니다."
        ) from exc
    return completed.stdout.rstrip("\n")


def _clean_head(repo_root: Path) -> str:
    expected_root = repo_root.resolve(strict=True)
    actual_root = Path(
        _run_git(expected_root, ["rev-parse", "--show-toplevel"])
    ).resolve(strict=True)
    if actual_root != expected_root:
        raise ProvenanceError("build context는 Git worktree root여야 합니다.")

    head = _run_git(expected_root, ["rev-parse", "--verify", "HEAD^{commit}"])
    if _COMMIT_RE.fullmatch(head) is None:
        raise ProvenanceError("Git HEAD는 40자리 소문자 commit이어야 합니다.")

    dirty = _run_git(
        expected_root,
        ["status", "--porcelain=v1", "--untracked-files=normal"],
    )
    if dirty:
        raise ProvenanceError(
            "immutable image는 clean Git worktree에서만 빌드할 수 있습니다."
        )
    return head


def resolve_revision(
    *, environment: str, repo_root: Path, requested: str | None
) -> str:
    """환경과 Git 상태를 대조해 Docker build arg로 전달할 revision을 반환한다."""

    if environment not in _ENVIRONMENTS:
        raise ProvenanceError("PINVI_ENVIRONMENT가 canonical 값이 아닙니다.")
    if requested == "":
        requested = None

    if requested is None and environment not in _IMMUTABLE_ENVIRONMENTS:
        return "development"
    if requested == "development":
        if environment in _IMMUTABLE_ENVIRONMENTS:
            raise ProvenanceError(
                "staging/production image는 development revision을 금지합니다."
            )
        return requested
    if requested is not None and _COMMIT_RE.fullmatch(requested) is None:
        raise ProvenanceError(
            "PINVI_SOURCE_REVISION은 40자리 소문자 commit이어야 합니다."
        )

    head = _clean_head(repo_root)
    if requested is not None and requested != head:
        raise ProvenanceError("PINVI_SOURCE_REVISION이 build context HEAD와 다릅니다.")
    return head


def compose_environment(document: object) -> str:
    """`docker compose config --format json`에서 API runtime 환경을 읽는다."""

    app_api = _compose_app_api(document)
    environment = app_api.get("environment")
    if not isinstance(environment, dict):
        raise ProvenanceError("compose app-api environment를 확인할 수 없습니다.")
    value = environment.get("PINVI_ENVIRONMENT")
    if not isinstance(value, str) or value not in _ENVIRONMENTS:
        raise ProvenanceError(
            "compose app-api PINVI_ENVIRONMENT가 canonical 값이 아닙니다."
        )
    return value


def compose_requested_revision(document: object) -> str | None:
    """resolved compose build args에서 명시된 source revision만 읽는다."""

    app_api = _compose_app_api(document)
    build = app_api.get("build")
    if not isinstance(build, dict):
        raise ProvenanceError("compose app-api build를 확인할 수 없습니다.")
    args = build.get("args")
    if not isinstance(args, dict):
        raise ProvenanceError("compose app-api build args 형식이 올바르지 않습니다.")
    value = args.get("PINVI_SOURCE_REVISION")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProvenanceError("compose source revision 형식이 올바르지 않습니다.")
    return value


def compose_image_reference(document: object) -> str:
    """resolved compose에서 API image reference를 읽는다."""

    value = _compose_app_api(document).get("image")
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise ProvenanceError(
            "compose app-api image reference 형식이 올바르지 않습니다."
        )
    return value


def compose_provenance_input(document: object, *, name: str) -> str | None:
    """고정 stdin Compose가 env-file에서 해석한 provenance 입력을 읽는다."""

    if not isinstance(document, dict):
        raise ProvenanceError("compose provenance document 형식이 올바르지 않습니다.")
    services = document.get("services")
    if not isinstance(services, dict):
        raise ProvenanceError("compose provenance services를 확인할 수 없습니다.")
    service = services.get("provenance")
    if not isinstance(service, dict):
        raise ProvenanceError("compose provenance service를 확인할 수 없습니다.")
    environment = service.get("environment")
    if not isinstance(environment, dict):
        raise ProvenanceError("compose provenance environment를 확인할 수 없습니다.")
    value = environment.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProvenanceError("compose provenance 입력 형식이 올바르지 않습니다.")
    return value


def verify_compose_build(
    document: object,
    *,
    context_root: Path,
    expected_environment: str,
    expected_revision: str,
) -> None:
    """immutable API build mapping이 canonical archive만 가리키는지 검증한다."""

    app_api = _compose_app_api(document)
    build = app_api.get("build")
    if not isinstance(build, dict) or set(build) != {"args", "context", "dockerfile"}:
        raise ProvenanceError(
            "immutable app-api build mapping key가 canonical 값이 아닙니다."
        )

    if context_root.is_symlink():
        raise ProvenanceError(
            "immutable build context가 canonical directory가 아닙니다."
        )
    canonical_context = context_root.resolve(strict=True)
    if not canonical_context.is_dir():
        raise ProvenanceError(
            "immutable build context가 canonical directory가 아닙니다."
        )
    context = build.get("context")
    if not isinstance(context, str):
        raise ProvenanceError("immutable build context 형식이 올바르지 않습니다.")
    if Path(context).resolve(strict=True) != canonical_context:
        raise ProvenanceError("immutable build context가 exact archive와 다릅니다.")

    dockerfile = build.get("dockerfile")
    if not isinstance(dockerfile, str):
        raise ProvenanceError("immutable Dockerfile 형식이 올바르지 않습니다.")
    dockerfile_path = Path(dockerfile)
    if not dockerfile_path.is_absolute():
        dockerfile_path = canonical_context / dockerfile_path
    dockerfile_path = dockerfile_path.resolve(strict=True)
    expected_dockerfile = _regular_archive_file(
        canonical_context,
        Path("apps/api/Dockerfile"),
    )
    if dockerfile_path != expected_dockerfile:
        raise ProvenanceError(
            "immutable Dockerfile이 canonical archive 파일이 아닙니다."
        )

    args = build.get("args")
    expected_args = {
        "PINVI_BUILD_ENVIRONMENT": expected_environment,
        "PINVI_SOURCE_REVISION": expected_revision,
    }
    if args != expected_args:
        raise ProvenanceError("immutable API build args가 canonical 값과 다릅니다.")

    _regular_archive_file(canonical_context, Path("infra/docker-compose.app.yml"))
    _regular_archive_file(canonical_context, Path("scripts/api_image_provenance.py"))


def _regular_archive_file(context_root: Path, relative: Path) -> Path:
    current = context_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ProvenanceError(
                "immutable control path에 symlink를 허용하지 않습니다."
            )
    if not current.is_file():
        raise ProvenanceError("immutable control path는 regular file이어야 합니다.")
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(context_root)
    except ValueError as exc:
        raise ProvenanceError(
            "immutable control path가 archive context 밖을 가리킵니다."
        ) from exc
    if resolved != current:
        raise ProvenanceError(
            "immutable control path가 archive context 밖을 가리킵니다."
        )
    return resolved


def _compose_app_api(document: object) -> dict[object, object]:
    if not isinstance(document, dict):
        raise ProvenanceError("compose document 형식이 올바르지 않습니다.")
    services = document.get("services")
    if not isinstance(services, dict):
        raise ProvenanceError("compose services를 확인할 수 없습니다.")
    app_api = services.get("app-api")
    if not isinstance(app_api, dict):
        raise ProvenanceError("compose app-api service를 확인할 수 없습니다.")
    return app_api


def verify_labels(
    *,
    expected_revision: str,
    actual_revision: str,
    expected_environment: str,
    actual_environment: str,
) -> None:
    """image label이 preflight에서 확정한 build 입력과 같은지 확인한다."""

    if (
        expected_revision != "development"
        and _COMMIT_RE.fullmatch(expected_revision) is None
    ):
        raise ProvenanceError("기대 source revision 형식이 올바르지 않습니다.")
    if expected_environment not in _ENVIRONMENTS:
        raise ProvenanceError("기대 build environment가 canonical 값이 아닙니다.")
    if actual_revision != expected_revision:
        raise ProvenanceError("API image revision label이 build source와 다릅니다.")
    if actual_environment != expected_environment:
        raise ProvenanceError("API image environment label이 deploy 환경과 다릅니다.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--environment", required=True)
    resolve.add_argument("--repo-root", type=Path, required=True)
    resolve.add_argument("--requested")

    subparsers.add_parser("compose-environment")
    subparsers.add_parser("compose-requested-revision")
    subparsers.add_parser("compose-image-reference")

    provenance_input = subparsers.add_parser("compose-provenance-input")
    provenance_input.add_argument("--name", required=True)

    verify_compose = subparsers.add_parser("verify-compose-build")
    verify_compose.add_argument("--context-root", type=Path, required=True)
    verify_compose.add_argument("--expected-environment", required=True)
    verify_compose.add_argument("--expected-revision", required=True)

    verify = subparsers.add_parser("verify-label")
    verify.add_argument("--expected-revision", required=True)
    verify.add_argument("--actual-revision", required=True)
    verify.add_argument("--expected-environment", required=True)
    verify.add_argument("--actual-environment", required=True)
    return parser


def _fail(message: str) -> NoReturn:
    print(f"api image provenance preflight failed: {message}", file=sys.stderr)
    raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "resolve":
            print(
                resolve_revision(
                    environment=args.environment,
                    repo_root=args.repo_root,
                    requested=args.requested,
                )
            )
        elif args.command == "compose-environment":
            print(compose_environment(json.load(sys.stdin)))
        elif args.command == "compose-requested-revision":
            print(compose_requested_revision(json.load(sys.stdin)) or "")
        elif args.command == "compose-image-reference":
            print(compose_image_reference(json.load(sys.stdin)))
        elif args.command == "compose-provenance-input":
            print(compose_provenance_input(json.load(sys.stdin), name=args.name) or "")
        elif args.command == "verify-compose-build":
            verify_compose_build(
                json.load(sys.stdin),
                context_root=args.context_root,
                expected_environment=args.expected_environment,
                expected_revision=args.expected_revision,
            )
        else:
            verify_labels(
                expected_revision=args.expected_revision,
                actual_revision=args.actual_revision,
                expected_environment=args.expected_environment,
                actual_environment=args.actual_environment,
            )
    except (json.JSONDecodeError, OSError, ProvenanceError) as exc:
        _fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
