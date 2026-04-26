# Architecture Baseline

주소/Juso/법정동코드/VWorld 경계 스키마의 상세 기준은 `docs/architecture/address-schema.md`를 따른다.

## 현재 상태

현재 저장소에는 `apps/web`의 Next.js 웹앱과 `apps/api`의 FastAPI 백엔드 골격이 있다.

```text
apps/web
  app/              # Next.js App Router
  package.json      # 웹앱 스크립트와 의존성
  next.config.ts
  tsconfig.json
  eslint.config.mjs
apps/api
  app/              # FastAPI app, routes, settings, DB, models
  alembic/          # migration environment and initial core migration
  tests/            # backend tests
  pyproject.toml    # backend dependencies and tooling
infra
  docker-compose.yml # Postgres/PostGIS local database
```

루트 `package.json`은 npm workspaces 진입점으로 사용한다.

현재 검증된 루트 명령은 다음과 같다.

```bash
npm run lint
npm run typecheck
npm run build
```

현재 API 기준선 명령은 `apps/api`에서 실행한다.

```bash
uv sync --group dev
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
uv run alembic upgrade head
```

## 목표 구조

```text
apps/web            # Next.js + React + TypeScript + PWA
apps/api            # FastAPI + SQLAlchemy 2 + GeoAlchemy2
packages/shared     # 공용 타입, API 계약, 상수
dags                # Airflow DAG
infra               # Docker Compose, Postgres/PostGIS, reverse proxy
scripts             # bootstrap, test, deploy, backup/restore
docs                # 문서, runbook, ADR, 실행 계획
```

## 주요 경계

- 웹앱은 사용자 흐름, 지도 상호작용, PWA UX를 담당한다.
- API는 인증, 인가, 여행 도메인 규칙, provider adapter, Telegram, Gemini 실행 요청을 담당한다.
- Postgres/PostGIS는 권위 있는 사용자/여행/장소/공간 데이터를 저장한다.
- Airflow는 공공데이터와 외부 API 데이터를 수집하고 raw/serving 테이블을 갱신한다.
- 외부 provider 원문 응답은 TTL 캐시에만 저장하고, UI와 도메인 로직은 내부 정규화 스키마를 사용한다.

## 데이터 원칙

- 사용자 로그인 식별자는 이메일이다.
- 인증은 httpOnly cookie 기반 서버 세션으로 시작한다. 세션 cookie에는 opaque token만 넣고, 서버는 해시된 세션 토큰과 만료 시각을 저장한다.
- 모든 사용자 소유 리소스는 `user_id` 인가 검사를 통과해야 한다.
- 장소는 사용자 표시 이름, 좌표, 정규화 주소, 행정구역 코드, provider 참조를 분리해 저장한다.
- Google/Naver/Kakao 원문 전체를 장기 저장 가능한 데이터로 가정하지 않는다.
- 외부 데이터 소스, 캐시 키, 갱신 주기, raw/serving 테이블 정책은 `docs/data-sources.md`를 단일 기준으로 따른다.
- 날씨/유가 화면은 serving 테이블을 우선 조회한다.
- “반경 nkm” 리포트는 엄밀한 원형 거리 계산이 아니라 행정구역 기반 근사일 수 있다.
- Gemini Deep Research는 사용자 개인 API 키 입력 구조로 설계한다. 상세는 `docs/integrations/gemini.md`를 따른다.

## 초기 구현 순서 결정

- 인증: httpOnly cookie 기반 서버 세션을 사용한다. access/refresh token 조합은 모바일 네이티브 앱이나 외부 API 클라이언트가 필요해질 때 재검토한다.
- 지도: Kakao JavaScript SDK 기반 지도 UI와 지도 클릭 장소 초안을 먼저 구현한다. Kakao Local API 검색 adapter는 `docs/data-sources.md`의 저장/캐시 정책과 API 계약을 먼저 확정한 뒤 추가한다.
- Telegram: DB에는 `telegram_bot_token_ref`만 저장한다. 상세는 `docs/integrations/telegram.md`를 따른다.
- Gemini: 사용자 개인 키를 입력받는다. 상세는 `docs/integrations/gemini.md`를 따른다.

## 공간 데이터 기준선

- 권위 있는 공간 필터링은 PostGIS에서 수행한다.
- 위도/경도 표시는 `lat`, `lng` 이름을 사용한다.
- 행정구역 원천 데이터는 V-WORLD `법정구역정보` SHP를 사용한다.
- 행정구역 raw 레이어는 원본 EPSG:5186 geometry를 그대로 보존한다.
- 행정구역 serving 레이어는 지도 표시와 API 응답을 위해 EPSG:4326 변환본을 둔다.
- 행정구역 point-in-polygon 판정은 PostGIS에서 수행한다.
- 웹 지도 출력과 API 응답은 EPSG:4326을 사용한다.
- geometry 저장과 공간 질의의 좌표 순서, 거리 단위는 백엔드 구현 단계에서 migration과 API 문서에 함께 명시한다.
- 근사 리포트는 UI와 API 문서에 근사라고 직접 표기한다.

## 현재 DB 기준선

초기 migration은 PostGIS extension을 활성화하고 다음 테이블을 생성한다.

- `users`
- `sessions`
- `trips`
- `trip_days`

세션 cookie에는 opaque token만 담는 것을 전제로 하며, DB에는 `session_token_hash`만 저장한다.

## 아직 구현되지 않은 것

- 인증 API
- Kakao 지도 연동
- Airflow DAG
- Telegram 발송
- Gemini Deep Research
- PWA manifest/service worker
- ODROID M1S 배포 스크립트
