# 코딩 / DB / 테스트 규약

본 디렉토리는 v1 `skills/*.ko.md`를 Pinvi v2 컨텍스트로 정리한 규약 모음.
**모든 AI agent와 사람이 본 규약을 PR 제출 전 확인**.

## 1. 인덱스

| 파일 | 범위 |
|------|------|
| [coding-style.md](./coding-style.md) | Python (FastAPI/Pydantic/SQLAlchemy) + TypeScript (Next.js) 규칙 |
| [database.md](./database.md) | PostgreSQL/PostGIS/Alembic 규칙 (Pinvi app schema) |
| [testing.md](./testing.md) | pytest / Vitest / Playwright 매트릭스 |
| [geospatial.md](./geospatial.md) | 좌표 / SRID / lon-lat / fuzzy 금지 |
| [normalization.md](./normalization.md) | 정규화 패턴 (1NF~BCNF + denorm) |

## 2. 우선순위

- 본 규약과 SPEC V8 / ADR가 충돌하면 **ADR 우선** (가장 최근 결정)
- 코드 구체적 패턴이 본 규약에 없으면 → 본 디렉토리에 ADR로 추가
- 모든 컨벤션 변경은 PR + ADR (`docs/decisions.md`)

## 3. AI agent 작업 가이드

새 PR 작성 시:

- [ ] [coding-style.md](./coding-style.md) lint/typecheck 통과
- [ ] [database.md](./database.md) — schema 변경 시 constraint 이름 / collation / index
- [ ] [testing.md](./testing.md) — 테스트 매트릭스 (unit/integration/e2e)
- [ ] [geospatial.md](./geospatial.md) — 좌표 다룰 때 lon-lat 순서 / SRID 명시
- [ ] [normalization.md](./normalization.md) — 새 테이블 설계 시 1NF~BCNF 점검
