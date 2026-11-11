"""Docker 실제 OCI/ENV revision을 검증한 checkout과 결박한다."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def verify_revision(document: Any, expected: str) -> None:
    """형식이 맞아도 checkout과 다른 label/ENV는 거부한다."""
    if re.fullmatch(r"[0-9a-f]{40}", expected) is None:
        raise ValueError("expected checkout revision must be an exact commit")
    if not isinstance(document, list) or len(document) != 1:
        raise ValueError("inspect must contain exactly one built image")
    config = document[0].get("Config") or {}
    labels = config.get("Labels") or {}
    if labels.get("org.opencontainers.image.revision") != expected:
        raise ValueError("image OCI revision does not match verified checkout")
    source_values = [
        entry.split("=", 1)[1]
        for entry in config.get("Env") or []
        if entry.startswith("PINVI_SOURCE_REVISION=")
    ]
    if source_values != [expected]:
        raise ValueError("image revision ENV does not match verified checkout")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("inspect_json", type=Path)
    args = parser.parse_args()
    try:
        verify_revision(json.loads(args.inspect_json.read_text()), args.expected_revision)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print("Image OCI revision and ENV match verified checkout " + args.expected_revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
