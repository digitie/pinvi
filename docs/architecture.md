# 아키텍처 기준선

주소 체계, Juso/법정동코드/VWorld 경계 스키마, 다른 데이터셋과의 주소 매핑 기준은 `docs/architecture/address-schema.md`를 따른다.
사용자, 이메일 인증, 여행 참여자, 여행 장소 스키마의 상세 기준안은 `docs/architecture/user-trip-schema.md`를 따른다.
내부 표준 장소, 장소 카테고리, provider 장소 참조, 여행 방문 장소와의 연결 기준은 `docs/architecture/place-schema.md`를 따른다.
장소·행사·경로·구역·지도 공지를 하나의 지도 객체로 수렴시키는 후속 통합 스키마 설계안은 `docs/architecture/map-feature-schema.md`를 따른다.
공공데이터 기반 수목원·휴양림·박물관·미술관·캠핑장 장소 ETL과 표준 장소 적재 기준은 `docs/architecture/public-place-etl-schema.md`를 따른다.
OpiNet 유가 스키마의 상세 기준은 `docs/architecture/fuel-schema.md`를 따른다.
OpiNet provider 지역코드와 Juso 시군구 코드의 매핑 기준은 `docs/architecture/opinet-region-mapping.md`를 따른다.
한국도로공사 휴게소 스키마의 상세 기준은 `docs/architecture/rest-area-schema.md`를 따른다.
날씨와 대기질 스키마의 상세 기준은 `docs/architecture/weather-air-quality-schema.md`를 따른다.
해수욕장 통합 도메인 스키마의 상세 기준은 `docs/architecture/beach-schema.md`를 따른다.
기상청 추천 관광코스 스키마의 상세 기준은 `docs/architecture/kma-tour-course-schema.md`를 따른다.
공공데이터포털 전국문화축제표준데이터 스키마는 `docs/architecture/public-cultural-festival-schema.md`를 따른다.
한국천문연구원 날짜·천문 정보 설계는 `docs/architecture/kasi-calendar-schema.md`를 따른다.
provider library 직접 사용 기준은 `docs/architecture/provider-library-direct-use.md`를 따른다.
지도 feature 공통 DTO, source trace, provider canonical name, debug fixture replay 기준은 `docs/architecture/krtour-map-library.md`와 하부 라이브러리 `python-krtour-map` 문서를 따른다.
지도 마커와 로그인 화면 디자인 기준은 `docs/architecture/map-marker-design.md`를 따른다.
Google/Naver/Kakao 소셜 로그인 통합 기준은 `docs/integrations/social-login.md`와 `docs/decisions/20260508-social-login-provider-identity.md`를 따른다.
TripMate MCP 도구 설계는 `docs/architecture/mcp-tools.md`를 따른다.
YouTube 국내여행 정보 수집과 Gemini 기반 장소 후보 추출 설계는 `docs/architecture/youtube-travel-intelligence.md`를 따른다.
이미지와 첨부 파일 저장은 RustFS 기반 object storage를 사용하며, API 계약은 `docs/api/storage.md`, 운영 절차는 `docs/runbooks/file-storage.md`를 따른다.
Dagster ETL 운영 흐름과 로그/알림 기반은 `docs/runbooks/etl.md`와 `docs/execplan/dagster-etl-migration.md`를 따른다.

## 현재 상태

현재 저장소에는 `apps/web`의 Next.js + Tailwind CSS 웹앱과 `apps/api`의 FastAPI 백엔드 골격이 있다.
관리자 전용 화면은 `/admin/login`, `/admin` 경로에 있으며, ETL로 적재한 테이블을 조회하는 내부 운영 도구이다. 상세는 `docs/runbooks/admin.md`와 `docs/api/admin.md`를 따른다.
로그인 전 공개 화면에서 사용하는 축제/해수욕장 조회 API는 `docs/api/public.md`를 따른다.

