# AGENTS.md

## 프로젝트 개요

이 저장소는 대한민국 전용 여행 계획 웹앱을 개발한다. 제품 방향은 구글 내지도와 TREK와 유사하되, 국내 여행 계획·장소 관리·지도 UX·알림 기능을 더 강화하는 것이다.

기술 스택:

- 프론트엔드: Next.js + React + TypeScript + PWA
- 지도: Kakao Map (`react-kakao-maps-sdk`)
- 백엔드: FastAPI + SQLAlchemy 2 + GeoAlchemy2 + PostgreSQL + PostGIS
- 데이터 파이프라인: Apache Airflow
- 공간/데이터 처리: Shapely
- 실행 환경: Docker on Ubuntu 24.04
- 로컬 개발: WSL2
- 배포 대상: ODROID M1S (SSH 접속 배포)

개발 단계:

1. 사용자 인증/관리, 여행 계획 CRUD, Airflow 기반 데이터 수집, Telegram 알림
2. 지도 UX 고도화, 사용자 정의 마커, 주변 정보 제공
3. 예산/물품 관리 등 고급 여행 계획 기능 확장

지리적 범위는 **대한민국 한정**이다. 별도 지시가 없는 한 해외 데이터를 설계 범위에 포함하지 않는다.

## 지시 우선순위

다음 순서로 따른다:

1. 사용자 요청
2. 이 `AGENTS.md`
3. `/docs` 하위의 관련 설계/운영 문서
4. `/skills` 하위의 관련 skill 문서
5. 기존 코드베이스 규칙
6. 최소한의, 되돌릴 수 있는 가정

이 우선순위와 충돌하는 요구를 임의로 만들지 않는다.

## 핵심 제품 불변 조건

- 비회원 사용은 지원하지 않는다.
- 사용자 로그인 식별자는 이메일이다.
- 인증은 httpOnly cookie 기반 서버 세션으로 시작한다.
- 여행별 Telegram 알림 대상은 최대 3개까지 지원한다.
- Telegram 대상은 사용자 소유 리소스로 분리 저장하고, 여행은 이를 참조한다.
- Telegram bot token 원문은 DB에 평문 저장하지 않는다.
- 장소 추가는 검색 결과 선택 또는 지도 클릭 기반 입력을 모두 지원한다.
- 장소 후보는 Kakao를 우선하고, Naver/Google/일반 검색 조합은 정책 검토 후 확장한다.
- 외부 provider 원문 전체를 장기 저장하지 않는다.
- 날씨/유가 리포트는 실시간 외부 API 연타가 아니라 저장된 지역 데이터와 ETL 캐시를 우선 사용한다.
- “반경 nkm” 리포트는 엄밀한 원형 거리 계산이 아니라, 반경 근처와 겹치는 행정구역 기반 근사 로직일 수 있다. 문서와 UI에서 이를 정확히 표현한다.
- Gemini Deep Research는 사용자 개인 API 키 입력 구조이며, 키 원문은 일반 DB/로그에 저장하지 않는다.

## 상세 문서 라우팅

작업 주제에 따라 아래 문서를 먼저 확인한다.

- 전체 실행 계획: `docs/execplan/korea-tripmate-implementation-plan.md`
- 아키텍처 기준선: `docs/architecture.md`
- 데이터 소스와 저장 정책의 단일 기준: `docs/data-sources.md`
- Telegram 상세 설계: `docs/integrations/telegram.md`
- Gemini 상세 설계: `docs/integrations/gemini.md`
- 로컬 개발: `docs/runbooks/local-dev.md`
- 아키텍처 결정: `docs/decisions/`

작업 주제에 따라 아래 skill을 사용한다.

- 테스트/QA: `skills/testing-and-qa.ko.md`
- 문서화/ADR: `skills/documentation-and-adrs.ko.md`
- 데이터 정책 적용: `skills/data-policy.ko.md`
- 공간/PostGIS: `skills/geospatial-postgis.ko.md`
- Airflow/ETL: `skills/airflow-etl.ko.md`
- 배포/ODROID: `skills/deployment-wsl2-odroid.ko.md`

## Codex 작업 기본 절차

단순한 작업이 아니라면 아래 순서로 진행한다:

1. 요청과 영향 범위를 파악한다.
2. 수정 대상 파일과 관련 문서/skill을 먼저 읽는다.
3. 여러 파일, 마이그레이션, 서비스 경계를 건드리면 `docs/execplan/<task-name>.md` 실행 계획 문서를 작성 또는 갱신한다.
4. 구현 전에 가능한 한 API 스키마, DB 스키마, 도메인 모델, 실패 동작, 테스트 케이스를 명확히 한다.
5. 가장 작은 일관된 변경 단위로 구현한다.
6. 테스트를 추가하거나 갱신한다.
7. 좁은 범위의 검사부터 실행하고, 이후 더 넓은 범위의 검사로 확장한다.
8. 문서와 운영 노트를 갱신한다.
9. 최종 요약에는 무엇을 바꿨는지, 무엇을 테스트했는지, 어떤 위험/미완료 사항이 남았는지 포함한다.

