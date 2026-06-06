# TripMate

`TripMate`는 한국 여행 계획·기록·공유 애플리케이션이다. 한국 공공 API에서 모은
지도/날씨/이벤트/가격/공지/경로/구역 데이터를 사용해 사용자가 여행 계획을 세우고,
이동 중 컨텍스트(날씨/혼잡/이벤트)를 확인하고, 결과를 기록·공유하도록 돕는다.

> **현재 상태 (Sprint 4 준비/진행 단계)**: Sprint 1~3는 머지 완료, 현재 기준선은
> 지도 UI + `maplibre-vworld-js` 통합 + CI/CD 재활성화가 포함된 Sprint 4다.
> 이전(v1) 구현은 `v1` 브랜치에 보존되어 있다. 상태 추적은 `docs/resume.md`,
> `docs/tasks.md`, `docs/sprints/README.md`를 우선한다.

## 정체성

- **GitHub 저장소**: `tripmate`
- **백엔드 import (계획)**: `from tripmate.api import ...`, `from tripmate.etl import ...`
- **프론트엔드 패키지 (계획)**: `apps/web` (Next.js App Router)
- **환경변수 prefix**: `TRIPMATE_*`
- **PostgreSQL DB 이름 (개발)**: `tripmate`
- **Postgres schema (계획)**: `app`, `feature`, `provider_sync`, `ops`, `x_extension`
  (`feature`/`provider_sync` 영역은 `python-krtour-map`이 소유. `app`은 TripMate
  도메인 — 사용자/여행 계획/POI 첨부/공유 등)

## 구성

TripMate는 **monorepo**다. 현재 저장소는 아래 구조를 이미 사용 중이며 Sprint별로
구현을 확장한다.

```
apps/
  api/      — FastAPI 백엔드 (인증, 여행 계획, 관리자, Storage, Dagster bridge)
  web/      — Next.js 사용자 UI + Admin
  etl/      — Dagster definitions/jobs/schedules (provider 적재 orchestration)
packages/   — 공유 TS 패키지 (UI/마커/타입)
infra/      — docker-compose, deployment manifests
docs/       — 본 저장소의 결정·기록·계약
```

핵심 의존:

- **`python-krtour-map`** (별 저장소 `F:\dev\python-krtour-map`):
  지도 feature 정규화·저장 + OpenAPI API/Admin. TripMate는 최신 OpenAPI HTTP
  계약으로 사용한다(ADR-026, API `9011` / admin `9012`).
- **`python-*-api`** (별 저장소들): KMA, VisitKorea, OpiNet, MOIS, KREX, KHOA,
  국가유산, 산림청 등 한국 공공 API 클라이언트.
- **`python-kraddr-geo`**: 주소·법정동·시군구 정규화/지오코딩.
- 인프라: PostgreSQL 16 + PostGIS 3.5 / SQLAlchemy 2 async / asyncpg / Pydantic
  v2 / FastAPI + Uvicorn / httpx + tenacity / Alembic / Dagster / Next.js +
  TanStack Query + zustand / RustFS (S3 호환 객체 저장소).

## TripMate ↔ `python-krtour-map`

TripMate는 `python-krtour-map` 최신 `main`의 `openapi.user.json` 계약을 기준으로
HTTP 호출한다. 대표 경로는 `GET /features/in-bounds`, `GET /features/search`,
`GET /features/{feature_id}`, `POST /tripmate/features/batch`다.

TripMate는 `feature` / `provider_sync` schema를 직접 읽거나 `python-krtour-map`을
import하지 않는다. 자세히는 `docs/krtour-map-integration.md`.

## 책임 / 비책임 요약

### 책임

- 사용자/세션/인증 (이메일·소셜·OAuth)
- 여행 계획 도메인 (Trip, Day, POI 첨부, Notice plan, 공유)
- Admin 콘솔 (사용자/엔티티/콘텐츠/파일)
- 사용자 대면 UI (Next.js + maplibre-vworld 기반 지도)
- Dagster orchestration (TripMate 자체 job + 외부 서비스 갱신 trigger)
- 파일 스토리지(RustFS) 운영 API
- 외부 통합 (Telegram, Gemini, Resend, 소셜 로그인 provider)

### 비책임 (`python-krtour-map`이 소유)

- Feature 정규화 / `feature_id` 생성 / SourceRecord 관리
- Postgres schema `feature` / `provider_sync` 의 DDL과 raw SQL
- Provider 원천 → DTO 변환 (KMA, VisitKorea, OpiNet, MOIS, ...)
- Record Linkage / dedup queue
- 지도 좌표·CRS 정책 (`coord_5179` 반경 검색 등)

