# AGENTS.md

## 역할
- 이 파일은 Codex/agent가 항상 읽는 최소 지침이다.
- 세부 규칙은 작업 주제에 맞는 문서와 skill을 필요할 때만 읽는다.
- 루트 기준과 하위 문서가 충돌하면 아래 우선순위를 따른다.

## 지시 우선순위
1. 사용자 요청
2. 이 `AGENTS.md`
3. `/docs` 하위의 관련 설계/운영 문서
4. `/skills` 하위의 관련 skill 문서
5. 기존 코드베이스 규칙
6. 최소한의, 되돌릴 수 있는 가정

## 프로젝트 기준
- TripMate는 대한민국 국내 여행을 일정, 장소, 지도, 지역 데이터, Telegram 알림으로 관리하는 로그인 기반 웹앱이다.
- 해외 데이터, 비회원 모드, 외부 provider 원문 장기 저장은 기본 범위가 아니다.
- 프론트엔드: Next.js, React, TypeScript, Tailwind CSS, PWA, Kakao Map.
- 백엔드/데이터: FastAPI, SQLAlchemy 2, GeoAlchemy2, PostgreSQL/PostGIS, Airflow, Shapely.
- 로컬 개발은 WSL2 Ubuntu 기준이며 프론트엔드 `3001`, 백엔드 `8001`을 쓴다. 배포 포트는 미정이다.

## 핵심 불변 조건
- 로그인 식별자는 이메일이며 인증은 httpOnly cookie 기반 서버 세션으로 시작한다.
- Telegram 알림 대상은 사용자 소유 리소스로 저장하고 여행별 최대 3개만 참조한다.
- Telegram bot token, Gemini API key, 비밀번호 원문은 일반 DB/로그에 저장하지 않는다.
- 장소 추가는 Kakao 검색 결과 선택과 지도 클릭 입력을 모두 지원한다.
- 장소 후보는 Kakao 우선, Naver/Google/일반 검색 확장은 정책 검토 후 진행한다.
- 날씨/유가 리포트는 실시간 API 연타 대신 저장된 지역 데이터와 ETL 캐시를 우선한다.
- “반경 nkm” 리포트는 행정구역 기반 근사일 수 있으며 UI/문서에서 근사라고 밝힌다.
- Gemini Deep Research는 사용자 개인 API 키 입력 구조이고 버튼 기반 수동 실행을 기본으로 한다.

## MCP 상태
- MCP 구현은 TODO로만 유지한다.
- `youtube_place_mcp`와 `address_code_lookup_mcp`는 별도 명시 지시가 있기 전까지 설계/구현/스캐폴딩하지 않는다.
- 관련 판단은 `docs/runbooks/agent-working-rules.md`와 해당 execplan에 남긴다.

## 문서 라우팅
- 공통 작업 규칙: `docs/runbooks/agent-working-rules.md`
- 전체 계획: `docs/execplan/korea-tripmate-implementation-plan.md`
- 아키텍처: `docs/architecture.md`, `docs/decisions/`
- 데이터 소스/저장 정책: `docs/data-sources.md`
- Telegram/Gemini: `docs/integrations/telegram.md`, `docs/integrations/gemini.md`
- 로컬 개발/운영: `docs/runbooks/local-dev.md`, `docs/runbooks/etl.md`
- API 계약: `docs/api/*.md`

## Skill 라우팅
- 테스트/QA: `skills/testing-and-qa.ko.md`
- 코딩 스타일/타입 안정성: `skills/coding-style.ko.md`
- DB/마이그레이션: `skills/database-architect.ko.md`
- 문서/ADR: `skills/documentation-and-adrs.ko.md`
- 데이터 정책: `skills/data-policy.ko.md`
- 공간/PostGIS: `skills/geospatial-postgis.ko.md`
- Airflow/ETL: `skills/airflow-etl.ko.md`
- 배포/ODROID: `skills/deployment-wsl2-odroid.ko.md`

## 작업 원칙
- 단순 작업이 아니면 영향 범위, 관련 문서/skill, API/DB/도메인/실패 동작, 테스트를 먼저 확인한다.
- 여러 파일, 마이그레이션, 서비스 경계를 건드리면 `docs/execplan/<task-name>.md`를 작성 또는 갱신한다.
- 의미 있는 변경은 테스트와 문서 갱신을 포함하고, 실행한 검사 명령과 환경(WSL2/Windows)을 보고한다.
- 유사한 실수가 반복되면 원인과 재발방지 기준을 관련 문서/runbook/skill에 남긴다.
- Docker, Compose, PostgreSQL/PostGIS, Airflow, backend test, Alembic 검증은 WSL2에서 실행한다.
- WSL2 테스트/검증은 NTFS 경로(`/mnt/f/dev/mapplan`)에서 직접 실행하지 않고 WSL 내부 볼륨의 미러(`~/tripmate-workspaces/mapplan`)에서 실행한다.
- 테스트/검증 명령 전에는 현재 프로젝트 디렉토리의 변경을 WSL 미러로 동기화하고, 명령이 끝날 때마다 WSL 미러의 변경을 현재 프로젝트 디렉토리로 다시 복사한다.
- Windows PowerShell로 한국어 문서를 읽을 때는 깨짐 방지를 위해 `Get-Content -Encoding UTF8` 또는 동등한 UTF-8 명시 옵션을 사용한다.
- 보안/인증/DB/공간/Airflow/Telegram/외부 API/PWA/Gemini 변경은 관련 문서와 모듈 경계를 먼저 읽는다.
- 제품 의사결정이 저장소에서 추론 불가능할 때만 멈추고 묻고, 그 외에는 안전한 가정을 문서에 남긴다.