사용자가 명시적으로 생략을 지시하지 않는 한, 테스트와 문서화를 빼지 않는다.

## 코딩 전 영향 확인

다음 중 하나라도 관련되면 해당 문서/skill과 모듈 경계를 먼저 읽는다:

- 인증/보안
- DB 스키마/마이그레이션
- 공간 질의 / 지도 로직
- Airflow 파이프라인
- Telegram 발송
- 외부 API 쿼터/캐시
- PWA / 모바일 UX
- Gemini / 사용자 API 키

## 엔지니어링 기준

- 프론트엔드는 TypeScript를 사용한다. 정당한 이유 없이는 `any`를 쓰지 않는다.
- 백엔드는 Python 타입 힌트를 작성한다.
- FastAPI 라우터는 얇게 유지하고, 실제 규칙은 서비스 계층으로 이동한다.
- React 컴포넌트에 비즈니스 로직을 과도하게 넣지 않는다.
- 외부 API 연동은 adapter/gateway 계층 뒤에 둔다.
- 반복 ETL/API 작업에는 캐시와 멱등성을 설계한다.
- 숨은 전역 상태를 피한다.
- 공간 로직은 SRID, 좌표 순서, 단위 변환, polygon/point 처리 규칙을 명시한다.
- 외부 API가 많은 기능은 retry, backoff, timeout, quota 보호, stale-cache fallback을 기본 설계에 포함한다.

## 도메인 기준

### 인증 및 사용자 관리

- 표준적인 비밀번호 해시와 세션 전략을 사용한다.
- 평문 비밀번호, Telegram token, Gemini API key를 저장하지 않는다.
- 이메일 중복을 허용하지 않는다.
- 사용자 정보 수정은 항상 인가 검사를 거친다.

### 여행 계획

- `trip`, `trip_day`, `place`를 분리된 도메인 개념으로 다룬다.
- 하루 내 장소 순서를 보존한다.
- 표시 이름은 외부 제공자 이름과 별개로 사용자가 수정 가능해야 한다.
- provider 메타데이터는 추적 및 재조회용 참조만 남기고, 원문은 `docs/data-sources.md` 정책을 따른다.

### 외부 데이터

- 모든 외부 데이터셋 및 OpenAPI 사용은 `docs/data-sources.md`를 단일 기준 문서로 따른다.
- 새로운 외부 데이터 소스를 도입할 경우 구현 전에 `docs/data-sources.md`를 먼저 업데이트한다.
- 데이터 구조, Airflow DAG, adapter, 캐시 정책, 테스트는 `docs/data-sources.md`와 동기화되어야 한다.
- 데이터 저장 정책이나 약관이 불명확한 경우 최소 저장 원칙을 적용하고 제한 사항을 문서에 명시한다.

### 공간 데이터

- 권위 있는 공간 필터링은 PostGIS를 우선 사용한다.
- 행정구역 원천 SHP는 raw EPSG:5186으로 보존하고, serving 레이어는 EPSG:4326 변환본을 둔다.
- 웹 지도 출력과 API 응답은 EPSG:4326을 사용한다.
- 행정구역 기반 근사 로직을 정확한 radius 검색이라고 쓰지 않는다.

### Telegram

- 상세 설계는 `docs/integrations/telegram.md`를 따른다.
- 여행별 대상 3개 제한을 도메인과 UI 모두에서 강제한다.
- 대상 검증은 `sendMessage` 또는 `getChat` 기반으로 수행한다.
- 발송 실패 시 `chat_id 없음`, `bot 권한 없음`, `topic 잘못됨` 등 조치 가능한 원인을 구분한다.

### Gemini Deep Research

- 상세 설계는 `docs/integrations/gemini.md`를 따른다.
- 버튼 기반 수동 실행과 선택적 재실행을 기본으로 한다.
- Gemini 생성 결과와 확인된 원천 데이터를 분리 표시한다.
- prompt, model, 실행 시각, 입력 컨텍스트 요약, 결과 요약, 출처 목록, 에러 상태를 기록한다.

## 테스트 정책

의미 있는 변경은 항상 적절한 수준의 테스트를 포함해야 한다.

백엔드:

- 도메인/서비스 로직 unit test
- API + DB integration test
- geospatial test
- ETL parser/cache/idempotency test
- Telegram 메시지/중복 제거 test

프론트엔드:

- UI 로직 component test
- 폼 흐름과 목록/상세 상호작용 integration test
- 핵심 사용자 흐름 Playwright E2E

필수 Playwright 최소 범위:

- 로그인
- 사용자 정보 수정
- 여행 생성/수정/삭제
- 검색으로 장소 추가
- 지도 클릭으로 장소 추가
- 날짜별 마커 색상과 리스트 동기화
- Telegram 설정 저장
- 모바일 viewport 기준 PWA smoke

