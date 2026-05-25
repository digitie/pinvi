# v1 → v2 자산 매핑 매트릭스

v1 브랜치(`v1`)의 모든 자산을 v2 컨텍스트로 어떻게 가져왔는지 추적한다. v2 작업
시 "v1에 어떤 자산이 있었나"와 "지금 어디 있나"를 한 곳에서 확인.

상태 표기:

- ✅ **반영됨** — 본 저장소 v2 문서/구조에 들어옴
- 🚚 **위임됨** — `python-krtour-map`이 소유 (ADR-001/003/005)
- 📋 **계획됨** — Sprint N에서 박을 예정 (시점 명시)
- ⛔ **폐기** — ADR로 명시적 제외
- 🆕 **신규** — v1에 없던 v2 신규 자산

## 1. docs/

### 1.1 docs/api/* (v1 8개)

| v1 파일 | v2 위치 | 상태 |
|---------|---------|------|
| `docs/api/auth.md` | `docs/api/auth.md` | 📋 본 PR로 신규 작성 |
| `docs/api/admin.md` | `docs/api/admin.md` | 📋 본 PR로 신규 작성 |
| `docs/api/trips.md` | `docs/api/trips.md` | 📋 본 PR로 신규 작성 |
| `docs/api/storage.md` | `docs/api/storage.md` | 📋 본 PR로 신규 작성 |
| `docs/api/health.md` | `docs/api/health.md` | 📋 본 PR로 신규 작성 |
| `docs/api/public.md` | `docs/api/public.md` | 📋 본 PR로 신규 작성 |
| `docs/api/regions.md` | `docs/api/regions.md` | 📋 본 PR로 신규 작성 |
| `docs/api/kto-tourapi.md` | (라이브러리로 이관) | 🚚 `python-krtour-map` |

### 1.2 docs/architecture/* (v1 23개)

