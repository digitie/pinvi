"""두 배포 wrapper가 공유하는 one-shot migrator lifecycle lock 회귀."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LOCK_HELPER = ROOT / "scripts" / "migrator-lifecycle-lock.sh"
BASH = "/usr/bin/bash"


def _environment(lock_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PINVI_ENVIRONMENT": "smoke",
            "PINVI_MIGRATOR_LIFECYCLE_LOCK_PATH": str(lock_path),
        }
    )
    return environment


def test_smoke_default_lock_uses_a_private_per_user_directory() -> None:
    environment = os.environ.copy()
    environment.pop("PINVI_MIGRATOR_LIFECYCLE_LOCK_PATH", None)
    environment["PINVI_ENVIRONMENT"] = "smoke"
    result = subprocess.run(  # noqa: S603 - fixed local Bash helper invocation
        [BASH, "-c", 'source "$1"; migrator_lifecycle_lock_path', "--", str(LOCK_HELPER)],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        f"{os.sep}tmp{os.sep}pinvi-migrator-lifecycle-{os.getuid()}{os.sep}migrator-lifecycle.lock"
    )


def test_migrator_lifecycle_lock_rejects_a_smoke_path_in_a_shared_writable_parent(
    tmp_path: Path,
) -> None:
    shared_parent = tmp_path / "shared"
    shared_parent.mkdir(mode=0o777)
    shared_parent.chmod(0o777)
    result = subprocess.run(  # noqa: S603 - fixed local Bash helper invocation
        [
            BASH,
            "-c",
            'source "$1"; acquire_migrator_lifecycle_lock',
            "--",
            str(LOCK_HELPER),
        ],
        env=_environment(shared_parent / "migrator-lifecycle.lock"),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "migrator lifecycle lock parent must be owned by the current user and non-writable" in (
        result.stderr
    )


def test_migrator_lifecycle_lock_serializes_two_wrapper_processes(tmp_path: Path) -> None:
    """두 wrapper가 공유 helper의 real flock 앞에서 writer drain 전에 멈춘다."""

    lock_path = tmp_path / "migrator-lifecycle.lock"
    ready_path = tmp_path / "holder-ready"
    environment = _environment(lock_path)
    holder = subprocess.Popen(  # noqa: S603 - fixed local Bash helper invocation
        [
            BASH,
            "-c",
            'source "$1"; acquire_migrator_lifecycle_lock; : >"$2"; sleep 10',
            "--",
            str(LOCK_HELPER),
            str(ready_path),
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for _ in range(100):
            if ready_path.exists():
                break
            assert holder.poll() is None, holder.stderr.read()
            time.sleep(0.02)
        assert ready_path.exists()

        contender = subprocess.run(  # noqa: S603 - fixed local Bash helper invocation
            [
                BASH,
                "-c",
                'source "$1"; acquire_migrator_lifecycle_lock',
                "--",
                str(LOCK_HELPER),
            ],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert contender.returncode == 2
        assert "another Pinvi migrator lifecycle is already running" in contender.stderr
    finally:
        holder.terminate()
        holder.wait(timeout=10)


def test_both_migration_wrappers_take_the_shared_lock_before_writer_drain() -> None:
    for name in ("docker-app.sh", "deploy-node.sh"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        lifecycle = source[
            source.index("migrate_under_lifecycle_lock() {") : source.index(
                "bootstrap_credential_file()"
            )
        ]
        wrapper = source[source.index("migrate() {") :]
        assert 'source "$ROOT_DIR/scripts/migrator-lifecycle-lock.sh"' in source
        assert wrapper.index("acquire_migrator_lifecycle_lock") < wrapper.index(
            "migrate_under_lifecycle_lock"
        )
        assert lifecycle.index("drain_runtime_writers") < lifecycle.index("prepare_migrator_login")
