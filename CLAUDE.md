# CLAUDE.md — 1쪽 진입 요약

이 파일은 Claude(Claude Code, Claude Agent SDK)가 가장 먼저 읽어야 할 1쪽 요약이다.
정식 정책·결정은 `AGENTS.md`, `SKILL.md`, `docs/decisions.md`가 갖는다.

> **다른 AI 도구 호환성** (ADR-016): Codex / Antigravity 등은 `AGENTS.md`를 1차
> 진입으로 사용한다. 본 파일과 `AGENTS.md`는 같은 결정·룰·식별자를 반영해야
> 한다 — 한 쪽 갱신 시 다른 쪽도 동기 갱신 필수.
>
> **Worktree + CodeGraph** (ADR-017): Claude Code는 `tripmate-claude` 전용 worktree
> (예: `F:/dev/tripmate-claude`)에서만 작업. trunk 직접 편집 금지. 작업마다
> 브랜치만 새로 (`git fetch && git switch -c agent/claude-<task> origin/main`
> — 로컬 `main` ref는 trunk가 점유하므로 worktree에서는 `origin/main`을 직접 사용),
> `codegraph sync`로 인덱스 유지. 절차는 `docs/runbooks/codegraph-worktrees.md`.
>
> **개발 환경** (ADR-024): **NTFS worktree = git source of truth**(`F:/dev/tripmate-claude`)
> — 편집/commit/push/PR은 여기서 **Windows git(`git.exe`)으로만**. WSL git으로
> `/mnt/f/...` 같은 worktree를 다루지 않는다(포인터 환경 혼용 → `prunable`/prune
> 사고). **WSL ext4 미러**(`~/tripmate-workspaces/tripmate-claude`)는 의존성·
> `pytest`·docker·장기 실행 전용 **일회용**(commit 금지). `apps/web` dev server,
> lint, typecheck, build, Vitest도 WSL 미러에서 실행한다. Playwright 기반 브라우저
> e2e만 Windows Node/브라우저에서 실행한다. **rsync는 NTFS→ext4 단방향**. 절차·
> 함정은 `docs/dev-environment.md`. 로컬 장기 실행 dev 포트는 API `9021`, 웹
> `9022`, Dagster `9023`, krtour-map API `9011`, krtour-map admin `9012`,
> RustFS API `9003`, RustFS console `9004`로 고정하며, `npm run dev:up`은 점유
> 중인 해당 포트를 먼저 종료한 뒤 같은 포트로 재기동한다. Docker app
> build/run/smoke는 `scripts/docker-app.sh`를 사용한다.
>
> **CodeGraph Commands**
> - 인덱싱 초기화: `codegraph init -i` (worktree마다 1회)
> - 동기화 상태 확인: `codegraph status`
> - 새 task 시작 시: `codegraph sync`
>
> **Code Style & Rules** — 컴포넌트 / 함수 / 서비스를 수정하기 전 반드시 CodeGraph
> 의 `codegraph_explore` 도구로 영향도를 먼저 평가한다. grep / Read fan-out 대신
> 한 번의 MCP 호출로 관련 심볼 source + 호출 관계를 본다. 보조: `codegraph_impact`
> (반경) / `codegraph_callers` (호출자) / `codegraph_trace` (경로).

## 1. 이 저장소가 하는 일

`TripMate`는 한국 여행 계획·기록·공유 애플리케이션이다. 한국 공공 API에서 모은
지도·날씨·이벤트·가격·공지·경로·구역 데이터를 사용해 사용자 여행 계획 흐름을
제공한다.

**구성**: `apps/api` (FastAPI), `apps/web` (Next.js), `apps/etl` (Dagster) +
`infra/`, `docs/`. 지도 feature 도메인은 본 저장소가 아니라 **별 저장소**
`python-krtour-map`이 소유한다. TripMate ↔ `python-krtour-map`은 최신
`python-krtour-map` **OpenAPI HTTP 계약**으로 통신한다(ADR-026, API `9011`,
admin `9012`).

