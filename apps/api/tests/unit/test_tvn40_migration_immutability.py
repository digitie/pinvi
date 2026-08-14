"""배포 가능한 T-VN-40 선행 migration의 byte 불변성을 고정한다."""

from __future__ import annotations

import hashlib
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2]
_PINNED_MIGRATION_SHA256 = {
    "20260811_0050_cache_target_restore_fence_receipts.py": (
        "b5c67e985dcf7d49f65a3ae3caa4e8ed5cd8e69ca0dafd31ccf0554ef44e7e98"
    ),
    "20260814_0051_curation_collection_import_receipts.py": (
        "d36f5f4a0c6133b4d2e2554fa5a26d176614a51f05b415e94c3015f779dd21c9"
    ),
}


def test_published_tvn40_migrations_are_byte_immutable() -> None:
    versions_dir = API_DIR / "alembic" / "versions"
    actual = {
        filename: hashlib.sha256((versions_dir / filename).read_bytes()).hexdigest()
        for filename in _PINNED_MIGRATION_SHA256
    }
    assert actual == _PINNED_MIGRATION_SHA256
