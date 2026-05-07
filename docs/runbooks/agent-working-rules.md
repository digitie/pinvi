# 에이전트 작업 규칙

이 문서는 `AGENTS.md`에서 분리한 세부 작업 기준이다. 루트 파일은 항상 읽고, 이 문서는 작업이 해당 주제에 닿을 때만 읽는다.

## 프로젝트 개요

TripMate는 대한민국 전용 여행 계획 웹앱이다. 제품 방향은 구글 내지도와 TREK와 유사하되, 국내 여행 계획, 장소 관리, 지도 UX, 알림 기능을 강화한다.

개발 단계:

1. 사용자 인증/관리, 여행 계획 CRUD, Airflow 기반 데이터 수집, Telegram 알림
2. 지도 UX 고도화, 사용자 정의 마커, 주변 정보 제공
3. 예산/물품 관리 등 고급 여행 계획 기능 확장

지리적 범위는 대한민국 한정이다. 별도 지시가 없는 한 해외 데이터를 설계 범위에 포함하지 않는다.

## Codex 작업 절차

단순한 작업이 아니라면 아래 순서로 진행한다.

1. 요청과 영향 범위를 파악한다.
2. 수정 대상 파일과 관련 문서/skill을 먼저 읽는다.
3. 여러 파일, 마이그레이션, 서비스 경계를 건드리면 `docs/execplan/<task-name>.md` 실행 계획 문서를 작성 또는 갱신한다.
4. 구현 전에 가능한 한 API 스키마, DB 스키마, 도메인 모델, 실패 동작, 테스트 케이스를 명확히 한다.
5. 가장 작은 일관된 변경 단위로 구현한다.
6. 테스트를 추가하거나 갱신한다.
7. 좁은 범위의 검사부터 실행하고, 이후 더 넓은 범위의 검사로 확장한다.
8. 문서와 운영 노트를 갱신한다.
9. 최종 요약에는 변경 내용, 실행한 테스트, 남은 위험/미완료 사항을 포함한다.

사용자가 명시적으로 생략을 지시하지 않는 한, 테스트와 문서화를 빼지 않는다.

## 반복 실수 재발방지

- 같은 종류의 실수, 누락, 오해가 반복되면 단순히 이번 변경만 고치지 않고 재발방지 문서화를 함께 수행한다.
- 문서에는 무엇이 반복됐는지, 왜 기존 지침으로 막지 못했는지, 다음 작업자가 어떤 체크를 해야 하는지 적는다.
- 적용 위치는 영향 범위에 맞춘다. 상시 규칙이면 `AGENTS.md` 또는 이 문서, 특정 영역이면 관련 `docs/runbooks/`, `docs/architecture/`, `docs/data-sources/`, `skills/*.ko.md`에 남긴다.
- 코드 동작 변경이 아니라 작업 방식 보완이면 테스트 대신 링크/검색으로 문서 반영 여부를 확인한다.

## 로컬 실행 환경

- 저장소에서 실행하는 명령은 WSL2 Ubuntu를 최우선 실행 환경으로 한다.
- Docker, Docker Compose, PostgreSQL/PostGIS, Airflow, backend test, Alembic migration 검증은 반드시 WSL2 Ubuntu에서 실행한다.
- Windows PowerShell은 WSL2 명령을 감싸서 실행하거나, 파일 확인, 간단한 Git 상태 확인, 문서 읽기 같은 보조 작업에만 사용한다.
- Windows PowerShell로 한국어 문서나 skill을 읽을 때는 기본 인코딩을 가정하지 말고 `Get-Content -Encoding UTF8 -Path ...`처럼 UTF-8을 명시한다. 한글이 깨져 보이면 내용을 근거로 판단하지 말고 UTF-8로 다시 읽은 뒤 작업한다.
- Docker 관련 명령을 Windows PowerShell에서 직접 실행하지 않는다.
- 테스트 결과를 보고할 때는 Windows에서 실행했는지 WSL2에서 실행했는지 함께 구분한다.
- WSL2 경로는 현재 저장소 기준 `/mnt/f/dev/mapplan`을 기본으로 사용한다.