```text
apps/web
  app/              # Next.js App Router
  package.json      # 웹앱 스크립트와 의존성
  next.config.ts
  tsconfig.json
  eslint.config.mjs
apps/api
  app/              # FastAPI 앱, route, 설정, DB, model
  alembic/          # migration 환경과 migration 파일
  tests/            # backend test
  pyproject.toml    # backend 의존성과 도구 설정
infra
  docker-compose.yml # Postgres/PostGIS와 Dagster 로컬 스택
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
apps/web            # Next.js + React + TypeScript + Tailwind CSS + PWA
apps/api            # FastAPI + SQLAlchemy 2 + GeoAlchemy2
packages/shared     # 공용 타입, API 계약, 상수
apps/api/app/dagster_etl
                    # Dagster job/schedule 정의
infra               # Docker Compose, Postgres/PostGIS, reverse proxy
scripts             # bootstrap, test, deploy, backup/restore
docs                # 문서, runbook, ADR, 실행 계획
```

## 주요 경계

- 웹앱은 사용자 흐름, 지도 상호작용, Tailwind CSS 기반 화면 스타일링, PWA UX를 담당한다.
- API는 인증, 인가, 여행 도메인 규칙, provider library 직접 호출, Telegram, Gemini 실행 요청을 담당한다.
- 지도 feature 계약, provider 결과 정규화, feature/source/weather/price 저장 schema는 `python-krtour-map`을 기준으로 두고, TripMate는 사용자/여행 제품 DB와 API 조립을 담당한다.
- Postgres/PostGIS는 권위 있는 사용자/여행/장소/공간 데이터를 저장한다.
- Dagster는 공공데이터와 외부 API 데이터를 수집하고 raw/serving 테이블을 갱신한다.
- 외부 provider 원문 응답은 TTL 캐시에만 저장하고, UI와 도메인 로직은 내부 정규화 스키마를 사용한다.
- OpiNet 유가 조회는 `python-opinet-api`의 `opinet` 공개 client를 직접 사용한다. TripMate 쪽 `app.etl.fuel.opinet_source`는 provider model을 DB 저장용 레코드로 옮기는 source 경계만 담당한다.
- KTO TourAPI 조회는 `python-visitkorea-api`의 `KrTourApiClient`, `TourApiHubClient`, typed `related_tour`, pagination helper, `Page.context`를 직접 사용한다. 새 endpoint별 typed model이 부족할 때만 `python-visitkorea-api`에 upstream한다.
- 한국도로공사 OpenAPI 조회는 `python-krex-api`의 `kex_openapi.KexClient`를 직접 사용한다. 부족한 휴게소/교통 endpoint나 typed model은 `python-krex-api`에 upstream한다.
- 기상청 단기/중기/특보 data.go.kr 조회와 DFS 격자 변환은 `python-kma-api`의 `KmaClient`, `DataGoKrClient`, `wgs84_to_kma_grid`, `kma_grid_to_wgs84`, metadata/cache helper를 직접 사용한다. 부족한 endpoint별 typed model이나 pagination 편의 API는 `python-kma-api`에 upstream한다.
- provider별 중간 계층은 만들지 않는다. 반복 수정을 줄여야 할 때는 앱에 우회 계층을 추가하지 않고 해당 라이브러리 공개 인터페이스를 빠르게 안정화한다. adapter/wrapper 증식은 코드 직관성과 유지보수성을 떨어뜨리므로 절대 지양하며, 계약이 바뀐 호출부는 감싸지 않고 관련 코드를 직접 수정한다.
- feature DTO, source role, weather domain/style, fixture replay 같은 중복되기 쉬운 계약은 TripMate 문서에 상세 재정의하지 않고 `python-krtour-map` 쪽 canonical 문서를 링크한다.

## 데이터 원칙

