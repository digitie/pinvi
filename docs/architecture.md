# architecture.md

`TripMate`의 아키텍처는 **monorepo + multi-process 애플리케이션** 모델이다. 본
저장소는 사용자 대면 앱(FastAPI 백엔드 + Next.js 프론트)과 TripMate 자체 ETL
orchestration(Dagster)을 담고, 지도 feature 도메인은 별 저장소
`python-krtour-map` 독립 프로그램의 **OpenAPI HTTP 계약**으로 사용한다.

SPEC V8 6편 적용 노트는 `docs/spec/v8/`. 본 문서는 v2 아키텍처의 자체 정리.

## 1. 큰 그림

```
┌────────────────────────────────────────────────────────────────────────┐
│ Browser / PWA                                                          │
│   apps/web (Next.js App Router + React 19 + TanStack Query + zustand)  │
│   maplibre-vworld-js (VWorld + MapLibre GL JS, ADR-015)                │
└────────────────────────────────────────────────────────────────────────┘
                              │ HTTPS (cookie session / JWT)
                              ▼
┌────────────────────────────────────────────────────────────────────────┐
│ apps/api (FastAPI + Uvicorn)                                           │
│   routes/   인증·여행 계획·관리자·Storage·Notice·소셜 로그인               │
│   services/ 비즈니스 로직 (사용자/여행/Admin CRUD/공지/첨부/이메일/소셜)     │
│   models/   SQLAlchemy 2 async — app schema만                          │
│   schemas/  Pydantic v2                                                │
│                                                                        │
│   httpx → krtour-map API :9011 (OpenAPI, ADR-026)                       │
│   httpx → kraddr-geo v2 REST (ADR-025)                                  │
└────────────────────────────────────────────────────────────────────────┘
                              │
       ┌──────────────────────┼──────────────────────────────┐
       ▼                      ▼                              ▼
┌──────────────┐    ┌────────────────────┐    ┌─────────────────────────┐
│ PostgreSQL16 │    │ RustFS (S3 호환)   │    │ python-krtour-map       │
│ + PostGIS3.5 │    │ - app/             │    │ API/Admin :9011/:9012   │
│ schema:      │    │   사용자 첨부      │    │                         │
│ - app (TM)   │    │ - feature-media/   │    │ feature/provider_sync   │
│ - feature    │    │   krtour-map 소유  │    │ schema 소유              │
│ - provider_  │    │                    │    │                         │
│   sync       │    └────────────────────┘    │ provider ETL 소유        │
│ - ops        │                              │                         │
│ - x_extension│                              │                         │
└──────────────┘                              │                         │
       ▲                                       └─────────────────────────┘
       │
┌──────────────────────────────────────────────┐
│ apps/etl (Dagster definitions/jobs/schedules)│
│   asset: KASI 특일/출몰시각, 알림, 보존정책 등 │
└──────────────────────────────────────────────┘
```

## 2. 의존 방향

### 2.1 백엔드(`apps/api`) 내부

```
schemas → models → services → routes
                  ↘ clients → krtour-map / kraddr-geo HTTP
```

- `schemas`는 Pydantic v2 입출력. 다른 내부 모듈에 의존하지 않는다.
- `models`는 SQLAlchemy 2 async 매핑. `app` schema만 갖는다. `feature`/
  `provider_sync`의 ORM 매핑은 본 저장소에 두지 않는다 (`python-krtour-map`이
  소유).
- `services`는 비즈니스 로직. raw SQL이 필요하면 `app` schema에 한정.
- `routes`는 FastAPI 라우터 + DI. 권한 미들웨어/dependency가 여기에 박힌다.
- `clients`는 외부 HTTP transport helper. krtour-map/kraddr-geo 계약을 호출하되
  provider 변환이나 feature 정규화 로직을 만들지 않는다.

CI에서 `import-linter`로 강제할 계약(코드 작성 단계 진입 후 박음):

