# CLAUDE.md — 1쪽 진입 요약

이 파일은 Claude(Claude Code, Claude Agent SDK)가 가장 먼저 읽어야 할 1쪽 요약이다.
정식 정책·결정은 `AGENTS.md`, `SKILL.md`, `docs/decisions.md`가 갖는다.

> **다른 AI 도구 호환성** (ADR-016): Codex / Antigravity 등은 `AGENTS.md`를 1차
> 진입으로 사용한다. 본 파일과 `AGENTS.md`는 같은 결정·룰·식별자를 반영해야
> 한다 — 한 쪽 갱신 시 다른 쪽도 동기 갱신 필수.
>
> **Worktree + CodeGraph** (ADR-017): Claude Code는 `geo-claude` 전용 worktree
> (예: `F:/dev/tripmate-geo-claude`)에서만 작업. trunk 직접 편집 금지. 작업마다
> 브랜치만 새로 (`git fetch && git switch -c agent/claude-<task> main`),
> `codegraph sync`로 인덱스 유지. 절차는 `docs/runbooks/codegraph-worktrees.md`.

## 1. 이 저장소가 하는 일

`TripMate`는 한국 여행 계획·기록·공유 애플리케이션이다. 한국 공공 API에서 모은
지도·날씨·이벤트·가격·공지·경로·구역 데이터를 사용해 사용자 여행 계획 흐름을
제공한다.

**구성**: `apps/api` (FastAPI), `apps/web` (Next.js), `apps/etl` (Dagster) +
`infra/`, `docs/`. 지도 feature 도메인은 본 저장소가 아니라 **별 저장소**
`python-krtour-map` (PyPI `python-krtour-map`, import `from krtour.map import ...`)
이 소유한다. TripMate ↔ `python-krtour-map`은 **함수 직접 호출** (HTTP 없음).

## 2. 현 단계

**v2 설계 단계 (Sprint 1 진입 직전)**. v1은 `v1` 브랜치 보존, main은 새로
시작. **별도 요청 전까지 코드 작성 금지** — 사용자가 Sprint 1 진입을 승인하면
첫 PR로 `apps/` scaffolding이 들어간다. 본 단계 산출물은 문서/계약/결정뿐이다.

ADR 현황: 본 저장소의 ADR은 `docs/decisions.md`에 누적된다. v2 시작 ADR-001 ~
초기 핵심 ADR이 박혀 있다. `python-krtour-map`의 ADR과는 별개로 관리하되,
계약 경계가 겹치면 양쪽 ADR이 서로 참조한다.

v1 산출물 요약: `v1` 브랜치에 9개월간 누적된 `apps/`, `docs/`, `infra/`,
`scripts/`, `skills/`. v2가 가져오는 항목은 ADR로 한 건씩 박는다.

## 3. 진입 순서

1. `AGENTS.md` — 지시 우선순위, DO NOT 룰
2. `SKILL.md` — 도메인 어휘, 자주 묻는 작업
3. `docs/sprints/README.md` — Sprint 1~N 계획
4. `docs/architecture.md` — 책임 경계 (TripMate vs `python-krtour-map`)
5. `docs/resume.md` — 다음 한 작업
6. `docs/journal.md` 최신 3건
7. 관련 ADR (`docs/decisions.md`)

## 3.1 Sprint 4까지 PR 운영

새 PR이 올라오거나 draft가 `ready_for_review`로 전환되면
`docs/runbooks/pr-review-sprint4.md`를 따른다. 리뷰 후 상세 코멘트를 남기고,
필요한 코드 수정·기반 라이브러리 PR·TripMate sync·검증·머지까지 이어간다.
변경량 최소화보다 Sprint 1~4를 버틸 설계 정합성을 우선한다.
`.github/workflows/codex-pr-monitor.yml`이 5분마다 열린 PR을 감시한다.

## 4. 의존 스택 (v2 확정 골격)

- 백엔드: Python 3.12 / FastAPI / Uvicorn / SQLAlchemy 2 async / asyncpg /
  Pydantic v2 / httpx + tenacity / Alembic / Dagster / `python-krtour-map`
  (함수 라이브러리)
