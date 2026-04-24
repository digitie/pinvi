# 대한민국 전용 TripMate 구현 계획

## 1. 목적

이 문서는 현재 `F:\dev\mapplan` 저장소를 대한민국 전용 여행 계획 웹앱으로 확장하기 위한 실행 계획이다. 현재 저장소는 `apps/web`에 Next.js 웹앱을 둔 npm workspaces 구조이며, 목표 아키텍처는 다음 경계를 가진다.

- `apps/web`: Next.js + React + TypeScript + PWA
- `apps/api`: FastAPI + SQLAlchemy 2 + GeoAlchemy2
- `packages/shared`: 공용 타입, API 계약, 상수
- `dags`: Airflow 데이터 수집 DAG
- `infra`: Docker Compose, Postgres/PostGIS, reverse proxy, 운영 설정
- `scripts`: 로컬 bootstrap, 테스트, 배포, 백업/복구
- `docs`: 아키텍처, API, 데이터 출처, runbook, ADR, 실행 계획

제품 범위는 대한민국 국내 여행으로 한정한다. 비회원 사용은 지원하지 않고, 로그인 식별자는 이메일이다.

## 2. 현재 상태 요약

- Next.js App Router 기반 웹앱은 `apps/web`에 있다.
- 루트 `package.json`은 npm workspaces 진입점이며 `dev`, `build`, `lint`, `typecheck` 스크립트를 웹앱 workspace로 위임한다.
- `README.md`, `docs/PROJECT_BRIEF.md`, `docs/architecture.md`, `docs/runbooks/local-dev.md`, 초기 ADR 문서가 있다.
- `docs/data-sources.md`가 외부 데이터 소스, 캐시, raw/serving 저장 정책의 단일 기준 문서다.
- 백엔드, 데이터베이스, Airflow, Docker, Playwright, 테스트 구조는 아직 없다.
- 웹앱 첫 화면의 깨진 한글 문구는 정리됐다.

## 3. 핵심 결정

1. 저장소 구조는 모노레포 형태로 전환한다.
2. 인증은 초기부터 필수로 설계한다.
3. 권위 있는 장소/여행 데이터는 백엔드와 Postgres/PostGIS에 저장한다.
4. 지도 UX는 Kakao Map을 기본 지도 표면으로 삼는다.
5. Kakao/Naver/Google/일반 검색 결과는 후보 표시와 내부 정규화 계층을 분리한다.
6. 날씨/유가/행정구역 기반 리포트는 실시간 연타 호출이 아니라 ETL 캐시와 serving 테이블을 우선 사용한다.
7. Telegram 발송 대상은 사용자 소유 리소스로 분리하고, 여행별 최대 3개 연결 제한을 도메인과 UI에서 모두 강제한다.
8. Gemini Deep Research는 수동 버튼 실행, 재사용 가능한 결과, 출처 추적을 기본으로 둔다.
9. 인증은 httpOnly cookie 기반 서버 세션으로 시작한다.
10. Kakao 지도는 JavaScript SDK 지도 UI와 지도 클릭 장소 초안을 먼저 구현하고, Kakao Local API 검색 adapter는 API/cache 계약 이후 붙인다.
11. Telegram bot token 실제 값은 환경변수에 두고 DB에는 `telegram_bot_token_ref`만 저장한다.
12. 행정구역 원천 데이터는 V-WORLD `법정구역정보` SHP를 사용한다.
13. 행정구역 raw 레이어는 EPSG:5186 원본을 보존하고, serving 레이어는 EPSG:4326 변환본을 둔다.
14. Gemini Deep Research는 사용자 개인 API 키 입력 구조로 설계하고, 키 원문은 일반 DB에 평문 저장하지 않는다.

## 4. 단계별 구현 계획

### Phase 0. 저장소 정리와 기준선 수립

상태: 완료.

목표: 이후 기능 구현이 흔들리지 않도록 구조, 문서, 테스트 기준선을 먼저 만든다.

작업:

