# decisions.md — ADR (Architecture Decision Records)

이 문서는 `TripMate`의 누적 ADR이다. 결정이 뒤집힐 때도 이전 기록은 지우지 않고
`superseded by ADR-XXX`로 표시한다. 각 ADR은 PR과 함께 커밋되어 코드/문서/결정이
동기된다.

`python-krtour-map`의 ADR과 충돌·연계가 있으면 양쪽 ADR이 서로 참조한다.

## ADR-001: v1은 `v1` 브랜치 보존, main은 v2로 재시작

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: v1은 9개월 운영하면서 FastAPI 백엔드, Next.js 프론트, Dagster
  ETL, Admin 콘솔, 다수의 provider 어댑터, 광범위한 docs를 축적했지만 다음
  문제가 누적되었다:
  - 지도 feature 도메인이 `apps/api` 안에 직접 박혀 있어 책임이 흐림.
  - provider raw → DTO 변환이 `apps/api/app/etl/<provider>/`에 산재.
  - WSL/NTFS 작업 흐름이 ext4 직접 작업본 vs WSL 미러로 두 번 바뀜.
  - skill/runbook/decisions 사이의 일관성이 흐려짐.
- **결정**: 현재 main의 모든 commit을 `v1` 브랜치에 보존하고, main은 같은 시점에서
  분기 후 대량 삭제 + v2 골격 신규 작성으로 다시 시작한다.
  - 지도 feature 도메인은 별 저장소 `python-krtour-map`으로 완전 분리한다
    (`python-krtour-map`의 ADR-001 mirror).
  - TripMate ↔ `python-krtour-map`은 함수 직접 호출 (`python-krtour-map` ADR-003).
  - v1의 개별 자산(예: 인증 라우트, Admin 콘솔, Resend 통합)은 v2에서 한 건씩
    ADR로 결정하고 가져온다.
- **근거**:
  - 책임 경계(TripMate vs `python-krtour-map`)를 처음부터 명확히 박는다.
  - v1 코드를 완전히 폐기하지 않음 — `v1` 브랜치 + git history로 복구 가능.
  - 새 에이전트가 main만 봐도 v2 의도가 명확.
- **결과 (긍정)**:
  - 의존 계층, 책임 경계, 작업 흐름을 처음부터 일관되게 박을 수 있다.
  - v1의 부분 폐기/유지 결정을 ADR로 명시적으로 박는다.
- **결과 (부정)**:
  - main의 워킹트리에는 직전 9개월 코드가 보이지 않는다 (`v1` 브랜치 참고 필요).
  - 일부 v1 코드를 v2에 가져올 때 cherry-pick 대신 재작성이 필요.
- **후속**:
  - `v1` 브랜치 origin push 완료 (T-000).
  - v2 골격(README/AGENTS/CLAUDE/SKILL + docs/) 작성 (본 PR).
  - Sprint 1 진입 PR에서 `apps/` scaffolding 박음.

## ADR-002: TripMate ↔ `python-krtour-map`은 함수 직접 호출 (REST 없음)

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자
- **컨텍스트**: 지도 feature 도메인을 별 저장소로 분리하기로 했다(ADR-001).
  TripMate가 그 라이브러리를 어떻게 호출할지 결정 필요. 선택지:
  - (A) HTTP 마이크로서비스로 띄우고 REST 호출
  - (B) 같은 venv에 `pip install`해서 함수 직접 호출
- **결정**: (B) `pip install` + 함수 직접 호출. `python-krtour-map` ADR-003 mirror.
- **근거**:
  - 두 코드베이스가 같은 운영 환경(Odroid 단일 노드)에서 동작 → HTTP overhead 무의미.
  - 직렬화/역직렬화 비용 없음 — Pydantic DTO 직접 전달.
  - DB connection pool/transaction 공유 가능.
- **결과 (긍정)**: 운영 단순화 + 성능 향상 + 디버깅 용이 + 타입 안전성.
- **결과 (부정)**: 라이브러리 변경 시 TripMate 재배포 필요 (단일 venv).
- **후속**:
  - `python-krtour-map` 의존은 `apps/api/pyproject.toml`에 git URL pin (`@<sha>`).
  - 라이브러리는 자체 client/engine을 생성하지 않고 모두 TripMate에서 주입.
  - 사용 패턴은 `docs/krtour-map-integration.md`.

## ADR-003: `feature` / `provider_sync` schema는 `python-krtour-map`이 소유

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: 같은 PostgreSQL 데이터베이스(`tripmate`)에 두 저장소가 schema를
  나누어 가질 때 DDL/migration 책임을 어디에 두는지 결정 필요.
