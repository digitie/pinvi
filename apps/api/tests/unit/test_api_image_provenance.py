"""PinVi API image source revision 계약 테스트."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

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


def _write_n150_host_fakes(fake_bin: Path) -> None:
    """`require_n150_execution_host`가 보는 arch·hostname·os-release를 N150으로 세운다."""

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


def test_compose_image_reference_cli_accepts_only_services_in_the_resolved_document(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    reference = f"postgis/postgis@sha256:{'a' * 64}"
    document = json.dumps({"services": {"app-postgres": {"image": reference}}})

    monkeypatch.setattr(sys, "stdin", io.StringIO(document))
    assert script.main(["compose-image-reference", "--service", "app-postgres"]) == 0
    assert capsys.readouterr().out == f"{reference}\n"

    monkeypatch.setattr(sys, "stdin", io.StringIO(document))
    with pytest.raises(SystemExit) as excinfo:
        script.main(["compose-image-reference", "--service", "app-rustfs"])
    assert excinfo.value.code == 2
    assert "compose app-rustfs service" in capsys.readouterr().err


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
    _write_n150_host_fakes(fake_bin)
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


def _fresh_stack_dependency_services() -> list[str]:
    """`fresh_stack_dependency_image_proof`가 실제로 증명하는 service — 호출부에서 읽는다."""

    deploy = (ROOT / "scripts/deploy-node.sh").read_text(encoding="utf-8")
    body = deploy.split("\nfresh_stack_dependency_image_proof() {\n", 1)[1].split("\n}\n", 1)[0]
    services = re.findall(r"fresh_stack_dependency_image_id (app-[a-z0-9-]+)\)", body)
    # 하한: 유도가 아무것도 찾지 못하면 아래 검사는 항진명제가 된다.
    assert {"app-postgres", "app-rustfs", "app-rustfs-init"} <= set(services)
    return services


@pytest.mark.parametrize("mode", ["sealed", "absent", "drift", "init-failed"])
def test_fresh_stack_dependency_proof_resolves_the_pinned_compose_images(
    tmp_path: Path,
    mode: str,
) -> None:
    """fresh deploy 의존성 증명이 checked-in compose의 핀 image로 끝까지 도는지 본다.

    2026-09-28: 이 증명이 부르는 `compose-image-reference --service app-postgres`를
    provenance CLI가 `invalid choice`(exit 2)로 거부해, fresh deploy가 migration 뒤
    상태 봉인 단계에서 항상 죽었다. 핀 image는 digest reference다.
    """

    services = _fresh_stack_dependency_services()
    compose = yaml.safe_load((ROOT / "infra/docker-compose.app.yml").read_text(encoding="utf-8"))
    pinned = {service: compose["services"][service]["image"] for service in services}
    image_ids = {
        reference: f"sha256:{hashlib.sha256(reference.encode()).hexdigest()}"
        for reference in pinned.values()
    }
    rendered_services = {service: {"image": reference} for service, reference in pinned.items()}
    if mode == "absent":
        del rendered_services["app-rustfs"]
    (tmp_path / "rendered.json").write_text(
        json.dumps({"services": rendered_services}), encoding="utf-8"
    )
    (tmp_path / "images.tsv").write_text(
        "".join(f"{reference}\t{image_id}\n" for reference, image_id in image_ids.items()),
        encoding="utf-8",
    )
    containers = []
    for service in services:
        image_id = image_ids[pinned[service]]
        if mode == "drift" and service == "app-rustfs":
            image_id = f"sha256:{'d' * 64}"
        state = "exited 0" if service == "app-rustfs-init" else "running 0"
        if mode == "init-failed" and service == "app-rustfs-init":
            state = "exited 1"
        containers.append(f"cid-{service}\t{image_id}\t{state}\n")
    (tmp_path / "containers.tsv").write_text("".join(containers), encoding="utf-8")

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    for dependency in (
        "api-image-provenance.sh",
        "api_image_provenance.py",
        "migrator-lifecycle-lock.sh",
    ):
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
    _write_executable(fake_bin / "python3", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    _write_executable(
        fake_bin / "docker",
        r"""#!/usr/bin/env bash