## 2. 현 단계

**Sprint 1~3 머지 완료**. 현재 기준선은 Sprint 4 준비/진행 단계다
(지도 + 사용자 UI + `maplibre-vworld-js` + CI/CD 재활성 → **v0.1.0** 출시).
이후 Sprint 5 (실시간 + ETL + Grafana embed + Backup 1차 → **v0.2.0**) → Sprint
6 (MCP 외부 인터페이스 + Backup UI 핫스왑 + Korean geofencing + T108 N150 병행
배포 + 법무 → **v1.0.0**). 릴리즈 마일스톤 표는 `docs/sprints/README.md`.

ADR 현황: ADR-001 ~ **ADR-035**. 최근 박힘: ADR-024 (NTFS worktree=git source of
truth), ADR-025 (geocoding은 kraddr-geo v2 REST 직접), ADR-026 (krtour-map은 OpenAPI
HTTP 계약), **ADR-027** (그 HTTP 계약은 krtour-map이 신규 구축해야 할 목표 — 현재
미존재, DEC-01=B), ADR-028 (정규 feature_id = krtour `make_feature_id`),
ADR-029 (`notice_plans` 충돌 → 큐레이션은 `curated_trip_plans`), ADR-030 (외부 API
규약 정본 + `/v1` 노출), ADR-031 (POI soft delete + `feature_id` nullable),
ADR-032 (access JWT + httpOnly cookie), ADR-033 (`users.roles[]` Admin RBAC),
ADR-034 (Admin audit hash chain), ADR-035 (Trip WebSocket in-memory broker). 다음
신규 = ADR-036. 2026-06-06 정합성 감사:
`docs/audit/2026-06-06-doc-impl-audit.md`.

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
`.github/workflows/codex-pr-monitor.yml`이 외부 API key 없이 5분마다 열린 PR을
감시하고 review reminder를 남긴다. 실제 리뷰는 에이전트 또는 사람이 수행한다.

## 4. 의존 스택 (v2 확정 골격)

- 백엔드: Python 3.12 / FastAPI / Uvicorn / SQLAlchemy 2 async / asyncpg /
  Pydantic v2 / httpx + tenacity / Alembic / Dagster / krtour-map OpenAPI HTTP client
- 프론트엔드: Next.js 15 (App Router) + React 19 + TanStack Query v5 + Zustand +
  React Hook Form + Zod + shadcn/ui + Tailwind + **`maplibre-vworld-js`**
  (VWorld + MapLibre GL JS, ADR-015)
- 인프라: PostgreSQL 16 + PostGIS 3.5 + pg_trgm + pgcrypto / RustFS (S3 호환)
  / Docker Compose / N150 16GB + Odroid M1S 병행 운영 (ADR-023)
- 패키지 매니저: 백엔드 `uv`, 프론트 `npm`(workspaces)

## 5. 절대 금지 (가장 중요한 6개)

1. **main에 직접 push 금지** — 모든 변경은 feature branch + PR.
2. **`python-krtour-map`의 `feature`/`provider_sync` schema에 TripMate가
   직접 DDL/migration 금지** — 해당 schema는 `python-krtour-map`이 소유.
   TripMate는 `app` schema와 자체 도메인만 관리한다.
3. **TripMate에서 provider raw → DTO 변환 직접 작성 금지** —
   `python-krtour-map.providers`에 위임. 새 provider는 그쪽 저장소에 PR.
4. **TripMate 사용자 경로에서 `python-krtour-map` import 금지** — feature read/write
   request는 `TRIPMATE_KRTOUR_MAP_API_BASE_URL`의 OpenAPI HTTP 계약을 호출한다.
5. **NTFS에서 직접 테스트/Docker 실행 금지 + ext4 미러에서 commit 금지** — 테스트·
   docker·의존성은 WSL ext4 미러, git/commit/push는 NTFS worktree. rsync는 NTFS→ext4
   단방향 (ADR-024, `docs/dev-environment.md`).