- **결정**:
  - `feature`, `provider_sync` schema의 DDL + Alembic migration은 `python-krtour-map`
    이 소유.
  - `app`, `ops` schema는 TripMate가 소유.
  - `x_extension` schema는 운영자가 수동 부트스트랩 (PostGIS / pg_trgm / pgcrypto).
- **근거**:
  - 책임이 한 저장소에 몰리지 않게 분산.
  - Feature 스키마 변경은 라이브러리 PR에서 마이그레이션과 함께 박힌다 — 라이브러리
    버전 핀이 곧 schema 호환성 핀.
- **결과 (긍정)**: schema 책임이 명확. TripMate가 라이브러리 schema에 함부로 손대지
  못한다.
- **결과 (부정)**:
  - 두 Alembic을 따로 돌려야 한다. 운영 절차에 추가 단계.
  - schema 간 외래키 참조 시 alembic dependency 순서를 잘 정해야 한다.
- **후속**:
  - 운영 절차에 `python-krtour-map alembic upgrade head` → `tripmate alembic
    upgrade head` 순서 박음.
  - `docs/postgres-schema.md`에 `app` schema만 기록. `feature` / `provider_sync`는
    그쪽 저장소의 `docs/postgres-schema.md`를 참조.

## ADR-004: WSL ext4 미러 단일 모델 (ext4 직접 작업본 vs export 모델 폐기)

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: v1 운영 중에 작업 모델이 두 번 흔들렸다:
  - 모델 A — WSL ext4 직접 작업본 (`~/dev/tripmate`)과 NTFS export
    (`/mnt/f/dev/tripmate`)
  - 모델 B — NTFS 직접 작업 + WSL 미러 테스트
  v1의 마지막 상태(codex/wsl-test-mirror-docs)는 모델 B로 정렬되어 있다.
- **결정**: **모델 B (WSL 미러)**를 v2의 표준으로 박는다.
  - 작업 디렉토리는 NTFS (`F:\dev\tripmate`) — 사용자의 일상 작업 위치.
  - WSL2 미러 (`~/tripmate-workspaces/tripmate`) — `git`/`pytest`/`docker`/`npm`
    등 실행 위치.
  - 명령 전후로 rsync로 양방향 동기.
- **근거**:
  - 사용자가 NTFS에서 IDE/탐색기를 자연스럽게 사용한다.
  - WSL2 ext4가 inotify/I/O 성능 + 파일 권한에 안전.
  - "직접 작업본" 모델은 NTFS의 변경을 ext4로 가져오는 흐름이 모호 — "미러" 모델은
    rsync 한 방향만 보면 된다.
- **결과 (긍정)**: 작업 흐름이 단순. NTFS는 view, ext4 미러는 작업.
- **결과 (부정)**: rsync 단계가 명령 전후로 필요. 누락 시 stale state.
- **후속**:
  - `docs/dev-environment.md`에 rsync 절차 박음.
  - `AGENTS.md` "개발 환경 정책" 갱신.
  - PowerShell `rg.exe` 금지, WSL `rg` 강제.

## ADR-005: provider raw → DTO 변환은 `python-krtour-map`에 위임 (TripMate 어댑터 제거)

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: v1에는 `apps/api/app/etl/<provider>/sources.py`, `loaders.py`,
  `opinet_source.py` 등 provider raw → 내부 모델 변환이 직접 박혀 있었다.
- **결정**: v2에서는 그 책임을 모두 `python-krtour-map.providers`로 이전한다.
  TripMate에는 `KrtourMapGateway` / `KrtourMapAdapter` 같은 wrapper class를 두지
  않는다 (`python-krtour-map` ADR-006 mirror).
- **근거**:
  - 같은 provider에 대해 두 곳에서 변환 로직을 유지하지 않는다.
  - dedup / source_link / feature_id 정책이 라이브러리에 일관되게 박혀 있다.
  - 라이브러리 단위 테스트가 fixture 기반으로 가능.
- **결과 (긍정)**: TripMate `apps/api`의 코드량 감소. provider 추가 시 작업 위치가
  하나.
- **결과 (부정)**: 새 provider는 라이브러리에 PR을 먼저 보내야 함. 두 단계 PR.
- **후속**:
  - Dagster asset 코드 (`apps/etl/assets/<name>.py`)는 얇은 어댑터로만 — provider
    client 주입 + `AsyncKrtourMapClient` 호출 + 로깅.
  - v1의 provider 어댑터 코드는 cherry-pick하지 않는다 — 라이브러리 ADR-006 후속
    으로 재작성.