- 현재 루트 Next.js 앱을 `apps/web`로 이동한다. 완료.
- npm workspaces 구조로 스크립트를 정리한다. 완료.
- `docs/PROJECT_BRIEF.md`를 대한민국 전용 제품 방향으로 갱신한다. 완료.
- `docs/architecture.md` 초안을 작성한다. 완료.
- `docs/runbooks/local-dev.md`를 작성한다. 완료.
- `docs/decisions/`에 초기 ADR을 추가한다. 완료.
- 깨진 한글 UI 문구를 정상 문구로 교체한다. 완료.
- ESLint, TypeScript, 빌드 기준선을 확인한다. 완료.

검증:

- `npm run lint`
- `npm run typecheck`
- `npm run build`
- `npm --workspace apps/web run dev -- --port 3001` 후 HTTP 200 smoke

완료 조건:

- 최상위 README가 실제 실행 명령과 구조를 설명한다.
- 앱이 이전과 동일하게 로컬에서 실행된다.
- 깨진 문구가 화면에서 사라진다.

### Phase 1. 백엔드와 데이터베이스 골격

상태: 진행 중. FastAPI 앱, Postgres/PostGIS Compose, Alembic 초기 migration, `users`/`sessions`/`trips`/`trip_days` 모델이 추가됐다. 장소, Telegram, Gemini, ETL 관련 테이블은 후속 phase에서 추가한다.

목표: 인증, 여행, 장소, Telegram, 캐시 데이터를 담을 서버와 DB 기반을 만든다.

작업:

- `apps/api`에 FastAPI 프로젝트를 추가한다.
- SQLAlchemy 2, Alembic, GeoAlchemy2, pytest, ruff, mypy 기준을 추가한다.
- Postgres/PostGIS용 `infra/docker-compose.yml`을 추가한다.
- `docs/data-sources.md`의 raw/serving/cache 정책과 충돌하지 않도록 DB schema 초안을 검토한다.
- DB 모델 초안을 만든다.
  - `users`
  - `sessions`
  - `trips`
  - `trip_days`
- `places` (후속)
- `trip_places` (후속)
- `place_provider_refs` (후속)
- `provider_response_cache` (후속)
- `telegram_targets` (후속)
- `trip_telegram_targets` (후속)
- `gemini_research_runs` (후속)
- `weather_observations_raw` (후속)
- `weather_region_daily` (후속)
- `fuel_prices_raw` (후속)
- `fuel_region_daily` (후속)
- `admin_regions` (후속)
- Alembic migration을 추가한다.
- `/health`와 DB 연결 smoke endpoint를 만든다.

