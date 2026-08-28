"""PinVi API image source revision 계약 테스트."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = ROOT / "scripts" / "api_image_provenance.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("api_image_provenance", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["api_image_provenance"] = module
    spec.loader.exec_module(module)
    return module


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def test_local_build_defaults_to_development_without_git_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "_clean_head",
        lambda _: pytest.fail("local development default must not inspect Git"),
    )

    assert (
        script.resolve_revision(environment="smoke", repo_root=ROOT, requested=None)
        == "development"
    )


def test_production_derives_exact_clean_head(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _load_script()
    head = "a" * 40
    monkeypatch.setattr(script, "_clean_head", lambda _: head)

    assert script.resolve_revision(environment="production", repo_root=ROOT, requested=None) == head


def test_isolated_derives_exact_clean_head(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _load_script()
    head = "a" * 40
    monkeypatch.setattr(script, "_clean_head", lambda _: head)

    assert script.resolve_revision(environment="isolated", repo_root=ROOT, requested=None) == head


@pytest.mark.parametrize("revision", ["development", "A" * 40, "a" * 39, "main"])
def test_production_rejects_non_commit_revision(revision: str) -> None:
    script = _load_script()

    with pytest.raises(script.ProvenanceError):
        script.resolve_revision(
            environment="production",
            repo_root=ROOT,
            requested=revision,
        )


def test_requested_commit_must_match_clean_head(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _load_script()
    monkeypatch.setattr(script, "_clean_head", lambda _: "a" * 40)

    with pytest.raises(script.ProvenanceError, match="HEAD"):
        script.resolve_revision(
            environment="production",
            repo_root=ROOT,
            requested="b" * 40,
        )


def test_clean_head_rejects_dirty_build_context(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _load_script()

    def fake_git(_: Path, args: list[str]) -> str:
        if args == ["rev-parse", "--show-toplevel"]:
            return str(ROOT)
        if args == ["rev-parse", "--verify", "HEAD^{commit}"]:
            return "a" * 40
        return " M apps/api/Dockerfile"

    monkeypatch.setattr(script, "_run_git", fake_git)

    with pytest.raises(script.ProvenanceError, match="clean"):
        script.resolve_revision(
            environment="production",
            repo_root=ROOT,
            requested=None,
        )


def test_compose_contract_reads_environment_and_optional_revision() -> None:
    script = _load_script()
    document = {
        "services": {
            "app-api": {
                "environment": {"PINVI_ENVIRONMENT": "production"},
                "build": {"args": {"PINVI_SOURCE_REVISION": "a" * 40}},
            }
        }
    }

    assert script.compose_environment(document) == "production"
    assert script.compose_requested_revision(document) == "a" * 40
    assert (
        script.compose_image_reference(
            {
                "services": {
                    "app-api": {
                        "image": "pinvi-api:latest-main",
                    }
                }
            }
        )
        == "pinvi-api:latest-main"
    )


def _build_document(
    context_root: Path,
    *,
    dockerfile: str = "apps/api/Dockerfile",
) -> dict[str, object]:
    return {
        "services": {
            "app-api": {
                "build": {
                    "args": {
                        "PINVI_BUILD_ENVIRONMENT": "production",
                        "PINVI_SOURCE_REVISION": "a" * 40,
                    },
                    "context": str(context_root),
                    "dockerfile": dockerfile,
                }
            }
        }
    }


def _write_archive_control_files(context_root: Path) -> None:
    for relative, content in (
        (Path("apps/api/Dockerfile"), "FROM scratch\n"),
        (Path("apps/web/Dockerfile"), "FROM scratch\n"),
        (Path("apps/etl/Dockerfile"), "FROM scratch\n"),
        (Path("infra/docker-compose.app.yml"), "services: {}\n"),
        (Path("scripts/api_image_provenance.py"), "# fixture\n"),
        (Path("scripts/validate-image-provenance.sh"), "#!/usr/bin/env sh\n"),
    ):
        path = context_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_immutable_compose_build_mapping_accepts_only_canonical_archive(
    tmp_path: Path,
) -> None:
    script = _load_script()
    context_root = tmp_path / "context"
    _write_archive_control_files(context_root)

    script.verify_compose_build(
        _build_document(context_root),
        context_root=context_root,
        expected_environment="production",
        expected_revision="a" * 40,
    )


def test_immutable_compose_rejects_external_dockerfile(tmp_path: Path) -> None:
    script = _load_script()
    context_root = tmp_path / "context"
    _write_archive_control_files(context_root)
    external = tmp_path / "evil.Dockerfile"
    external.write_text("FROM scratch\n", encoding="utf-8")

    with pytest.raises(script.ProvenanceError, match="Dockerfile"):
        script.verify_compose_build(
            _build_document(context_root, dockerfile=str(external)),
            context_root=context_root,
            expected_environment="production",
            expected_revision="a" * 40,
        )


def test_immutable_compose_rejects_additional_build_key(tmp_path: Path) -> None:
    script = _load_script()
    context_root = tmp_path / "context"
    _write_archive_control_files(context_root)
    document = _build_document(context_root)
    document["services"]["app-api"]["build"]["additional_contexts"] = {  # type: ignore[index]
        "evil": str(tmp_path)
    }

    with pytest.raises(script.ProvenanceError, match="mapping key"):
        script.verify_compose_build(
            document,
            context_root=context_root,
            expected_environment="production",
            expected_revision="a" * 40,
        )


def test_immutable_compose_rejects_wrong_snapshot_context(tmp_path: Path) -> None:
    script = _load_script()
    context_root = tmp_path / "context"
    wrong_context = tmp_path / "wrong-context"
    _write_archive_control_files(context_root)
    wrong_context.mkdir()

    with pytest.raises(script.ProvenanceError, match="exact archive"):
        script.verify_compose_build(
            _build_document(wrong_context),
            context_root=context_root,
            expected_environment="production",
            expected_revision="a" * 40,
        )


@pytest.mark.parametrize(
    "relative",
    [
        Path("apps/api/Dockerfile"),
        Path("infra/docker-compose.app.yml"),
        Path("scripts/api_image_provenance.py"),
    ],
)
def test_immutable_compose_rejects_symlinked_control_file(
    tmp_path: Path,
    relative: Path,
) -> None:
    script = _load_script()
    context_root = tmp_path / "context"
    _write_archive_control_files(context_root)
    external = tmp_path / "external-control"
    external.write_text("untrusted\n", encoding="utf-8")
    control = context_root / relative
    control.unlink()
    control.symlink_to(external)

    with pytest.raises(script.ProvenanceError, match="symlink"):
        script.verify_compose_build(
            _build_document(context_root),
            context_root=context_root,
            expected_environment="production",
            expected_revision="a" * 40,
        )


def test_image_label_must_equal_preflight_revision() -> None:
    script = _load_script()

    with pytest.raises(script.ProvenanceError, match="label"):
        script.verify_labels(
            expected_revision="a" * 40,
            actual_revision="b" * 40,
            expected_environment="production",
            actual_environment="production",
        )


def test_image_build_environment_must_equal_deploy_environment() -> None:
    script = _load_script()

    with pytest.raises(script.ProvenanceError, match="environment"):
        script.verify_labels(
            expected_revision="a" * 40,
            actual_revision="a" * 40,
            expected_environment="production",
            actual_environment="smoke",
        )


def test_docker_and_deploy_files_bind_the_same_revision_contract() -> None:
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")
    validator = (ROOT / "scripts/validate-image-provenance.sh").read_text(encoding="utf-8")
    compose = (ROOT / "infra/docker-compose.app.yml").read_text(encoding="utf-8")
    docker_app = (ROOT / "scripts/docker-app.sh").read_text(encoding="utf-8")
    deploy = (ROOT / "scripts/deploy-node.sh").read_text(encoding="utf-8")

    assert "ARG PINVI_SOURCE_REVISION=development" in dockerfile
    assert "PINVI_SOURCE_REVISION=${PINVI_SOURCE_REVISION}" in dockerfile
    assert 'org.opencontainers.image.revision="${PINVI_SOURCE_REVISION}"' in dockerfile
    assert 'io.pinvi.build.environment="${PINVI_BUILD_ENVIRONMENT}"' in dockerfile
    assert "isolated|staging|production" in validator
    assert "- PINVI_SOURCE_REVISION" in compose
    assert "PINVI_BUILD_ENVIRONMENT=${PINVI_ENVIRONMENT:-smoke}" in compose
    assert "PINVI_API_BUILD_CONTEXT" in compose
    assert "PINVI_APP_BUILD_CONTEXT" in compose
    assert "pinvi_verify_runtime_image_provenance app-api app-web" in docker_app
    assert 'git -C "$ROOT_DIR" archive' in (ROOT / "scripts/api-image-provenance.sh").read_text(
        encoding="utf-8"
    )
    assert "build_images" in deploy
    assert "pinvi_verify_runtime_image_provenance app-api app-web" in deploy


def test_resolved_compose_passes_provenance_to_every_runtime_image() -> None:
    environment = os.environ | {
        "PINVI_ENVIRONMENT": "production",
        "PINVI_SOURCE_REVISION": "a" * 40,
    }
    docker = shutil.which("docker")
    assert docker is not None
    completed = subprocess.run(  # noqa: S603 - checked-in compose contract only
        [
            docker,
            "compose",
            "--profile",
            "etl",
            "-f",
            str(ROOT / "infra/docker-compose.app.yml"),
            "config",
            "--format",
            "json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=environment,
    )
    services = json.loads(completed.stdout)["services"]

    for service in ("app-api", "app-web", "app-dagster"):
        args = services[service]["build"]["args"]
        assert args["PINVI_SOURCE_REVISION"] == "a" * 40
        assert args["PINVI_BUILD_ENVIRONMENT"] == "production"
        assert services[service]["environment"]["PINVI_ENVIRONMENT"] == "production"


def test_all_pinvi_runtime_images_have_the_same_provenance_contract() -> None:
    validator = (ROOT / "scripts/validate-image-provenance.sh").read_text(encoding="utf-8")

    assert "isolated|staging|production" in validator
    assert "exact source commit" in validator
    for dockerfile_path in (
        ROOT / "apps/api/Dockerfile",
        ROOT / "apps/web/Dockerfile",
        ROOT / "apps/etl/Dockerfile",
    ):
        dockerfile = dockerfile_path.read_text(encoding="utf-8")
        assert "ARG PINVI_BUILD_ENVIRONMENT=development" in dockerfile
        assert "ARG PINVI_SOURCE_REVISION=development" in dockerfile
        assert (
            "COPY scripts/validate-image-provenance.sh /tmp/validate-image-provenance.sh"
            in dockerfile
        )
        assert 'org.opencontainers.image.revision="${PINVI_SOURCE_REVISION}"' in dockerfile
        assert 'io.pinvi.build.environment="${PINVI_BUILD_ENVIRONMENT}"' in dockerfile


@pytest.mark.parametrize(
    ("environment", "revision", "returncode"),
    [
        ("isolated", "a" * 40, 0),
        ("isolated", "development", 2),
        ("production", "a" * 40, 0),
        ("staging", "development", 2),
        ("production", "A" * 40, 2),
        ("unknown", "development", 2),
    ],
)
def test_runtime_image_provenance_validator_is_fail_closed(
    environment: str,
    revision: str,
    returncode: int,
) -> None:
    completed = subprocess.run(  # noqa: S603 - test inputs are fixed parametrize literals
        ["/bin/sh", str(ROOT / "scripts/validate-image-provenance.sh"), environment, revision],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == returncode


def test_api_image_installs_console_scripts_after_copying_app_source() -> None:
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")

    source_copy = dockerfile.index("COPY apps/api/app ./app")
    project_install = dockerfile.index("RUN pip install --no-deps -e .")

    assert source_copy < project_install


def test_immutable_context_uses_exact_archive_and_excludes_worktree_drift(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "apps/api").mkdir(parents=True)
    (repo / "apps/web").mkdir(parents=True)
    (repo / "apps/etl").mkdir(parents=True)
    (repo / "infra").mkdir()
    (repo / "scripts").mkdir()
    (repo / "apps/api/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / "apps/web/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / "apps/etl/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / "infra/docker-compose.app.yml").write_text(
        """services:
  app-api:
    build:
      context: ${PINVI_API_BUILD_CONTEXT:-..}
      dockerfile: apps/api/Dockerfile
      args:
        - PINVI_SOURCE_REVISION
        - PINVI_BUILD_ENVIRONMENT=${PINVI_ENVIRONMENT:-smoke}