- 사용자 로그인 식별자는 이메일이다.
- 인증은 httpOnly cookie 기반 JWT access/refresh token을 사용한다. Access token 기본 만료는 15분, refresh token 기본 만료는 7일이다.
- DB에는 refresh token 원문이 아니라 hash와 만료 시각만 `sessions`에 저장한다.
- Google/Naver/Kakao 소셜 로그인도 provider token을 앱 세션으로 쓰지 않고, callback 검증 후 기존 `tripmate_access`, `tripmate_refresh` cookie로 수렴시킨다.
- provider 고유 사용자는 `users`에 직접 컬럼으로 넣지 않고 `user_oauth_accounts` 연결 테이블로 관리한다.
- 기존 이메일 계정과 provider 계정은 자동 병합하지 않는다.
- 모든 사용자 소유 리소스는 `user_id` 인가 검사를 통과해야 한다.
- 사용자 권한은 시스템 역할과 여행별 역할을 분리한다. 관리자는 시스템 역할이고, 여행 작성자/참여자는 여행별 멤버십으로 판단한다.
- 초대된 참여자는 `invited` 상태의 사용자로 먼저 생성하고, 첫 로그인 때 비밀번호를 설정한다.
- 장소는 사용자 표시 이름, 좌표, 정규화 주소, 행정구역 코드, provider 참조를 분리해 저장한다.
- Google/Naver/Kakao 원문 전체를 장기 저장 가능한 데이터로 가정하지 않는다.
- 외부 데이터 소스, 캐시 키, 갱신 주기, raw/serving 테이블 정책은 `docs/data-sources.md`를 단일 기준으로 따른다.
- DB에 저장하는 timezone-aware datetime은 KST(`Asia/Seoul`) 기준이다. 앱의 PostgreSQL 세션은 연결 시 `SET TIME ZONE 'Asia/Seoul'`을 실행한다.
- 코드에서 저장용 현재 시각을 만들 때는 KST helper를 사용한다.
- 날씨/유가 화면은 serving 테이블을 우선 조회한다.
- “반경 nkm” 리포트는 엄밀한 원형 거리 계산이 아니라 행정구역 기반 근사일 수 있다.
- Gemini Deep Research는 사용자 개인 API 키 입력 구조로 설계한다. 상세는 `docs/integrations/gemini.md`를 따른다.

## 초기 구현 순서 결정

- 인증: httpOnly cookie 기반 JWT access/refresh token을 사용한다. 이메일 인증은 필수이며 인증 메일은 Resend로 발송한다.
- 소셜 로그인: Google/Naver/Kakao 버튼은 `/login`에만 추가하고, provider OAuth 결과는 `user_oauth_accounts` 연결 뒤 기존 JWT cookie 흐름으로 수렴시킨다.
- 지도: Kakao JavaScript SDK 기반 지도 UI와 지도 클릭 장소 초안을 먼저 구현한다. Kakao Local API 검색은 `docs/data-sources.md`의 저장/캐시 정책과 API 계약을 먼저 확정한 뒤 직접 호출 경계로 추가한다.
- Telegram: DB에는 `telegram_bot_token_ref`만 저장한다. 상세는 `docs/integrations/telegram.md`를 따른다.
- Gemini: 사용자 개인 키를 입력받는다. 상세는 `docs/integrations/gemini.md`를 따른다.

## 공간 데이터 기준선

- 권위 있는 공간 필터링은 PostGIS에서 수행한다.
- 위도/경도 표시는 `lat`, `lng` 이름을 사용한다.
- 행정구역 원천 데이터는 V-WORLD `법정구역정보` SHP를 사용한다.
- 행정구역 raw 레이어는 V-WORLD 원본 EPSG:5179 geometry를 그대로 보존한다.
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

인증 cookie에는 JWT를 담고, DB에는 refresh token hash인 `session_token_hash`만 저장한다.

사용자/여행 도메인의 다음 목표 스키마는 `docs/architecture/user-trip-schema.md`의 설계안을 따른다. 현재 `users`, `sessions`, `trips`, `trip_days`는 최소 구현 상태이므로 Phase 2~3에서 migration으로 확장해야 한다.

## 아직 구현되지 않은 것

- 비밀번호 재설정, Google/Naver/Kakao 소셜 로그인 등 인증 확장
- Kakao 지도 연동
- Telegram 발송
- Gemini Deep Research
- PWA manifest/service worker
- ODROID M1S 배포 스크립트