자세한 책임 경계는 `docs/architecture.md`, `docs/krtour-map-integration.md`.

## 운영 URL

| 서비스 | 로컬 고정 포트 | Production URL |
|--------|---------------|----------------|
| API | `9021` | `https://tripmateapi.digitie.mywire.org` |
| Web | `9022` | `https://tripmate.digitie.mywire.org` |

운영 OAuth callback은 API 도메인 기준
`https://tripmateapi.digitie.mywire.org/auth/oauth/{provider}/callback`이며, Google
승인된 JavaScript 원본은 `https://tripmate.digitie.mywire.org`다.

## 빠른 시작

```bash
# WSL ext4 테스트 미러 (의존성/테스트 전용; git/commit/push는 NTFS worktree)
cd ~/tripmate-workspaces/tripmate-codex

# 시스템 의존성
sudo apt install -y libgdal-dev gdal-bin libpq-dev libgeos-dev libproj-dev

# 백엔드 (uv 권장)
uv venv && uv pip install -e "apps/api[dev]"
# krtour-map은 별도 프로그램으로 실행 (API 9011 / admin 9012)

# 프론트엔드 / API / Dagster dev server
npm install
scripts/dev-up.sh                     # API 9021 / Web 9022 / Dagster 9023

# 인프라 (RustFS API 9003 / console 9004)
docker compose -f infra/docker-compose.yml up -d postgres rustfs

# Docker app build/run/smoke
npm run docker:app:smoke

# krtour-map 독립 프로그램은 별 저장소에서 실행 (API 9011 / admin 9012)

# Alembic (앱 도메인)
uv run --package apps/api alembic upgrade head

# python-krtour-map alembic은 그 저장소에서 실행 (feature schema 소유)

# 테스트
pytest apps/api/tests -q
npm --workspace apps/web run lint && npm --workspace apps/web run typecheck
```

현재는 Sprint 4 기준선 문서와 일부 구현이 함께 존재한다. 정확한 실행 전제와
진척도는 `docs/agent-workflow.md`, `docs/dev-environment.md`,
`docs/runbooks/local-dev.md`, `docs/resume.md`, 각 Sprint 문서를 함께 본다.

## 문서 지도

진입 순서 (5~10분):

1. 도구별 1차 진입 파일 확인
   - Claude: `CLAUDE.md`
   - Codex / Antigravity / Cursor / Copilot: `AGENTS.md`
2. `AGENTS.md` — 지시 우선순위, DO NOT
3. `SKILL.md` — 도메인 어휘, 자주 묻는 작업
4. `docs/agent-guide.md` — 기록·ADR·PR 워크플로
5. `docs/sprints/README.md` — Sprint 1~N 계획
6. `docs/resume.md` — 현재 상태와 다음 한 작업
7. `docs/journal.md` 최신 3건 — 직전 컨텍스트
8. 관련 ADR (`docs/decisions.md`)

상세 문서 (역할별):

**진입 / 작업 가이드**
- 작업·문서화 가이드: [`docs/agent-guide.md`](docs/agent-guide.md)
- 개발 환경: [`docs/agent-workflow.md`](docs/agent-workflow.md) /
  [`docs/dev-environment.md`](docs/dev-environment.md) /
  [`docs/agent-failure-patterns.md`](docs/agent-failure-patterns.md)
- v1 → v2 자산 매핑: [`docs/v1-to-v2-mapping.md`](docs/v1-to-v2-mapping.md)
- 현재 상태 추적: [`docs/resume.md`](docs/resume.md) / [`docs/tasks.md`](docs/tasks.md)

**아키텍처**
- 큰 그림: [`docs/architecture.md`](docs/architecture.md)
- Frontend (Next.js + Expo 공용 monorepo): [`docs/architecture/frontend.md`](docs/architecture/frontend.md)
- 사용자 위치 정보: [`docs/architecture/user-location.md`](docs/architecture/user-location.md)
- Notice plan 도메인: [`docs/architecture/notice-plans.md`](docs/architecture/notice-plans.md)
- 지도 마커 / 로그인 디자인: [`docs/architecture/map-marker-design.md`](docs/architecture/map-marker-design.md)
- Dagster ETL bridge: [`docs/architecture/dagster-etl-bridge.md`](docs/architecture/dagster-etl-bridge.md)
- API 계약 표준: [`docs/architecture/api-contract.md`](docs/architecture/api-contract.md)
- MCP tools: [`docs/architecture/mcp-tools.md`](docs/architecture/mcp-tools.md)
- YouTube intelligence (v2): [`docs/architecture/youtube-travel-intelligence.md`](docs/architecture/youtube-travel-intelligence.md)

