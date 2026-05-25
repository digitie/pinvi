# SPRINT-1 — 모노레포 scaffolding + DB schema + 핵심 인증

- **상태**: proposed (사용자 진입 승인 대기)
- **목표**: v2 main에 `apps/{api,web,etl}` + `infra/` + `packages/` scaffolding을
  박고, `app` schema의 핵심 DDL + 회원가입/로그인의 첫 vertical slice를 통과시킨다.
- **DoD (Definition of Done)**:
  - `apps/api`가 FastAPI app으로 부팅하고 `/healthz` 응답.
  - `apps/web`이 Next.js dev로 부팅하고 `/`, `/login`, `/signup` 라우트 렌더.
  - `apps/etl`이 Dagster code location으로 등록되고 빈 asset 목록 노출.
  - `infra/docker-compose.yml`로 PostgreSQL + RustFS 기동.
  - `tripmate alembic upgrade head`로 `app.users`, `app.user_sessions`,
    `app.user_email_verifications` 적재.
  - `pytest apps/api/tests/unit -q` 통과 (단위 5건 이상).
  - `pytest apps/api/tests/integration -q` 통과 (testcontainer PostGIS 기동).
  - `npm run lint typecheck build`(`apps/web`) 통과.
  - `import-linter` 4 계약 통과 (코드 작성 전 박힌 룰).
  - CI workflow 3개 (api / web / etl) 활성화.
  - 본 Sprint의 ADR들이 `proposed` → `accepted` 전환 (해당 시).

## 1. 진입 전 준비

- [ ] 사용자가 Sprint 1 진입 승인 (이 문서 §4 미해결 결정 모두 정리 후)
- [ ] `docs/decisions.md` ADR-010 (인증 토큰 모델) 결정
- [ ] `docs/decisions.md` ADR-011 (Admin RBAC 모델) 결정 — Sprint 1은 단순 admin
      이메일 화이트리스트로 시작 가능

## 2. 산출물

### 2.1 백엔드 `apps/api`

- `apps/api/pyproject.toml` (uv + dependencies + dev/providers extras +
  import-linter 계약)
- `apps/api/app/main.py` (FastAPI app + lifespan + `/healthz`)
- `apps/api/app/core/config.py` (`Settings` + `TRIPMATE_*` 환경변수)
- `apps/api/app/core/database.py` (async engine + session factory)
- `apps/api/app/models/user.py`, `session.py` (SQLAlchemy 매핑)
- `apps/api/app/schemas/user.py`, `auth.py` (Pydantic v2)
- `apps/api/app/services/user_registration.py`, `services/admin_auth.py`
- `apps/api/app/api/routes/auth.py` (signup / verify-email / login / logout)
- `apps/api/app/api/routes/healthz.py`
- `apps/api/alembic/env.py`, `alembic/script.py.mako`
- `apps/api/alembic/versions/20YYMMDD_0001_initial_app_schema.py`
- `apps/api/tests/unit/test_user_registration.py`, `test_admin_auth.py`
- `apps/api/tests/integration/test_auth_api.py`, `test_app_schema.py`

### 2.2 프론트 `apps/web`

- `apps/web/package.json`, `tsconfig.json`, `next.config.mjs`
- `apps/web/app/layout.tsx`, `app/page.tsx`
- `apps/web/app/login/page.tsx`, `app/signup/page.tsx`, `app/verify-email/page.tsx`
- `apps/web/app/shared/api-base.ts`, `query-provider.tsx`, `query-keys.ts`,
  `stores.ts`
- `apps/web/tests/auth-flow.test.mjs` (Playwright smoke)

### 2.3 ETL `apps/etl`

- `apps/etl/pyproject.toml`
- `apps/etl/tripmate/etl/__init__.py`
- `apps/etl/tripmate/etl/definitions.py` (빈 code location)
- `apps/etl/tripmate/etl/resources.py` (`KrtourMapResource` skeleton)
- `apps/etl/tests/test_definitions.py`

### 2.4 인프라 `infra`

- `infra/docker-compose.yml` (postgres + rustfs + api + web + dagster)
- `infra/docker-compose.app.yml` (운영 차분)
- `infra/odroid/README.md` (배포 절차 placeholder)

### 2.5 패키지 `packages` (Next.js / Expo 공용 — `docs/architecture/frontend.md` §2)

- `packages/schemas/` — Zod schema 공용 (User / Trip / POI / Feature / NoticePlan / Auth)
- `packages/api-client/` — fetch wrapper + TanStack Query keys + endpoints
- `packages/state/` — Zustand store (storage adapter 주입형)
- `packages/design-tokens/` — Airbnb 톤 토큰 + 16색 팔레트 + Tailwind preset
  (DESIGN.md / `airbnb-marker-palette.html` 기준)
- `packages/hooks/` — `useUserLocation` 등 공용 React hook (RN 호환)
- `packages/i18n/` — next-intl + i18n-js 공유 메시지 카탈로그 (ko 기본)
- `packages/map-marker-react/` placeholder (`@krtour/map-marker-react` thin
  wrapper, Sprint 4 활성화)

