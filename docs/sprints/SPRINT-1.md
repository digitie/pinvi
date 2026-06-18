# SPRINT-1 — 모노레포 scaffolding + DB schema + 핵심 인증

- **상태**: merged (PR #9, 2026-05-26)
- **목표**: v2 main에 `apps/{api,web,etl}` + `infra/` + `packages/` scaffolding을
  박고, `app` schema의 핵심 DDL + 회원가입/로그인의 첫 vertical slice를 통과시킨다.
- **DoD (Definition of Done)**:
  - `apps/api`가 FastAPI app으로 부팅하고 `/healthz` 응답.
  - `apps/web`이 Next.js dev로 부팅하고 `/`, `/login`, `/signup` 라우트 렌더.
  - `apps/etl`이 Dagster code location으로 등록되고 빈 asset 목록 노출.
  - `infra/docker-compose.yml`로 PostgreSQL + RustFS 기동.
  - `pinvi alembic upgrade head`로 `app.users`, `app.user_sessions`,
    `app.user_email_verifications` 적재.
  - `pytest apps/api/tests/unit -q` 통과 (단위 5건 이상).
  - `pytest apps/api/tests/integration -q` 통과 (testcontainer PostGIS 기동).
  - `npm run lint typecheck build`(`apps/web`) 통과.
  - `import-linter` 4 계약 통과 (코드 작성 전 박힌 룰).
  - CI workflow 3개 (api / web / etl) 활성화.
  - 본 Sprint의 ADR들이 `proposed` → `accepted` 전환 (해당 시).

## 1. 진입 전 준비

- [x] 사용자가 Sprint 1 진입 승인 (PR #9에서 완료)
- [x] Sprint 1 scaffold / auth vertical slice merge 완료
- [x] 인증 토큰 / Admin RBAC / audit-chain ADR 백필 완료 (ADR-032~034)

## 2. 산출물

### 2.1 백엔드 `apps/api`

- `apps/api/pyproject.toml` (uv + dependencies + dev/providers extras +
  import-linter 계약)
- `apps/api/app/main.py` (FastAPI app + lifespan + `/healthz`)
- `apps/api/app/core/config.py` (`Settings` + `PINVI_*` 환경변수)
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
- `apps/etl/pinvi/etl/__init__.py`
- `apps/etl/pinvi/etl/definitions.py` (빈 code location)
- `apps/etl/pinvi/etl/resources.py` (`KorTravelMapResource` skeleton)
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
- 지도 전용 React wrapper 패키지는 만들지 않는다. Sprint 4 지도 UI는
  `apps/web`이 `vworld-map-web`을 직접 import하고, Pinvi 전용 팔레트/쿼리
  helper만 `apps/web/lib`에 둔다(ADR-015).

본 Sprint는 패키지 skeleton만 박는다 (실제 export는 Sprint 1~2에서 점진 추가).

### 2.6 CI

- `.github/workflows/api.yml` — pytest unit/integration + ruff + mypy +
  import-linter + coverage
- `.github/workflows/web.yml` — npm lint/typecheck/build + Playwright smoke
- `.github/workflows/etl.yml` — Dagster asset registry sanity
- `.github/workflows/openapi.yml` — OpenAPI export drift (Sprint 1은
  `continue-on-error: true`로 시작)

### 2.7 ADR

본 Sprint 진입 PR 시점의 ADR 참조는 이후 번호 배정과 다르게 정리됐다. 현재 기준:

- ADR-010: SPEC V8 6편 채택 + 책임 분담 정정
- ADR-011: Frontend 스택 + Next.js / Expo 공용 패키지 구조
- ADR-015: Kakao Maps SDK 폐기 + VWorld/MapLibre 채택
- ADR-046: Web 지도 클라이언트 `vworld-map-web` 전환
- ADR-032: 인증 토큰 기준(access JWT + httpOnly cookie)
- ADR-033: Admin RBAC(`users.roles[]` + 서버 dependency)
- ADR-034: Admin audit hash chain

## 3. 의존성 / 외부

- `kor-travel-map`은 본 Sprint에서 import하지 않는다. 이후 ADR-026에 따라
  Sprint 4 feature read는 kor-travel-map OpenAPI HTTP client로 활성화한다.
- `python-kraddr-base / kor-travel-geo / python-kraddr-gop`도 Sprint 2 이후 도입.
- 외부 API 키는 placeholder만 `.env.example`에 둠.

## 4. 미해결 결정 (Sprint 진입 전 결정 필요)

- [x] 인증 토큰 모델: ADR-032 기준(access JWT + httpOnly cookie, refresh persistence는 T-134).
- [x] Admin RBAC: ADR-033 기준(`users.roles[]` + 백엔드 dependency, 매트릭스는 후속).
- [x] 이메일 검증 발신: Sprint 1 console-log mock, Sprint 2/T-070에서 Resend 통합.
- [x] 소셜 로그인: Sprint 1은 이메일/비밀번호만, 현재 활성 provider는 Google만 사용.
  Naver/Kakao는 T-122 future provider로 보류(ADR-032).

## 5. 회귀 방지

- `import-linter` 계약 4종 활성화 (`apps/api/pyproject.toml`):
  - `pinvi.api.routes → services → models → schemas` layers
  - `pinvi.api` forbidden `pinvi.api.models.feature/provider_sync`
  - `pinvi.api` forbidden `cachetools` / `async_lru` (라이브러리 ADR-030 mirror)
  - `pinvi.api` forbidden `kafka` / `aiokafka` (streaming 의존 차단)
- `mypy --strict` (`apps/api/app/` 전체)
- `ruff check apps/api apps/etl tests`
- Coverage `fail_under=50` 시작 (Sprint별 상향, `kor-travel-map` ADR-032 mirror)

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
패턴 — `kor-travel-map` Sprint 1 분할 방식과 동일).

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
- `docs/kor-travel-map-integration.md` — Sprint 4부터 활성화