검증:

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy .`
- `uv run pytest`
- migration upgrade smoke

완료 조건:

- Docker 기반 DB가 뜬다.
- FastAPI가 DB에 연결된다.
- 초기 migration이 성공한다.

### Phase 2. 인증과 사용자 관리

목표: 비회원 사용 불가 원칙을 API와 UI에 적용한다.

작업:

- 이메일 기반 회원가입/로그인/로그아웃 API를 만든다.
- httpOnly cookie 기반 서버 세션을 구현한다.
- 세션 cookie에는 opaque token만 저장하고, DB에는 해시된 세션 토큰과 만료 시각을 저장한다.
- 비밀번호 해시 정책을 문서화한다.
- 사용자 정보 조회/수정 API를 만든다.
- 인가 dependency를 추가한다.
- 웹에 로그인, 회원가입, 사용자 정보 수정 화면을 추가한다.
- 인증이 필요한 화면 접근 제어를 구현한다.
- `docs/api/auth.md`를 작성한다.

검증:

- 정상 로그인 테스트
- 중복 이메일 실패 테스트
- 잘못된 비밀번호 실패 테스트
- 사용자 정보 수정 인가 테스트
- Playwright 로그인 및 사용자 정보 수정 smoke

완료 조건:

- 인증 없이 여행 화면에 접근할 수 없다.
- 이메일 중복이 허용되지 않는다.
- 비밀번호나 비밀값이 평문 저장되지 않는다.

### Phase 3. 여행 계획 CRUD

목표: Trip, TripDay, Place의 핵심 수동 계획 흐름을 구현한다.

작업:

- 여행 생성/조회/수정/삭제 API를 만든다.
- 날짜 범위에서 `trip_days`를 생성/갱신하는 서비스 로직을 만든다.
- 장소 수동 추가, 수정, 삭제, 순서 변경 API를 만든다.
- 장소 표시 이름과 provider 원본 이름을 분리한다.
- 웹에 여행 목록, 생성/수정 폼, 여행 상세, 날짜별 일정 리스트를 만든다.
- 모바일 우선 레이아웃으로 작성한다.
- `docs/api/trips.md`를 작성한다.

검증:

- 여행 CRUD unit/integration tests
- 날짜 변경 시 day 재계산 테스트
- 하루 내 장소 순서 보존 테스트
- Playwright 여행 생성/수정/삭제 smoke

완료 조건:

- 로그인 사용자가 자신의 여행만 관리할 수 있다.
- 하루 내 장소 순서가 안정적으로 유지된다.

### Phase 4. Kakao 지도와 장소 입력

목표: 지도 검색 결과 선택과 지도 클릭 기반 장소 추가를 모두 지원한다.

작업:

1차 작업:

- `react-kakao-maps-sdk`를 도입한다.
- Kakao JavaScript 키 환경변수를 문서화한다.
- 지도 화면과 일정 리스트 동기화를 구현한다.
- 지도 클릭으로 좌표 기반 장소 초안을 만든다.
- 지도 클릭 장소 초안은 provider 원문 없이 사용자 입력 이름, 좌표, 메모를 우선 저장한다.

2차 작업:

- `docs/api/places.md`에 검색 후보와 내부 장소 저장 계약을 작성한다.
- `docs/data-sources.md`에 Kakao Local API cache key, TTL, 저장 제한을 확정한다.
- Kakao Local API adapter를 백엔드에 추가한다.
- provider 후보를 내부 정규화 스키마로 변환한다.
- `provider_response_cache`에 TTL 기반 원문 캐시만 저장한다.
- Google/Naver 데이터 저장 제한을 코드 주석과 문서에 반영한다.
- Naver/Google 후보 조합은 약관/정책 검토가 완료될 때까지 adapter 인터페이스만 열어두고 기본 구현에서 제외한다.

검증:

- 지도 클릭 장소 추가 component/integration test
- Kakao 후보 정규화 unit test
- provider cache TTL 테스트
- Playwright 검색으로 장소 추가
- Playwright 지도 클릭으로 장소 추가
- 모바일 viewport 지도 smoke

완료 조건:

- UI는 내부 정규화 장소 스키마만 의존한다.
- 공급자 원문 전체를 장기 저장하지 않는다.
- Kakao 지도와 리스트 선택 상태가 동기화된다.

### Phase 5. 행정구역과 공간 로직

목표: 장소와 지역 데이터를 연결하고, 근사 리포트의 한계를 명확히 한다.

작업:

- 행정구역 원천 데이터는 V-WORLD `법정구역정보` SHP로 확정한다.
- `region_raw_boundary`는 원본 SHP의 EPSG:5186 geometry를 그대로 적재한다.
- `region_serving_boundary`는 웹 지도/API 조회용 EPSG:4326 변환본으로 생성한다.
- 원본 보존, SHP 갱신 비교, 재처리는 raw EPSG:5186 레이어 기준으로 수행한다.
- 웹 지도 출력과 API 응답은 EPSG:4326을 사용한다.
- 행정구역 point-in-polygon 판정은 PostGIS에서 수행한다.
- 좌표 순서와 거리 단위 정책을 `docs/architecture.md`와 API 문서에 기록한다.
- 장소 좌표를 행정구역 코드와 매칭하는 서비스를 만든다.
- “반경 nkm” 리포트는 인접/겹침 행정구역 기반 근사로 구현한다.
- UI에 정확한 원형 거리 검색이 아님을 표시한다.

검증:

- 좌표 fixture 기반 행정구역 매칭 테스트
- 경계 근처 좌표 테스트
- SRID 불일치 방어 테스트
- 근사 반경 리포트 테스트

완료 조건:

- 공간 질의는 PostGIS를 우선 사용한다.
- 근사 동작이 문서와 UI에 명확히 표현된다.

### Phase 6. Airflow ETL, 날씨, 유가 캐시

목표: 외부 API 반복 호출을 줄이고 저장된 지역 데이터를 우선 사용하는 데이터 파이프라인을 만든다.

작업:

- `dags` 구조를 추가한다.
- Airflow용 Docker 설정을 추가한다.
- 새 데이터 소스나 cache key가 필요하면 구현 전에 `docs/data-sources.md`를 먼저 갱신한다.
- 기상청 단기/초단기 예보용 WGS84 ↔ DFS `nx`,`ny` 변환은 `apps/api/app/geospatial/kma_grid.py`를 사용한다.
- 날씨 수집 DAG를 만든다.
- 유가 수집 DAG를 만든다.
- raw 적재 테이블과 serving 테이블을 분리한다.
- source, schedule, freshness target, retry policy, 저장 대상 테이블을 DAG 문서에 기록한다.
- cache hit/miss와 수집 윈도우 로그를 남긴다.
- `docs/runbooks/etl.md`를 작성한다.

검증:

- 파서 unit test
- 멱등성 테스트
- stale-cache fallback 테스트
- DAG import test
- 샘플 데이터 serving query 테스트

완료 조건:

- 동일 지역/시간창 조회에서 외부 API를 반복 호출하지 않는다.
- ETL 실패 시 기존 serving 데이터 사용 가능 여부가 명확하다.

### Phase 7. Telegram 알림

목표: 사용자와 여행 단위의 Telegram 알림 대상을 안전하게 관리한다.

작업:

- Telegram target CRUD API를 만든다.
- `sendMessage` 또는 `getChat` 기반 검증 플로우를 만든다.
- 여행별 Telegram target 최대 3개 연결 제한을 구현한다.
- chat type, thread/topic id, label, enabled, last status 필드를 UI에 노출한다.
- 일주일 전 요약과 하루 전 상세 예보 메시지 생성 서비스를 분리한다.
- 발송 실패 원인을 구분해 저장한다.
- `docs/api/telegram.md`와 `docs/runbooks/telegram.md`를 작성한다.

검증:

- target 등록/검증 unit/integration test
- 여행별 3개 제한 테스트
- 메시지 생성 테스트
- 중복 발송 방지 테스트
- Playwright Telegram 설정 저장 smoke

완료 조건:

- bot token은 DB 평문으로 저장되지 않는다.
- 여행별 알림 대상 제한이 API와 UI에서 모두 강제된다.

### Phase 8. Gemini Deep Research

목표: 저장된 장소에 대해 수동 실행 가능한 보강 조사 결과를 생성하고 추적한다.

작업:

- 사용자 개인 Gemini API 키 입력/검증/교체/삭제 흐름을 만든다.
- Gemini API 키 원문은 일반 DB와 로그에 저장하지 않는다.
- 사용자/실행 결과 테이블에는 secret reference, masked fingerprint, 검증 상태만 저장한다.
- 실제 키는 secret store 또는 암호화된 비밀 저장 계층에서 읽는다.
- Gemini 실행 adapter를 만든다.
- 수동 실행 endpoint를 만든다.
- prompt, model, 실행 시각, 입력 컨텍스트 요약, 결과 섹션, 출처, 에러 상태를 저장한다.
- 동일 입력의 최근 결과 재사용 옵션을 제공한다.
- UI에서 “생성 결과”와 “확인된 원천 데이터”를 분리 표시한다.
- 자동 주기 실행은 비활성화 상태로 둔다.
- `docs/api/gemini-research.md`를 작성한다.

검증:

- idempotency key 테스트
- 사용자 키 검증/교체/삭제 테스트
- Gemini API 키가 로그와 일반 DB에 남지 않는지 확인하는 테스트
- 실패 상태 저장 테스트
- 최근 결과 재사용 테스트
- section schema validation test

완료 조건:

- 생성 결과와 provider 원천 데이터가 섞이지 않는다.
- 사용자가 출처 링크를 확인할 수 있다.
- 사용자가 자신의 Gemini API 키를 철회할 수 있다.

### Phase 9. PWA와 핵심 E2E

목표: 모바일 중심 여행 계획 흐름과 오프라인 한계를 명확히 한다.

작업:

- PWA manifest와 service worker 전략을 추가한다.
- 오프라인에서 가능한 화면과 불가능한 기능을 정의한다.
- 모바일 viewport에서 여행 생성/수정, 장소 추가, 지도 대체 메뉴를 점검한다.
- Playwright E2E 최소 범위를 구성한다.
  - 로그인
  - 사용자 정보 수정
  - 여행 생성/수정/삭제
  - 검색으로 장소 추가
  - 지도 클릭으로 장소 추가
  - 날짜별 마커 색상과 리스트 동기화
  - Telegram 설정 저장
  - 모바일 viewport PWA smoke

검증:

- `npm run lint`
- `npm run typecheck`
- web unit/component tests
- Playwright smoke

완료 조건:

- 핵심 모바일 플로우에 가로 overflow가 없다.
- hover 전용 UX가 핵심 기능을 막지 않는다.

### Phase 10. 배포, 백업, 운영 문서

목표: WSL2 로컬 개발과 ODROID M1S 배포를 반복 가능하게 만든다.

작업:

- `scripts/bootstrap-local.sh`를 추가한다.
- `scripts/test-local.sh`를 추가한다.
- `scripts/deploy.sh`를 추가한다.
- `scripts/backup-db.sh`와 `scripts/restore-db.sh`를 추가한다.
- ODROID M1S 배포 runbook을 작성한다.
- reverse proxy와 컨테이너 health check를 구성한다.
- DB 관리 도구는 인증된 컨테이너로만 노출한다.
- rollback 절차를 문서화한다.

검증:

- 로컬 bootstrap smoke
- 전체 테스트 스크립트 smoke
- Docker Compose health check
- 백업/복구 dry run

완료 조건:

- 신규 환경에서 문서만 보고 로컬 스택을 띄울 수 있다.
- 배포와 rollback 절차가 체크리스트로 존재한다.

## 5. API 계약 초안

초기 엔드포인트:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /users/me`
- `PATCH /users/me`
- `GET /trips`
- `POST /trips`
- `GET /trips/{trip_id}`
- `PATCH /trips/{trip_id}`
- `DELETE /trips/{trip_id}`
- `POST /trips/{trip_id}/places`
- `PATCH /trips/{trip_id}/places/{trip_place_id}`
- `DELETE /trips/{trip_id}/places/{trip_place_id}`
- `POST /trips/{trip_id}/places/reorder`
- `GET /places/search`
- `POST /places/from-map-click`
- `GET /telegram-targets`
- `POST /telegram-targets`
- `POST /telegram-targets/{target_id}/verify`
- `POST /trips/{trip_id}/telegram-targets`
- `DELETE /trips/{trip_id}/telegram-targets/{target_id}`
- `POST /places/{place_id}/gemini-research`

