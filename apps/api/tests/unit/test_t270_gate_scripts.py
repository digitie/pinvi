"""T-270 load/security gate script helper tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[4]


def _load_script(relative_path: str) -> ModuleType:
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def test_api_p95_latency_summary_passes_within_threshold() -> None:
    script = _load_script("tests/load/api_p95_latency.py")
    samples = [
        script.Sample(path="/health", status_code=200, elapsed_ms=10.0),
        script.Sample(path="/health", status_code=200, elapsed_ms=20.0),
        script.Sample(path="/health", status_code=200, elapsed_ms=30.0),
    ]

    summary = script.summarize(samples, p95_ms_threshold=50.0, max_error_rate=0.0)

    assert summary.passed is True
    assert summary.p95_ms == 30.0
    assert summary.errors == 0


def test_api_p95_latency_summary_fails_on_error_rate() -> None:
    script = _load_script("tests/load/api_p95_latency.py")
    samples = [
        script.Sample(path="/health", status_code=200, elapsed_ms=10.0),
        script.Sample(path="/health", status_code=503, elapsed_ms=20.0),
    ]

    summary = script.summarize(samples, p95_ms_threshold=50.0, max_error_rate=0.0)

    assert summary.passed is False
    assert summary.errors == 1
    assert summary.error_rate == 0.5


def test_security_header_findings_accept_expected_headers() -> None:
    script = _load_script("tests/security/csp_cors_rate_limit.py")
    headers = {
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin-when-cross-origin",
        "x-frame-options": "DENY",
        "permissions-policy": "geolocation=(self)",
        "content-security-policy": "default-src 'none'",
    }

    assert script.security_header_findings(headers) == []


def test_cors_findings_reject_wildcard_credentials() -> None:
    script = _load_script("tests/security/csp_cors_rate_limit.py")
    headers = {
        "access-control-allow-origin": "*",
        "access-control-allow-credentials": "true",
    }

    findings = script.cors_findings(headers, origin="https://pinvi.example.com")

    assert "wildcard origin cannot be combined with credentials" in " ".join(findings)