set -euo pipefail
case "$1 $2" in
  "compose -p")
    [[ "$3" == pinvi-test && " $* " == *" config --format json "* ]] || exit 41
    cat "$PINVI_TEST_DIR/rendered.json"
    ;;
  "container ls")
    [[ "$*" == *"label=com.docker.compose.project=pinvi-test"* ]] || exit 42
    service=""
    for arg in "$@"; do
      if [[ "$arg" == label=com.docker.compose.service=* ]]; then
        service="${arg#label=com.docker.compose.service=}"
      fi
    done
    awk -F '\t' -v cid="cid-$service" '$1 == cid {print $1}' "$PINVI_TEST_DIR/containers.tsv"
    ;;
  "container inspect")
    case "$4" in
      '{{.Image}}') column=2 ;;
      '{{.State.Status}} {{.State.ExitCode}}') column=3 ;;
      *) exit 43 ;;
    esac
    awk -F '\t' -v cid="$5" -v column="$column" \
      '$1 == cid {print $column; found=1} END {exit !found}' "$PINVI_TEST_DIR/containers.tsv"
    ;;
  "image inspect")
    [[ "$3 $4" == "--format {{.Id}}" ]] || exit 44
    awk -F '\t' -v ref="$5" \
      '$1 == ref {print $2; found=1} END {exit !found}' "$PINVI_TEST_DIR/images.tsv"
    ;;
  *) exit 45 ;;
esac
""",
    )
    shell = r"""
source "$1"
if ! fresh_stack_dependency_image_proof; then
  exit 7
fi
printf '%s\n' "$FRESH_STACK_POSTGRES_IMAGE_ID" "$FRESH_STACK_RUSTFS_IMAGE_ID" \
  "$FRESH_STACK_RUSTFS_INIT_IMAGE_ID"