## ADR-006: Dagster code location 분리 (`apps/etl` 독립)

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: v1은 `apps/api/app/dagster_etl/`에 asset/job/schedule이 있었다.
  Dagster 데몬과 FastAPI 프로세스가 같은 코드 위치를 공유했다.
- **결정**: v2에서는 Dagster code location을 `apps/etl/`로 분리한다. FastAPI는
  Dagster 코드를 import하지 않는다.
- **근거**:
  - Dagster 데몬 재시작이 FastAPI 재시작과 결합되지 않는다.
  - `apps/etl`의 의존성(`dagster`, `dagit`)이 `apps/api`의 venv에 들어가지 않는다.
  - Dagster code location 표준 패턴.
- **결과 (긍정)**: 분리된 venv + 별도 컨테이너 + 재시작 독립.
- **결과 (부정)**: 두 venv 유지 — `apps/api`와 `apps/etl` 모두 `python-krtour-map`
  의존성을 갖는다.
- **후속**:
  - `infra/docker-compose.yml`에 `dagster` 서비스 정의.
  - `apps/etl/pyproject.toml` 신설 (코드 작성 단계).
  - schedule/sensor는 `apps/etl/definitions.py`에 등록.

## ADR-007: PR-only workflow + main branch protection

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자
- **컨텍스트**: v1은 일부 직접 push와 일부 PR이 섞여 있었다. 운영자/에이전트가
  실수로 main에 push하는 경우가 발생.
- **결정**: 모든 변경은 feature branch + PR. main 직접 push 금지. GitHub branch
  protection으로 서버에서도 거부.
- **근거**:
  - 단일 작성자라도 PR 페이지에서 한 번 더 변경 확인.
  - 자동 status check(lint, test, import-linter, openapi drift)를 강제할 수 있다.
  - `python-krtour-map`과 동일 패턴(ADR-021).
- **결과 (긍정)**: 회귀 방지 + 자동 게이트 + 일관된 워크플로.
- **결과 (부정)**: 작은 docs 변경도 PR을 거쳐야 한다 — 약간의 오버헤드.
- **후속**:
  - 운영자가 GitHub branch protection 설정 (Require PR, Require approvals,
    Require status checks).
  - `docs/agent-guide.md` §8에 PR 워크플로 박힘.

## ADR-008: Postgres extension은 `x_extension` schema에 분리

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: PostGIS / pg_trgm / pgcrypto를 `public`에 설치하면 dump/restore,
  schema 비교, 권한 부여에서 혼선이 생긴다. `python-krtour-map`은 ADR-008로
  `x_extension`을 채택했다.
- **결정**: TripMate도 동일하게 `x_extension` schema를 사용한다.
- **근거**:
  - `feature`/`provider_sync`/`app`/`ops` schema가 깨끗하게 비즈니스 데이터만 가진다.
  - search_path를 `public, x_extension`으로 두면 호출 측 코드 변경 없음.
- **결과 (긍정)**: 운영 schema dump가 깨끗. 권한 관리 단순.
- **결과 (부정)**: 첫 부트스트랩 시 `CREATE EXTENSION ... SCHEMA x_extension` 한 줄
  추가.
- **후속**:
  - `docs/dev-environment.md` §5에 부트스트랩 SQL 박음.
  - `apps/api/app/core/config.py`의 connect_args에 `search_path` 설정 박음
    (코드 작성 단계).

## ADR-009: 한국어 문서 정책 + 코드 식별자 영문 유지

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자
- **컨텍스트**: v1 문서는 한국어 중심이지만 일부 영문이 섞여 일관성이 흐려졌다.
- **결정**:
  - 모든 Markdown 문서는 한국어 산문.
  - 코드 식별자 / API 필드명 / 명령 / URL / 환경변수 / 라이브러리·provider 영어
    이름은 그대로 보존.
  - 새 문서는 기존 문서와 동일 규칙을 우선.
- **근거**:
  - 도메인 어휘(법정동, 시군구, 공공API)가 한국어 중심.
  - 외부 식별자를 한글로 번역하면 검색·grep가 불가능.
- **결과 (긍정)**: 일관성 + 가독성.
- **결과 (부정)**: 일부 영어권 협업자에게 진입 장벽 — 다만 본 저장소는 한국 도메인
  특화.
