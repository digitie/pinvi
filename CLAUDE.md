# CLAUDE.md — 1쪽 진입 요약

이 파일은 Claude(Claude Code, Claude Agent SDK)가 가장 먼저 읽어야 할 1쪽 요약이다.
정식 정책·결정은 `AGENTS.md`, `SKILL.md`, `docs/decisions.md`가 갖는다.

> **다른 AI 도구 호환성** (ADR-016): Codex / Antigravity 등은 `AGENTS.md`를 1차
> 진입으로 사용한다. 본 파일과 `AGENTS.md`는 같은 결정·룰·식별자를 반영해야
> 한다 — 한 쪽 갱신 시 다른 쪽도 동기 갱신 필수.
>
> **작업 원칙**: 모호한 요청은 중요한 가정을 드러내고, 해석에 따라 구현 방향이
> 크게 달라지면 먼저 확인한다. 요청을 완전히 해결하는 최소 코드만 작성하고,
> 일회성 추상화·요청 밖 기능·관련 없는 포맷 변경을 피한다. 변경은 리뷰 가능한
> 범위로 유지하며, 버그 수정은 재현과 목적이 분명한 검증으로 확인한다. 완전한
> 검증이 불가능하면 미검증 범위를 명확히 남긴다.
>
> **Worktree + CodeGraph** (ADR-017/051): Claude Code는 `pinvi-claude` 전용 worktree
> (예: `/mnt/f/dev/pinvi-claude`)에서만 작업. trunk 직접 편집 금지. 작업마다
> 브랜치만 새로 (`git fetch && git switch -c agent/claude-<task> origin/main`
> — 로컬 `main` ref는 trunk가 점유하므로 worktree에서는 `origin/main`을 직접 사용),
> Linux native `codegraph sync`로 인덱스 유지. 절차는
> `docs/runbooks/codegraph-worktrees.md`.
>
> **개발 환경** (ADR-051): **모든 개발·git·CodeGraph는 Linux에서 수행**한다.
> 기존 `/mnt/f/...` worktree에 Windows `F:/...` 포인터가 남아 있으면 Linux에서
> `git worktree repair <path>`를 먼저 실행한다. `command -v codegraph`가 `/mnt/c/...`,
> `.exe`, `.cmd`를 가리키면 중지하고 Linux native 설치/PATH로 교정한다. 의존성 설치,
> `pytest`, Docker, dev server, lint/typecheck/build/Vitest도 Linux에서 실행한다.
> Playwright는 N150에서 먼저 실행하고, 기본은 `scripts/n150-playwright-runner.sh` Docker
> runner다. N150 Docker runner와 host browser 실행이 모두 runtime/권한/네트워크 문제로
> 불가능할 때만 Windows runner를 fallback으로 사용하며 사유를 기록한다. 절차·함정은
> `docs/dev-environment.md`. **dev/prod 분리(ADR-047)**: 별도 지시가 없으면
> 작업 대상은 **dev**다. **dev**는 이 worktree에서 직접(`npm run dev:up`) 또는 ktdctl로
> 띄우며 **내부 주소 `127.0.0.1`의 12xxx 고정 포트**만 쓴다(외부 미노출). **prod**는
> `kor-travel-docker-manager`(`ktdctl`)로 컨테이너를 올리고 **공식 도메인**(gitignore된
> `infra/.env.prod`)을 적용한다. 로컬 장기 실행 12xxx 고정 포트는 PostgreSQL `5432`,
> API `12801`, 웹 `12805`, Dagster `12802`, kor-travel-map API/Admin API `12701`,
> RustFS API `12101`, RustFS console `12105`다. **포트 충돌 정책(ADR-047)**: 고정 포트가
> 이미 점유돼 있으면 **새 포트로 바꾸지 않고**, prod/dev 무관하게 **강제종료 여부를
> 사용자에게 묻는다**. 사용자가 거부하면(또는 비대화형 기본) **작업을 중지**한다
> (`npm run dev:up`은 자동 종료하지 않음; `PINVI_DEV_FORCE_KILL=1`로만 비대화형 강제종료).
> Docker 빌드/실행은 `kor-travel-docker-manager`(`ktdctl`)를 1차 경로로 쓰고, 불가 시
> `scripts/docker-app.sh`로 폴백한다 (Docker 진입 경로 ADR-040, 포트 정책 ADR-042,
> `docs/runbooks/docker-app.md` §0).
>
> **CodeGraph Commands**
>
> - 인덱싱 초기화: `codegraph init -i` (worktree마다 1회)
> - 동기화 상태 확인: `codegraph status`
> - 새 task 시작 시: `codegraph sync`
>
> **Telegram 완료 알림 MCP** — PR을 만들면 최종 응답 전 `mcp-telegram` MCP의
> `send_message`(`entity` 기본 `me`)로 완료 요약 + PR 링크를 보낸다. credential은
> worktree 로컬 `.env.mcp-telegram`(gitignore, GitHub secret 미사용)에만 둔다. 모든
> agent(claude/codex/antigravity) 공통. 셋업 `docs/runbooks/codegraph-worktrees.md`,
> 규칙 `AGENTS.md` "Telegram 작업 완료 알림 MCP".
>
> **Code Style & Rules** — 컴포넌트 / 함수 / 서비스를 수정하기 전 반드시 CodeGraph
> 의 `codegraph_explore` 도구로 영향도를 먼저 평가한다. grep / Read fan-out 대신
> 한 번의 MCP 호출로 관련 심볼 source + 호출 관계를 본다. 보조: `codegraph_impact`
> (반경) / `codegraph_callers` (호출자) / `codegraph_trace` (경로).

