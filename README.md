# TripMate

`TripMate`는 한국 여행 계획·기록·공유 애플리케이션이다. 한국 공공 API에서 모은
지도/날씨/이벤트/가격/공지/경로/구역 데이터를 사용해 사용자가 여행 계획을 세우고,
이동 중 컨텍스트(날씨/혼잡/이벤트)를 확인하고, 결과를 기록·공유하도록 돕는다.

> **현재 상태 (v2 설계 단계 — Sprint 1 진입 직전)**: master/main 브랜치는 v2
> 사양으로 새로 시작했다. 이전(v1) 구현은 `v1` 브랜치에 보존되어 있다. 본 단계는
> **문서/계약/결정 전용**이며 별도 요청 전까지 코드를 작성하지 않는다. 자세히는
> `CLAUDE.md`, `AGENTS.md`, `docs/sprints/README.md`.

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

TripMate는 **monorepo**다. 코드 작성 단계 진입 시 다음 구조로 박는다 (Sprint 1).

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

- **`python-krtour-map`** (별 저장소 `F:\dev\python-krtour-map`, PyPI/Git URL pin):
  지도 feature 정규화·저장 함수 라이브러리. TripMate는 함수 직접 호출로 사용
  (REST 없음 — ADR-003 mirrored from `python-krtour-map` 측).
- **`python-*-api`** (별 저장소들): KMA, VisitKorea, OpiNet, MOIS, KREX, KHOA,
  국가유산, 산림청 등 한국 공공 API 클라이언트.
- **`python-kraddr-geo`**: 주소·법정동·시군구 정규화/지오코딩.
- 인프라: PostgreSQL 16 + PostGIS 3.5 / SQLAlchemy 2 async / asyncpg / Pydantic
  v2 / FastAPI + Uvicorn / httpx + tenacity / Alembic / Dagster / Next.js +
  TanStack Query + zustand / RustFS (S3 호환 객체 저장소).

## TripMate ↔ `python-krtour-map`

```python
# apps/api/app/etl/festival_asset.py (예시)
from krtour.map import AsyncKrtourMapClient

async with AsyncKrtourMapClient(
    engine=tripmate_async_engine,
    file_store=tripmate_rustfs_store,
    kraddr_geo_client=tripmate_kraddr_client,
) as client:
    features = await client.features_in_bounds(bbox, kinds=["place", "event"])
```

`python-krtour-map`은 어떤 resource(engine, S3 client, provider client,
geocoder)도 스스로 만들지 않고 TripMate에서 주입받는다. HTTP/REST는 사용하지
않는다. 자세히는 `docs/krtour-map-integration.md`.

## 책임 / 비책임 요약

### 책임

- 사용자/세션/인증 (이메일·소셜·OAuth)
- 여행 계획 도메인 (Trip, Day, POI 첨부, Notice plan, 공유)
- Admin 콘솔 (사용자/엔티티/콘텐츠/파일)
- 사용자 대면 UI (Next.js + maplibre-vworld 기반 지도)
- Dagster orchestration (`python-krtour-map`의 collect/load 함수를 asset으로 호출)
- 파일 스토리지(RustFS) 운영 API
- 외부 통합 (Telegram, Gemini, Resend, 소셜 로그인 provider)

### 비책임 (`python-krtour-map`이 소유)

- Feature 정규화 / `feature_id` 생성 / SourceRecord 관리
- Postgres schema `feature` / `provider_sync` 의 DDL과 raw SQL
- Provider 원천 → DTO 변환 (KMA, VisitKorea, OpiNet, MOIS, ...)
- Record Linkage / dedup queue
- 지도 좌표·CRS 정책 (`coord_5179` 반경 검색 등)

자세한 책임 경계는 `docs/architecture.md`, `docs/krtour-map-integration.md`.

## 빠른 시작 (코드 작성 단계 이후)

```bash
# WSL ext4 작업 디렉토리
cd ~/dev/tripmate

# 시스템 의존성
sudo apt install -y libgdal-dev gdal-bin libpq-dev libgeos-dev libproj-dev

# 백엔드 (uv 권장)
uv venv && uv pip install -e "apps/api[dev,providers]"
uv pip install -e "git+https://github.com/digitie/python-krtour-map@<sha>#egg=python-krtour-map"

# 프론트엔드
npm install
npm --workspace apps/web run dev      # http://localhost:3001

# 인프라
docker compose -f infra/docker-compose.yml up -d postgres rustfs

# Alembic (앱 도메인)
uv run --package apps/api alembic upgrade head

# python-krtour-map alembic은 그 저장소에서 실행 (feature schema 소유)

# 테스트
pytest apps/api/tests -q
npm --workspace apps/web run lint && npm --workspace apps/web run typecheck
```

현 단계(v2 설계)는 위 명령이 의미 있는 산출물을 만들지 않는다. 코드 작성
요청이 들어오면 Sprint 1 PR로 위 절차를 부트스트랩한다.

## 문서 지도

진입 순서 (5~10분):

1. `CLAUDE.md` — 1쪽 진입 요약
2. `AGENTS.md` — 지시 우선순위, DO NOT
3. `SKILL.md` — 도메인 어휘, 자주 묻는 작업
4. `docs/sprints/README.md` — Sprint 1~N 계획
5. `docs/architecture.md` — 의존 방향, 책임 경계
6. `docs/resume.md` — 다음 한 작업
7. `docs/journal.md` 최신 3건 — 직전 컨텍스트
8. 관련 ADR (`docs/decisions.md`)

상세 문서:

- 작업·문서화 가이드: `docs/agent-guide.md`
- 개발 환경: `docs/dev-environment.md`
- 데이터 모델 (app 도메인): `docs/data-model.md`
- Postgres schema: `docs/postgres-schema.md`
- 테스트 전략: `docs/test-strategy.md`
- `python-krtour-map` 연계: `docs/krtour-map-integration.md`
- 의사결정 (ADR): `docs/decisions.md`
- 작업 일지: `docs/journal.md`
- 진척도/다음 작업: `docs/resume.md`
- 백로그: `docs/tasks.md`

## 라이선스

별도 명시 전까지 비공개(사내). `LICENSE`는 v2 코드 작성 단계 진입 시 결정.
