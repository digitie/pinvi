"""TripMate 소유 Dagster asset 모음.

`app` schema 소유 job만 둔다. feature/provider 적재 asset은 추가하지 않는다 —
그 책임은 `python-krtour-map` 독립 프로그램이 소유한다(ADR-003/ADR-026/ADR-045
Phase 6 T-210c, `docs/architecture/dagster-etl-bridge.md`).
"""

from __future__ import annotations

from .tripmate_kasi_special_days import tripmate_kasi_special_days

__all__ = ["tripmate_kasi_special_days"]