""",
        encoding="utf-8",
    )
    (repo / "scripts/api_image_provenance.py").write_bytes(SCRIPT_PATH.read_bytes())
    (repo / "scripts/validate-image-provenance.sh").write_text(
        "#!/usr/bin/env sh\n", encoding="utf-8"
    )
    (repo / "tracked.txt").write_text("committed\n", encoding="utf-8")
    (repo / ".gitignore").write_text("ignored-secret\n", encoding="utf-8")
    for args in (
        ["init", "-q"],
        ["config", "user.name", "PinVi Test"],
        ["config", "user.email", "pinvi-test@example.com"],
        ["add", "."],
        ["commit", "-qm", "fixture"],
    ):
        subprocess.run(  # noqa: S603
            ["/usr/bin/git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    shell = r"""
set -euo pipefail
ROOT_DIR="$1"
COMPOSE_FILE="$ROOT_DIR/infra/docker-compose.app.yml"
compose() {
  printf '{"services":{"app-api":{"build":{"args":{"PINVI_BUILD_ENVIRONMENT":"%s","PINVI_SOURCE_REVISION":"%s"},"context":"%s","dockerfile":"apps/api/Dockerfile"}}}}\n' \
    "$PINVI_PROVENANCE_ENVIRONMENT" "$PINVI_SOURCE_REVISION" "$PINVI_API_BUILD_CONTEXT"
}
source "$2"
PINVI_PROVENANCE_ENVIRONMENT=production
PINVI_SOURCE_REVISION="$(git -C "$ROOT_DIR" rev-parse --verify HEAD^{commit})"
printf 'worktree drift\n' > "$ROOT_DIR/tracked.txt"
printf 'must not enter context\n' > "$ROOT_DIR/ignored-secret"
pinvi_materialize_api_build_context
test "$(cat "$PINVI_API_BUILD_CONTEXT/tracked.txt")" = committed
test ! -e "$PINVI_API_BUILD_CONTEXT/ignored-secret"
archive_root="$PINVI_PROVENANCE_ARCHIVE_ROOT"
pinvi_cleanup_api_build_context
test ! -e "$archive_root"
"""
    subprocess.run(  # noqa: S603
        [
            "/usr/bin/bash",
            "-c",
            shell,
            "archive-test",
            str(repo),
            str(ROOT / "scripts/api-image-provenance.sh"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_shell_preflight_pins_image_id_and_verifies_running_container(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    image_id = f"sha256:{'a' * 64}"
    drifted_image_id = f"sha256:{'b' * 64}"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == compose ]]; then
  cat >/dev/null
  printf '%s\\n' '{{"services":{{"provenance":{{"environment":{{"PINVI_ENVIRONMENT":"smoke","PINVI_SOURCE_REVISION":""}}}}}}}}'
  exit 0
fi
case "$1:$2:$3" in
  image:inspect:--format)
    case "$4" in
      *org.opencontainers.image.revision*) printf 'development\\n' ;;
      *io.pinvi.build.environment*) printf 'smoke\\n' ;;
      *)
        [[ -e "$PINVI_TEST_STATE_DIR/retagged" ]] && \
          printf '{drifted_image_id}\\n' || printf '{image_id}\\n'
        ;;
    esac
    ;;
  container:inspect:--format)
    printf '%s\\n' "$FAKE_RUNNING_IMAGE_ID"
    ;;
  container:ls:*)
    if [[ "$*" == *"app-api"* ]]; then
      [[ ! -e "$PINVI_TEST_STATE_DIR/removed" ]] && printf 'api-container-id api-container-name\\n'
    elif [[ "$*" == *"app-web"* ]]; then
      [[ ! -e "$PINVI_TEST_STATE_DIR/removed" ]] && printf 'web-container-id web-container-name\\n'
    fi
    ;;
  container:stop:*)
    touch "$PINVI_TEST_STATE_DIR/stopped"
    ;;
  container:rm:-f)
    test "$4" = api-container-id
    test "$5" = web-container-id
    touch "$PINVI_TEST_STATE_DIR/removed"
    ;;
  *) exit 44 ;;
esac
""",
    )
    shell = r"""
set -euo pipefail
ROOT_DIR="$1"
COMPOSE_FILE="$ROOT_DIR/infra/docker-compose.app.yml"
ENV_FILE="$ROOT_DIR/missing.env"
EXPECTED_IMAGE_ID="$3"
compose() {
  if [[ "$1" == --profile ]]; then
    test "$2" = etl
    shift 2
  fi
  if [[ "$1" == config ]]; then
    printf '%s\n' '{"services":{"app-api":{"environment":{"PINVI_ENVIRONMENT":"smoke"},"build":{"args":{"PINVI_SOURCE_REVISION":"development"}},"image":"pinvi-api:test"},"app-web":{"image":"pinvi-web:test"},"app-dagster":{"image":"pinvi-dagster:test"}}}'
  elif [[ "$1 $2" == "ps -q" ]]; then
    printf 'api-container-id\n'
  elif [[ "$1 $2" == "ps -aq" ]]; then
    if [[ ! -e "$PINVI_TEST_STATE_DIR/removed" ]]; then
      printf 'api-container-id\nweb-container-id\n'
    fi
  elif [[ "$1" == up ]]; then
    test "$PINVI_API_IMAGE" = "$EXPECTED_IMAGE_ID"
  elif [[ "$1" == stop ]]; then
    touch "$PINVI_TEST_STATE_DIR/stopped"
  else
    exit 45
  fi
}
source "$2"
pinvi_verify_api_image_provenance
test "$PINVI_API_IMAGE" = "$3"
pinvi_verify_runtime_image_provenance app-api app-web app-dagster
test "$PINVI_WEB_IMAGE" = "$3"
test "$PINVI_DAGSTER_IMAGE" = "$3"
pinvi_verify_running_app
touch "$PINVI_TEST_STATE_DIR/retagged"
compose up -d app-api
pinvi_verify_running_api_image_id
export FAKE_RUNNING_IMAGE_ID="$4"
if pinvi_verify_running_app; then
  exit 46
fi
test ! -e "$PINVI_TEST_STATE_DIR/stopped"
test ! -e "$PINVI_TEST_STATE_DIR/removed"
"""
    env = {
        "FAKE_RUNNING_IMAGE_ID": image_id,
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "PINVI_TEST_STATE_DIR": str(state_dir),
    }
    result = subprocess.run(  # noqa: S603
        [
            "/usr/bin/bash",
            "-c",
            shell,
            "image-pin-test",
            str(ROOT),
            str(ROOT / "scripts/api-image-provenance.sh"),
            image_id,
            drifted_image_id,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr


def test_running_web_and_dagster_image_drift_is_fail_closed_without_cleanup(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    expected_image_id = f"sha256:{'a' * 64}"
    drifted_image_id = f"sha256:{'b' * 64}"
    _write_executable(
        fake_bin / "docker",
        r"""#!/usr/bin/env bash
set -euo pipefail
case "$1:$2:$3" in
  container:inspect:--format)
    case "$5" in
      api-container-id) printf '%s\n' "$FAKE_API_RUNNING_IMAGE_ID" ;;
      web-container-id) printf '%s\n' "$FAKE_WEB_RUNNING_IMAGE_ID" ;;
      dagster-container-id) printf '%s\n' "$FAKE_DAGSTER_RUNNING_IMAGE_ID" ;;
      *) exit 44 ;;
    esac
    ;;
  container:ls:*)
    case "$*" in
      *"app-api"*) [[ ! -e "$PINVI_TEST_STATE_DIR/app-cleaned" ]] && printf 'api-container-id api-container-name\\n' ;;
      *"app-web"*) [[ ! -e "$PINVI_TEST_STATE_DIR/app-cleaned" ]] && printf 'web-container-id web-container-name\\n' ;;
      *"app-dagster"*) [[ ! -e "$PINVI_TEST_STATE_DIR/dagster-cleaned" ]] && printf 'dagster-container-id dagster-container-name\\n' ;;
    esac
    ;;
  container:stop:*)
    if [[ "$*" == *api-container-id* || "$*" == *web-container-id* ]]; then
      touch "$PINVI_TEST_STATE_DIR/app-cleaned"
    fi
    if [[ "$*" == *dagster-container-id* ]]; then
      touch "$PINVI_TEST_STATE_DIR/dagster-cleaned"
    fi
    ;;
  container:rm:-f) exit 0 ;;
  *) exit 45 ;;
esac
""",
    )
    shell = r"""
set -euo pipefail
ROOT_DIR="$1"
COMPOSE_FILE="$ROOT_DIR/infra/docker-compose.app.yml"
ENV_FILE="$ROOT_DIR/missing.env"
compose() {
  local profile=""
  if [[ "$1 $2" == "--profile etl" ]]; then
    profile=etl
    shift 2
  fi
  case "$1 $2" in
    "ps -q")
      case "$3" in
        app-api) [[ ! -e "$PINVI_TEST_STATE_DIR/app-cleaned" ]] && printf 'api-container-id\n' ;;
        app-web) [[ ! -e "$PINVI_TEST_STATE_DIR/app-cleaned" ]] && printf 'web-container-id\n' ;;
        app-dagster) [[ ! -e "$PINVI_TEST_STATE_DIR/dagster-cleaned" ]] && printf 'dagster-container-id\n' ;;
        *) exit 46 ;;
      esac
      ;;
    "ps -aq")
      if [[ "$profile" == etl ]]; then
        [[ ! -e "$PINVI_TEST_STATE_DIR/dagster-cleaned" ]] && printf 'dagster-container-id\n'
      elif [[ ! -e "$PINVI_TEST_STATE_DIR/app-cleaned" ]]; then
        printf 'api-container-id\nweb-container-id\n'
      fi
      ;;
    "stop app-web") touch "$PINVI_TEST_STATE_DIR/app-cleaned" ;;
    "stop app-dagster")
      [[ "$profile" == etl ]]
      touch "$PINVI_TEST_STATE_DIR/dagster-cleaned"
      ;;
    *) exit 47 ;;
  esac
}
source "$2"
PINVI_ATTESTED_API_IMAGE_ID="$3"
PINVI_ATTESTED_WEB_IMAGE_ID="$3"
PINVI_ATTESTED_DAGSTER_IMAGE_ID="$3"
pinvi_verify_running_app
export FAKE_WEB_RUNNING_IMAGE_ID="$4"
if pinvi_verify_running_app; then
  exit 48
fi
test ! -e "$PINVI_TEST_STATE_DIR/app-cleaned"
if pinvi_verify_running_dagster; then
  exit 49
fi
test ! -e "$PINVI_TEST_STATE_DIR/dagster-cleaned"
"""
    result = subprocess.run(  # noqa: S603 - fixed local shell fixture
        [
            "/usr/bin/bash",
            "-c",
            shell,
            "runtime-container-drift-test",
            str(ROOT),
            str(ROOT / "scripts/api-image-provenance.sh"),
            expected_image_id,
            drifted_image_id,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            "FAKE_API_RUNNING_IMAGE_ID": expected_image_id,
            "FAKE_WEB_RUNNING_IMAGE_ID": expected_image_id,
            "FAKE_DAGSTER_RUNNING_IMAGE_ID": drifted_image_id,
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "PINVI_TEST_STATE_DIR": str(state_dir),
        },
    )

    assert result.returncode == 0, result.stderr


def test_preflight_freezes_environment_across_env_file_drift(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "apps/api").mkdir(parents=True)
    (repo / "apps/web").mkdir(parents=True)
    (repo / "apps/etl").mkdir(parents=True)
    (repo / "infra").mkdir()
    (repo / "scripts").mkdir()
    (repo / "apps/api/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / "apps/web/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / "apps/etl/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / "scripts/api_image_provenance.py").write_bytes(SCRIPT_PATH.read_bytes())
    (repo / "scripts/validate-image-provenance.sh").write_text(
        "#!/usr/bin/env sh\n", encoding="utf-8"
    )
    (repo / "infra/docker-compose.app.yml").write_text(
        """services:
  app-api:
    build:
      context: ${PINVI_API_BUILD_CONTEXT:-..}
      dockerfile: apps/api/Dockerfile
      args:
        - PINVI_SOURCE_REVISION
        - PINVI_BUILD_ENVIRONMENT=${PINVI_ENVIRONMENT:-smoke}
""",
        encoding="utf-8",
    )
    for args in (
        ["init", "-q"],
        ["config", "user.name", "PinVi Test"],
        ["config", "user.email", "pinvi-test@example.com"],
        ["add", "."],
        ["commit", "-qm", "fixture"],
    ):
        subprocess.run(  # noqa: S603
            ["/usr/bin/git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    env_file = tmp_path / "pinvi.env"
    env_file.write_text("PINVI_ENVIRONMENT=production\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        r"""#!/usr/bin/env bash
set -euo pipefail
test "$1" = compose
environment="${PINVI_ENVIRONMENT:-}"
if [[ -z "$environment" ]]; then
  while (( $# > 0 )); do
    if [[ "$1" == --env-file ]]; then
      environment="$(sed -n 's/^PINVI_ENVIRONMENT=//p' "$2")"
      break
    fi
    shift
  done
fi
cat >/dev/null
printf '{"services":{"provenance":{"environment":{"PINVI_ENVIRONMENT":"%s","PINVI_SOURCE_REVISION":""}}}}\n' "$environment"
""",
    )
    shell = r"""
set -euo pipefail
ROOT_DIR="$1"
ENV_FILE="$3"
COMPOSE_FILE="$ROOT_DIR/infra/docker-compose.app.yml"
compose() {
  printf '{"services":{"app-api":{"build":{"args":{"PINVI_BUILD_ENVIRONMENT":"%s","PINVI_SOURCE_REVISION":"%s"},"context":"%s","dockerfile":"apps/api/Dockerfile"},"environment":{"PINVI_ENVIRONMENT":"%s"}}}}\n' \
    "$PINVI_ENVIRONMENT" "$PINVI_SOURCE_REVISION" "$PINVI_API_BUILD_CONTEXT" "$PINVI_ENVIRONMENT"
}
source "$2"
trap pinvi_cleanup_api_build_context EXIT
pinvi_prepare_api_image_provenance
test "$PINVI_ENVIRONMENT" = production
printf 'PINVI_ENVIRONMENT=staging\n' > "$ENV_FILE"
test "$(pinvi_read_provenance_input PINVI_ENVIRONMENT)" = production
"""
    subprocess.run(  # noqa: S603
        [
            "/usr/bin/bash",
            "-c",
            shell,
            "environment-freeze-test",
            str(repo),
            str(ROOT / "scripts/api-image-provenance.sh"),
            str(env_file),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": f"{fake_bin}:/usr/bin:/bin", "TMPDIR": str(tmp_path)},
    )


@pytest.mark.parametrize(
    "command",
    ["deploy", "build", "pull", "migrate", "up", "dagster", "smoke"],
)
@pytest.mark.parametrize("environment", [None, "smoke"])
def test_deploy_entry_rejects_mutation_outside_immutable_environment(
    tmp_path: Path,
    command: str,
    environment: str | None,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    mutation_log = tmp_path / "mutations.log"
    _write_executable(
        fake_bin / "docker",
        r"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$1 $2" == "compose version" ]]; then
  exit 0
fi
if [[ "$1" == compose && "$2" == -f ]]; then
  cat >/dev/null
  printf '{"services":{"provenance":{"environment":{"PINVI_ENVIRONMENT":"%s","PINVI_SOURCE_REVISION":""}}}}\n' \
    "${PINVI_ENVIRONMENT:-smoke}"
  exit 0
fi
printf '%s\n' "$*" >> "$PINVI_TEST_MUTATION_LOG"
""",
    )
    empty_env_file = tmp_path / "empty.env"
    empty_env_file.write_text("", encoding="utf-8")
    env = {
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "PINVI_ENV_FILE": str(empty_env_file),
        "PINVI_ROOT_DIR": str(ROOT),
        "PINVI_TEST_MUTATION_LOG": str(mutation_log),
    }
    if environment is not None:
        env["PINVI_ENVIRONMENT"] = environment

    result = subprocess.run(  # noqa: S603
        [str(ROOT / "scripts/deploy-node.sh"), command],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "requires PINVI_ENVIRONMENT=staging or production" in result.stderr
    assert not mutation_log.exists()


def test_deploy_entry_rejects_external_database_endpoint(tmp_path: Path) -> None:
    env_file = tmp_path / "stage.env"
    env_file.write_text("PINVI_ENVIRONMENT=staging\n", encoding="utf-8")
    result = subprocess.run(  # noqa: S603
        [str(ROOT / "scripts/deploy-node.sh"), "build"],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "PINVI_ROOT_DIR": str(ROOT),
            "PINVI_ENV_FILE": str(env_file),
            "PINVI_ENVIRONMENT": "staging",
            "PINVI_DATABASE_URL": "postgresql+asyncpg://pinvi:secret@external-db.example:5432/pinvi",
        },
    )

    assert result.returncode != 0
    assert "isolated app-postgres service" in result.stderr


def test_deploy_entry_rejects_invalid_host_port(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
[[ "$1 $2" == "compose version" ]]
""",
    )
    env_file = tmp_path / "stage.env"
    env_file.write_text("PINVI_ENVIRONMENT=staging\n", encoding="utf-8")
    result = subprocess.run(  # noqa: S603
        [str(ROOT / "scripts/deploy-node.sh"), "build"],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "PINVI_ROOT_DIR": str(ROOT),
            "PINVI_ENV_FILE": str(env_file),
            "PINVI_ENVIRONMENT": "staging",
            "PINVI_API_PORT": "0",
        },
    )

    assert result.returncode != 0
    assert "PINVI_API_PORT" in result.stderr


def test_deploy_fresh_contract_rejects_existing_compose_resources(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra/docker-compose.app.yml").write_text("services: {}\n", encoding="utf-8")
    for dependency in ("api-image-provenance.sh", "migrator-lifecycle-lock.sh"):
        shutil.copy2(ROOT / "scripts" / dependency, scripts_dir / dependency)
    script = scripts_dir / "deploy-node.sh"
    script.write_text(
        (ROOT / "scripts/deploy-node.sh")
        .read_text(encoding="utf-8")
        .rsplit('\nmain "$@"', maxsplit=1)[0]
        + "\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "uname", "#!/usr/bin/env bash\nprintf '%s\\n' x86_64\n")
    _write_executable(fake_bin / "hostname", "#!/usr/bin/env bash\nprintf '%s\\n' n150\n")
    _write_executable(
        fake_bin / "sed",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${@: -1}" == "/etc/os-release" ]]; then
  case "$*" in
    *'s/^ID='*) printf 'ubuntu\\n' ;;
    *'s/^VERSION_ID='*) printf '26.04\\n' ;;
    *) exit 0 ;;
  esac
else
  exec /usr/bin/sed "$@"
fi
""",
    )
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
case "$1 $2" in
  "container ls") printf '%s\\n' existing-container ;;
  "volume ls"|"network ls") ;;
  *) exit 0 ;;
esac
""",
    )
    result = subprocess.run(  # noqa: S603
        ["/usr/bin/bash", "-c", 'source "$1"; require_fresh_stack_contract', "bash", str(script)],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "PINVI_ROOT_DIR": str(tmp_path),
            "PINVI_ENV_FILE": str(tmp_path / "missing.env"),
            "PINVI_ENVIRONMENT": "staging",
            "PINVI_DOCKER_MANAGER_UNAVAILABLE": "1",
            "PINVI_DEPLOY_FRESH_STACK": "1",
            "PINVI_DOCKER_PROJECT": "pinvi-test",
        },
    )

    assert result.returncode != 0
    assert "existing Compose project" in result.stderr


@pytest.mark.parametrize("failure_mode", ["archive", "build", "label"])
def test_pre_start_provenance_failure_leaves_no_container_or_temp_context(
    tmp_path: Path,
    failure_mode: str,
) -> None:
    repo = tmp_path / "repo"
    (repo / "apps/api").mkdir(parents=True)
    (repo / "apps/web").mkdir(parents=True)
    (repo / "apps/etl").mkdir(parents=True)
    (repo / "infra").mkdir()
    (repo / "scripts").mkdir()
    (repo / "apps/api/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / "apps/web/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / "apps/etl/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / "scripts/api_image_provenance.py").write_bytes(SCRIPT_PATH.read_bytes())
    (repo / "scripts/validate-image-provenance.sh").write_text(
        "#!/usr/bin/env sh\n", encoding="utf-8"
    )
    (repo / "infra/docker-compose.app.yml").write_text(
        """services:
  app-api:
    build:
      context: ${PINVI_API_BUILD_CONTEXT:-..}
      dockerfile: apps/api/Dockerfile
      args:
        - PINVI_SOURCE_REVISION
        - PINVI_BUILD_ENVIRONMENT=${PINVI_ENVIRONMENT:-smoke}
    image: pinvi-api:test
    environment:
      PINVI_ENVIRONMENT: ${PINVI_ENVIRONMENT:-smoke}
""",
        encoding="utf-8",
    )
    if failure_mode == "archive":
        (repo / ".gitattributes").write_text(
            "apps/api/Dockerfile export-ignore\n",
            encoding="utf-8",
        )
    for args in (
        ["init", "-q"],
        ["config", "user.name", "PinVi Test"],
        ["config", "user.email", "pinvi-test@example.com"],
        ["add", "."],
        ["commit", "-qm", "fixture"],
    ):
        subprocess.run(  # noqa: S603
            ["/usr/bin/git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    head = subprocess.run(  # noqa: S603
        ["/usr/bin/git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    mutation_log = tmp_path / "mutations.log"
    contexts = tmp_path / "contexts"
    contexts.mkdir()
    image_id = f"sha256:{'a' * 64}"
    _write_executable(
        fake_bin / "docker",
        f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == compose ]]; then
  cat >/dev/null
  printf '%s\\n' '{{"services":{{"provenance":{{"environment":{{"PINVI_ENVIRONMENT":"production","PINVI_SOURCE_REVISION":""}}}}}}}}'
  exit 0
fi
case "$1:$2:$3" in
  image:inspect:--format)
    case "$4" in
      *org.opencontainers.image.revision*)
        [[ "$PINVI_TEST_FAILURE_MODE" == label ]] && printf '%040d\\n' 0 || printf '%s\\n' "$PINVI_TEST_HEAD"
        ;;
      *io.pinvi.build.environment*) printf 'production\\n' ;;
      *) printf '{image_id}\\n' ;;
    esac
    ;;
  *) exit 44 ;;
esac
""",
    )
    shell = r"""
set -euo pipefail
ROOT_DIR="$1"
ENV_FILE="$ROOT_DIR/missing.env"
PROJECT=pinvi-test
COMPOSE_FILE="$ROOT_DIR/infra/docker-compose.app.yml"
compose() {
  case "$1" in
    config)
      printf '{"services":{"app-api":{"build":{"args":{"PINVI_BUILD_ENVIRONMENT":"production","PINVI_SOURCE_REVISION":"%s"},"context":"%s","dockerfile":"apps/api/Dockerfile"},"environment":{"PINVI_ENVIRONMENT":"production"},"image":"pinvi-api:test"}}}\n' \
        "$PINVI_SOURCE_REVISION" "$PINVI_API_BUILD_CONTEXT"
      ;;
    build)
      printf 'image-build\n' >> "$PINVI_TEST_MUTATION_LOG"
      [[ "$PINVI_TEST_FAILURE_MODE" != build ]]
      ;;
    up|run|start|create)
      printf 'container-mutation\n' >> "$PINVI_TEST_MUTATION_LOG"
      ;;
    *) exit 45 ;;
  esac
}
source "$2"
trap pinvi_cleanup_api_build_context EXIT
pinvi_prepare_api_image_provenance
compose build app-api
pinvi_verify_api_image_provenance
compose up -d app-api
"""
    env = {
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "PINVI_TEST_FAILURE_MODE": failure_mode,
        "PINVI_TEST_HEAD": head,
        "PINVI_TEST_MUTATION_LOG": str(mutation_log),
        "TMPDIR": str(contexts),
    }
    result = subprocess.run(  # noqa: S603
        [
            "/usr/bin/bash",
            "-c",
            shell,
            "failure-test",
            str(repo),
            str(ROOT / "scripts/api-image-provenance.sh"),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    mutations = mutation_log.read_text(encoding="utf-8") if mutation_log.exists() else ""
    assert "container-mutation" not in mutations
    assert list(contexts.iterdir()) == []