```toml
[tool.importlinter]
root_packages = ["tripmate"]

[[tool.importlinter.contracts]]
type = "layers"
layers = [
  "tripmate.api.routes",
  "tripmate.api.services",
  "tripmate.api.models",
  "tripmate.api.schemas",
]

[[tool.importlinter.contracts]]
type = "forbidden"
source_modules = ["tripmate.api"]
forbidden_modules = [
  "tripmate.api.models.feature",       # feature schema 매핑 금지
  "tripmate.api.models.provider_sync", # provider_sync schema 매핑 금지
]
```

### 2.2 프론트(`apps/web` + Expo `apps/mobile` 공용 패키지)

자세한 스택·디자인 토큰·공용 패키지 구조는 [`docs/architecture/frontend.md`](architecture/frontend.md).

핵심:

- Next.js 15 (App Router) + React 19 + shadcn/ui + Tailwind + Zustand +
  TanStack Query v5 + React Hook Form + Zod
- DESIGN.md / `airbnb-marker-palette.html` 디자인 톤 단일 기준
- **`packages/{schemas,api-client,state,design-tokens,hooks,i18n}`** 공용 코드
  — Expo `apps/mobile`(v2)이 그대로 import
- 클라이언트가 외부 API를 직접 호출하지 않는다 (모두 백엔드 경유).
- 지도는 `maplibre-vworld-js`를 lazy load + dynamic import로 SSR 영향 차단
  (Kakao Maps SDK는 ADR-015로 폐기).
- 위치 정보는 [`useUserLocation`](architecture/user-location.md) 공용 hook +
  웹/모바일 어댑터.

### 2.3 ETL(`apps/etl`, Dagster)

- 각 asset은 TripMate `app` schema 소유 job을 수행한다. 예: KASI 특일 일 1회
  upsert, POI 출몰시각 생성 시 1회 갱신, 알림 outbox, PII retention.
- krtour-map feature provider 적재 job은 krtour-map 저장소의 API/Admin/Dagster가
  소유한다.
- Asset 정의는 `apps/etl/assets/<name>.py`, 코드 위치는 `definitions.py`에 등록.

## 3. TripMate ↔ `python-krtour-map`

TripMate는 최신 krtour-map `openapi.user.json`을 기준으로 HTTP 호출한다.

- API base URL: `TRIPMATE_KRTOUR_MAP_API_BASE_URL` (`http://localhost:9011`)
- Admin base URL: `TRIPMATE_KRTOUR_MAP_ADMIN_BASE_URL` (`http://localhost:9012`)
- 대표 경로: `GET /features/in-bounds`, `GET /features/search`,
  `GET /features/{feature_id}`, `POST /tripmate/features/batch`

TripMate는 `python-krtour-map` import, `feature` schema 직접 SQL, provider 변환을
하지 않는다. 사용자 대면 geocoding(조회)은 별개로 `kraddr-geo` v2 REST를 직접
HTTP 호출한다(ADR-025, `docs/integrations/kraddr-geo.md`).

자세한 통합 가이드는 `krtour-map-integration.md`.

## 4. 데이터 흐름

### 4.1 사용자 요청 (예: "내일 부산 여행 계획")

1. 브라우저 `apps/web` → TripMate API
2. `apps/api/app/api/routes/trips.py` 라우터가 사용자 인증 + Trip 도메인 처리
3. POI 첨부 시 `feature_id`로 krtour-map `POST /tripmate/features/batch` 호출
4. krtour-map API가 `feature` schema에서 결과 반환
5. 라우터가 Pydantic 응답 셰입으로 변환해 클라이언트에 반환

### 4.2 TripMate 자체 ETL (예: KASI 특일)

1. Dagster scheduler가 `kasi_special_days_daily` asset/job 트리거
2. `python-kasi-api`로 특일 계열 dataset을 조회
3. `app.kasi_special_days`에 upsert
4. 별도 삭제 없이 로그 + 메타데이터는 Dagster `ops` schema에 기록