## 1. 이 저장소가 하는 일

`Pinvi`는 한국 여행 계획·기록·공유 애플리케이션이다. 한국 공공 API에서 모은
지도·날씨·이벤트·가격·공지·경로·구역 데이터를 사용해 사용자 여행 계획 흐름을
제공한다.

**구성**: `apps/api` (FastAPI), `apps/web` (Next.js), `apps/mobile` (Expo Dev Client
앱, 활성 — Sprint M-1, SDK 56 / minSdk 24), `apps/etl` (Dagster) + `infra/`, `docs/`. 지도 feature 도메인은 본
저장소가 아니라 **별 저장소**
`kor-travel-map`이 소유한다. Pinvi ↔ `kor-travel-map`은 최신
`kor-travel-map` **OpenAPI HTTP 계약**으로 통신한다(ADR-026, API/Admin API
`12701`).

## 2. 현 단계

**Sprint 1~4 완료**. Sprint 4의 라이브 feature read / 지도 UI / CI 게이트는
머지됐고, **v0.1.0** tag/GitHub Release는 2026-06-13에 완료됐다. 현재 기준선은
post-v0.1.0 `Unreleased` 보강 진행 단계다. 이후 Sprint 5 (실시간 + ETL + Grafana embed + Backup 1차 → **v0.2.0**) → Sprint
6 (MCP 외부 인터페이스 + Backup UI 핫스왑 + Korean geofencing + T108 N150 병행
배포 + 법무 → **v1.0.0**). 릴리즈 마일스톤 표는 `docs/sprints/README.md`.