CI 기대치:

- lint
- typecheck
- unit tests
- integration tests
- Playwright smoke 또는 관련 E2E

실행한 명령을 적지 않고 성공했다고 주장하지 않는다.

## 문서화 정책

기능, 구조, 운영 동작, 데이터 출처, 배포 방식이 바뀌면 문서도 함께 바뀌어야 한다.

관련 시 항상 갱신:

- `README.md`: 설치/실행/로컬 개발 변화
- `docs/architecture.md`: 구조 변화
- `docs/api/*.md`: 엔드포인트/계약 변화
- `docs/data-sources.md`: 외부 API / 공공데이터 / 캐시 정책 변화
- `docs/integrations/*.md`: 외부 서비스 연동 상세 변화
- `docs/runbooks/*.md`: 배포, ETL, 장애 대응, 복구, 운영 변화
- `docs/decisions/`: 아키텍처 결정과 trade-off

문서는 현재 실제로 존재하는 상태, 예제, 명령어, 파일 경로, 가정과 한계를 기록한다. 근사 동작이면 근사라고 직접 쓴다.

## 권장 저장소 구조

기존 저장소가 크게 다르지 않다면 아래 구조를 유지한다:

- `apps/web/` - Next.js 프론트엔드
- `apps/api/` - FastAPI 백엔드
- `dags/` - Airflow DAG
- `packages/shared/` - 공용 타입/스키마/상수
- `infra/` - docker, reverse proxy, deployment, compose
- `scripts/` - bootstrap, test, deploy, backup 등 헬퍼
- `tests/` - unit, integration, e2e
- `docs/` - architecture, data-sources, integrations, runbooks, decisions, execplan
- `skills/` - 프로젝트 작업 skill

## 선호 명령어

실제 저장소와 다를 수 있으므로 먼저 확인한 뒤 사용한다.

현재 프론트엔드:

- install: `npm install`
- dev: `npm run dev`
- lint: `npm run lint`
- typecheck: `npm run typecheck`
- build: `npm run build`

백엔드:

- install: `uv sync` 또는 저장소 표준 명령
- dev: `uv run uvicorn app.main:app --reload`
- lint: `uv run ruff check .`
- format check: `uv run ruff format --check .`
- typecheck: `uv run mypy .`
- test: `uv run pytest`

Airflow / infra:

- 로컬 스택: `docker compose up -d`
- 로그: `docker compose logs --tail=200`
- DB migrate: 저장소의 마이그레이션 명령 사용
- deploy: `scripts/` 하위의 체크인된 스크립트를 우선 사용

명령이 존재하는지 확인하지 않고 가정하지 않는다.

## 마이그레이션 규칙

DB 스키마가 바뀌면 migration 추가, upgrade 검증, downgrade 영향 고려, seed/test fixture 갱신 필요 여부 확인, destructive/backfill 동작 문서화를 함께 수행한다.

애플리케이션 시작 시점에 몰래 스키마를 바꾸지 않는다.

## 보안 및 비밀정보

- 환경변수 또는 secret store만 사용한다.
- 토큰, 비밀번호, API 키, SSH endpoint, bot credential을 하드코딩하지 않는다.
- 로그/문서/테스트에서 비밀값을 가린다.
- DB와 외부 서비스 자격 증명은 최소 권한 원칙을 따른다.

## 배포 기대치

- 로컬 개발은 WSL2 + Docker에서 수행한다.
- 배포 대상은 SSH로 접속 가능한 ODROID M1S이다.
- 아래 스크립트를 우선 고려한다:
  - `scripts/bootstrap-local.sh`
  - `scripts/test-local.sh`
  - `scripts/deploy.sh`
  - `scripts/backup-db.sh`
  - `scripts/restore-db.sh`
- 배포 설정이 바뀌면 runbook과 rollback 절차를 같이 갱신한다.
- 웹 DB 관리 도구는 인증을 갖춘 컨테이너형 도구로 제공하되, 외부 공개를 기본값으로 두지 않는다.

## 완료 정의

아래가 해당되면 모두 만족해야 완료다:

- 구현 완료
- 테스트 추가/갱신 완료
- 관련 검사 실행 완료
- 문서 갱신 완료
- 설정/환경변수 변경 사항 문서화 완료
- 운영 영향 기록 완료
- 위험/한계 명시 완료

## 멈추고 물어봐야 하는 경우

아래처럼 진짜 제품 의사결정이 막힐 때만 사용자에게 묻는다:

- 저장소에서 추론 불가능한 인증 모델 선택
- 공급자간 충돌하는 단일 진실원 선택
- 제3자 데이터 사용의 법률/정책 판단
- 배포 대상 또는 시크릿 소유권이 모호한 경우

그 외에는 가장 안전한 가정을 하고 문서에 남긴다.