## 5. 운영 환경 (Odroid M1S)

- Ubuntu 24.04 + Docker Compose plugin
- 서비스 컨테이너:
  - PostgreSQL 16 + PostGIS 3.5 (단일 DB `tripmate`)
  - RustFS (S3 호환)
  - `apps/api` (Uvicorn workers)
  - `apps/web` (Next.js standalone)
  - `apps/etl` (Dagster webserver + daemon)
- Reverse proxy: Cloudflare Tunnel (또는 nginx)
- 백업: PostgreSQL pg_dump + RustFS snapshot (별도 schedule)

자세한 운영 절차는 `docs/runbooks/odroid-docker.md`와
`docs/runbooks/deploy.md`를 따른다.

## 6. 보안 / 권한

- 사용자 세션: HttpOnly cookie + CSRF 또는 JWT. 실제 정책은 인증 ADR/구현 PR에서
  확정한다.
- Admin RBAC: 서버 dependency에서 권한 검사. UI 라우팅은 보조.
- 외부 API 키: `.env`에 `SecretStr` → systemd `EnvironmentFile`/vault.
- Webhook(Telegram/Resend/소셜 OAuth callback): HMAC/state 검증.
- 파일 업로드: MIME/크기 검증 + RustFS 별 prefix + 가상 파일명.

## 7. CI / 정합성 게이트 (계획)

- `.github/workflows/api.yml` — pytest + ruff + mypy --strict + import-linter
- `.github/workflows/web.yml` — npm lint/typecheck/build + playwright(smoke)
- `.github/workflows/etl.yml` — Dagster asset registry sanity + asset-level dry run
- `.github/workflows/openapi.yml` — OpenAPI export drift gate
- `.github/workflows/security.yml` — bandit + npm audit

각 게이트는 ADR과 함께 박는다. `python-krtour-map`의 CI는 그쪽 저장소에서
독립 운영.

## 8. 로컬 개발 흐름 (요약)

자세히는 `dev-environment.md`. 핵심:

1. NTFS worktree `F:/dev/tripmate-<agent>`에서 Windows `git.exe`로 branch/commit/push
2. WSL ext4 테스트 미러 `~/tripmate-workspaces/tripmate-<agent>`에서 테스트/Docker 실행
3. `dataset/`, `refdocs/`는 NTFS에 두고 ext4에 심볼릭 링크 또는 직접 참조
4. `python-krtour-map`은 별도 sibling 저장소에서 API `9011` / admin `9012`로 실행
   하고, TripMate는 HTTP base URL만 설정한다.
5. 동기는 NTFS → ext4 단방향. ext4 미러에서 commit/push 금지

## 9. v1과의 차이 (요약)

v1(`v1` 브랜치)에서 v2로 가져오는 결정은 ADR로 한 건씩 박는다. 큰 차이는:

- **지도 feature 도메인을 별 저장소로 분리** — v1은 `apps/api` 안에 모든
  모델/서비스가 있었다. v2는 `python-krtour-map`이 소유.
- **provider 어댑터 wrapper 제거** — v1에는 `apps/api/app/etl/<provider>/` 아래
  raw → DTO 변환이 있었다. v2는 모두 `python-krtour-map.providers`로 이전.
- **Dagster asset 위치 변경** — v1은 `apps/api/app/dagster_etl/`. v2는
  `apps/etl/`로 분리해 백엔드와 코드 위치를 다르게 한다.
- **개발 환경 모델 변경** — v1의 ext4 직접 작업본/NTFS export 표현과 ADR-004의
  WSL source-of-truth 주장은 ADR-024로 supersede. v2는 **NTFS worktree가 git
  source of truth**, WSL ext4는 테스트 미러. 자세히는 `dev-environment.md`.

v1 → v2 마이그레이션 항목별 처리는 `docs/decisions.md`에 ADR로 박는다.