ADR 현황: ADR-001 ~ **ADR-056**. 최근 박힘: ADR-024 (ADR-051로 superseded —
과거 NTFS/WSL 미러 모델), ADR-025 (geocoding은 kor-travel-geo v2 REST 직접), ADR-026 (kor-travel-map은 OpenAPI
HTTP 계약), **ADR-027** (그 HTTP 계약은 kor-travel-map이 신규 구축해야 할 목표 — 현재
미존재, DEC-01=B), ADR-028 (정규 feature_id = kor_travel_map `make_feature_id`),
ADR-029 (`notice_plans` 충돌 → 큐레이션은 `curated_trip_plans`), ADR-030 (외부 API
규약 정본 + `/v1` 노출), ADR-031 (POI soft delete + `feature_id` nullable),
ADR-032 (access JWT + httpOnly cookie), ADR-033 (`users.roles[]` Admin RBAC),
ADR-034 (Admin audit hash chain), ADR-035 (Trip WebSocket in-memory broker),
ADR-036 (curated plan 자체 큐레이션 + kor_travel_map `curated_features` import + nullable
feature link), ADR-037 (로컬 고정 포트 재배정 — ADR-042로 superseded),
ADR-038 (운영 HTTP rate-limit는
Postgres fixed-window bucket), ADR-039 (운영 노드 간 DB live sync 미사용), ADR-040
(Docker 빌드/실행은 kor-travel-docker-manager 1차 + `scripts/docker-app.sh` 폴백),
ADR-041 (Expo `apps/mobile` 구조 스캐폴드 — 활성화는 Sprint M-1),
ADR-042 (`kor-travel-docker-manager` target 대역 기반 로컬 포트 정책),
ADR-043 (모바일은 Expo Dev Client + EAS Build, Expo Go 미사용, RN New Architecture,
Android minSdk 24, VWorld server-issued key 구조),
ADR-044 (모바일 지도 엔진 = `maplibre-vworld-react`/`vworld-map-rn`, vendored tarball `file:` 핀
소비, server-issued 키),
ADR-045 (모바일 VWorld 키 런타임 정책 — 현 단계는 인증 게이트 + 감사 로깅의 문서화된 운영
제한, opaque token/tile proxy는 공개 배포 전 게이트),
ADR-046 (Web 지도 클라이언트도 `maplibre-vworld-react`의 `vworld-map-web` + `vworld-map-core`
vendored tarball 소비로 전환, 기존 `maplibre-vworld`/`maplibre-vworld-js` 의존 삭제),
ADR-047 (운영 도메인은 공개 repo 비노출 — gitignore `infra/.env.prod`에만 두고
compose `--env-file`로 주입, 추적 문서는 `*.example.com` placeholder + Dagster webserver는
12802로 고정), ADR-048 (`kor-travel-geo` v2 공개 API key는 서버 `PINVI_VWORLD_API_KEY`와
동일하며, hash 저장/검증은 `kor-travel-geo`가 소유), ADR-049 (외부 계약 동기화 2026-06-25 —
kor-travel-map 큐레이션 import는 admin `detail-snapshot`(`plan`→`content`, 서비스 토큰),
kor-travel-geo `/v2/regions/within-radius`는 `radius_km`+`levels[]`(`legal_dong`→`emd`) 그룹 응답),
ADR-050 (Pinvi app-owned Dagster job 표준 — retry/backoff, idempotency, failure notification,
destructive dry-run gate), ADR-051 (개발·git·CodeGraph는 Linux 기준, Playwright는 N150 우선),
ADR-052 (category mapping은 taxonomy가 아니라 Admin presentation override만 저장),
ADR-053 (trip day 경로 최적화 = 순수 Python nearest-neighbor + 2-opt, haversine),
ADR-054 (외부 장소 provider Kakao/Naver Local = 서버측 display-only 검색·place-link + `GET /search`
통합 + feature-request 확장, ADR-015의 Local-검색 부분 supersede),
ADR-055 (Trip-day 표시 모델 — 파생 effective_date + 일자 팔레트 색 + 서버 display_marker_color +
전용 `trip_day_rise_sets`),
ADR-056 (Feature 상세 = kind별 `detail-card` 투영 + 옵트인 외부 enrichment + 공용 `useModalDialog`).
다음 신규 = ADR-057. **TDR(Trip Detail Rewrite)** 마스터 계획 = `docs/execplan/trip-detail-rewrite.md`.
2026-06-06 정합성 감사:
`docs/audit/2026-06-06-doc-impl-audit.md`.

v1 산출물 요약: `v1` 브랜치에 9개월간 누적된 `apps/`, `docs/`, `infra/`,
`scripts/`, `skills/`. v2가 가져오는 항목은 ADR로 한 건씩 박는다.

## 3. 진입 순서

1. `AGENTS.md` — 지시 우선순위, DO NOT 룰
2. `SKILL.md` — 도메인 어휘, 자주 묻는 작업
3. `docs/sprints/README.md` — Sprint 1~N 계획
4. `docs/architecture.md` — 책임 경계 (Pinvi vs `kor-travel-map`)
5. `docs/resume.md` — 다음 한 작업
6. `docs/journal.md` 최신 3건
7. 관련 ADR (`docs/decisions.md`)

