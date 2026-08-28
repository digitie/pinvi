from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

import pytest


def _admission_module() -> ModuleType:
    path = Path(__file__).resolve().parents[4] / "scripts/m05_isolated_manager_admission.py"
    spec = importlib.util.spec_from_file_location("m05_isolated_manager_admission", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_admission(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "kind": "pinvi-m05-isolated-manager-admission-v1",
                "manager_source_revision": "a" * 40,
                "map_source_revision": "b" * 40,
                "pinset_sha256": "c" * 64,
                "pinvi_source_revision": "d" * 40,
                "transaction_id": "e" * 32,
                "version": 1,
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def test_accepts_only_a_bound_root_admission(tmp_path: Path) -> None:
    module = _admission_module()
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    admission = runtime / "manager-admission.json"
    _write_admission(admission)

    module.validate_admission(
        path=str(admission),
        project="m05i-pinvi-" + "e" * 32,
        pinvi_source_revision="d" * 40,
        pinset_sha256="c" * 64,
        expected_uid=os.getuid(),
    )


@pytest.mark.parametrize(
    ("project", "revision", "pinset"),
    [
        ("m05i-pinvi-" + "f" * 32, "d" * 40, "c" * 64),
        ("m05i-pinvi-" + "e" * 32, "f" * 40, "c" * 64),
        ("m05i-pinvi-" + "e" * 32, "d" * 40, "f" * 64),
    ],
)
def test_rejects_project_or_pair_mismatch(
    tmp_path: Path, project: str, revision: str, pinset: str
) -> None:
    module = _admission_module()
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    admission = runtime / "manager-admission.json"
    _write_admission(admission)

    with pytest.raises(module.AdmissionError):
        module.validate_admission(
            path=str(admission),
            project=project,
            pinvi_source_revision=revision,
            pinset_sha256=pinset,
            expected_uid=os.getuid(),
        )


def test_rejects_non_private_or_symlink_admission(tmp_path: Path) -> None:
    module = _admission_module()
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    admission = runtime / "manager-admission.json"
    _write_admission(admission)
    admission.chmod(0o644)

    with pytest.raises(module.AdmissionError):
        module.validate_admission(
            path=str(admission),
            project="m05i-pinvi-" + "e" * 32,
            pinvi_source_revision="d" * 40,
            pinset_sha256="c" * 64,
            expected_uid=os.getuid(),
        )

    admission.chmod(0o600)
    linked = runtime / "linked-admission.json"
    linked.symlink_to(admission)
    with pytest.raises(module.AdmissionError):
        module.validate_admission(
            path=str(linked),
            project="m05i-pinvi-" + "e" * 32,
            pinvi_source_revision="d" * 40,
            pinset_sha256="c" * 64,
            expected_uid=os.getuid(),
        )