본 Sprint는 패키지 skeleton만 박는다 (실제 export는 Sprint 1~2에서 점진 추가).

### 2.6 CI

- `.github/workflows/api.yml` — pytest unit/integration + ruff + mypy +
  import-linter + coverage
- `.github/workflows/web.yml` — npm lint/typecheck/build + Playwright smoke
- `.github/workflows/etl.yml` — Dagster asset registry sanity
- `.github/workflows/openapi.yml` — OpenAPI export drift (Sprint 1은
  `continue-on-error: true`로 시작)

### 2.7 ADR

본 Sprint 진입 PR에서 다음 ADR 박음 (proposed → accepted):

- ADR-010 인증 토큰 모델
- ADR-011 Admin RBAC 모델 (잠정)
- ADR-016 지도 클라이언트 정책 (잠정)

## 3. 의존성 / 외부

- `python-krtour-map`은 본 Sprint에서 import하지 않는다. `apps/etl/resources.py`의
  `KrtourMapResource`는 빈 skeleton — Sprint 4에서 라이브러리 호출 활성화.
- `python-kraddr-*`도 Sprint 2 이후 도입.
- 외부 API 키는 placeholder만 `.env.example`에 둠.

## 4. 미해결 결정 (Sprint 진입 전 결정 필요)

- [ ] 인증 토큰 모델: cookie session (보안 강함, CSRF 처리) vs JWT (stateless).
- [ ] Admin RBAC: roles 배열 + 백엔드 dependency 만으로 시작 vs RBAC 매트릭스 도입.
- [ ] 이메일 검증 발신: Sprint 1은 console-log mock 발신, Sprint 2에서 Resend 통합.
- [ ] 소셜 로그인: Sprint 1은 이메일/비밀번호만, Sprint 2에서 Kakao/Naver/Google.

## 5. 회귀 방지

- `import-linter` 계약 4종 활성화 (`apps/api/pyproject.toml`):
  - `tripmate.api.routes → services → models → schemas` layers
  - `tripmate.api` forbidden `tripmate.api.models.feature/provider_sync`
  - `tripmate.api` forbidden `cachetools` / `async_lru` (라이브러리 ADR-030 mirror)
  - `tripmate.api` forbidden `kafka` / `aiokafka` (streaming 의존 차단)
- `mypy --strict` (`apps/api/app/` 전체)
- `ruff check apps/api apps/etl tests`
- Coverage `fail_under=50` 시작 (Sprint별 상향, `python-krtour-map` ADR-032 mirror)

## 6. 작업 분할 (PR 단위)

본 Sprint를 한 큰 PR로 박지 않고 작은 PR로 분할 권장:

- PR #1 — 본 골격 PR (현재 작업) — docs만
- PR #2 — `apps/api` scaffolding + `/healthz` + Alembic env
- PR #3 — `app.users` + `app.user_sessions` + signup/verify/login
- PR #4 — `apps/web` scaffolding + login/signup/verify-email UI
- PR #5 — `apps/etl` scaffolding + Dagster code location
- PR #6 — `infra/docker-compose.yml` + smoke test 스크립트
- PR #7 — `.github/workflows/*` 활성화 + import-linter 박기

PR 사이에 의존이 있으면 base branch를 명시 (`gh pr create --base feat/sprint1-pr2`
패턴 — `python-krtour-map` Sprint 1 분할 방식과 동일).

## 7. 종료 체크리스트 (Sprint 1 PR-Last)

- [ ] 본 §1.DoD 모두 통과
- [ ] `docs/journal.md`에 Sprint 1 종료 엔트리
- [ ] `docs/resume.md`의 "다음 한 작업" → Sprint 2 진입
- [ ] `docs/sprints/SPRINT-2.md` 활성화 (proposed → active)
- [ ] CI workflow 3개 main에서 green
- [ ] Odroid 배포는 본 Sprint에서 다루지 않음 — Sprint 6

## 8. SPEC V8 정합

- 00-infrastructure.md §2 (Sentry/Loki 초기 통합 — 본 Sprint는 Sentry만, Loki는 Sprint 5)
- 01-data.md §2.1 ~ §2.2 (`app.users`, `user_email_verifications`)
- 02-backend.md §1 (FastAPI 스택)
- 02-backend.md §4 (G장 회원가입 — 본 Sprint는 일반 가입+verify까지, Resend/소셜은 Sprint 2)
- 03-frontend.md §1 (Next.js 스택)
- 05-execution.md §3 (Sprint 1)

## 8. 관련 파일

- `docs/decisions.md` — ADR-001 ~ ADR-009 (v2 시작 결정)
- `docs/architecture.md` — 큰 그림
- `docs/data-model.md` — `app` schema 도메인
- `docs/postgres-schema.md` — DDL 골격
- `docs/test-strategy.md` — 테스트 계층
- `docs/dev-environment.md` — WSL 미러 작업 흐름
- `docs/krtour-map-integration.md` — Sprint 4부터 활성화
