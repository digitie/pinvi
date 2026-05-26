"""Audit log content_hash chain — `docs/compliance/lbs-act.md` §3.3.

직전 row content_hash + 현재 row 표준 표현 SHA-256 → chain 검증.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

GENESIS_HASH = "0" * 64


def compute_content_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    """SHA-256(prev_hash + canonical JSON of payload)."""
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + serialized).encode("utf-8")).hexdigest()


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