- **후속**: AGENTS.md "문서 언어 정책"에 박힘.

## ADR-010: SPEC V8 6편 채택 + 책임 분담 정정 반영

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: 외부에서 제공된 "여행 계획 서비스 SW 개발 명세서 V8" 6부작
  (`spec_v8_0_infrastructure` ~ `spec_v8_5_execution`)이 v1 시점에 작성되어
  `python-krtour-map` 분리 이전의 단일 모노레포 가정을 일부 포함한다. 다만
  원본의 후속 메모(M~R, 2026-05-16 ~ 2026-05-20)에는 이미 같은 책임 분리
  결정이 들어 있다. v2 골격 작성 후 본 SPEC을 어떻게 반영할지 결정 필요.
- **결정**:
  - SPEC V8 6편을 TripMate v2의 작업 기준으로 채택한다.
  - 본 저장소에 `docs/spec/v8/` 디렉토리 신설 후 6편 적용 노트 작성 — 원본의
    의도를 v2 책임 분담(ADR-001/002/003)으로 재정리한다.
  - 단일 모노레포 가정 부분(예: `feature.features` schema가 TripMate 안에 있다는
    문장)은 후속 메모와 ADR-003에 따라 `python-krtour-map`이 소유하는 것으로
    재해석. 원본을 수정하지 않고 본 저장소의 적용 노트에서 정리.
  - SPEC V8의 Sprint 1~6 계획(P장)을 본 저장소의 `docs/sprints/SPRINT-*.md`로
    가져온다. Sprint 3(Admin)이 Sprint 4(지도)보다 앞이라는 원본 결정 유지.
  - SPEC V8 N-7.2의 "WSL ext4 직접 작업본 + NTFS export" 모델은 ADR-004의 "WSL
    미러 단일 모델"로 정정 (v1 운영 중 발견한 양방향 동기 모호함 해소).
  - 16색 마커 팔레트(I-6)와 Airbnb 디자인 reference(`DESIGN.md` /
    `airbnb-marker-palette.html`)를 v1에서 가져와 `docs/design/`에 박는다.
- **근거**:
  - SPEC V8은 v1 시점의 작성이지만 도메인 정의/API/Admin/Sprint 계획이 매우
    구체적 — v2가 이를 모두 새로 작성할 필요 없다.
  - 원본의 후속 메모가 이미 책임 분리를 반영 — 추가 큰 결정 없이 적용 가능.
  - python-krtour-map과 정합 유지를 위해 본 저장소도 같은 분리 원칙을 박는다.
- **결과 (긍정)**:
  - Sprint 1~6 계획이 즉시 가용 — 별도 plan 작성 비용 없음.
  - API 명세 + DB schema 골격이 명확.
  - 위치정보법 / PIPA 컴플라이언스 항목이 명시됨.
- **결과 (부정)**:
  - SPEC V8의 일부 도메인 모델 문장이 책임 분리 이전 표현으로 남아 있어 본
    저장소 적용 노트가 cross-reference로 정리해야 한다.
  - 원본의 docx는 외부 저장소에 두고 본 저장소는 적용 노트만 가짐 — 원본
    갱신 시 동기 비용.
- **후속**:
  - `docs/spec/v8/{README, 00-infrastructure, 01-data, 02-backend, 03-frontend,
    04-admin, 05-execution}.md` 신규 작성 (본 PR).
  - `docs/sprints/SPRINT-{2,3,4,5,6}.md` 신규 작성 (본 PR).
  - `docs/design/marker-palette.md` 신규 + 저장소 루트 `DESIGN.md` /
    `airbnb-marker-palette.html` 복원 (본 PR).
  - `docs/data-model.md`, `docs/postgres-schema.md`, `docs/architecture.md`,
    `docs/krtour-map-integration.md` 갱신 — SPEC V8 후속 메모와 정합.
  - 원본 docx는 운영자가 `refdocs/` 또는 외부에 보관. 본 저장소 git에는
    포함하지 않음.

## ADR-011: Frontend 스택 + Next.js / Expo 공용 패키지 구조

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: SPEC V8은 Next.js 15 + Zustand + TanStack Query + RHF + Zod +
  dnd-kit + Tailwind를 권장하지만 (1) UI 컴포넌트 라이브러리(shadcn/ui 등)
  미지정, (2) 디자인 톤(Airbnb DESIGN.md / airbnb-marker-palette.html)과의 결합
  방식 미지정, (3) 추후 Expo 모바일 앱 추가 가능성 미반영. 사용자가 (a) 스택
  상세 (shadcn/ui 포함) 명시, (b) DESIGN.md / 팔레트 톤·UX 따름 명시, (c)
  Next.js / Expo 공용 코드(주요 로직 + 데이터 정의) 구조 명시, (d) Expo 프론트
  구성 명시를 요청.
