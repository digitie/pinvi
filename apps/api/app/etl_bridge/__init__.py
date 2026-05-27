"""TripMate ↔ `python-krtour-map` 라이브러리 bridge.

- ADR-002: 함수 직접 호출 (REST 없음)
- ADR-005: provider 어댑터 wrapper 금지 — 본 모듈은 lifespan/DI helper만 제공
- ADR-006: Dagster code location 분리 (apps/etl) — 본 모듈은 apps/api 전용
- `docs/krtour-map-integration.md` §3 기준
"""