계약 작성 순서:

1. 인증과 공통 오류 모델
2. Trip/TripDay/Place 스키마
3. provider 후보와 내부 정규화 장소 스키마
4. Telegram target 스키마
5. ETL serving 조회 스키마
6. Gemini research result 스키마

## 6. 데이터 모델 주의사항

- 모든 사용자 소유 리소스는 `user_id` 기반 인가 검사를 거친다.
- 위치 좌표는 lat/lng 표시와 geometry 저장의 좌표 순서를 혼동하지 않도록 명시한다.
- 행정구역 raw geometry는 EPSG:5186, serving geometry는 EPSG:4326으로 분리한다.
- 외부 provider 원문은 TTL 캐시에만 저장한다.
- Google/Naver/Kakao 원문 데이터의 장기 저장 가능 여부를 임의로 확정하지 않는다.
- Gemini 생성 결과는 provider 원천 데이터와 다른 테이블/타입으로 관리한다.
- Gemini 사용자 API 키는 secret reference와 masked fingerprint만 도메인 DB에 저장한다.
- Telegram bot token은 실제 값이 아니라 secret reference만 저장한다.

## 7. 테스트 전략

좁은 범위에서 넓은 범위로 확장한다.

1. 도메인 서비스 unit test
2. API + DB integration test
3. geospatial fixture test
4. ETL parser/cache/idempotency test
5. Telegram message/verification test
6. React component/integration test
7. Playwright 핵심 사용자 흐름 smoke
8. 전체 lint/typecheck/build