"""
    result = subprocess.run(  # noqa: S603 - fixed local shell fixture
        ["/usr/bin/bash", "-c", shell, "bash", str(script)],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "PINVI_ROOT_DIR": str(tmp_path),
            "PINVI_ENV_FILE": str(tmp_path / "missing.env"),
            "PINVI_DOCKER_PROJECT": "pinvi-test",
            "PINVI_TEST_DIR": str(tmp_path),
        },
    )

    if mode == "sealed":
        assert result.returncode == 0, result.stderr
        sealed_order = ("app-postgres", "app-rustfs", "app-rustfs-init")
        assert result.stdout.splitlines() == [image_ids[pinned[s]] for s in sealed_order]
        return
    assert result.returncode == 7
    expected = {
        "absent": "could not resolve the pinned app-rustfs image reference",
        "drift": "fresh deploy app-rustfs image drifted from the pinned Compose image",
        "init-failed": "fresh deploy RustFS bucket initializer did not exit successfully",
    }[mode]
    assert expected in result.stderr, result.stderr


_FRESH_STACK_FAKE_DOCKER = r'''
"""world.json의 컨테이너·image와 checked-in compose로 docker CLI를 흉내 낸다."""

import json
import os
import re
import sys
from pathlib import Path

world = json.loads(Path(os.environ["PINVI_TEST_DIR"], "world.json").read_text(encoding="utf-8"))
args = sys.argv[1:]
containers = {container["id"]: container for container in world["containers"]}
images = world["images"]
images_by_id = {image["id"]: image for image in images.values()}
project_filter = f"label=com.docker.compose.project={world['project']}"


def fail(code):
    print(f"fake docker: unexpected {args!r}", file=sys.stderr)
    raise SystemExit(code)


def options(name):
    return [args[index + 1] for index, arg in enumerate(args[:-1]) if arg == name]


def interpolate(value):
    # Compose처럼 문자열 값만 치환한다: `$$`는 문자 그대로, `${A:-${B:-x}}`는 안쪽부터.
    if isinstance(value, dict):
        return {key: interpolate(item) for key, item in value.items()}
    if isinstance(value, list):
        return [interpolate(item) for item in value]
    if not isinstance(value, str):
        return value

    def substitute(match):
        name, operator, default = match.group(1), match.group(2), match.group(3) or ""
        current = os.environ.get(name)
        if operator == ":-":
            return current or default
        if operator == "-":
            return default if current is None else current
        return current or ""

    text = value.replace("$$", "\0")
    pattern = r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:?-)([^${}]*))?\}"
    while (replaced := re.sub(pattern, substitute, text)) != text:
        text = replaced
    return text.replace("\0", "$")


command = args[:2]
if command == ["compose", "-p"]:
    import yaml

    if args[2] != world["project"] or args[-3:] != ["config", "--format", "json"]:
        fail(41)
    document = yaml.safe_load(Path(options("-f")[0]).read_text(encoding="utf-8"))
    active = set(options("--profile"))
    document["services"] = {
        name: service
        for name, service in document["services"].items()
        if not service.get("profiles") or active & set(service["profiles"])
    }
    print(json.dumps(interpolate(document)))
elif command == ["image", "inspect"] and args[2] == "--format":
    image = images.get(args[4]) or images_by_id.get(args[4])
    if image is None:
        print(f"Error: No such image: {args[4]}", file=sys.stderr)
        raise SystemExit(1)
    if args[3] == "{{.Id}}":
        print(image["id"])
    elif "org.opencontainers.image.revision" in args[3]:
        print(image.get("revision", ""))
    elif "io.pinvi.build.environment" in args[3]:
        print(image.get("environment", ""))
    else:
        fail(42)
elif command == ["container", "ls"]:
    filters = options("--filter")
    if project_filter not in filters:
        fail(43)
    prefix = "label=com.docker.compose.service="
    wanted = [item[len(prefix):] for item in filters if item.startswith(prefix)]
    for container in world["containers"]:
        if wanted and container["service"] not in wanted:
            continue
        if "--all" not in args and container["status"] != "running":
            continue
        row = {
            "{{.ID}}": container["id"],
            "{{.ID}} {{.Names}}": f"{container['id']} {container['name']}",
        }.get(options("--format")[0])
        print(row if row is not None else fail(44))
elif command == ["container", "inspect"] and args[2] == "--format":
    template, container = args[3], containers.get(args[4])
    if container is None:
        raise SystemExit(1)
    if template == "{{.Image}}":
        print(container["image"])
    elif template == "{{.State.Status}} {{.State.ExitCode}}":
        print(f"{container['status']} {container['exit_code']}")
    elif template == "{{.State.Running}}":
        print("true" if container["status"] == "running" else "false")
    elif ".Mounts" in template:
        destination = re.search(r'eq \.Destination "([^"]+)"', template).group(1)
        print(container["mounts"].get(destination, ""))
    elif ".NetworkSettings.Networks" in template:
        print("".join(f"{network}\n" for network in container["networks"]))
    elif "com.docker.compose.service" in template:
        print(container["service"])
    else:
        fail(45)
elif command in (["volume", "ls"], ["network", "ls"]):
    if project_filter not in options("--filter") or options("--format") != ["{{.Name}}"]:
        fail(46)
    for name in world["volumes" if command[0] == "volume" else "networks"]:
        print(name)
elif command == ["volume", "inspect"] and args[2:4] == ["--format", "{{json .}}"]:
    if args[4] not in world["volumes"]:
        raise SystemExit(1)
    print(json.dumps({"Driver": "local", "Name": args[4]}))
elif command == ["network", "inspect"] and args[2:4] == ["--format", "{{.Id}}"]:
    if args[4] not in world["networks"]:
        raise SystemExit(1)
    print(world["networks"][args[4]])
elif args[0] == "exec" and containers.get(args[1], {}).get("service") == "app-postgres":
    if "system_identifier" in args[-1]:
        print(world["system_identifier"])
    elif "alembic_version" in args[-1]:
        print(world["alembic_version"])
    else:
        fail(47)
else:
    fail(49)
'''


def _fresh_stack_alembic_head() -> str:
    """`capture_fresh_stack_migration_proof`가 받는 canonical head — 스크립트에서 읽는다."""

    deploy = (ROOT / "scripts/deploy-node.sh").read_text(encoding="utf-8")
    heads = re.findall(r'"\$alembic_version" == "([0-9]{8}_[0-9]{4})"', deploy)
    assert heads, "deploy-node.sh의 canonical Alembic head 목록을 찾지 못했다"
    return heads[-1]


@pytest.mark.parametrize(
    "mode", ["migrated", "runtime-started", "image-rebuilt", "foreign-service"]
)
def test_standalone_up_reuses_a_stack_sealed_by_another_process(
    tmp_path: Path,
    mode: str,
) -> None:
    """migrate가 봉인한 fresh stack을 **다른 프로세스**의 up/dagster 재사용 검사가 받는지 본다.

    2026-09-28 리뷰가 이 경로의 두 결함을 짚었다.

    - 재사용 검사가 effective compose digest를 runtime image 결박 **전에** 계산했다. 봉인값은
      결박 뒤에 계산되므로 새 프로세스의 standalone up/dagster는 항상 "does not match"로
      거부됐다. `deploy`는 한 프로세스 안에서 둘 다 결박 뒤라 가려졌다.
    - runtime을 띄운 `compose up`이 남기는 `app-db-runtime-role` one-shot을 모양 검사가
      "unexpected Compose service"로 거부했다.

    fake docker의 `compose config`는 checked-in compose를 이 프로세스의 환경으로 치환해
    돌려준다 — 결박이 render를 바꾸는 효과를 변수 이름 목록 없이 재현한다. 뒤 두 case는
    같은 검사가 여전히 실제 변화(다시 빌드된 image, 모르는 service)를 거부하는지 본다.
    """

    project = "pinvi-test"
    revision = "c" * 40
    compose_text = (ROOT / "infra/docker-compose.app.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)

    def reference(service: str) -> str:
        image = compose["services"][service]["image"]
        return re.sub(r"\$\{[A-Za-z0-9_]+:-([^}]*)\}", r"\1", image)

    images: dict[str, dict[str, str]] = {}
    for service in ("app-postgres", "app-db-runtime-role", "app-rustfs", "app-rustfs-init"):
        digest = hashlib.sha256(reference(service).encode()).hexdigest()
        images[reference(service)] = {"id": f"sha256:{digest}"}
    for service in ("app-api", "app-web"):
        digest = hashlib.sha256(reference(service).encode()).hexdigest()
        images[reference(service)] = {
            "id": f"sha256:{digest}",
            "revision": revision,
            "environment": "isolated",
        }

    def container(service: str, status: str, mounts: dict[str, str] | None = None) -> dict:
        return {
            "id": hashlib.sha256(service.encode()).hexdigest()[:12],
            "name": f"{project}-{service}-1",
            "service": service,
            "image": images[reference(service)]["id"],
            "status": status,
            "exit_code": 0,
            "mounts": mounts or {},
            "networks": [f"{project}_default"],
        }

    world = {
        "project": project,
        "images": images,
        "containers": [
            container(
                "app-postgres",
                "running",
                {"/var/lib/postgresql/data": f"{project}_app-postgres"},
            ),
            container("app-rustfs", "running", {"/data": f"{project}_app-rustfs"}),
            container("app-rustfs-init", "exited"),
        ],
        "volumes": [f"{project}_app-postgres", f"{project}_app-rustfs"],
        "networks": {f"{project}_default": "e" * 64},
        "system_identifier": "7412345678901234567",
        "alembic_version": _fresh_stack_alembic_head(),
    }

    (tmp_path / "infra").mkdir()
    (tmp_path / "infra/docker-compose.app.yml").write_text(compose_text, encoding="utf-8")
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    for dependency in (
        "api-image-provenance.sh",
        "api_image_provenance.py",
        "migrator-lifecycle-lock.sh",
    ):
        shutil.copy2(ROOT / "scripts" / dependency, scripts_dir / dependency)
    script = scripts_dir / "deploy-node.sh"
    script.write_text(
        (ROOT / "scripts/deploy-node.sh")
        .read_text(encoding="utf-8")
        .rsplit('\nmain "$@"', maxsplit=1)[0]
        + "\n",
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_dir.chmod(0o700)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_n150_host_fakes(fake_bin)
    _write_executable(fake_bin / "python3", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    fake_docker = tmp_path / "fake_docker.py"
    fake_docker.write_text(_FRESH_STACK_FAKE_DOCKER, encoding="utf-8")
    _write_executable(
        fake_bin / "docker", f'#!/bin/sh\nexec "{sys.executable}" "{fake_docker}" "$@"\n'
    )

    # provenance 준비(git archive·clean HEAD 대조)는 이 검사의 대상이 아니다 — 준비된
    # 결과만 세우고, 결박(pinvi_verify_runtime_image_provenance)은 실제 코드가 한다.
    prelude = r"""