## 3.1 Sprint 4까지 PR 운영

새 PR이 올라오거나 draft가 `ready_for_review`로 전환되면
`docs/runbooks/pr-review-sprint4.md`를 따른다. 리뷰 후 상세 코멘트를 남기고,
필요한 코드 수정·기반 라이브러리 PR·Pinvi sync·검증·머지까지 이어간다.
변경량 최소화보다 Sprint 1~4를 버틸 설계 정합성을 우선한다.
`.github/workflows/codex-pr-monitor.yml`이 외부 API key 없이 5분마다 열린 PR을
감시하고 review reminder를 남긴다. 실제 리뷰는 에이전트 또는 사람이 수행한다.

## 4. 의존 스택 (v2 확정 골격)

- 백엔드: Python 3.12 / FastAPI / Uvicorn / SQLAlchemy 2 async / asyncpg /
  Pydantic v2 / httpx + tenacity / Alembic / Dagster / kor-travel-map OpenAPI HTTP client
- 프론트엔드: Next.js 15 (App Router) + React 19 + TanStack Query v5 + Zustand +
  React Hook Form + Zod + shadcn/ui + Tailwind + **`vworld-map-web`**
  (`maplibre-vworld-react` Web 패키지, VWorld + MapLibre GL JS, ADR-046)
- 모바일: Expo SDK 56 + Expo Router + **Expo Dev Client** + EAS Build + React Native
  New Architecture + NativeWind. Expo Go는 사용하지 않고 Android `minSdkVersion`은
  24 이상이다(ADR-043, SDK 56 요구).
- 인프라: PostgreSQL 16 + PostGIS 3.5 + pg_trgm + pgcrypto / RustFS (S3 호환)
  / Docker Compose / N150 16GB + Odroid M1S 병행 운영 (ADR-023)
- 패키지 매니저: 백엔드 `uv`, 프론트 `npm`(workspaces)

## 5. 절대 금지 (가장 중요한 6개)

1. **main에 직접 push 금지** — 모든 변경은 feature branch + PR.
2. **`kor-travel-map`의 `feature`/`provider_sync` schema에 Pinvi가
   직접 DDL/migration 금지** — 해당 schema는 `kor-travel-map`이 소유.
   Pinvi는 `app` schema와 자체 도메인만 관리한다.
3. **Pinvi에서 provider raw → DTO 변환 직접 작성 금지** —
   `kor-travel-map.providers`에 위임. 새 provider는 그쪽 저장소에 PR.
4. **Pinvi 사용자 경로에서 `kor-travel-map` import 금지** — feature read/write
   request는 `PINVI_KOR_TRAVEL_MAP_API_BASE_URL`의 OpenAPI HTTP 계약을 호출한다.
5. **Windows git / Windows CodeGraph shim 사용 금지** — 개발·git·CodeGraph·테스트·
   docker·의존성은 Linux에서 실행한다. Playwright는 N150 우선, Windows는 fallback만
   허용한다(ADR-051, `docs/dev-environment.md`).
6. **trunk** (`/mnt/f/dev/pinvi`, `~/pinvi-workspaces/pinvi`) **에 AI 도구가
   체크아웃 / 편집 금지** — Claude는 `pinvi-claude` worktree에서만 작업 (ADR-017,
   `docs/runbooks/codegraph-worktrees.md`).

전체 룰은 `SKILL.md` §4, `AGENTS.md`.

## 6. 작업 후 체크리스트 (1줄)

`pytest -q` + `ruff check` + `mypy --strict` (`apps/api`, Linux) + `npm run
lint` + `npm run typecheck` (`apps/web`, Linux) + Playwright는 N150 우선/Windows fallback +
`docs/journal.md` + `docs/resume.md` (+ ADR/CHANGELOG/OpenAPI 해당 시) +
**remote 푸시 직전 보안 감사**(`git diff --cached` 비밀/민감값 스캔 — 걸리면 push 금지. AGENTS.md "remote 푸시 전 보안 감사").