의미 있는 변경은 테스트 없이 완료하지 않는다. 테스트가 기술적으로 아직 구성되지 않은 단계에서는 해당 단계에서 테스트 러너를 먼저 추가한다.

## 8. 문서 갱신 목록

필수 문서:

- `README.md`
- `docs/PROJECT_BRIEF.md`
- `docs/architecture.md`
- `docs/api/auth.md`
- `docs/api/trips.md`
- `docs/api/places.md`
- `docs/api/telegram.md`
- `docs/api/gemini-research.md`
- `docs/data-sources.md`
- `docs/integrations/telegram.md`
- `docs/integrations/gemini.md`
- `docs/runbooks/local-dev.md`
- `docs/runbooks/etl.md`
- `docs/runbooks/telegram.md`
- `docs/runbooks/deploy.md`
- `docs/decisions/YYYYMMDD-initial-architecture.md`
- `docs/decisions/YYYYMMDD-initial-implementation-defaults.md`
- `docs/decisions/YYYYMMDD-data-source-policy-cleanup.md`
- `docs/decisions/YYYYMMDD-region-boundary-crs-policy.md`
- `docs/decisions/YYYYMMDD-provider-data-storage-policy.md`
- `docs/decisions/YYYYMMDD-geospatial-radius-approximation.md`

