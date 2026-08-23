"""M05 activation의 파일 anchor와 Postgres append-only anchor를 대조한다."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from sqlalchemy import text

from app.core.config import settings
from app.db import session as db_session


class M05ActivationAnchorError(RuntimeError):
    """파일/DB activation anchor가 서로 다르다."""


def _file_anchor() -> tuple[int, str, str]:
    high_watermark = json.loads(
        Path(settings.pinvi_m05_activation_high_watermark_path).read_text(encoding="utf-8")
    )
    ledger_lines = (
        Path(settings.pinvi_m05_activation_ledger_path).read_text(encoding="utf-8").splitlines()
    )
    if not isinstance(high_watermark, dict) or not ledger_lines:
        raise M05ActivationAnchorError("M05 activation file anchor is empty")
    latest = json.loads(ledger_lines[-1])
    generation = high_watermark.get("generation")
    receipt_sha256 = high_watermark.get("receipt_sha256")
    record_sha256 = latest.get("record_sha256") if isinstance(latest, dict) else None
    if (
        type(generation) is not int
        or not isinstance(receipt_sha256, str)
        or not isinstance(record_sha256, str)
        or hashlib.sha256(
            json.dumps(
                {key: value for key, value in latest.items() if key != "record_sha256"},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        != record_sha256
        or latest.get("activation_generation") != generation
        or latest.get("receipt_sha256") != receipt_sha256
    ):
        raise M05ActivationAnchorError("M05 activation file anchor is inconsistent")
    return generation, receipt_sha256, record_sha256


async def verify_m05_activation_database_anchor() -> None:
    """운영 activation은 DB에 남은 최고 generation보다 낮아지면 startup을 거부한다."""

    if (
        settings.pinvi_environment not in {"staging", "production"}
        or not settings.pinvi_kor_travel_map_feature_reference_reconciliation_enabled
    ):
        return
    file_generation, file_receipt_sha256, file_record_sha256 = _file_anchor()
    try:
        async with db_session.async_session_factory() as db:
            result = await db.execute(
                text(
                    "SELECT generation, receipt_sha256, record_sha256 "
                    "FROM ops.m05_activation_database_anchor "
                    "ORDER BY generation DESC LIMIT 1"
                )
            )
            row = result.mappings().one_or_none()
    except Exception as exc:
        raise M05ActivationAnchorError("M05 activation DB anchor could not be read") from exc
    if row is None:
        raise M05ActivationAnchorError("M05 activation DB anchor is empty")
    database_anchor = cast(dict[str, object], row)
    if (
        database_anchor.get("generation") != file_generation
        or database_anchor.get("receipt_sha256") != file_receipt_sha256
        or database_anchor.get("record_sha256") != file_record_sha256
    ):
        raise M05ActivationAnchorError("M05 activation DB anchor does not match the file anchor")
