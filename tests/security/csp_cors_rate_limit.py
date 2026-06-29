#!/usr/bin/env python3
"""CSP/CORS/rate-limit smoke gate for T-270."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

REQUIRED_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "x-frame-options": "DENY",
    "permissions-policy": "geolocation=(self)",
}


@dataclass(frozen=True)
class ProbeResult:
    name: str
    passed: bool
    findings: list[str]


def normalize_headers(headers: Any) -> dict[str, str]:
    return {str(name).lower(): str(value) for name, value in dict(headers).items()}


def security_header_findings(
    headers: dict[str, str],
    *,
    require_hsts: bool = False,
    require_csp: bool = True,
) -> list[str]:
    findings: list[str] = []
    for name, expected in REQUIRED_SECURITY_HEADERS.items():
        actual = headers.get(name)
        if actual != expected:
            findings.append(f"{name}: expected {expected!r}, got {actual!r}")
    if require_csp and not headers.get("content-security-policy"):
        findings.append("content-security-policy: missing")
    if require_hsts and not headers.get("strict-transport-security", "").startswith("max-age="):
        findings.append("strict-transport-security: missing or invalid")
    return findings


def cors_findings(
    headers: dict[str, str],
    *,
    origin: str,
    require_credentials: bool = True,
) -> list[str]:
    findings: list[str] = []
    allow_origin = headers.get("access-control-allow-origin")
    allow_credentials = headers.get("access-control-allow-credentials")
    if allow_origin != origin:
        findings.append(f"access-control-allow-origin: expected {origin!r}, got {allow_origin!r}")
    if require_credentials and allow_credentials != "true":
        findings.append("access-control-allow-credentials: expected 'true'")
    if allow_origin == "*" and allow_credentials == "true":
        findings.append("cors: wildcard origin cannot be combined with credentials")
    return findings


def rate_limit_findings(status_codes: list[int]) -> list[str]:
    if not status_codes:
        return ["rate-limit: probe skipped"]
    if 429 not in status_codes:
        return [f"rate-limit: expected at least one 429, got {status_codes!r}"]
    return []


def _request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    timeout_seconds: float,
) -> tuple[int, dict[str, str]]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = Request(url, method=method, headers=headers or {})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - caller supplies target
            response.read()
            return int(response.status), normalize_headers(response.headers)
    except HTTPError as exc:
        return int(exc.code), normalize_headers(exc.headers)
    except (OSError, URLError) as exc:
        return 0, {"x-pinvi-probe-error": str(exc)}


def run_probe(
    *,
    base_url: str,
    origin: str,
    security_path: str,
    timeout_seconds: float,
    require_hsts: bool,
    rate_limit_path: str | None,
    rate_limit_attempts: int,
) -> list[ProbeResult]:
    _, security_headers = _request(
        base_url,
        security_path,
        headers={"Origin": origin},
        timeout_seconds=timeout_seconds,
    )
    security = security_header_findings(security_headers, require_hsts=require_hsts)
    results = [ProbeResult(name="security_headers", findings=security, passed=not security)]

    _, cors_headers = _request(
        base_url,
        security_path,
        method="OPTIONS",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
        timeout_seconds=timeout_seconds,
    )
    cors = cors_findings(cors_headers, origin=origin)
    results.append(ProbeResult(name="cors", findings=cors, passed=not cors))

    if rate_limit_path and rate_limit_attempts > 0:
        status_codes = [
            _request(base_url, rate_limit_path, timeout_seconds=timeout_seconds)[0]
            for _ in range(rate_limit_attempts)
        ]
        rate_limit = rate_limit_findings(status_codes)
        results.append(ProbeResult(name="rate_limit", findings=rate_limit, passed=not rate_limit))
    else:
        results.append(ProbeResult(name="rate_limit", findings=["probe skipped"], passed=True))

    return results


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check API CSP/CORS/rate-limit boundaries.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PINVI_API_BASE_URL", "http://127.0.0.1:12801"),
    )
    parser.add_argument("--origin", default=os.environ.get("PINVI_WEB_ORIGIN", "http://127.0.0.1:12805"))
    parser.add_argument("--security-path", default="/health")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--require-hsts", action="store_true")
    parser.add_argument("--rate-limit-path", default="")
    parser.add_argument("--rate-limit-attempts", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    results = run_probe(
        base_url=str(args.base_url),
        origin=str(args.origin),
        security_path=str(args.security_path),
        timeout_seconds=float(args.timeout_seconds),
        require_hsts=bool(args.require_hsts),
        rate_limit_path=str(args.rate_limit_path) or None,
        rate_limit_attempts=max(0, int(args.rate_limit_attempts)),
    )
    payload: dict[str, Any] = {
        "base_url": args.base_url,
        "origin": args.origin,
        "results": [asdict(result) for result in results],
        "passed": all(result.passed for result in results),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