문서는 실제 구현 상태만 기록한다. 아직 구현되지 않은 기능은 “계획” 또는 “미구현”으로 명시한다.

## 9. 주요 위험과 대응

- 지도/provider 약관 위험: 원문 장기 저장 금지, TTL 캐시, 출처/재조회 시각 기록, 법무/정책 확인 필요 표시.
- 공간 질의 오류: SRID, 좌표 순서, 단위 변환을 테스트 fixture로 고정.
- 외부 API 쿼터 초과: timeout, backoff, quota guard, stale-cache fallback 적용.
- Telegram 발송 실패: 실패 사유 분류, last status 저장, 검증 플로우 제공.
- 모바일 UX 저하: Playwright 모바일 smoke와 수동 지도 대체 메뉴 제공.
- ODROID 리소스 제약: 컨테이너 수, DB 백업, Airflow 스케줄, 로그 보존 정책을 runbook에서 제한한다.

## 10. 다음 구현 단위 추천

Phase 0은 완료됐다. 다음으로 가장 작은 안전한 구현 단위는 Phase 1의 API/DB 골격이다.

구체 작업:

1. `apps/api` FastAPI 골격을 추가한다.
2. `infra/docker-compose.yml`에 Postgres/PostGIS를 추가한다.
3. Alembic 기반 초기 migration 구조를 추가한다.
4. `users`, `sessions`, `trips`, `trip_days`의 최소 schema를 먼저 만든다.
5. `/health`와 DB 연결 smoke endpoint를 만든다.
6. `docs/api/auth.md`와 `docs/runbooks/local-dev.md`를 갱신한다.
7. API lint/typecheck/test와 migration smoke를 실행한다.