6. **trunk** (`F:/dev/tripmate`, `~/tripmate-workspaces/tripmate`) **에 AI 도구가
   체크아웃 / 편집 금지** — Claude는 `tripmate-claude` worktree에서만 작업 (ADR-017,
   `docs/runbooks/codegraph-worktrees.md`).

전체 룰은 `SKILL.md` §4, `AGENTS.md`.

## 6. 작업 후 체크리스트 (1줄)

`pytest -q` + `ruff check` + `mypy --strict` (`apps/api`, WSL 미러) + `npm run
lint` + `npm run typecheck` (`apps/web`, WSL 미러) + Playwright는 Windows +
`docs/journal.md` + `docs/resume.md` (+ ADR/CHANGELOG/OpenAPI 해당 시).

## 7. 빠른 문서 검색

| 무엇을 하려는가 | 어디 보나 |
|---------------|----------|
| API endpoint 구현 / 변경 | `docs/api/<도메인>.md` + `docs/api/common.md` |
| DB schema 변경 | `docs/postgres-schema.md` + `docs/conventions/database.md` |
| krtour-map OpenAPI 호출 (feature 데이터) | `docs/krtour-map-integration.md` |
| Geocoding (주소/좌표/행정구역) | `docs/integrations/kraddr-geo.md` (ADR-025, kraddr-geo v2 REST 직접) + `docs/architecture/geocoding-open-decisions.md` |
| 외부 통합 (이메일/OAuth/AI companion 호출 계약) | `docs/integrations/<서비스>.md` |
| Frontend UI | `docs/architecture/frontend.md` + `DESIGN.md` |
| 지도 (`maplibre-vworld-js`) | `docs/integrations/maplibre-vworld.md` + `docs/design/marker-palette.md` |
| Admin 콘솔 | `docs/api/admin.md` + `docs/runbooks/admin.md` |
| ETL asset | `docs/runbooks/etl.md` + `docs/architecture/dagster-etl-bridge.md` |
| 사용자 위치 사용 | `docs/architecture/user-location.md` + `docs/compliance/lbs-act.md` |
| Notice plan (추천 여행) | `docs/architecture/notice-plans.md` + `docs/api/notice-plans.md` |
| 인프라 / 배포 | `docs/runbooks/{local-dev,docker-app,odroid-docker}.md` (Sprint 6에 N150 병행 — ADR-023) |
| 릴리즈 마일스톤 | `docs/sprints/README.md` (v0.1.0 / v0.2.0 / v1.0.0 표) |
| MCP 외부 인터페이스 | `docs/architecture/mcp-server.md` + `docs/runbooks/mcp-server.md` (ADR-019, Sprint 6) |
| 한국 전용 geofencing | `docs/architecture/korea-only-policy.md` + `docs/runbooks/korea-only.md` (ADR-018, Sprint 6) |
| Backup / Restore | `docs/architecture/backup-restore.md` + `docs/runbooks/backup-restore.md` (ADR-022, Sprint 5~6) |
| Admin Grafana embed | `docs/runbooks/grafana-admin-embed.md` (Sprint 5) |
| Worktree + CodeGraph 운영 | `docs/runbooks/codegraph-worktrees.md` (ADR-017) |
| 개발 환경 (NTFS git + WSL 테스트 미러) | `docs/agent-workflow.md` (런북) + `docs/dev-environment.md` (ADR-024) |
| 환경/도구 실패 패턴 | `docs/agent-failure-patterns.md` |
| 컴플라이언스 / PII | `docs/compliance/{lbs-act,pipa,data-policy}.md` |
| 테스트 작성 | `docs/conventions/testing.md` |
| Sprint 작업 | `docs/sprints/SPRINT-<N>.md` |
| 결정 / ADR | `docs/decisions.md` |
| v1과 비교 | `docs/v1-to-v2-mapping.md` |

자세한 진입 순서는 `AGENTS.md` "AI Agent 작업 진입 절차".