- **결정**:
  - 웹: Next.js 15 + React 19 + **shadcn/ui** + Tailwind + Zustand + TanStack
    Query v5 + React Hook Form + Zod + dnd-kit + react-kakao-maps-sdk
  - 모바일 (v2): Expo SDK 53+ + Expo Router + NativeWind (Tailwind for RN) +
    동일 Zustand / TanStack Query / RHF + Zod (공용)
  - 디자인 톤: 본 저장소 루트 `DESIGN.md` + `airbnb-marker-palette.html`을
    v1.0의 단일 기준으로 사용 (TripMate 자체 브랜드 확정 시 ADR로 교체)
  - 공용 코드 위치: `packages/{schemas,api-client,state,design-tokens,hooks,i18n}`
    — Zod schema / 데이터 정의 / API 클라이언트 / 상태 store / 디자인 토큰 /
    공용 hook / 메시지 카탈로그를 모든 앱이 import
  - 플랫폼 어댑터 패턴: 스토리지(localStorage/AsyncStorage), 위치(navigator/
    expo-location), 지도(kakao-maps-sdk/react-native-maps) 등은 `apps/*/lib/`에
    두고, 공용 코드는 어댑터를 함수 인자로 받음
  - `packages/*`에서 DOM / Node / next/* / react-native/* import 금지
    (ESLint `no-restricted-imports`)
- **근거**:
  - shadcn/ui는 Tailwind 기반 vendoring 모델 — DESIGN.md의 Airbnb 톤을 컴포넌트
    레벨에서 customizing하기 적합 (vendored copy를 직접 수정 가능)
  - 공용 패키지를 처음부터 박으면 Expo 추가 시 큰 재작성 없이 점진 전환 가능
  - Zod schema가 단일 진실 — API 응답 파싱 / 폼 validator / 타입 정의 한 곳
  - SPEC V8 C-4 (v2/장기) "푸시 알림 → Web Push API"를 앞당겨 실제 모바일 앱
    까지의 경로를 v1.0 단계부터 박음
- **결과 (긍정)**:
  - 디자인 톤이 명시적 — 진입 에이전트가 추측하지 않음
  - 공용 패키지가 v1.0에 박혀 있어 Expo 추가 시 비용 적음
  - 스택이 사용자 요구와 일치 (React/Next.js/TanStack Query/Zod/Zustand/RHF/
    shadcn/ui/Tailwind)
- **결과 (부정)**:
  - 모노레포 패키지 관리 비용 — npm workspaces / TypeScript project references
  - v1.0 단계에서는 `packages/*`가 부분적으로만 사용 — 의도된 over-engineering
- **후속**:
  - `docs/architecture/frontend.md` 신규 (본 PR)
  - `docs/design/marker-palette.md`에 P-01~P-16 박힘
  - Sprint 1에 `packages/*` skeleton 등록
  - Sprint 1~2에 공용 schema / api-client / state 활성화
  - Expo `apps/mobile`은 v1.0 출시 후 별도 Sprint M-1 (Mobile)에서 추가

## ADR-012: 사용자 위치 정보 획득 — Geolocation + expo-location + 공용 hook

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: SPEC V8은 위치정보법(O-1 LBS 신고, O-2 4 분리 동의, O-3 감사
  로그 chain)을 명시하지만 클라이언트 측 위치 획득 메커니즘이 구체적이지 않음.
  사용자가 "프론트엔드 웹/앱에서 사용자 위치 정보를 얻어옴을 기능 사양에 명시"
  요청.
- **결정**:
  - 웹: `navigator.geolocation` (HTTPS 필수, Secure Context)
  - 모바일: `expo-location` (foreground only, v1.0 — background는 v2 후보)
  - 공용 hook: `packages/hooks/src/useUserLocation.ts` — `LocationAdapter`를
    인자로 받는 추상화. 웹/모바일이 각자의 어댑터를 주입
  - 동의: `app.user_consents.consent_type = 'location_collection'` (G-5의 4
    필수 동의 중 하나)
  - 권한 prompt: 사용자 명시 액션 (지도 진입 / "내 위치" 버튼) 후에만 호출
  - 좌표 서버 전송 시 `app.location_access_log` content_hash chain 자동 적재
    (`location_audit` 미들웨어)
  - fallback chain: 동의 X → UI 비활성 / 권한 거부 → viewport 중심점 → 거주
    시군구 → 서울 시청
  - 좌표 정밀도 제한: 6자리 → UI 표시는 4자리 (~10m)까지
  - 좌표는 일반 로그(Loki / Sentry)에 적재하지 않고 `location_access_log`에만
  - CPO 권한만 `location_access_log` SELECT
- **근거**:
  - 위치정보법 / PIPA 위반 시 형사 처벌 + 매출 3% (최대 10%) 과징금
  - audit chain (prev_hash + content_hash)으로 변조 검증
  - 공용 hook으로 웹/모바일 동일 사용 패턴 → 추후 코드 중복 회피
- **결과 (긍정)**: 컴플라이언스 정합 + Expo 추가 시 위치 코드 재사용
- **결과 (부정)**: 클라이언트마다 어댑터를 구현해야 함 (cost는 1회성)
- **후속**: `docs/architecture/user-location.md` 신규. Sprint 2 진입 시
  `useUserLocation` 활성화 + `location_audit` 미들웨어 박음.

## ADR-013: Notice plan (추천 여행) 도메인 v1에서 v2로 이전 + "notice" 명명 분리

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: v1 (`v1` 브랜치 마지막)에 9개월 운영한 추천 여행 plan 도메인이
  존재:
  - `notice_plans` (Admin이 작성한 추천 여행)
  - `notice_pois` (해당 plan의 POI)
  - `plan_poi_attachments` (단일 테이블 4 대상 — trip / trip_poi / notice_plan /
    notice_poi 첨부)
  - `POST /notice-plans/{id}/copy` (사용자 trip으로 복사)
  - `docs/architecture/plan-poi-attachments.md`
  사용자가 "v1에서 notice poi 관련 문서/코드 확인해서 보강할 것" 요청. 또한
  같은 단어 "notice"가 두 개의 별개 개념에 쓰여 혼동:
  1. **notice feature** — 지도 위 공지/자연현상 (SPEC V8 D-10, kind=notice,
     `python-krtour-map` 소유)
  2. **notice plan** — Admin이 작성한 추천 여행 plan (TripMate `app` schema)
- **결정**:
  - v1의 추천 여행 plan 도메인을 v2로 가져온다. 본 저장소 `app` schema에
    `app.notice_plans` + `app.notice_pois` + `app.plan_poi_attachments` 도입.
  - **v1 코드를 cherry-pick하지 않고 본 저장소의 schema 정합성 + SPEC V8 E-6
    (COLLATE "C") + import-linter 계약에 맞춰 재작성**한다.
  - 명명 정정: "notice plan" (TripMate 도메인) vs "notice feature" (라이브러리
    도메인) — 모든 신규 문서에서 두 개념을 명시적으로 구분.
  - v1 컬럼 `position INT` (trip_pois)는 v2의 `sort_order TEXT COLLATE "C"`로
    교체 (SPEC V8 E-6 Critical).
  - v1의 `map_feature_id UUID` 컬럼은 v2에서 제거 후보 (라이브러리 `feature_id
    TEXT`만 reference).
  - 단일 테이블 4 대상 모델은 v1과 동일하게 유지 (`num_nonnulls(...) = 1`
    CHECK).
  - RustFS 설정은 v1 환경변수 패턴 그대로 유지.
- **근거**:
  - v1에서 사용자 가시 동작이 안정적 — 운영 검증된 도메인
  - 코드 재작성이 cherry-pick보다 schema 정합성 안전
  - 명명 분리로 향후 혼동 비용 절감 (notice feature와 직관적으로 구분)
- **결과 (긍정)**: v1 자산의 가치 보존 + v2 schema 정합
- **결과 (부정)**: v1 → v2 재작성 비용 (Sprint 2에서 박음)
- **후속**:
  - `docs/architecture/notice-plans.md` 신규 (본 PR)
  - `docs/data-model.md` § (Trip / POI 다음에) notice plan 도메인 추가
  - Sprint 2 Alembic `0007_notice_plans.py` + `0008_plan_poi_attachments.py`
  - Sprint 4에 사용자 listing + copy 다이얼로그 UI
  - Sprint 6에 Admin notice plan 작성기 UI

## 다음 ADR 번호

- 다음 신규 ADR = **ADR-014**
- 사용자 정의 결정이 새로 발생하면 본 §끝에 추가.