> **민감 운영 노트(LOCAL ONLY)**: prod 노드 접근/실 도메인/반복 배포 실수는 gitignore된
> `docs/deploy-runbook.local.md`(`*.local.md`, kor-travel-concierge 동일 패턴)에 둔다. git 미전파 → 각
> worktree에 수동 복사(AGENTS.md "prod 배포 & 민감 운영 노트"). 운영 배포는 GHCR 없이
> `ktdctl pinvi --build`(`docs/runbooks/deploy.md`).

## 7. 빠른 문서 검색

| 무엇을 하려는가                                 | 어디 보나                                                                                                                      |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| API endpoint 구현 / 변경                        | `docs/api/<도메인>.md` + `docs/api/common.md`                                                                                  |
| DB schema 변경                                  | `docs/postgres-schema.md` + `docs/conventions/database.md`                                                                     |
| kor-travel-map OpenAPI 호출 (feature 데이터)    | `docs/integrations/kor-travel-map-rest-api.md` (REST 계약 정본 + 연결 작업) + `docs/kor-travel-map-integration.md` (패턴 개요) |
| Geocoding (주소/좌표/행정구역)                  | `docs/integrations/kor-travel-geo.md` (ADR-025, kor-travel-geo v2 REST 직접) + `docs/architecture/geocoding-open-decisions.md` |
| 외부 통합 (이메일/OAuth/AI companion 호출 계약) | `docs/integrations/<서비스>.md`                                                                                                |
| Frontend UI                                     | `docs/architecture/frontend.md` + `DESIGN.md`                                                                                  |
| 지도 (`vworld-map-web`)                         | `docs/integrations/maplibre-vworld.md` + `docs/design/marker-palette.md`                                                       |
| Admin 콘솔                                      | `docs/api/admin.md` + `docs/runbooks/admin.md`                                                                                 |
| ETL asset                                       | `docs/runbooks/etl.md` + `docs/architecture/dagster-etl-bridge.md`                                                             |
| 사용자 위치 사용                                | `docs/architecture/user-location.md` + `docs/compliance/lbs-act.md`                                                            |
| Notice plan (추천 여행)                         | `docs/architecture/notice-plans.md` + `docs/api/notice-plans.md`                                                               |
| 인프라 / 배포                                   | `docs/runbooks/{local-dev,docker-app,odroid-docker}.md` (Sprint 6에 N150 병행 — ADR-023)                                       |
| 릴리즈 마일스톤                                 | `docs/sprints/README.md` (v0.1.0 / v0.2.0 / v1.0.0 표)                                                                         |
| MCP 외부 인터페이스                             | `docs/architecture/mcp-server.md` + `docs/runbooks/mcp-server.md` (ADR-019, Sprint 6)                                          |
| 한국 전용 geofencing                            | `docs/architecture/korea-only-policy.md` + `docs/runbooks/korea-only.md` (ADR-018, Sprint 6)                                   |
| Backup / Restore                                | `docs/architecture/backup-restore.md` + `docs/runbooks/backup-restore.md` (ADR-022, Sprint 5~6)                                |
| Admin Grafana embed                             | `docs/runbooks/grafana-admin-embed.md` (Sprint 5)                                                                              |
| Worktree + CodeGraph 운영                       | `docs/runbooks/codegraph-worktrees.md` (ADR-017)                                                                               |
| 개발 환경 (Linux git + CodeGraph)               | `docs/agent-workflow.md` (런북) + `docs/dev-environment.md` (ADR-051)                                                          |
| 환경/도구 실패 패턴                             | `docs/agent-failure-patterns.md`                                                                                               |
| 컴플라이언스 / PII                              | `docs/compliance/{lbs-act,pipa,data-policy}.md`                                                                                |
| 테스트 작성                                     | `docs/conventions/testing.md`                                                                                                  |
| Sprint 작업                                     | `docs/sprints/SPRINT-<N>.md`                                                                                                   |
| 결정 / ADR                                      | `docs/decisions.md`                                                                                                            |
| v1과 비교                                       | `docs/v1-to-v2-mapping.md`                                                                                                     |

자세한 진입 순서는 `AGENTS.md` "AI Agent 작업 진입 절차".
