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
    "20260814_0052_curation_import_causal_seal.py": (
        "47fe6ec05e1c239372cfd7c9b725ff748ed86f28bff41d0ad3248e675a8da198"
    ),
    "20260814_0053_curation_import_receipt_lock.py": (
        "4f970fb4bb7e650c10eb99c2effdb144482e4e4f6690ef8cc3f72904df025cb2"
    ),
    "20260814_0054_curation_import_receipt_undelete_lock.py": (
        "430b4bc1ea214c4e89c9824f5dc97687f7f1386bd74a35b9819352b18238f9df"
    ),
    "20260814_0055_curation_import_response_correlation.py": (
        "ef08e2e3307736731ddc62fe8b2df96762ac605c52aa92a5f538f863808abdca"
    ),
    "20260814_0056_curation_import_authority.py": (
        "6b937cc2a395c4b180f77a86e718ab0e4c4da2e315a86a3a50f1b607013ac32a"
    ),
    "20260814_0057_curation_cutover_mapping_receipts.py": (
        "182b4b65c25a4144327d822533b7ecb0e2069b8c89201bedbd8d0104e58a9ae8"
    ),
    "20260814_0058_curation_cutover_mapping_capture.py": (
        "84591b5af9b65112762167c001d3d6abd2e756e346e9a2a2283460a5135a867e"
    ),
    "20260814_0059_curation_cutover_backfill_receipts.py": (
        "ee8e9467c048518c0f0e19a34ad937528dec3e578fb85d277938015d83c110d9"
    ),
}


def test_published_tvn40_migrations_are_byte_immutable() -> None:
    versions_dir = API_DIR / "alembic" / "versions"
    actual = {
        filename: hashlib.sha256((versions_dir / filename).read_bytes()).hexdigest()
        for filename in _PINNED_MIGRATION_SHA256
    }
    assert actual == _PINNED_MIGRATION_SHA256
