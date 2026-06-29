#!/usr/bin/env python3
"""Small API p95 latency gate for T-270.

The script intentionally uses only the Python standard library so it can run on
N150, Odroid, or a CI shell without extra load-test dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Sample:
    path: str
    status_code: int
    elapsed_ms: float
    error: str | None = None


@dataclass(frozen=True)
class Summary:
    total: int
    ok: int
    errors: int
    error_rate: float
    p50_ms: float
    p95_ms: float
    max_ms: float
    passed: bool


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, int(round((percentile_value / 100.0) * len(ordered))))
    return ordered[min(rank, len(ordered)) - 1]


def summarize(
    samples: list[Sample],
    *,
    p95_ms_threshold: float,
    max_error_rate: float,
) -> Summary:
    elapsed = [sample.elapsed_ms for sample in samples]
    errors = sum(1 for sample in samples if sample.error or sample.status_code >= 500)
    total = len(samples)
    error_rate = errors / total if total else 1.0
    p95_ms = percentile(elapsed, 95)
    return Summary(
        total=total,
        ok=total - errors,
        errors=errors,
        error_rate=round(error_rate, 4),
        p50_ms=round(percentile(elapsed, 50), 2),
        p95_ms=round(p95_ms, 2),
        max_ms=round(max(elapsed) if elapsed else 0.0, 2),
        passed=p95_ms <= p95_ms_threshold and error_rate <= max_error_rate,
    )


def run_request(base_url: str, path: str, *, timeout_seconds: float) -> Sample:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    started = time.perf_counter()
    request = Request(url, headers={"User-Agent": "pinvi-t270-load-gate/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - caller supplies target
            response.read()
            status_code = int(response.status)
            error = None
    except HTTPError as exc:
        status_code = int(exc.code)
        error = None if exc.code < 500 else str(exc)
    except (OSError, URLError) as exc:
        status_code = 0
        error = str(exc)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return Sample(path=path, status_code=status_code, elapsed_ms=elapsed_ms, error=error)


def run_load(
    *,
    base_url: str,
    paths: list[str],
    requests: int,
    concurrency: int,
    timeout_seconds: float,
) -> list[Sample]:
    selected_paths = [paths[index % len(paths)] for index in range(requests)]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        futures = [
            executor.submit(run_request, base_url, path, timeout_seconds=timeout_seconds)
            for path in selected_paths
        ]
        return [future.result() for future in as_completed(futures)]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure simple API p95 latency.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PINVI_API_BASE_URL", "http://127.0.0.1:12801"),
    )
    parser.add_argument("--paths", default="/health,/health/db")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--p95-ms-threshold", type=float, default=500.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    paths = [path.strip() for path in args.paths.split(",") if path.strip()]
    if not paths:
        raise SystemExit("--paths must contain at least one path")
    samples = run_load(
        base_url=str(args.base_url),
        paths=paths,
        requests=max(1, int(args.requests)),
        concurrency=max(1, int(args.concurrency)),
        timeout_seconds=float(args.timeout_seconds),
    )
    summary = summarize(
        samples,
        p95_ms_threshold=float(args.p95_ms_threshold),
        max_error_rate=float(args.max_error_rate),
    )
    payload: dict[str, Any] = {
        "base_url": args.base_url,
        "paths": paths,
        "thresholds": {
            "p95_ms": args.p95_ms_threshold,
            "max_error_rate": args.max_error_rate,
        },
        "summary": asdict(summary),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