**데이터**
- TripMate `app` 도메인: [`docs/data-model.md`](docs/data-model.md)
- Postgres schema 골격: [`docs/postgres-schema.md`](docs/postgres-schema.md)
- 데이터 소스 인덱스: [`docs/data-sources/README.md`](docs/data-sources/README.md)

**API**
- 인덱스 + 공통 규약: [`docs/api/README.md`](docs/api/README.md) / [`docs/api/common.md`](docs/api/common.md)
- 도메인별: [`auth`](docs/api/auth.md) / [`users`](docs/api/users.md) / [`trips`](docs/api/trips.md) / [`pois`](docs/api/pois.md) / [`features`](docs/api/features.md) / [`notice-plans`](docs/api/notice-plans.md) / [`storage`](docs/api/storage.md) / [`admin`](docs/api/admin.md) / [`public`](docs/api/public.md) / [`regions`](docs/api/regions.md) / [`health`](docs/api/health.md) / [`websocket`](docs/api/websocket.md)
- 교차 검색 / 외부 상태: [`GET /search`](docs/api/features.md#26-get-search),
  [`GET /health/external`](docs/api/health.md#13-get-healthexternal)

**외부 통합**
- 인덱스: [`docs/integrations/README.md`](docs/integrations/README.md)
- Resend / 소셜 로그인 (현재 Google만 활성, Naver/Kakao는 future provider) /
  Gemini / Telegram / [maplibre-vworld-js](docs/integrations/maplibre-vworld.md) /
  Sentry / Loki

**규약 (코딩 / DB / 테스트)**
- 인덱스: [`docs/conventions/README.md`](docs/conventions/README.md)
- [`coding-style`](docs/conventions/coding-style.md) / [`database`](docs/conventions/database.md) / [`testing`](docs/conventions/testing.md) / [`geospatial`](docs/conventions/geospatial.md) / [`normalization`](docs/conventions/normalization.md)

**운영 Runbook**
- 인덱스: [`docs/runbooks/README.md`](docs/runbooks/README.md)
- [`local-dev`](docs/runbooks/local-dev.md) / [`docker-app`](docs/runbooks/docker-app.md) / [`etl`](docs/runbooks/etl.md) / [`admin`](docs/runbooks/admin.md) / [`file-storage`](docs/runbooks/file-storage.md) / [`odroid-docker`](docs/runbooks/odroid-docker.md)

**컴플라이언스 / 법무**
- 인덱스: [`docs/compliance/README.md`](docs/compliance/README.md)
- 위치정보법: [`docs/compliance/lbs-act.md`](docs/compliance/lbs-act.md)
- PIPA 2024: [`docs/compliance/pipa.md`](docs/compliance/pipa.md)
- Provider 데이터 정책: [`docs/compliance/data-policy.md`](docs/compliance/data-policy.md)

**Sprint / 결정**
- Sprint 계획: [`docs/sprints/README.md`](docs/sprints/README.md)
- 의사결정 (ADR): [`docs/decisions.md`](docs/decisions.md)
- 작업 일지: [`docs/journal.md`](docs/journal.md)
- 진척도 / 다음 작업: [`docs/resume.md`](docs/resume.md)
- 백로그: [`docs/tasks.md`](docs/tasks.md)

**라이브러리 연계**
- [`docs/krtour-map-integration.md`](docs/krtour-map-integration.md)

**SPEC V8 적용 노트** (외부 문서 기반)
- [`docs/spec/v8/`](docs/spec/v8/README.md)

**디자인**
- 마커 팔레트 (16색 + maki): [`docs/design/marker-palette.md`](docs/design/marker-palette.md)
- 루트 `DESIGN.md` — Airbnb 디자인 톤 reference
- 루트 `airbnb-marker-palette.html` — 16색 시각 미리보기

루트 디자인 reference:

- `DESIGN.md` — Airbnb 디자인 시스템 톤 (v2 v1.0 임시 기준)
- `airbnb-marker-palette.html` — 16색 마커 시각 미리보기 (브라우저에서 직접 열기)

## 라이선스

별도 명시 전까지 비공개(사내). `LICENSE`는 v2 코드 작성 단계 진입 시 결정.