source "$1"
pinvi_prepare_api_image_provenance() {
  PINVI_PROVENANCE_PREPARED=1
  PINVI_PROVENANCE_ENVIRONMENT="$PINVI_ENVIRONMENT"
}
pinvi_prepare_api_image_provenance require-immutable
"""
    env = {
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "PINVI_ROOT_DIR": str(tmp_path),
        "PINVI_ENV_FILE": str(tmp_path / "missing.env"),
        "PINVI_ENVIRONMENT": "isolated",
        "PINVI_SOURCE_REVISION": revision,
        "PINVI_DOCKER_MANAGER_UNAVAILABLE": "1",
        "PINVI_DEPLOY_FRESH_STACK": "1",
        "PINVI_DOCKER_PROJECT": project,
        "PINVI_FRESH_STACK_STATE_PATH": str(state_dir / "fresh-stack"),
        "PINVI_TEST_DIR": str(tmp_path),
    }

    def run_process(body: str) -> subprocess.CompletedProcess[str]:
        (tmp_path / "world.json").write_text(json.dumps(world), encoding="utf-8")
        return subprocess.run(  # noqa: S603 - fixed local shell fixture
            ["/usr/bin/bash", "-c", prelude + body, "bash", str(script)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=tmp_path,
        )

    # 프로세스 1: `migrate`의 마지막 단계 — 결박 뒤 상태를 봉인한다.
    sealed = run_process("if ! write_fresh_stack_state; then exit 7; fi\n")
    assert sealed.returncode == 0, sealed.stderr
    assert (state_dir / "fresh-stack").is_file()

    if mode == "runtime-started":
        # `deploy`/`up`의 `compose up -d app-api app-web`가 남기는 모양.
        world["containers"] += [
            container("app-db-runtime-role", "exited"),
            container("app-api", "running"),
            container("app-web", "running"),
        ]
    elif mode == "image-rebuilt":
        images[reference("app-api")]["id"] = f"sha256:{'f' * 64}"
    elif mode == "foreign-service":
        world["containers"].append(container("app-migrator", "exited"))

    # 프로세스 2: standalone `up`/`dagster`의 재사용 검사 — 아무것도 결박되지 않은 새 셸.
    reused = run_process("if ! require_reusable_fresh_stack_contract; then exit 7; fi\n")

    if mode in {"migrated", "runtime-started"}:
        assert reused.returncode == 0, reused.stderr
        return
    assert reused.returncode == 7, reused.stderr
    expected = {
        "image-rebuilt": "fresh stack state does not match",
        "foreign-service": "refuses unexpected Compose service: app-migrator",
    }[mode]
    assert expected in reused.stderr, reused.stderr


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