- 프론트엔드: Next.js 15 (App Router) + React 19 + TanStack Query v5 + Zustand +
  React Hook Form + Zod + shadcn/ui + Tailwind + **`maplibre-vworld-js`**
  (VWorld + MapLibre GL JS, ADR-015)
- 인프라: PostgreSQL 16 + PostGIS 3.5 + pg_trgm + pgcrypto / RustFS (S3 호환)
  / Docker Compose / Odroid M1S (운영 single node)
- 패키지 매니저: 백엔드 `uv`, 프론트 `npm`(workspaces)

## 5. 절대 금지 (가장 중요한 5개)

1. **main에 직접 push 금지** — 모든 변경은 feature branch + PR.
2. **`python-krtour-map`의 `feature`/`provider_sync` schema에 TripMate가
   직접 DDL/migration 금지** — 해당 schema는 `python-krtour-map`이 소유.
   TripMate는 `app` schema와 자체 도메인만 관리한다.
3. **TripMate에서 provider raw → DTO 변환 직접 작성 금지** —
   `python-krtour-map.providers`에 위임. 새 provider는 그쪽 저장소에 PR.
4. **`from krtour_map import ...` (flat) 사용 금지** — 항상
   `from krtour.map import ...` (PEP 420 namespace, `python-krtour-map`
   ADR-022).
5. **WSL ext4 미러를 거치지 않고 NTFS에서 직접 테스트/Docker 실행 금지** —
   `docs/dev-environment.md`의 미러 절차 준수.
6. **trunk** (`F:/dev/tripmate`, `~/tripmate-workspaces/tripmate`) **에 AI 도구가
   체크아웃 / 편집 금지** — Claude는 `geo-claude` worktree에서만 작업 (ADR-017,
   `docs/runbooks/codegraph-worktrees.md`).

전체 룰은 `SKILL.md` §4, `AGENTS.md`.

## 6. 작업 후 체크리스트 (1줄)

`pytest -q` + `ruff check` + `mypy --strict` (`apps/api`) + `npm run
lint` + `npm run typecheck` (`apps/web`) + `docs/journal.md` +
`docs/resume.md` (+ ADR/CHANGELOG/OpenAPI 해당 시).

## 7. 빠른 문서 검색

| 무엇을 하려는가 | 어디 보나 |
|---------------|----------|
| API endpoint 구현 / 변경 | `docs/api/<도메인>.md` + `docs/api/common.md` |
| DB schema 변경 | `docs/postgres-schema.md` + `docs/conventions/database.md` |
| 라이브러리 호출 | `docs/krtour-map-integration.md` |
| 외부 통합 (이메일/OAuth/AI) | `docs/integrations/<서비스>.md` |
| Frontend UI | `docs/architecture/frontend.md` + `DESIGN.md` |
| 지도 (`maplibre-vworld-js`) | `docs/integrations/maplibre-vworld.md` + `docs/design/marker-palette.md` |
| Admin 콘솔 | `docs/api/admin.md` + `docs/runbooks/admin.md` |
| ETL asset | `docs/runbooks/etl.md` + `docs/architecture/dagster-etl-bridge.md` |
| 사용자 위치 사용 | `docs/architecture/user-location.md` + `docs/compliance/lbs-act.md` |
| Notice plan (추천 여행) | `docs/architecture/notice-plans.md` + `docs/api/notice-plans.md` |
| 인프라 / 배포 | `docs/runbooks/{local-dev,docker-app,odroid-docker}.md` |
| Worktree + CodeGraph 운영 | `docs/runbooks/codegraph-worktrees.md` (ADR-017) |
| 컴플라이언스 / PII | `docs/compliance/{lbs-act,pipa,data-policy}.md` |
| 테스트 작성 | `docs/conventions/testing.md` |
| Sprint 작업 | `docs/sprints/SPRINT-<N>.md` |
| 결정 / ADR | `docs/decisions.md` |
| v1과 비교 | `docs/v1-to-v2-mapping.md` |

자세한 진입 순서는 `AGENTS.md` "AI Agent 작업 진입 절차".