| v1 파일 | v2 위치 | 상태 |
|---------|---------|------|
| `architecture/address-schema.md` | (라이브러리 schema) | 🚚 |
| `architecture/beach-schema.md` | (라이브러리 schema) | 🚚 |
| `architecture/dagster-krtour-map-boundary.md` | `docs/architecture/dagster-etl-bridge.md` | 📋 본 PR |
| `architecture/fuel-schema.md` | (라이브러리 schema) | 🚚 |
| `architecture/kasi-calendar-schema.md` | (라이브러리 schema) | 🚚 |
| `architecture/khoa-ocean-index-schema.md` | (라이브러리 schema) | 🚚 |
| `architecture/kma-tour-course-schema.md` | (라이브러리 schema) | 🚚 |
| `architecture/kraddr-base-boundary.md` | `docs/krtour-map-integration.md` cross-ref | ✅ |
| `architecture/krtour-map-db-initialization.md` | `docs/dev-environment.md` §5 | ✅ |
| `architecture/krtour-map-library.md` | `docs/krtour-map-integration.md` | ✅ |
| `architecture/map-feature-schema.md` | (라이브러리 schema) | 🚚 |
| `architecture/map-marker-design.md` | `docs/architecture/map-marker-design.md` | 📋 본 PR |
| `architecture/mcp-tools.md` | `docs/architecture/mcp-tools.md` | 📋 본 PR |
| `architecture/opinet-region-mapping.md` | (라이브러리) | 🚚 |
| `architecture/outdoor-feature-db.md` | (라이브러리) | 🚚 |
| `architecture/place-schema.md` | (라이브러리) | 🚚 |
| `architecture/plan-poi-attachments.md` | `docs/architecture/notice-plans.md` (PR #6) | ✅ |
| `architecture/provider-library-direct-use.md` | ADR-005 본문 | ✅ |
| `architecture/public-cultural-festival-schema.md` | (라이브러리) | 🚚 |
| `architecture/public-place-etl-schema.md` | (라이브러리) | 🚚 |
| `architecture/rest-area-schema.md` | (라이브러리) | 🚚 |
| `architecture/user-trip-schema.md` | `docs/data-model.md` §2 | ✅ |
| `architecture/weather-air-quality-schema.md` | (라이브러리) | 🚚 |
| `architecture/youtube-travel-intelligence.md` | `docs/architecture/youtube-travel-intelligence.md` | 📋 본 PR |

### 1.3 docs/data-sources/* (v1 8개)

| v1 파일 | v2 위치 | 상태 |
|---------|---------|------|
| `data-sources.md` (1쪽) | (라이브러리 → TripMate compliance) | 🚚 + ✅ |
| `data-sources/address-region.md` | (라이브러리) | 🚚 |
| `data-sources/beach-sources.md` | (라이브러리) | 🚚 |
| `data-sources/fuel-opinet.md` | (라이브러리) | 🚚 |
| `data-sources/provider-policy-and-todo.md` | `docs/compliance/data-policy.md` | 📋 본 PR |
| `data-sources/public-places.md` | (라이브러리) | 🚚 |
| `data-sources/rest-area-expressway.md` | (라이브러리) | 🚚 |
| `data-sources/tour-festival.md` | (라이브러리) | 🚚 |
| `data-sources/weather-air-quality.md` | (라이브러리) | 🚚 |

### 1.4 docs/decisions/* (v1 10개 → v2 단일 누적 decisions.md)

| v1 ADR | v2 ADR | 상태 |
|--------|--------|------|
| `20260418-data-source-policy-cleanup.md` | `docs/compliance/data-policy.md` cross-ref | ✅ |
| `20260418-initial-architecture.md` | ADR-001 (v2 시작) + ADR-006 (Dagster 분리) | ✅ |
| `20260418-initial-implementation-defaults.md` | ADR-002/011 + 개별 통합 문서 | ✅ |
| `20260418-kma-dfs-grid-conversion.md` | (라이브러리 결정) | 🚚 |
| `20260418-region-boundary-crs-policy.md` | (라이브러리 결정) | 🚚 |
| `20260418-scope-cleanup.md` | ADR-001 본문 | ✅ |
| `20260425-postgres-migration-constraints.md` | `docs/conventions/database.md` | 📋 본 PR |
| `20260506-visitkorea-client-boundary.md` | ADR-005 (wrapper 금지) 선조 | ✅ |
| `20260507-pykma-weather-client-boundary.md` | ADR-005 선조 | ✅ |
| `20260508-social-login-provider-identity.md` | `docs/integrations/social-login.md` | 📋 본 PR |

### 1.5 docs/execplan/* (v1 15개 → 대부분 Sprint로 흡수)

| v1 파일 | v2 위치 | 상태 |
|---------|---------|------|
| `beach-integrated-source-etl.md` | (라이브러리 Sprint) | 🚚 |
| `dagster-etl-migration.md` | ADR-006 + SPRINT-5 | ✅ |
| `data-source-api-documentation-split.md` | `docs/api/` 구조로 흡수 | ✅ |
| `etl-runtime-and-address-ops.md` | (라이브러리) | 🚚 |
| `etl-soak-validation.md` | `docs/runbooks/etl.md` + `etl-soak-runbook.md` | 📋 본 PR |
| `festival-login-provider-library.md` | ADR-005 + SPRINT-5 | ✅ |
| `juso-legal-dong-etl.md` | (라이브러리) | 🚚 |
| `kma-beach-weather-etl.md` | (라이브러리) | 🚚 |
| `korea-tripmate-implementation-plan.md` | SPRINT-1~6 전체 | ✅ |
| `legal-dong-code-standard-etl.md` | (라이브러리) | 🚚 |
| `post-login-trek-kakao-ui.md` | `docs/architecture/frontend.md` + SPRINT-4 | ✅ |
| `pykex-kex-openapi-integration.md` | (라이브러리) | 🚚 |
| `pykma-weather-integration.md` | (라이브러리) | 🚚 |
| `social-login-providers.md` | `docs/integrations/social-login.md` + SPRINT-2 | ✅ |
| `visitkorea-tourapi-integration.md` | (라이브러리) | 🚚 |
| `vworld-boundary-shp-etl.md` | (라이브러리) | 🚚 |

### 1.6 docs/integrations/* (v1 4개)

| v1 파일 | v2 위치 | 상태 |
|---------|---------|------|
| `integrations/gemini.md` | `docs/integrations/gemini.md` | 📋 본 PR |
| `integrations/resend.md` | `docs/integrations/resend.md` | 📋 본 PR |
| `integrations/social-login.md` | `docs/integrations/social-login.md` | 📋 본 PR |
| `integrations/telegram.md` | `docs/integrations/telegram.md` | 📋 본 PR |

### 1.7 docs/runbooks/* (v1 9개)

| v1 파일 | v2 위치 | 상태 |
|---------|---------|------|
| `runbooks/admin.md` | `docs/runbooks/admin.md` | 📋 본 PR |
| `runbooks/agent-working-rules.md` | `docs/agent-guide.md` + AGENTS.md에 흡수 | ✅ |
| `runbooks/docker-app.md` | `docs/runbooks/docker-app.md` | 📋 본 PR |
| `runbooks/etl.md` | `docs/runbooks/etl.md` | 📋 본 PR |
| `runbooks/file-storage.md` | `docs/runbooks/file-storage.md` | 📋 본 PR |
| `runbooks/kto-tourapi.md` | (라이브러리 runbook) | 🚚 |
| `runbooks/local-dev.md` | `docs/runbooks/local-dev.md` | 📋 본 PR |
| `runbooks/odroid-docker.md` | `docs/runbooks/odroid-docker.md` | 📋 본 PR |
| `runbooks/wsl-ext4-workflow.md` | ADR-004로 폐기 → `docs/dev-environment.md` | ⛔ |

### 1.8 skills/* (v1 9개 → v2 docs/conventions/)

| v1 파일 | v2 위치 | 상태 |
|---------|---------|------|
| `skills/coding-style.ko.md` | `docs/conventions/coding-style.md` | 📋 본 PR |
| `skills/dagster-etl.ko.md` | (라이브러리) + `docs/runbooks/etl.md` | 🚚 + ✅ |
| `skills/data-policy.ko.md` | `docs/compliance/data-policy.md` | 📋 본 PR |
| `skills/database-architect.ko.md` | `docs/conventions/database.md` | 📋 본 PR |
| `skills/deployment-wsl2-odroid.ko.md` | `docs/runbooks/odroid-docker.md` + `dev-environment.md` | ✅ |
| `skills/documentation-and-adrs.ko.md` | `docs/agent-guide.md` §3 | ✅ |
| `skills/geospatial-postgis.ko.md` | `docs/conventions/geospatial.md` | 📋 본 PR |
| `skills/normalization-patterns.ko.md` | `docs/conventions/normalization.md` | 📋 본 PR |
| `skills/testing-and-qa.ko.md` | `docs/conventions/testing.md` | 📋 본 PR |

### 1.9 기타 docs

| v1 파일 | v2 위치 | 상태 |
|---------|---------|------|
| `docs/PROJECT_BRIEF.md` | `README.md` + `docs/spec/v8/` | ✅ |
| `docs/architecture.md` | `docs/architecture.md` | ✅ |
| `docs/reports/tripmate-outdoor-feature-db-report-20260518.docx` | 운영자 보관 | ⛔ (git 미포함) |

## 2. apps/api (v1 → v2 Sprint 매핑)

### 2.1 routes/

| v1 파일 | v2 위치 (Sprint) | 상태 |
|---------|------------------|------|
| `api/routes/auth.py` | `apps/api/app/api/v1/auth.py` (Sprint 1) | 📋 |
| `api/routes/admin.py` | `apps/api/app/api/v1/admin/*.py` (Sprint 3) | 📋 |
| `api/routes/health.py` | `apps/api/app/api/v1/healthz.py` (Sprint 1) | 📋 |
| `api/routes/notice.py` | `apps/api/app/api/v1/notice_plans.py` (Sprint 2) | 📋 |
| `api/routes/public.py` | `apps/api/app/api/v1/public.py` (Sprint 4) | 📋 |
| `api/routes/regions.py` | `apps/api/app/api/v1/regions.py` (Sprint 4) | 📋 |
| `api/routes/storage.py` | `apps/api/app/api/v1/storage.py` (Sprint 2) | 📋 |
| `api/routes/trips.py` | `apps/api/app/api/v1/trips.py` + `pois.py` (Sprint 2) | 📋 |

### 2.2 services/

| v1 파일 | v2 위치 | 상태 |
|---------|---------|------|
| `services/admin_auth.py` | `apps/api/app/services/admin_auth.py` (Sprint 3) | 📋 |
| `services/admin_data_browser.py` | `apps/api/app/services/admin/entity_browser.py` (Sprint 3) | 📋 |
| `services/admin_entity_crud.py` | `apps/api/app/services/admin/entity_crud.py` (Sprint 3) | 📋 |
| `services/email_delivery.py` | `apps/api/app/services/email_service.py` (Sprint 2) | 📋 |
| `services/etl_runtime.py` | (라이브러리) | 🚚 |
| `services/file_storage.py` | `apps/api/app/services/rustfs_storage.py` (Sprint 2) | 📋 |
| `services/fuel_report.py` | (라이브러리) | 🚚 |
| `services/krtour_map.py` (wrapper) | ⛔ 제거 (ADR-005) | ⛔ |
| `services/krtour_map_contract.py` | ⛔ 제거 (ADR-005) | ⛔ |
| `services/krtour_map_feature_store.py` | ⛔ 제거 (ADR-005) | ⛔ |
| `services/notice_plan.py` | `apps/api/app/services/notice_plan.py` (Sprint 2) | 📋 |
| `services/oauth_email_policy.py` | `apps/api/app/services/oauth_google.py` (Sprint 2) | 📋 |
| `services/plan_poi_attachment.py` | `apps/api/app/services/plan_poi_attachment.py` (Sprint 2) | 📋 |
| `services/region_boundary.py` | (라이브러리) — DI helper만 TripMate | 🚚 + 📋 |
| `services/trip_plan.py` | `apps/api/app/services/trip.py` (Sprint 2) | 📋 |
| `services/user_registration.py` | `apps/api/app/services/user_registration.py` (Sprint 1) | 📋 |

### 2.3 models/

| v1 파일 | v2 위치 | 상태 |
|---------|---------|------|
| `models/address.py` | (라이브러리) | 🚚 |
| `models/beach.py` | (라이브러리) | 🚚 |
| `models/etl.py` | (라이브러리) + TripMate `app.import_jobs` (Sprint 5) | 🚚 + 📋 |
| `models/fuel.py` | (라이브러리) | 🚚 |
| `models/mixins.py` | `apps/api/app/models/mixins.py` (Sprint 1) | 📋 |
| `models/ocean.py` | (라이브러리) | 🚚 |
| `models/place.py` | (라이브러리) | 🚚 |
| `models/rest_area.py` | (라이브러리) | 🚚 |
| `models/session.py` | `apps/api/app/models/session.py` (Sprint 1) | 📋 |
| `models/tour.py` | (라이브러리) | 🚚 |
| `models/trip.py` | `apps/api/app/models/{trip,poi,companion,share_link,notice_plan,attachment}.py` (Sprint 2) | 📋 |
| `models/user.py` | `apps/api/app/models/user.py` (Sprint 1) | 📋 |
| `models/weather.py` | (라이브러리) | 🚚 |

### 2.4 schemas/

| v1 파일 | v2 위치 (`packages/schemas/` Zod + `apps/api/app/schemas/` Pydantic) | 상태 |
|---------|------------------|------|
| `schemas/admin.py` | `apps/api/app/schemas/admin.py` (Sprint 3) | 📋 |
| `schemas/attachment.py` | `apps/api/app/schemas/attachment.py` + Zod (Sprint 2) | 📋 |
| `schemas/auth.py` | `apps/api/app/schemas/auth.py` + Zod (Sprint 1) | 📋 |
| `schemas/health.py` | (단순 → main.py에 inline) | 📋 |
| `schemas/notice.py` | `apps/api/app/schemas/notice.py` + Zod (Sprint 2) | 📋 |
| `schemas/public.py` | `apps/api/app/schemas/public.py` (Sprint 4) | 📋 |
| `schemas/region.py` | `apps/api/app/schemas/region.py` (Sprint 4) | 📋 |
| `schemas/storage.py` | `apps/api/app/schemas/storage.py` + Zod (Sprint 2) | 📋 |
| `schemas/trip.py` | `apps/api/app/schemas/{trip,poi}.py` + Zod (Sprint 2) | 📋 |

### 2.5 etl/, dagster_etl/, cli/, core/etl_config.py 등

| v1 영역 | v2 처리 | 상태 |
|---------|---------|------|
| `app/etl/*` (provider 어댑터 전체) | ⛔ 제거 → `python-krtour-map` 소유 (ADR-005) | ⛔ + 🚚 |
| `app/dagster_etl/*` (definitions/registry/runtime/loaders) | ⛔ 제거 → `apps/etl/` (ADR-006) | ⛔ + 📋 |
| `app/cli/{legal_dong_code,opinet_fuel,vworld_boundary}.py` | ⛔ 제거 → 라이브러리 CLI | ⛔ + 🚚 |
| `app/core/{kex,kto,krtour_map_contract}.py` | ⛔ 제거 (ADR-005 wrapper 금지) | ⛔ |
| `app/core/{config,etl_config,json_types,redaction}.py` | `apps/api/app/core/*` (Sprint 1) | 📋 |
| `app/db/*` | `apps/api/app/core/database.py` (Sprint 1) | 📋 |
| `app/geospatial/__init__.py` | (라이브러리) | 🚚 |
| `app/main.py` | `apps/api/app/main.py` (Sprint 1) | 📋 |

## 3. apps/web (v1 → v2 `apps/web` + `packages/*`)

| v1 영역 | v2 위치 | 상태 |
|---------|---------|------|
| `app/admin/{api,config,data,files,login,users,page}.tsx` | `apps/web/app/admin/...` (Sprint 3) | 📋 |
| `app/{login,signup,verify-email}/*` | `apps/web/app/(auth)/...` (Sprint 1) | 📋 |
| `app/shared/{api-base,query-keys,query-provider,stores,file-upload-panel,user-attachment-workbench}.ts` | `packages/{api-client,state,...}` + `apps/web/components/` (Sprint 1~3) | 📋 |
| `app/{layout,page}.tsx`, `globals.css` | `apps/web/app/{layout,page}.tsx` (Sprint 1) | 📋 |
| `public/maki/*.svg` (13개) | `apps/web/public/maki/*.svg` (Sprint 4) | 📋 |
| `next.config.ts`, `eslint.config.mjs`, `tsconfig.json`, `postcss.config.mjs` | `apps/web/*` (Sprint 1) | 📋 |
| `tests/admin-ui.test.mjs` | `apps/web/tests/admin-flow.test.mjs` (Sprint 3) | 📋 |
| `Dockerfile` | `apps/web/Dockerfile` (Sprint 1) | 📋 |

## 4. infra / scripts / config

| v1 파일 | v2 처리 | 상태 |
|---------|---------|------|
| `infra/docker-compose.yml` | `infra/docker-compose.yml` (Sprint 1) | 📋 |
| `infra/docker-compose.app.yml` | `infra/docker-compose.app.yml` (Sprint 1) | 📋 |
| `scripts/backup-db.sh`, `restore-db.sh` | `scripts/*` (Sprint 6) | 📋 |
| `scripts/docker-app-smoke-test.sh` | `scripts/*` (Sprint 1) | 📋 |
| `scripts/docker-keepalive.sh` | (운영 환경 결정 후) | 📋 |
| `scripts/etl-soak-*.sh` (5개) | (라이브러리) + TripMate Dagster (Sprint 5) | 🚚 + 📋 |
| `scripts/odroid-docker-*.sh` (3개) | `scripts/*` (Sprint 6) | 📋 |
| `scripts/admin-etl-data-smoke-test.sh` | `scripts/*` (Sprint 3) | 📋 |
| `config/etl-datasets.json`, `*.soak.json` | (라이브러리) | 🚚 |
| `config/kma-mid-term-regions.json` | (라이브러리) | 🚚 |

## 5. v2에만 있는 신규 자산

| 파일 | 목적 | 상태 |
|------|------|------|
| `CLAUDE.md` | 1쪽 진입 요약 (Claude Code) | ✅ |
| `SKILL.md` | 에이전트 매뉴얼 (1 파일로 통합, v1 9 skills와 다름) | ✅ |
| `docs/spec/v8/*` (7개) | 외부 SPEC V8 적용 노트 | ✅ |
| `docs/sprints/SPRINT-{1..6}.md` | Sprint 계획 | ✅ |
| `docs/architecture/frontend.md` | Next.js + Expo 공용 monorepo | ✅ |
| `docs/architecture/user-location.md` | Geolocation + expo-location | ✅ |
| `docs/architecture/notice-plans.md` | Notice plan 도메인 (v1 자산 정리) | ✅ |
| `docs/krtour-map-integration.md` | 라이브러리 사용 패턴 | ✅ |
| `docs/design/marker-palette.md` | 16색 + maki 매핑 | ✅ |
| `docs/v1-to-v2-mapping.md` | 본 문서 | 📋 본 PR |

## 6. ADR 매핑

| ADR | 주제 | v1 관련 |
|-----|------|---------|
| ADR-001 | v1 보존 + v2 재시작 | v1 전체 |
| ADR-002 | 함수 직접 호출 (REST 없음) | v1 `services/krtour_map_*` 폐기 |
| ADR-003 | schema 책임 분담 (feature/app) | v1 monorepo 단일 |
| ADR-004 | WSL 미러 단일 모델 | v1 `runbooks/wsl-ext4-workflow.md` 폐기 |
| ADR-005 | provider 어댑터 wrapper 금지 | v1 `services/krtour_map_*` + `core/{kex,kto}.py` 폐기 |
| ADR-006 | Dagster code location 분리 (`apps/etl`) | v1 `apps/api/app/dagster_etl/*` 이전 |
| ADR-007 | PR-only workflow | v1 일부 직접 push 정정 |
| ADR-008 | Postgres `x_extension` schema | v1과 동일 채택 |
| ADR-009 | 한국어 문서 정책 | v1 정책 계승 |
| ADR-010 | SPEC V8 채택 | (외부 문서) |
| ADR-011 | Frontend 스택 + Expo 공용 | v1 `apps/web` 단일 → 공용 패키지 |
| ADR-012 | 위치 정보 (Geolocation + expo-location) | v1 미명시 → v2 신규 |
| ADR-013 | Notice plan 이전 + 명명 분리 | v1 `notice_plans` 도메인 |

## 7. v1 → v2 누락 점검 — 본 PR로 메우는 항목

본 PR 신규 작성 (📋 표시 항목):

- `docs/api/` 7개 (auth/admin/trips/storage/health/public/regions)
- `docs/integrations/` 4개 (resend/social-login/gemini/telegram)
- `docs/runbooks/` 6개 (local-dev/docker-app/etl/admin/odroid-docker/file-storage)
- `docs/conventions/` 5개 (coding-style/database/testing/geospatial/normalization)
- `docs/compliance/` 3개 (lbs-act/pipa/data-policy)
- `docs/legal/` 4개 placeholder (terms/privacy/lbs-terms/location-consent)
- `docs/architecture/` 5개 (map-marker-design/mcp-tools/youtube-travel-intelligence/dagster-etl-bridge/api-contract)

## 8. ADR로 명시적 폐기 (⛔)

- WSL ext4 직접 작업본 모델 (ADR-004 — 본 v2는 NTFS 작업 + WSL 미러)
- `apps/api/app/services/krtour_map_*` 위장 service layer (ADR-005)
- `apps/api/app/core/{kex,kto,krtour_map_contract}.py` provider wrapper (ADR-005)
- `apps/api/app/etl/` provider 어댑터 전체 (ADR-005 + ADR-006)
- `apps/api/app/dagster_etl/` (ADR-006 → `apps/etl/`)
- `apps/api/app/cli/{vworld_boundary,legal_dong_code,opinet_fuel}.py` (라이브러리 CLI로 이전)
- `pyXyz` 짧은 alias 표기 (`docs/spec/v8/01-data.md` Q-1)

## 9. 작업 추적

본 매핑은 살아 있는 문서다. 새 v1 자산이 발견되거나 v2 작업이 진행되면 본 표를
갱신한다. Sprint 진입 PR마다 📋 → 📋(in_progress) → ✅로 상태 갱신.
