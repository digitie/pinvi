"""KST 시간 헬퍼.

DB는 UTC `timestamptz` 저장, 응용 변환은 KST. `docs/conventions/coding-style.md` §2.10.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def kst_now() -> datetime:
    return datetime.now(tz=KST)


def utc_now() -> datetime:
    return datetime.now(tz=UTC)