예시:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -f infra/docker-compose.yml up -d"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/python -m pytest"
```

PowerShell에서 문서 확인 예시:

```powershell
Get-Content -Encoding UTF8 -Path 'F:\dev\mapplan\docs\runbooks\agent-working-rules.md'
Get-Content -Encoding UTF8 -Path 'F:\dev\mapplan\skills\documentation-and-adrs.ko.md'
```

## 코딩 전 영향 확인

다음 중 하나라도 관련되면 해당 문서/skill과 모듈 경계를 먼저 읽는다.

- 인증/보안
- DB 스키마/마이그레이션
- 공간 질의 / 지도 로직
- Airflow 파이프라인
- Telegram 발송
- 외부 API 쿼터/캐시
- PWA / 모바일 UX
- Gemini / 사용자 API 키
- MCP 후보 기능

## 엔지니어링 기준

- 프론트엔드는 TypeScript를 사용한다. 정당한 이유 없이는 `any`를 쓰지 않는다.
- 웹페이지 스타일링은 Tailwind CSS 기반으로 작성한다.
- 백엔드는 Python 타입 힌트를 작성한다.
- 타입 안정성은 구현 완료 조건에 포함한다.
- 외부 API 응답, DB row, JSONB, 관리자 데이터 브라우저처럼 런타임 shape가 동적인 값은 `unknown`/`object` 경계에서 parser, Pydantic model, `TypedDict`, JSON value 타입으로 좁힌 뒤 사용한다.
- `Any`, TypeScript `as` 캐스팅, Python `cast`/`type: ignore`는 불가피한 라이브러리 경계에만 좁게 사용하고, 도메인 서비스 public return type이나 React state type으로 퍼뜨리지 않는다.
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
- V-WORLD 행정구역 원천 SHP는 raw EPSG:5179로 보존하고, serving 레이어는 EPSG:4326 변환본을 둔다.
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

### MCP 후보 기능

- `youtube_place_mcp`와 `address_code_lookup_mcp`는 TODO 후보로만 둔다.
- 별도의 사용자 지시가 있기 전까지 MCP 설계, 구현, 스캐폴딩, 의존성 추가, 테스트 추가를 하지 않는다.
- MCP 구현 착수 지시가 내려지면 먼저 `docs/data-sources.md`, 관련 execplan, 보안/비밀정보 정책, 저장 가능한 원문 범위를 갱신한 뒤 진행한다.
- YouTube 장소 분석 MCP의 입력 범위와 저장 가능 원문 범위, 주소 코드 조회 MCP의 대상 DB 범위는 구현 착수 시점의 별도 제품 의사결정으로 남긴다.

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

모든 프로젝트 문서는 한국어로 작성한다. 문서 제목, 설명 문장, 실행 계획, runbook, ADR은 한국어를 기본으로 한다. 코드 식별자, 테이블명, 컬럼명, 명령어, API endpoint, provider 고유 명칭처럼 원문 보존이 필요한 기술 용어만 영어를 허용한다.

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

실제 저장소와 다를 수 있으므로 먼저 확인한 뒤 사용한다. 명령 예시는 특별한 이유가 없으면 WSL2 경로(`/mnt/f/dev/mapplan`)와 `wsl.exe -e bash -lc "..."` 형태를 우선한다.

현재 프론트엔드:

- install: WSL2에서 `cd /mnt/f/dev/mapplan && npm install`
- dev: WSL2에서 `cd /mnt/f/dev/mapplan && npm run dev`
- lint: WSL2에서 `cd /mnt/f/dev/mapplan && npm run lint`
- typecheck: WSL2에서 `cd /mnt/f/dev/mapplan && npm run typecheck`
- build: WSL2에서 `cd /mnt/f/dev/mapplan && npm run build`

백엔드:

- install: WSL2에서 `cd /mnt/f/dev/mapplan/apps/api && uv sync` 또는 저장소 표준 명령
- dev: WSL2에서 `uv run uvicorn app.main:app --reload`
- lint: WSL2에서 `uv run ruff check .`
- format check: WSL2에서 `uv run ruff format --check .`
- typecheck: WSL2에서 `uv run mypy .`
- test: WSL2에서 `uv run pytest`

Airflow / infra:

- 로컬 스택: WSL2에서 `docker compose up -d`
- 로그: WSL2에서 `docker compose logs --tail=200`
- DB migrate: WSL2에서 저장소의 마이그레이션 명령 사용
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
- 아래 스크립트를 우선 고려한다.
  - `scripts/bootstrap-local.sh`
  - `scripts/test-local.sh`
  - `scripts/deploy.sh`
  - `scripts/backup-db.sh`
  - `scripts/restore-db.sh`
- 배포 설정이 바뀌면 runbook과 rollback 절차를 같이 갱신한다.
- 웹 DB 관리 도구는 인증을 갖춘 컨테이너형 도구로 제공하되, 외부 공개를 기본값으로 두지 않는다.

## 완료 정의

아래가 해당되면 모두 만족해야 완료다.

- 구현 완료
- 테스트 추가/갱신 완료
- 관련 검사 실행 완료
- 문서 갱신 완료
- 설정/환경변수 변경 사항 문서화 완료
- 운영 영향 기록 완료
- 위험/한계 명시 완료

## 멈추고 물어봐야 하는 경우

아래처럼 진짜 제품 의사결정이 막힐 때만 사용자에게 묻는다.

- 저장소에서 추론 불가능한 인증 모델 선택
- 공급자간 충돌하는 단일 진실원 선택
- 제3자 데이터 사용의 법률/정책 판단
- 배포 대상 또는 시크릿 소유권이 모호한 경우
- MCP 구현 착수 시점과 저장 가능한 원문 범위를 결정해야 하는 경우

그 외에는 가장 안전한 가정을 하고 문서에 남긴다.
