# decisions.md — ADR (Architecture Decision Records)

이 문서는 `Pinvi`의 누적 ADR이다. 결정이 뒤집힐 때도 이전 기록은 지우지 않고
`superseded by ADR-XXX`로 표시한다. 각 ADR은 PR과 함께 커밋되어 코드/문서/결정이
동기된다.

`kor-travel-map`의 ADR과 충돌·연계가 있으면 양쪽 ADR이 서로 참조한다.

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
  - 지도 feature 도메인은 별 저장소 `kor-travel-map`으로 완전 분리한다
    (`kor-travel-map`의 ADR-001 mirror).
  - Pinvi ↔ `kor-travel-map`은 함수 직접 호출 (`kor-travel-map` ADR-003).
  - v1의 개별 자산(예: 인증 라우트, Admin 콘솔, Resend 통합)은 v2에서 한 건씩
    ADR로 결정하고 가져온다.
- **근거**:
  - 책임 경계(Pinvi vs `kor-travel-map`)를 처음부터 명확히 박는다.
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

## ADR-002: Pinvi ↔ `kor-travel-map`은 함수 직접 호출 (REST 없음)

- **상태**: superseded by ADR-026
- **날짜**: 2026-05-25
- **결정자**: 사용자
- **컨텍스트**: 지도 feature 도메인을 별 저장소로 분리하기로 했다(ADR-001).
  Pinvi가 그 라이브러리를 어떻게 호출할지 결정 필요. 선택지:
  - (A) HTTP 마이크로서비스로 띄우고 REST 호출
  - (B) 같은 venv에 `pip install`해서 함수 직접 호출
- **결정**: (B) `pip install` + 함수 직접 호출. `kor-travel-map` ADR-003 mirror.
- **근거**:
  - 두 코드베이스가 같은 운영 환경(Odroid 단일 노드)에서 동작 → HTTP overhead 무의미.
  - 직렬화/역직렬화 비용 없음 — Pydantic DTO 직접 전달.
  - DB connection pool/transaction 공유 가능.
- **결과 (긍정)**: 운영 단순화 + 성능 향상 + 디버깅 용이 + 타입 안전성.
- **결과 (부정)**: 라이브러리 변경 시 Pinvi 재배포 필요 (단일 venv).
- **후속**:
  - `kor-travel-map` 의존은 `apps/api/pyproject.toml`에 git URL pin (`@<sha>`).
  - 라이브러리는 자체 client/engine을 생성하지 않고 모두 Pinvi에서 주입.
  - 사용 패턴은 `docs/kor-travel-map-integration.md`.

## ADR-003: `feature` / `provider_sync` schema는 `kor-travel-map`이 소유

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: 같은 PostgreSQL 데이터베이스(`pinvi`)에 두 저장소가 schema를
  나누어 가질 때 DDL/migration 책임을 어디에 두는지 결정 필요.
- **결정**:
  - `feature`, `provider_sync` schema의 DDL + Alembic migration은 `kor-travel-map`
    이 소유.
  - `app`, `ops` schema는 Pinvi가 소유.
  - `x_extension` schema는 운영자가 수동 부트스트랩 (PostGIS / pg_trgm / pgcrypto).
- **근거**:
  - 책임이 한 저장소에 몰리지 않게 분산.
  - Feature 스키마 변경은 라이브러리 PR에서 마이그레이션과 함께 박힌다 — 라이브러리
    버전 핀이 곧 schema 호환성 핀.
- **결과 (긍정)**: schema 책임이 명확. Pinvi가 라이브러리 schema에 함부로 손대지
  못한다.
- **결과 (부정)**:
  - 두 Alembic을 따로 돌려야 한다. 운영 절차에 추가 단계.
  - schema 간 외래키 참조 시 alembic dependency 순서를 잘 정해야 한다.
- **후속**:
  - 운영 절차에 `kor-travel-map alembic upgrade head` → `pinvi alembic
    upgrade head` 순서 박음.
  - `docs/postgres-schema.md`에 `app` schema만 기록. `feature` / `provider_sync`는
    그쪽 저장소의 `docs/postgres-schema.md`를 참조.

## ADR-004: WSL ext4 미러 단일 모델 (ext4 직접 작업본 vs export 모델 폐기)

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: v1 운영 중에 작업 모델이 두 번 흔들렸다:
  - 모델 A — WSL ext4 직접 작업본 (`~/dev/pinvi`)과 NTFS export
    (`/mnt/f/dev/pinvi`)
  - 모델 B — NTFS 직접 작업 + WSL 미러 테스트
  v1의 마지막 상태(codex/wsl-test-mirror-docs)는 모델 B로 정렬되어 있다.
- **결정**: **모델 B (WSL 미러)**를 v2의 표준으로 박는다.
  - 작업 디렉토리는 NTFS (`F:\dev\pinvi`) — 사용자의 일상 작업 위치.
  - WSL2 미러 (`~/pinvi-workspaces/pinvi`) — `git`/`pytest`/`docker`/`npm`
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

## ADR-005: provider raw → DTO 변환은 `kor-travel-map`에 위임 (Pinvi 어댑터 제거)

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: v1에는 `apps/api/app/etl/<provider>/sources.py`, `loaders.py`,
  `opinet_source.py` 등 provider raw → 내부 모델 변환이 직접 박혀 있었다.
- **결정**: v2에서는 그 책임을 모두 `kor-travel-map.providers`로 이전한다.
  Pinvi에는 `KorTravelMapGateway` / `KorTravelMapAdapter` 같은 wrapper class를 두지
  않는다 (`kor-travel-map` ADR-006 mirror).
- **근거**:
  - 같은 provider에 대해 두 곳에서 변환 로직을 유지하지 않는다.
  - dedup / source_link / feature_id 정책이 라이브러리에 일관되게 박혀 있다.
  - 라이브러리 단위 테스트가 fixture 기반으로 가능.
- **결과 (긍정)**: Pinvi `apps/api`의 코드량 감소. provider 추가 시 작업 위치가
  하나.
- **결과 (부정)**: 새 provider는 라이브러리에 PR을 먼저 보내야 함. 두 단계 PR.
- **후속**:
  - Dagster asset 코드 (`apps/etl/assets/<name>.py`)는 얇은 어댑터로만 — provider
    client 주입 + `AsyncKorTravelMapClient` 호출 + 로깅.
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
- **결과 (부정)**: 두 venv 유지 — `apps/api`와 `apps/etl` 모두 `kor-travel-map`
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
  - `kor-travel-map`과 동일 패턴(ADR-021).
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
  schema 비교, 권한 부여에서 혼선이 생긴다. `kor-travel-map`은 ADR-008로
  `x_extension`을 채택했다.
- **결정**: Pinvi도 동일하게 `x_extension` schema를 사용한다.
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
  `kor-travel-map` 분리 이전의 단일 모노레포 가정을 일부 포함한다. 다만
  원본의 후속 메모(M~R, 2026-05-16 ~ 2026-05-20)에는 이미 같은 책임 분리
  결정이 들어 있다. v2 골격 작성 후 본 SPEC을 어떻게 반영할지 결정 필요.
- **결정**:
  - SPEC V8 6편을 Pinvi v2의 작업 기준으로 채택한다.
  - 본 저장소에 `docs/spec/v8/` 디렉토리 신설 후 6편 적용 노트 작성 — 원본의
    의도를 v2 책임 분담(ADR-001/002/003)으로 재정리한다.
  - 단일 모노레포 가정 부분(예: `feature.features` schema가 Pinvi 안에 있다는
    문장)은 후속 메모와 ADR-003에 따라 `kor-travel-map`이 소유하는 것으로
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
  - kor-travel-map과 정합 유지를 위해 본 저장소도 같은 분리 원칙을 박는다.
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
    `docs/kor-travel-map-integration.md` 갱신 — SPEC V8 후속 메모와 정합.
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
  - 모바일 (v2): Expo SDK 56+ + Expo Router + NativeWind (Tailwind for RN) +
    동일 Zustand / TanStack Query / RHF + Zod (공용)
  - 디자인 톤: 본 저장소 루트 `DESIGN.md` + `airbnb-marker-palette.html`을
    v1.0의 단일 기준으로 사용 (Pinvi 자체 브랜드 확정 시 ADR로 교체)
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
  - **2026-06-06 보정**: 아래 v1 명칭(`notice_plans`, `notice_pois`,
    `plan_poi_attachments`)은 ADR-029가 DB/ORM 정본을 `curated_trip_plans`,
    `curated_plan_pois`, `curated_plan_attachments`로 개명하면서 supersede했다.
    `/notice-plans` API 경로와 `notice_plan_id` 응답 필드는 Sprint 4 호환 alias로
    유지한다.
  사용자가 "v1에서 notice poi 관련 문서/코드 확인해서 보강할 것" 요청. 또한
  같은 단어 "notice"가 두 개의 별개 개념에 쓰여 혼동:
  1. **notice feature** — 지도 위 공지/자연현상 (SPEC V8 D-10, kind=notice,
     `kor-travel-map` 소유)
  2. **notice plan** — Admin이 작성한 추천 여행 plan (Pinvi `app` schema)
- **결정**:
  - v1의 추천 여행 plan 도메인을 v2로 가져온다. 초기 도입 이름은
    `app.notice_plans` + `app.notice_pois` + `app.plan_poi_attachments`였으나,
    ADR-029 이후 DB/ORM 정본은 `app.curated_trip_plans` +
    `app.curated_plan_pois` + `app.curated_plan_attachments`다.
  - **v1 코드를 cherry-pick하지 않고 본 저장소의 schema 정합성 + SPEC V8 E-6
    (COLLATE "C") + import-linter 계약에 맞춰 재작성**한다.
  - 명명 정정: "notice plan" (Pinvi 도메인) vs "notice feature" (라이브러리
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
  - `docs/data-model.md` § (Trip / POI 다음에) curated trip plan 도메인 추가
  - Sprint 2 Alembic `20260602_0005_notice_plans_and_attachments.py` +
    T-137 rename migration `20260607_0011_curated_trip_plans.py`
  - Sprint 4에 사용자 listing + copy 다이얼로그 UI
  - Sprint 6에 Admin notice plan 작성기 UI

## ADR-014: v1 자산 전수 조사 + 누락 항목 일괄 반영 + 문서 일관성 정리

- **상태**: accepted
- **날짜**: 2026-05-25
- **결정자**: 사용자 + Claude
- **컨텍스트**: v2 골격 작성 후 v1의 9개월 운영 자산 (docs 50+ / apps/api / apps/web /
  scripts / config / skills 등)이 v2에 부분적으로만 반영됨. 사용자가 "v1 코드와
  문서를 전반적으로 확인해서 v2에 반영할 수 있는 부분 중 아직 안된 것은 일단
  빠짐없이 반영하고 그 후 문서의 일관성, 문서간 충돌여부를 확인해서 정리. 또한
  AI Agent가 작업할 수 있도록 문서의 상세함과 명확함을 보완"을 요청.
- **결정**:
  1. v1 자산 전수 조사 → `docs/v1-to-v2-mapping.md` 매핑 매트릭스 작성
  2. 누락된 영역을 본 PR로 일괄 신규 작성:
     - `docs/api/` 11개 (README/common/auth/users/trips/pois/features/notice-plans/storage/admin/public/regions/health/websocket)
     - `docs/integrations/` 9개 (README/resend/social-login/gemini/telegram/kakao-map/sentry/loki)
     - `docs/runbooks/` 7개 (README/local-dev/docker-app/etl/admin/file-storage/odroid-docker)
     - `docs/compliance/` 4개 (README/lbs-act/pipa/data-policy)
     - `docs/conventions/` 6개 (README/coding-style/database/testing/geospatial/normalization)
     - `docs/architecture/` 5개 추가 (map-marker-design/youtube-travel-intelligence/mcp-tools/dagster-etl-bridge/api-contract)
     - `docs/data-sources/README.md` 인덱스 + cross-ref
  3. ADR-005 / ADR-001 / ADR-004 일관성 점검 — 모든 신규 문서가 책임 분담 (Pinvi
     vs `kor-travel-map`) 명시
  4. AI agent 진입 절차 강화 — `AGENTS.md` + `CLAUDE.md`에 작업 종류별 진입 문서표
  5. 명명 일관성: `pyXyz` 짧은 alias 사용 금지 → `python-xyz-api` canonical
- **근거**:
  - v1의 9개월 운영 노하우를 v2로 가져오지 않으면 같은 결정을 반복
  - AI agent가 본 저장소 단일 진입점에서 모든 도메인 작업을 시작할 수 있어야 함
  - 문서 일관성 결여는 책임 분담 (Pinvi vs 라이브러리) 오인의 가장 큰 원인
- **결과 (긍정)**:
  - AI agent가 한 PR에서 작업 진입에 필요한 모든 문서를 찾을 수 있음
  - v1 자산 (특히 notice_plans / plan_poi_attachments / oauth flow / Resend
    템플릿 / Telegram target / RustFS shared / Sentry PII 마스킹)이 명문화됨
  - 컴플라이언스 (LBS / PIPA) 박힘 — Sprint 6 출시 직전 체크 가능
- **결과 (부정)**:
  - 본 PR 문서량 큼 (~30 신규 파일) — review 비용 증가
  - 일부 문서는 design-only (구현 placeholder) — 코드 작성 단계에서 추가 갱신 필요
- **후속**:
  - 본 PR 머지 후 Sprint 1 진입 PR (`apps/{api,web,etl}` + `packages/*`
    scaffolding) 작성
  - Sprint별 진입 시 본 문서 디테일을 코드에 맞춰 검증
  - `docs/v1-to-v2-mapping.md`를 살아 있는 문서로 유지 — 새 v1 자산 발견 또는
    v2 작업 진행 시 상태 갱신
  - `docs/conventions/{coding-style,database,testing}.md`을 PR 템플릿에 cross-ref
  - 추후 메이저 변경 시 본 ADR superseded 처리

## ADR-015: 지도 클라이언트 변경 — Kakao Maps SDK → `maplibre-vworld-js`

- **상태**: accepted (ADR-011 frontend 스택의 지도 항목 정정 — SPEC V8 A-1 #4
  채택 superseded)
- **날짜**: 2026-05-26
- **결정자**: 사용자
- **컨텍스트**: SPEC V8 A-1 #4 + ADR-011은 `react-kakao-maps-sdk`를 채택했지만,
  사용자가 내부 라이브러리 `maplibre-vworld-js` (Antigravity 2.0 + Gemini 3.1
  Pro로 만든 VWorld + MapLibre GL JS 선언형 React 통합)를 이미 보유하고 있어
  지도 클라이언트를 전환.
- **결정**:
  - 지도 SDK를 `maplibre-vworld-js`로 변경
  - 환경변수 `NEXT_PUBLIC_KAKAO_MAP_APP_KEY` / `KAKAO_REST_API_KEY` 제거 →
    `NEXT_PUBLIC_VWORLD_API_KEY`만 사용
  - `apps/web/lib/coordAdapter.ts` (`(lat, lng)` 변환 어댑터) 제거 — VWorld는
    `(lng, lat)` GeoJSON 순서를 따르므로 Pinvi stack과 일관
  - 라이브러리는 git URL pin 또는 npm 배포로 `apps/web`이 직접 import
  - Pinvi에 wrapper class 만들지 않음 (ADR-005 mirror) — 부족 기능은
    `maplibre-vworld-js` 저장소에 PR
  - 라이브러리에 있는 `PlaceMarker` / `PriceMarker` / `WeatherMarker` /
    `ClusterLayer` (이전 `MarkerClusterer`) / `PolygonArea` / `RouteLine` /
    `Popup` (이전 `MapPopup`) generic primitive 직접 사용
  - 16색 팔레트 (P-01 ~ P-16) hex 값을 라이브러리 마커 컴포넌트에 props로 전달
  - **Pinvi 도메인 wrapper (`PinviFeatureLayer`)와 팔레트 상수
    (`PINVI_MARKER_PALETTE` / `PINVI_CATEGORY_MARKERS` /
    `resolvePinviMarkerStyle`)는 라이브러리에 두지 않고 `apps/web/lib`에서
    직접 구현** — 라이브러리는 generic primitive에 한정
- **근거**:
  - 좌표 순서 일관 — `(lng, lat)` 전체 stack
  - 선언형 React — `useEffect`로 명령형 호출 불필요
  - 마커 / 클러스터 / Popup / Polygon / RouteLine generic primitive 라이브러리에 내장 (Pinvi 도메인 매핑은 `apps/web/lib`에서 어댑터)
  - VWorld는 국토교통부 공식 — 위탁자 명시 간소 (국내)
  - 카카오맵 SDK 오프라인 캐싱 약관 제약 회피 (PWA v2 후보 활성화)
  - 같은 진영 (Antigravity / 내부 자산) — wrapper 추가 없이 직접 의존 가능
- **결과 (긍정)**:
  - 좌표 어댑터 제거 → 코드 단순화
  - WebGL GPU 렌더링 (60fps fractional zoom)
  - 16색 + Maki 통합 더 자연스러움
  - 사용 / 보강 권한이 Pinvi 측에 있음 (내부 라이브러리)
- **결과 (부정)**:
  - Kakao Local 검색이 빠짐 — `/search` 구현은 `kor-travel-map`의 검색
    함수로 대체 (또는 라이브러리 추가)
  - Kakao 모빌리티 길찾기가 빠짐 — Sprint 6 일정 최적화는 OR-Tools 직선 거리 +
    라이브러리 PR로 대응
  - VWorld 일 호출 한도 + 도메인 화이트리스트는 새로 학습 필요
- **후속**:
  - `docs/integrations/maplibre-vworld.md` 신규 (본 PR)
  - `docs/integrations/kakao-map.md` 폐기 표시 (본 PR)
  - `docs/architecture/frontend.md` / `map-marker-design.md` / `user-location.md`
    / `api/features.md` / `api/common.md` / `spec/v8/{00,03,05}.md` /
    `sprints/SPRINT-{1,4}.md` / `runbooks/docker-app.md` /
    `compliance/{data-policy,pipa}.md` / `conventions/geospatial.md` /
    `integrations/{sentry,loki}.md` 모두 본 PR로 갱신
  - 라이브러리 부족 기능은 `docs/integrations/maplibre-vworld.md` §6에 카탈로그
    유지 → 발견 시 `maplibre-vworld-js` 저장소에 PR

## ADR-016: AI 에이전트 도구 다중 지원 — `AGENTS.md` ↔ `CLAUDE.md` 동기 정책

- **상태**: accepted
- **날짜**: 2026-05-26
- **결정자**: 사용자
- **컨텍스트**: 본 저장소는 Claude Code 외에 OpenAI Codex / Google Antigravity /
  Cursor / Copilot 등 여러 AI 코딩 도구로도 작업한다. Claude는 `CLAUDE.md`를
  1차 진입으로 보지만 Codex / Antigravity는 `AGENTS.md`를 1차로 본다. 한 쪽만
  갱신하면 도구별로 다른 결정·식별자가 반영되어 fact drift 발생.
- **결정**:
  - 본 저장소의 진입 가이드는 두 파일 (`AGENTS.md` + `CLAUDE.md`)이 **항상 같은
    결정·룰·식별자를 반영**한다.
  - 한 파일 갱신 시 다른 파일도 같은 PR 내에서 동기 갱신 — `docs/agent-guide.md`
    §7.1 PR 체크리스트에 항목 추가.
  - 도구별 1차 진입:
    - **Claude Code / Claude Agent SDK** — `CLAUDE.md` → `AGENTS.md` → `SKILL.md`
    - **OpenAI Codex (CLI)** — `AGENTS.md` → `SKILL.md`
    - **Google Antigravity (Gemini)** — `AGENTS.md` → `SKILL.md`
    - **Cursor / Copilot** — `AGENTS.md` + `SKILL.md`
  - `SKILL.md`는 도메인 어휘 / DO NOT 카탈로그로 공통 — 두 진입 파일이 모두
    참조.
  - `CLAUDE.md` 첫 줄에 "다른 AI 도구 호환성" 안내 박힘.
  - `AGENTS.md` 진입 절차 첫 섹션에 도구별 1차 진입 표 박힘.
  - 사용자 / 다른 도구가 `.codex/agents/<role>.md` 같은 별도 파일을 두면 본
    저장소의 `AGENTS.md`에 위임하는 1쪽 stub만 둔다 (v1에서 했던 것처럼 별도
    rule 전체를 옮기지 않는다).
- **근거**:
  - 도구 다양화는 막을 수 없음 — Pinvi 자체도 Antigravity로 만든
    `maplibre-vworld-js` (ADR-015)를 사용
  - fact drift는 운영 사고의 흔한 원인 (특히 식별자 / 환경변수 / 정책 충돌)
  - 두 파일 동기는 PR 리뷰 시점에 자연스럽게 강제 가능
- **결과 (긍정)**:
  - 도구 변경 시 새 가이드 작성 비용 없음 — 기존 파일이 모두 호환
  - PR 체크리스트로 동기 강제 — drift 가능성 낮음
- **결과 (부정)**:
  - PR마다 두 파일 함께 갱신해야 함 — 약간의 오버헤드
  - `CLAUDE.md` 1쪽 분량 유지하면서 `AGENTS.md` 본문과 일치해야 — 요약 갱신
    누락 시 drift
- **후속**:
  - `AGENTS.md` 머리에 "AI 에이전트 도구 지원 — `AGENTS.md` 단일 진실" 섹션 박음
  - `CLAUDE.md` 머리에 호환성 안내 박음
  - `SKILL.md` 진입 안내에 도구별 표 박음
  - `docs/agent-guide.md` 머리에 동기 룰 박음 + §7.1 체크리스트
  - 향후 도구 추가 시 본 ADR superseded 또는 항목 추가

## ADR-017: CodeGraph 인덱스 + agent별 고정 worktree 운영

- **상태**: accepted
- **날짜**: 2026-05-26
- **amendment (2026-05-27)**: worktree 이름 prefix `geo-` → `pinvi-` 변경
  (`geo-claude` → `pinvi-claude` 등). 사용자 지시. 경로 예시도 `F:/dev/pinvi-<agent>`.
  실제 worktree 디렉터리는 `git worktree move`로 rename.
- **amendment (2026-05-31)**: Windows worktree(NTFS, 예: `F:/dev/pinvi-claude`)에서
  git 명령은 **Windows 버전 git (`git.exe`)** 으로 실행한다 (사용자 지시). WSL git으로
  `/mnt/f/...` NTFS 경로를 조작하지 않는다 — 권한·I/O 성능·CRLF 변환 문제. pytest /
  docker / npm 등 나머지 실행은 ADR-004대로 WSL ext4 미러를 유지한다 (git만 예외).
  `.codegraph/`는 본 ADR 후속(`.gitignore`)에 이미 반영됨.
- **결정자**: 사용자
- **컨텍스트**: AGENTS.md / CLAUDE.md 동기 정책 (ADR-016)으로 Claude Code / OpenAI
  Codex / Google Antigravity 2.0 + Gemini 3.1 Pro 세 도구가 본 저장소를 동시에
  편집한다. 도구마다 별도 worktree를 쓰지 않으면 (1) 같은 디렉터리에 두 도구가
  체크아웃 충돌, (2) `.next` / `.venv` / IDE 캐시 / 인덱스가 서로 덮어쓰기,
  (3) AI 도구마다 작업 흐름·체크아웃 상태가 불투명해진다. 동시에 `colbymchenry/
  codegraph`는 SQLite 기반 코드 지식 그래프로 Claude Code의 grep / Read fan-out
  비용을 ~35% / 70% 줄여준다 (저자 벤치). codegraph는 worktree마다 `.codegraph/`
  로컬 인덱스를 두며 1회 init 후 incremental sync로 유지된다.
- **결정**:
  - **agent별 고정 worktree**:
    - Claude Code → worktree 이름 `pinvi-claude` (예: `F:/dev/pinvi-claude`)
    - OpenAI Codex (CLI / VS Code) → `pinvi-codex`
    - Google Antigravity 2.0 → `pinvi-antigravity`
    - worktree 이름은 고정. 경로는 자유 (예: NTFS `F:/dev/pinvi-<agent>`,
      WSL `~/pinvi-workspaces/pinvi-<agent>`).
  - **작업 단위는 worktree가 아니라 branch**:
    - 새 작업 시작 시 같은 worktree 안에서 `git fetch && git switch -c agent/<agent>-<task> origin/main`.
      (로컬 `main` ref는 trunk가 점유 — worktree에서는 `origin/main`을 직접 기준 ref로 쓴다.
      자세한 사유는 `docs/runbooks/codegraph-worktrees.md` §3.3.)
    - 즉 worktree는 영속, 브랜치만 task마다 새로.
  - **CodeGraph**:
    - worktree마다 **1회** `codegraph init -i` (interactive — `npx
      @colbymchenry/codegraph` 또는 글로벌 `codegraph init -i`).
    - 이후 task 시작 시 `codegraph sync` (incremental).
    - `.codegraph/` 디렉터리는 `.gitignore`에 박힘 (로컬 SQLite, 머신 / worktree
      마다 별개).
  - **사람이 직접 만지는 trunk** `F:/dev/pinvi` (메인 checkout)은 자유.
    AI 도구는 절대 trunk를 직접 만지지 않고 각자의 worktree만 사용.
  - **runbook** `docs/runbooks/codegraph-worktrees.md`가 1차 reference.
- **근거**:
  - 도구 동시 사용은 ADR-016이 이미 인정. 별 worktree 없이 운영하면 fact drift가
    아니라 file drift / lock 충돌이 직접 발생한다.
  - codegraph는 100% 로컬 (네트워크 호출 없음), MIT, 한 번 init 후 `codegraph
    sync`가 file watcher 없이도 가능 → CI / 자동화에 친화적.
  - branch만 새로 따는 패턴은 worktree create / delete 비용을 0으로 만든다.
  - `.codegraph/`를 ignore하면 도구 / OS / worktree마다 인덱스가 격리되어
    충돌이 발생하지 않는다 (SQLite WAL 파일 포함).
- **결과 (긍정)**:
  - AI 도구마다 동시에 무관한 task 진행 가능 (Claude는 Sprint 3 Admin, Codex는
    Sprint 4 지도 prep 등). 충돌은 PR 머지 시점에만 발생.
  - codegraph 인덱스로 Claude Code의 Explore sub-agent 비용 ↓.
  - 새 task 시 90초 setup → `git fetch && git switch -c ... && codegraph sync`.
- **결과 (부정)**:
  - worktree 3개 추가 디스크 사용 (Next.js `.next` 캐시 등 포함 시 worktree당
    ~수 GB). 단 `.gitignore` 항목은 worktree 간 공유 안 됨 — 사용자가 신경 쓸 것.
  - codegraph 인덱스 worktree마다 별개 = 디스크 추가. 단 `.codegraph/` 크기는
    저장소 코드 size의 ~10% 수준 (저자 사양).
  - 첫 init 1회 비용 (대형 monorepo는 5~15분).
- **후속**:
  - `docs/runbooks/codegraph-worktrees.md` 작성 (본 PR)
  - `.gitignore`에 `.codegraph/` 추가 (본 PR)
  - `CLAUDE.md` / `AGENTS.md`에 worktree 정책 reference (본 PR)
  - 향후 도구 추가 시 본 ADR에 worktree 이름 추가 (ADR-016과 동일 운영).

## ADR-018: 한국 전용 서비스 — geofencing 3중 안전망

- **상태**: accepted
- **날짜**: 2026-05-27
- **결정자**: 사용자
- **컨텍스트**: Pinvi v1은 한국 사용자만 대상. 한국 공공 API (VWorld / KMA /
  VisitKorea 등) TOS가 한국 도메인 / IP 제한을 두는 항목이 있고, LBS 사업자
  신고도 국내 대상 한정. 해외 IP는 차단해 트래픽 / API 한도 / 법적 리스크를
  통째로 줄인다.
- **결정**:
  - **3중 안전망** (어느 하나가 뚫려도 다음이 막음):
    1. **Cloudflare WAF rule** — "Country ≠ KR → Block 451". 가장 외곽.
    2. **nginx `geo` 모듈 + GeoIP2 DB** — `infra/nginx/geo-kr.conf`로
       비KR `return 451`. 컨테이너 단계.
    3. **FastAPI middleware** (`apps/api/app/middleware/geofence.py`) —
       `X-Real-IP` 또는 `CF-Connecting-IP` 헤더 기준 MaxMind 또는
       `python-vworld-api`의 행정구역 조회로 검증. 응용 단계 fallback.
  - **차단 응답**: HTTP 451 (Unavailable For Legal Reasons) + landing page
    안내 (한/영) — "Pinvi는 한국 거주자 전용 서비스입니다."
  - **예외**: admin / cpo role 사용자는 비KR에서도 접근 허용 (운영자 출장 등).
    `geofence.py`에서 인증된 사용자 role 확인 후 우회.
  - **VPN / Tor**: Cloudflare WAF에서 known VPN/Tor exit node도 차단 옵션
    적용. 위 3중 안전망 위에서 동작.
  - **모니터링**: 451 응답 카운트 → Loki + Grafana 대시보드.
- **근거**:
  - VWorld TOS: 국내 서비스 한정 권장
  - LBS 사업자 신고: 국내 사용자 대상으로 신청
  - 외부 API 일 호출 한도 보호 (KMA / VisitKorea 등)
  - 결제 / 환불 / 법무 부담 최소화
- **결과 (긍정)**:
  - API 호출 / DB 부하 / 보안 위협 모두 감소
  - PIPA / LBS 컴플라이언스 단순화
  - VWorld / 카카오 / KMA TOS 위반 가능성 차단
- **결과 (부정)**:
  - 해외 거주 한국인 → 차단됨 (불편). 추후 인증 사용자에 한해 IP 무관 허용
    옵션 검토.
  - GeoIP DB 갱신 주기 관리 필요 (월 1회)
  - Cloudflare 무료 플랜 한도 내 운영
- **후속**:
  - `docs/architecture/korea-only-policy.md` — 절차 / 예외 / 모니터링 (본 PR)
  - `docs/runbooks/korea-only.md` — Cloudflare WAF rule 설정 / nginx geo
    설정 / GeoIP DB 갱신 cron (본 PR)
  - Sprint 6에 구현 (DoD에 포함)
  - 해외 진출 결정 시 본 ADR superseded — 동시 결정 PR 필수
- **참조**: SPRINT-6 DoD, `docs/compliance/lbs-act.md`

## ADR-019: Pinvi MCP 외부 인터페이스 서빙 (read-only)

- **상태**: accepted
- **날짜**: 2026-05-27
- **결정자**: 사용자
- **컨텍스트**: AI agent (Claude Code / Codex / Antigravity / 사용자 본인의
  Claude Desktop 등)가 Pinvi 데이터를 직접 query할 수 있으면 trip planning
  loop가 짧아진다 — "내 부산 여행에 추가할 카페 추천" / "다음 주 일정 보여줘"
  등을 사용자가 AI 도구에 직접 물어볼 수 있다. MCP (Model Context Protocol,
  Anthropic 표준)는 이런 외부 노출의 사실상 표준 포맷.
- **결정**:
  - Pinvi가 **MCP 서버를 노출**한다 (Sprint 6, v1.0에 포함).
  - **트랜스포트**: stdio + SSE 둘 다 지원. stdio는 Claude Desktop 로컬, SSE
    는 Claude Code remote MCP / web client. (`apps/api/app/mcp/server.py`)
  - **인증**: 전용 MCP 토큰 (JWT scope=`mcp:read`). 일반 `pinvi_access`
    cookie 토큰과 분리 — MCP 토큰은 long-lived (30일 default, 무한대 옵션) +
    사용자가 `/users/me/mcp-tokens`에서 발급 / 회수.
  - **tools (1차)** — 모두 **read-only**:
    - `list_trips` — 본인 trip 목록
    - `get_trip(trip_id)` — trip + POI + day 트리
    - `list_pois(trip_id, day_index?)` — POI 필터
    - `search_features(q, kind?, bounds?)` — feature 검색 (라이브러리 read 위임)
    - `get_user_profile` — 본인 프로필 (마스킹 적용)
  - **mutating tool은 v1.1 이후 검토** — MCP 인증 보안 검증 + 사용자 UX 패턴
    파악 후. (예: `add_poi_to_trip` / `optimize_day`)
  - **rate limit**: 사용자당 60 calls/min — admin_audit_log + api_call_log에
    기록.
  - **scope 확장 정책**: ADR-019 amendment 또는 후속 ADR.
- **근거**:
  - Anthropic MCP 표준 — Claude / Codex 양쪽 지원. (Antigravity / Cursor /
    opencode도 차츰 지원)
  - 본 저장소가 codegraph로 이미 MCP를 사용 중 (ADR-017) → 운영 친숙
  - read-only 1차로 시작 → 보안 / UX 검증 후 확장
- **결과 (긍정)**:
  - 사용자가 AI 도구로 trip planning 자연어 query 가능
  - 외부 챗봇 / 자동화 통합 길 열림
  - MCP token은 일반 cookie 토큰과 분리 → blast radius 제한
- **결과 (부정)**:
  - MCP 표준 자체가 빠르게 진화 — breaking change 추적 비용
  - 토큰 leak 시 사용자 trip 전체 노출 — 사용자 교육 필요
  - 신규 도메인 / port 노출 → 보안 surface 증가
- **후속**:
  - `docs/architecture/mcp-server.md` — 트랜스포트 / 인증 / tool 상세 (본 PR)
  - `docs/runbooks/mcp-server.md` — 토큰 발급 / 회수 / 모니터링 (본 PR)
  - Sprint 6 DoD에 포함. 본격 구현은 별 PR.
  - mutating tool은 v1.1 ADR-019-amend로 결정.
- **참조**: ADR-017 (codegraph MCP), `docs/runbooks/codegraph-worktrees.md`

## ADR-020: T-107 (Gemini AI Companion) 별도 서비스 분리

- **상태**: accepted
- **날짜**: 2026-05-27
- **결정자**: 사용자
- **컨텍스트**: 원래 backlog T-107은 본 저장소에 Gemini 통합 (Sprint 4 후보).
  하지만 AI provider (Gemini / Claude / GPT)는 빠르게 진화하고 모델 변경 /
  rate limit / 비용 / 책임 분리 측면에서 본 서비스와 lifecycle이 다르다. 또
  본 저장소가 한국 전용 (ADR-018)인 반면 AI API는 글로벌 (US/EU 호스팅).
- **결정**:
  - T-107을 본 저장소에서 **제거**. 별 repo `kor-travel-concierge` (또는
    사용자 지정 명)로 분리.
  - **통신 패턴**: 로컬 docker-to-docker 호출 — `kor-travel-concierge`이
    별도 컨테이너로 동일 호스트(Odroid / N150)에서 실행, Pinvi API는
    `http://ai-companion:8000/...`으로 호출.
  - **인터페이스**: HTTP API + MCP 토큰 (ADR-019 재사용 가능) 두 가지 지원.
  - **AI provider**: Gemini / Claude / Codex 중 사용자 선택. 별 repo의
    내부 결정.
  - **본 저장소의 통합**: `docs/integrations/ai-companion.md` 신규 — 호출
    컨트랙트 + 헬스체크 + 재시도 / 회로 차단.
  - `apps/api/app/services/ai_companion_client.py` (Sprint 6) — httpx +
    tenacity wrapper.
- **근거**:
  - AI provider lifecycle / 비용 / 법적 책임을 본 서비스와 분리
  - 한국 전용 정책 (ADR-018)과 글로벌 AI API의 호스팅 위치 충돌 회피
  - 사용자가 provider 교체 시 본 저장소 영향 최소화
  - MCP 외부 인터페이스 (ADR-019) 재사용 가능
- **결과 (긍정)**:
  - 책임 경계 명확
  - AI 모델 / provider 변경이 본 서비스 배포에 영향 없음
  - 본 저장소 PR 수 / 복잡도 감소
- **결과 (부정)**:
  - 별 repo 신설 / 운영 부담
  - docker-to-docker 호출 leg 추가 (latency / failure mode)
  - 두 repo CI/CD 동기 필요
- **후속**:
  - 별 repo 생성 — 사용자 결정 시점 / 명명
  - `docs/integrations/ai-companion.md` 신규 (Sprint 6 진입 시)
  - `docs/tasks.md`에서 T-107 → "deferred to `kor-travel-concierge` repo"
- **참조**: ADR-019 (MCP), ADR-018 (한국 전용)

## ADR-021: GitHub Actions CI/CD 재활성화

- **상태**: accepted
- **날짜**: 2026-05-27
- **결정자**: 사용자
- **amendment (2026-06-02)**: GitHub Actions에서 외부 LLM API key를 사용하지
  않는다. `OPENAI_API_KEY`는 등록하지 않고 앞으로도 쓰지 않는다(사용자 지시).
  `codex-pr-review.yml` / `codex-pr-monitor.yml`은 `openai/codex-action` 호출을
  제거하고, PR마다 리뷰 필요 체크리스트와 head SHA 마커만 남긴다. 실제 리뷰는
  `docs/runbooks/pr-review-sprint4.md` 기준으로 에이전트 또는 사람이 로컬/connector/
  `gh`를 사용해 수행한다.
- **amendment (2026-06-02)**: 프론트엔드 실행(`next dev`), lint/typecheck/build,
  Vitest는 WSL ext4 테스트 미러에서 수행한다. Playwright 기반 브라우저 e2e만
  Windows Node/브라우저에서 실행한다. e2e 대상 dev server는 WSL에서 띄운다.
- **amendment (2026-06-05)**: required status check는 `Aggregate CI gate` 하나로
  강제한다. `api` / `web` / `etl` workflow는 path-filtered 상태를 유지하고,
  aggregate gate가 PR 변경 파일을 기준으로 필요한 check(`lint-typecheck-test`,
  `lint-typecheck-build`, `sanity`)만 기다린다. docs-only PR은 aggregate gate 자체만
  통과하면 된다.
- **amendment (2026-06-07)**: PR review reminder는 `scripts/pr_review_monitor.py`로
  단일화한다. `pull_request` 이벤트는 `opened` / `ready_for_review` / `reopened` /
  `synchronize`에서 즉시 대상 PR을 확인하고, 5분 schedule은 GitHub 지연 가능성을
  감안한 보정 감시로 둔다. 알림 본문은 `kor-travel-map`과 같은 MCP 진입 방식
  (CodeGraph / Playwright / Sequential Thinking / Telegram)을 명시하되, 외부 LLM API
  key와 GitHub secret은 계속 쓰지 않는다.
- **컨텍스트**: Sprint 1~3 진행 중 사용자 지시 "깃헙 ci / cd 쓰지마"로 PR #10
  직전 모든 `.github/workflows/`를 삭제했었다. Sprint 4 진입 시 사용자 결정
  뒤집힘 — 운영 가시화 / 정합성 게이트 / Sprint 4 이후 회귀 방지를 위해
  CI/CD 부활.
- **결정**:
  - **Sprint 4 진입 PR**에서 `.github/workflows/` 5개 workflow 복원:
    - `api.yml` — `apps/api` ruff + mypy --strict + pytest -q + alembic check
    - `web.yml` — `apps/web` lint + typecheck + build
    - `etl.yml` — `apps/etl` ruff + mypy + dagster validate (Sprint 5 본격 활성)
    - `codex-pr-review.yml` — PR review reminder trigger(API key 없음)
    - `codex-pr-monitor.yml` — 5분 주기 PR 감시 + review reminder(API key 없음)
  - **branch protection**: main 직접 push 금지와 PR-only 머지 정책을 적용한다.
    path-filtered workflow를 required status check로 바로 묶으면 docs-only PR이
    대기 상태에 갇힐 수 있으므로, required check는 항상 실행되는 aggregate gate가
    생긴 뒤 추가한다.
  - **secret 관리**: 현재 필수 GitHub Actions secret 없음. `RESEND_API_KEY_TEST` 등
    외부 통합 테스트 secret은 필요 시 별도 카탈로그에 추가한다.
  - **로컬 검증 병행**: WSL에서 `pytest` / `ruff` / `npm run lint`는 계속 1차
    검증. GitHub Actions는 2차 안전망.
  - **AI agent 리뷰 운영**: Actions는 리뷰 필요 알림만 남긴다. 실제 리뷰 코멘트와
    수정·검증·머지는 에이전트 또는 사람이 수행한다.
- **근거**:
  - Sprint 4 이후 산출물이 커지면서 회귀 가능성 ↑
  - 한 명의 AI agent + 사용자만으로는 모든 PR 정합성 검증 어려움
  - GitHub Actions는 무료 플랜 한도 내에서 충분
- **결과 (긍정)**:
  - 모든 PR이 동일 게이트 통과 → 회귀 방지
  - 사용자 + AI agent가 코드 변경에만 집중 가능
- **결과 (부정)**:
  - GitHub Actions 비용 (초기 무료 한도 후 유료 가능)
  - workflow 자체 유지보수 부담
  - secret이 필요한 외부 통합은 별도 등록 절차가 필요
- **후속**:
  - Sprint 4 진입 PR에 `.github/workflows/` 복원
  - `docs/runbooks/pr-review-sprint4.md` 갱신 — workflow status 확인 절차
  - secret 카탈로그 — `docs/runbooks/secrets.md` 신규 (Sprint 5)
- **참조**: ADR-007 (PR-only), `docs/runbooks/pr-review-sprint4.md`

## ADR-022: Backup / Restore 핫스왑 정책

- **상태**: accepted
- **날짜**: 2026-05-27
- **결정자**: 사용자
- **컨텍스트**: Sprint 6 DoD에 "백업 + 복구 훈련 1회"가 있고 SPEC V8도 RTO 1h
  / RPO 24h 요구. 단순 pg_restore는 다운타임 발생 — 핫스왑 패턴 (블루-그린
  유사)으로 복구 중 트래픽 무중단을 목표.
- **결정**:
  - **2단계 구현**:
    - **Sprint 5 (1차)**: `scripts/backup-db.sh` + `scripts/restore-db.sh`
      + `POST /admin/backup/snapshot` (manual trigger). UI는 없음.
    - **Sprint 6 (finalize)**: Backup/Restore UI + 핫스왑 워크플로
      (`/admin/backup` 페이지).
  - **Backup**:
    - `pg_dump --format=custom` → `app` + `app.audit` schema만
      (라이브러리 schema는 `kor-travel-map`이 별도 백업).
    - 결과 파일을 RustFS (`backup` 버킷) + 옵션으로 외부 (BackBlaze B2 또는
      NAS) 미러.
    - **자동**: 매일 03:00 KST (Dagster schedule 또는 systemd timer).
    - **수동**: `POST /admin/backup/snapshot` (admin role 전용, audit log).
  - **Restore (핫스왑)**:
    - 1. `pg_restore`를 같은 Postgres database의 임시 schema
      `app_restore_<ts>`에 적용한다. 신규 DB instance 방식은 쓰지 않는다.
    - 2. restored schema가 healthy하면 짧은 write drain 후 schema rename으로
      cut-over한다: `app` → `app_previous_<ts>`,
      `app_restore_<ts>` → `app`.
    - 3. previous schema는 N150/staging 7일, Odroid M1S 24시간 보존 후 자동 삭제한다.
    - 핫스왑은 무중단이 아니라 near-zero downtime(목표 30~90초) schema-swap이다.
  - **훈련**: 분기 1회 staging에서 핫스왑 PoC. Sprint 6 종료 시 1회 prod에서
    훈련 (read-only mode + 가족 베타 사용자에게 안내).
  - **모니터링**: backup 성공/실패 → admin_audit_log + Grafana 대시보드.
    RPO 위반 시 알림.
- **구현 보정 (2026-06-06)**:
  - PostgreSQL custom format은 단일 파일 artifact라 `pg_dump --jobs`와 함께 쓰지
    않는다. 병렬 처리는 restore 단계의 `pg_restore --jobs`에서만 적용한다.
- **구현 보정 (2026-06-06, T-145)**:
  - Odroid M1S / N150 단일 노드 예산을 고려해 신규 DB instance 방식은 폐기하고,
    동일 database schema-swap으로 확정한다. SQLAlchemy metadata가 `app` schema를 직접
    참조하므로 `DATABASE_URL` 교체가 아니라 schema rename이 cut-over다.
- **근거**:
  - SPEC V8 RTO 1h / RPO 24h 요구
  - 사용자 데이터 (PII / trip / 동의 이력) 보호가 최우선
  - 무중단 복구는 사용자 신뢰 / 운영 부담 모두 줄임
- **결과 (긍정)**:
  - 복구 시 다운타임 최소 (~분 단위)
  - 분기 훈련으로 절차 / 도구 검증
  - admin UI로 운영자가 직접 트리거 가능
- **결과 (부정)**:
  - 구현 복잡도 ↑ (단순 pg_restore 대비)
  - restore schema와 previous schema 보존 중 일시적으로 `app` schema 데이터의 추가
    디스크가 필요
  - cut-over 중 짧은 write drain / API-Web restart가 필요
  - restore는 point-in-time rollback이므로 snapshot 이후 audit row는 previous schema에
    forensic 보존되고 canonical chain에서는 사라짐
- **후속**:
  - `docs/runbooks/backup-restore.md` 신규 (본 PR) — 절차 + 트러블슈팅
  - `docs/architecture/backup-restore.md` 신규 — 핫스왑 아키텍처
  - Sprint 5: 1차 구현. Sprint 6: 핫스왑 finalize + UI + 훈련
- **참조**: SPEC V8 §운영, `docs/runbooks/odroid-docker.md`

## ADR-023: 운영 하드웨어 확장 — Odroid M1S + N150 16GB 병행

- **상태**: accepted (Postgres streaming replication / hot-standby 가정은 ADR-039가 supersede)
- **날짜**: 2026-05-27
- **결정자**: 사용자
- **컨텍스트**: 원래 운영 환경은 Odroid M1S (ARM64, Ubuntu 24.04, ADR
  들에서 single node 가정). 사용자가 신규 박스 N150 16GB / NVMe 1TB /
  Ubuntu 26.04 도입 검토. Odroid를 폐기하지 않고 **병행 운영**으로 결정.
- **결정**:
  - **두 노드 병행**:
    - **Odroid M1S** (ARM64) — 기존 위치. dev/staging 또는 백업 운영.
    - **N150 16GB + NVMe 1TB** (x86_64) — primary 운영. Ubuntu 26.04 LTS.
  - **이미지**: `apps/api/Dockerfile`을 multi-platform build로 — `linux/amd64`
    + `linux/arm64`. GitHub Actions에서 `docker buildx`로 두 플랫폼 빌드 후
    GHCR push.
  - **데이터 운영**:
    - Postgres streaming replication은 사용하지 않는다(ADR-039).
    - 장애 대응은 backup/restore 후 수동 DNS / nginx upstream switch로 제한한다.
    - RustFS 동기화는 별도 backup/mirror 절차로 다루고, 본 ADR은 live mirror를 강제하지 않는다.
  - **선택 기준 (사용자 작업 환경에서)**:
    - 평상시 트래픽 / 일 호출 한도 / Dagster ETL 부하 → N150이 처리
    - Odroid는 ARM64 검증, 백업 복구 훈련, 필요 시 수동 대체 운영
  - **운영 비용 / 전력**: Odroid는 저전력 (5W) → 야간 / 비상시 단독 운영도
    가능. N150은 일반 전력.
  - **N150 환경 사전 검토 항목** (사용자가 도입 전 확인할 것):
    - Ubuntu 26.04 (예정 또는 BETA — 시점 따라 24.04 LTS fallback)
    - PostgreSQL 16 + PostGIS 3.5 호환
    - Docker / Compose 24+ 호환
    - NVMe 1TB 가용 IOPS (random 4k 80K+ 권장 — Dagster + Postgres bg)
    - 16GB RAM 사용량 ceiling (api 2GB + web 1GB + postgres 4GB + dagster
      2GB + rustfs 1GB + grafana/loki 1.5GB + 여유 4.5GB)
- **근거**:
  - 운영 안정성 / 장애 복구 시간 ↓
  - Odroid 자산 활용 + N150 신규 자원의 보강 효과
  - 멀티 플랫폼 빌드 = 향후 다른 ARM SBC / x86 NUC 등에도 호환
- **결과 (긍정)**:
  - 단일 플랫폼에 묶이지 않고 x86_64/ARM64 양쪽 배포 경로를 확보
  - 신규 기능 (Dagster ETL / Grafana / MCP 서버) 부하 흡수
- **결과 (부정)**:
  - 운영 / 모니터링 복잡도 ↑
  - DB live sync가 없으므로 장애 시 RPO는 최신 backup/snapshot에 의존
  - 두 노드의 OS / 패키지 / 시간 동기화 부담
  - 멀티 플랫폼 이미지 빌드 CI 시간 ↑
- **후속**:
  - `infra/n150/README.md` 신규 (Sprint 6) — 배포 절차
  - `docs/runbooks/odroid-docker.md` 갱신 — N150 병행 시 변경점
  - `apps/api/Dockerfile` multi-platform (Sprint 4 CI 활성화 시 함께)
  - 사용자 N150 도입 시점 / 사양 확정 후 본 ADR amendment
- **참조**: ADR-022 (백업), `docs/runbooks/odroid-docker.md`

## ADR-024: NTFS worktree = git source of truth + WSL ext4 일회용 테스트 미러

- **상태**: accepted (ADR-004의 "Git source of truth는 WSL ext4" 부분을 supersede.
  ADR-017 worktree 정책을 개발 환경 모델로 확정)
- **날짜**: 2026-06-01
- **결정자**: 사용자 + Claude
- **컨텍스트**: ADR-017로 AI 도구(Claude / Codex / Antigravity)마다 NTFS에 고정
  worktree(`F:/dev/pinvi-<agent>`)를 두고, NTFS worktree에서 git을 Windows 버전
  git(`git.exe`)으로 실행하기로 했다. 그런데 `docs/dev-environment.md`는 여전히
  ADR-004 시절의 구 모델("WSL ext4 미러가 표준 작업 위치", "Git source of truth는
  ext4", commit은 ext4 한 쪽에서만, 양방향 rsync)을 서술하고 있었다. 두 모델이
  공존하면서 다음 실제 사고가 반복됐다:
  - **worktree 포인터 환경 혼용**: codex worktree의 `.git`는
    `gitdir: /mnt/f/dev/pinvi/.git/worktrees/pinvi-codex`(WSL에서 생성),
    claude worktree는 `gitdir: F:/dev/pinvi/.git/worktrees/...`(Windows에서
    생성)로 절대경로 표기가 환경별로 달랐다. 같은 worktree를 다른 환경 git으로
    다루면 `fatal: not a git repository` / `git worktree list`에서 `prunable`로
    표시되고, 그 상태로 `git worktree prune`을 돌리면 살아있는 worktree 등록까지
    지워질 수 있다.
  - **source of truth 모호**: "ext4에서 commit" vs "NTFS worktree에서 commit"이
    문서마다 달라, 에이전트가 양방향 rsync 후 어느 쪽을 push 기준으로 삼을지
    헤맸다. 특히 rsync 왕복 중 파일 일부에 중복/오염이 섞이는 사고가 있었다.
  - **WSL에서 Windows 도구 PATH 오염**: `npm`/`git`이 `/mnt/c/...`의 Windows
    shim으로 잡혀 `node: not found`, UNC 경로 경고, 잘못된 경로 전달이 발생.
  같은 NTFS+WSL 혼용 문제를 별 저장소 `kor-travel-geo`가 ADR-041로 이미
  해결했고(동일 패턴), 본 저장소도 그 패턴으로 통일한다.
- **결정**:
  - **git source of truth = NTFS worktree**. 코드 편집 / branch / commit / push /
    PR은 NTFS worktree(`F:/dev/pinvi-<agent>`)에서 Windows git(`git.exe`)으로만
    수행한다. ADR-004의 "Git source of truth는 ext4" 문장은 **supersede**.
  - **WSL ext4 = 일회용 테스트 미러**. 의존성 설치(`uv`/`pip`/`npm`), 테스트
    (`pytest`/통합), Docker, 장기 실행(`uvicorn`)은 ext4 미러
    (`~/pinvi-workspaces/pinvi-<agent>`)에서 수행한다. **미러에서는 commit /
    push 하지 않는다.**
  - **rsync는 단방향(NTFS → ext4)**. 작업/검증 직전 NTFS worktree → ext4 미러로
    `rsync -a --delete` 복사. 검증 중 발견한 수정은 **NTFS worktree에 직접 반영**
    하고 다시 단방향 sync한다. ext4 → NTFS 역카피를 source-of-truth 절차로 쓰지
    않는다(포매터가 ext4에서 파일을 고쳤을 때만, 그 파일에 한해 NTFS로 단방향
    sync-back 후 `git diff`로 확인).
  - **worktree는 환경 전용**: 각 worktree의 git은 한 환경에서만 다룬다. 같은
    worktree를 Windows git과 WSL git으로 번갈아 조작하지 않는다. `git worktree
    prune`은 그 worktree를 운용하는 환경에서만 실행한다. 환경을 바꿔야 하면 먼저
    `git worktree repair <경로>`로 포인터를 그 환경 기준으로 맞춘다.
  - **데이터(`dataset/`, `refdocs/`)**는 NTFS 원본을 기준으로 두고 ext4 미러에서는
    절대경로 또는 심볼릭 링크로 참조한다(ext4에서 변경 금지).
- **근거**:
  - NTFS worktree를 단일 git 기준으로 두면 "어디서 commit?" 모호함이 사라진다.
    Windows 탐색기 / IDE에서 같은 파일을 그대로 본다.
  - ext4를 실행 전용 일회용으로 두면 양방향 동기의 오염 위험이 사라지고, 미러는
    언제든 폐기·재생성 가능하다(I/O·inotify·권한은 ext4가 우월).
  - `kor-travel-geo` ADR-041과 동일 패턴 → 도구·저장소 간 일관.
- **결과 (긍정)**: 환경 모델 단일화. codex/antigravity도 같은 절차를 따른다.
  worktree prune 사고·rsync 오염·git.exe vs WSL git 혼용이 문서로 차단된다.
- **결과 (부정)**: 작업 직전 단방향 rsync 1회가 필요. ext4에서 포맷한 파일은
  NTFS로 sync-back 후 diff 확인하는 한 단계가 추가된다.
- **후속**:
  - `docs/dev-environment.md` 신 모델로 전면 재작성 (본 PR).
  - `AGENTS.md` "WSL ext4 미러" 섹션 + `CLAUDE.md` worktree 블록 동기 (ADR-016).
  - `docs/runbooks/codegraph-worktrees.md`에 Windows/WSL git 포인터 함정 절 +
    ADR-024 참조 추가.
- **참조**: ADR-004(미러 모델 — 디스크/경로는 유지, source-of-truth 주장만
  supersede), ADR-017(worktree + git.exe), `kor-travel-geo` 진영
  ADR-041, `docs/dev-environment.md`.

## ADR-025: 사용자 대면 geocoding은 `kor-travel-geo` v2 REST API 직접 호출

- **상태**: accepted
- **날짜**: 2026-06-02
- **결정자**: 사용자 + Claude
- **컨텍스트**: Pinvi는 두 종류의 외부 도메인 데이터를 쓴다.
  1. **Feature 데이터**(place/event/notice/price/weather/route/area) — 당시 기준은
     `kor-travel-map` 함수 직접 호출(ADR-002)이었으나, 이후 ADR-026으로
     OpenAPI HTTP 계약으로 전환.
  2. **Geocoding/주소**(주소→좌표 geocode, 좌표→주소 reverse, 주소/장소 search,
     행정구역 region 조회) — 사용자가 "geocoding 관련 기능은 kor-travel-geo v2 API에
     직접 접근"하라고 지시.
  그런데 기존 문서(`docs/api/regions.md`, `docs/kor-travel-map-integration.md`)는
  region/주소 조회를 **kor-travel-map 함수 호출 경유**로 서술해, 지시와 어긋났다.
  한편 `kor-travel-geo`는 이미 v2 REST API(`POST /v2/geocode|reverse|search`,
  candidate 목록 표면)를 제공하고, kor-travel-map도 자기 ETL 적재 시 이 v2 REST를
  HTTP로 호출한다(kor-travel-map `address-geocoding.md`, ADR-006). 즉 v2 REST가
  geocoding의 공식 표면이다.
- **결정**:
  - **Pinvi 사용자 대면 geocoding은 `kor-travel-geo` v2 REST API를 직접 HTTP 호출**
    한다. `apps/api`가 `httpx.AsyncClient`로 `POST /v2/geocode|reverse|search`를
    부른다. kor-travel-map을 경유하지 않는다.
    - 신설 endpoint(예): `GET /geo/search`, `GET /geo/reverse`, `GET /geo/geocode`
      — Pinvi가 v2 candidate를 자기 응답 셰입(`{data, meta}`)으로 래핑.
  - **Feature 데이터는 kor-travel-map 계약** — 본 결정은 geocoding 경계만 다루며,
    feature 데이터 경계는 이후 ADR-026의 OpenAPI HTTP 계약을 따른다.
  - **경계**: Pinvi는 kor-travel-geo의 **v2 REST 표면만** 의존한다. python 패키지
    (`kor_travel_geo`) in-process import나 DB 직접 접근을 사용자 대면 경로에서 쓰지
    않는다(kor-travel-map이 ETL 내부에서 쓰는 것과 별개). v1 vworld-호환 표면(`/v1/
    address/*`)도 신규 사용하지 않는다 — candidate 중심 v2만.
  - **region 조회**(시도/시군구/법정동)도 v2로 수렴: 좌표→행정구역은 `POST
    /v2/reverse`(`include_region=true`)의 `candidates[].region`, 행정구역 검색은
    `POST /v2/search`(`type="district"`)로 처리한다. 기존 `regions.md`의 kor-travel-map
    경유 서술은 본 ADR로 정정한다.
  - **VWorld/juso/epost 등 외부 API 직접 호출 금지** — 모두 kor-travel-geo REST 내부
    책임(`fallback="api"`). Pinvi는 v2 응답만 신뢰.
- **근거**:
  - 사용자 지시 + kor-travel-geo가 이미 v2 REST를 공식 표면으로 제공.
  - geocoding은 feature 적재와 lifecycle/배포가 다르다(별 서비스로 기동 가능,
    HTTP 경계가 자연스럽다). 함수 호출로 묶으면 kor-travel-map에 불필요한 결합.
  - kor-travel-map과 동일한 v2 표면을 공유 → 좌표·코드 해석 일관(같은 `(lon,lat)`,
    같은 region 코드 체계).
- **결과 (긍정)**: geocoding 의존이 명확한 HTTP 경계 1개로 단순화. kor-travel-map
  버전과 독립적으로 geocoding 진화. 캐싱/rate-limit을 Pinvi가 자기 경계에서 관리.
- **결과 (부정)**: in-process 함수 호출 대비 HTTP hop(직렬화·네트워크). 단 같은
  호스트(docker network)면 무시 가능. kor-travel-geo REST 서비스가 reachable해야 함
  (healthz 의존).
- **후속**:
  - `docs/integrations/kor-travel-geo.md` 신규 — v2 endpoint 계약 + httpx client 주입 +
    환경변수 + 캐싱 + 에러 매핑 + 위치 감사 + 사용처 + AI agent 체크리스트 (본 PR).
  - `docs/api/regions.md` 정정 — kor-travel-map 경유 → kor-travel-geo v2 직접.
  - `docs/architecture/user-location.md` — 역지오코딩 region label 경로를 v2 reverse로.
  - `docs/kor-travel-map-integration.md` — geocoding은 본 경계 밖임을 명시.
  - 열린 결정은 `docs/architecture/geocoding-open-decisions.md`에 별도 정리(본 PR).
- **참조**: ADR-002(superseded), ADR-026(kor-travel-map OpenAPI HTTP), ADR-003(schema
  책임), `kor-travel-map` `docs/address-geocoding.md`·ADR-006,
  `kor-travel-geo` `docs/api-reference/v2/*`.

## ADR-026: Pinvi ↔ `kor-travel-map`은 최신 OpenAPI HTTP 계약으로 전환

- **상태**: accepted
- **날짜**: 2026-06-04
- **결정자**: 사용자 + Codex
- **컨텍스트**: ADR-002는 `kor-travel-map`을 같은 venv에서 함수 직접 호출하는
  모델로 Pinvi 통합을 정의했다. 그러나 2026-06-04에 최신 `kor-travel-map`
  `main`을 새로 받아 확인한 결과, 그 저장소의 현재 권위 계약은
  `packages/kor-travel-map-admin/openapi.user.json`(Pinvi/user-facing subset)과
  `packages/kor-travel-map-admin/openapi.json`(Admin/ops/debug 포함 전체 OpenAPI)이다.
  `docs/pinvi-rest-api.md`와 `docs/openapi-admin-contract.md`도 Pinvi가
  kor-travel-map을 import/DB 직접 접근하지 않고 OpenAPI HTTP로 호출해야 한다고
  명시한다.
- **결정**:
  - Pinvi는 `kor-travel-map`을 **독립 프로그램의 OpenAPI HTTP API**로
    호출한다. 로컬 고정 포트는 API/Admin API `12301`.
    이 포트 값은 ADR-042에서 docker-manager 대역 정책에 따라 `12701`로 supersede됐다.
  - Pinvi 사용자/서비스 경로에서 `from kor_travel_map.map import ...`,
    `AsyncKorTravelMapClient`, `feature`/`provider_sync` 직접 SQL/ORM 접근을 쓰지
    않는다. HTTP client는 transport wrapper만 허용한다.
  - Pinvi/user-facing 권위 계약은 kor-travel-map 최신 `openapi.user.json`이다.
    현재 주요 경로는 `GET /features/in-bounds`, `GET /features/search`,
    `GET /features/nearby/by-target`, `GET /features/{feature_id}`,
    `POST /pinvi/features/batch`, `POST /admin/feature-update-requests`,
    `GET /admin/feature-update-requests/{request_id}`다.
  - Admin/ops/debug 경로는 최신 `openapi.json`을 따른다. 일반 사용자 API에서는
    admin/offline/dedup/ops/debug 경로를 노출하지 않는다.
  - `feature` / `provider_sync` schema 소유권은 ADR-003 그대로 유지한다. Pinvi는
    `feature_id`와 snapshot만 `app` schema에 저장하고 최신 feature 정보는
    kor-travel-map API로 조회한다.
  - Geocoding/주소/행정구역은 ADR-025 그대로 `kor-travel-geo` v2 REST 직접 호출이다.
- **근거**:
  - 최신 kor-travel-map `main`의 구현 산출물이 OpenAPI를 권위 계약으로 제공한다.
  - 독립 HTTP 경계는 kor-travel-map 자체 Admin/Dagster/ops 운영과 Pinvi 사용자 앱의
    배포·장애·버전 관리를 분리한다.
  - Pinvi가 `feature` schema 내부 모델이나 provider 변환 로직을 다시 알 필요가
    없다.
- **결과 (긍정)**: Pinvi와 kor-travel-map의 런타임 결합이 낮아지고, OpenAPI drift
  검증으로 계약 변경을 잡을 수 있다. 최신 kor-travel-map Admin/ops 표면과 일관된다.
- **결과 (부정)**: 함수 직접 호출 대비 HTTP hop과 장애 경계가 생긴다. Pinvi
  read 경로는 kor-travel-map API reachable 상태를 확인해야 하며, POI snapshot fallback
  정책이 필요하다.
- **후속**:
  - `docs/kor-travel-map-integration.md`를 OpenAPI HTTP 기준으로 전면 갱신.
  - `AGENTS.md`, `CLAUDE.md`, `SKILL.md`, `README.md`, API/ETL 문서의 함수 호출
    표현을 OpenAPI HTTP 표현으로 정정.
  - feature read 구현 시 `httpx.MockTransport` 계약 테스트와 kor-travel-map
    `openapi.user.json` drift 확인을 추가.
- **참조**: ADR-002(superseded), ADR-003(schema 책임), ADR-025(kor-travel-geo v2 REST),
  `kor-travel-map` 최신 `packages/kor-travel-map-admin/openapi.user.json`,
  `docs/pinvi-rest-api.md`, `docs/openapi-admin-contract.md`.
- **2026-06-06 정정(ADR-027)**: 위 "근거/참조"가 가정한 kor-travel-map 산출물
  (`kor-travel-map-admin` 패키지, `openapi.user.json`, 포트 12301, `/pinvi/features/batch`)
  은 2026-06-06 `kor-travel-map` `main`(`HEAD=b775c74`) 실측 결과 **존재하지
  않는다.** kor-travel-map의 실제 HTTP 표면은 인증 없는 debug-UI(`kor-travel-map-debug-ui`,
  포트 8087, `GET /features` bbox·`GET /features/{id}`)뿐이다. ADR-026의 HTTP 방향은
  ADR-027에서 유지하되, 그 계약은 kor-travel-map이 **신규로 구축해야 할 목표**임을
  명확히 한다.

## ADR-027: kor-travel-map 통합은 운영급 HTTP 서비스로 확정 (ADR-026 reality-check)

- **상태**: accepted
- **날짜**: 2026-06-06
- **결정자**: 사용자 (DEC-01)
- **컨텍스트**: 2026-06-06 문서·구현 정합성 감사
  (`docs/audit/2026-06-06-doc-impl-audit.md`)에서 두 저장소의 통합 모델이 정반대임을
  확인했다. Pinvi는 ADR-026으로 HTTP 계약(포트 12301)을 선언했으나, kor-travel-map은
  9개월간 in-process 함수 라이브러리(kor_travel_map ADR-003)로 만들어졌고 HTTP는 인증 없는
  debug-UI(8087)뿐이며, ADR-026이 참조한 kor_travel_map 산출물은 실재하지 않는다.
- **결정**:
  - 통합 모델은 **운영급 HTTP 서비스(DEC-01 안 B)** 로 확정한다. ADR-026 유지.
  - 이 HTTP 계약(인증 있는 운영 API, 포트 12301, 전 엔드포인트, OpenAPI 생성 +
    drift gate)은 kor-travel-map이 **신규로 구축해야 할 목표**다. 현재 미존재임을 인지한다.
    이 포트 값은 ADR-042에서 docker-manager 대역 정책에 따라 `12701`로 supersede됐다.
  - Pinvi가 kor-travel-map에 필요로 하는 능력의 권위 명세는
    `docs/kor-travel-map-requirements.md`다. kor-travel-map 에이전트가 이를 읽고 우선순위·계약을
    회신한다.
  - **클러스터링(DEC-04)**: 지도 in-bounds 클러스터링은 **kor-travel-map 서버(DB 집계)**
    가 수행한다(단일 노드 대역폭·성능). Pinvi `cluster_query.py`는 fallback 한정.
  - **feature 갱신요청 큐(DEC-05)**: 큐는 Pinvi `app` schema가 소유하고, Admin 승인
    시에만 kor-travel-map 적재 경로를 호출한다. kor_travel_map HTTP 표면 최소화.
- **결과**: feature read 전 경로가 kor_travel_map HTTP 서비스 가용성에 의존한다. v0.1.0은
  이 연동 완료까지 대기한다(DEC-06, `docs/sprints/README.md`).
- **후속**: T-066(HTTP client 구현), T-124(계약 정렬), T-148(SPRINT-4 재작성). kor-travel-map
  측 신규 HTTP 서비스 구축은 kor_travel_map 저장소 백로그.
- **참조**: ADR-026, ADR-002(superseded), `docs/kor-travel-map-requirements.md`,
  `docs/decisions-needed-2026-06-06.md` DEC-01/04/05.

## ADR-028: 정규 `feature_id` 포맷은 kor-travel-map `make_feature_id` 출력

- **상태**: accepted
- **날짜**: 2026-06-06
- **결정자**: 사용자 (DEC-02)
- **컨텍스트**: `feature_id`가 3곳에서 다름 — Pinvi 문서 `f_{bjd}_{kind[0]}_{sha1[:16]}`,
  kor_travel_map 실제 `core.make_feature_id`(예 `{kind}:{hash}`), Pinvi **코드는 UUID**(버그).
- **결정**: feature 소유자는 kor-travel-map이므로 **`make_feature_id`의 출력이 정본**이다.
  Pinvi는 이를 **불투명 문자열**로 그대로 저장·전달한다. kor-travel-map이 확정 포맷을
  명문화한다(`docs/kor-travel-map-requirements.md` K-13). Pinvi 코드의 UUID 가정은
  제거한다(T-125).
- **참조**: ADR-027, `docs/api/features.md`, `apps/api/app/services/trip_view_builder.py`.

## ADR-029: `notice_plans` 명칭 충돌 해소 — 큐레이션은 `curated_trip_plans`

- **상태**: accepted
- **날짜**: 2026-06-06
- **결정자**: 사용자 (DEC-03)
- **컨텍스트**: `app.notice_plans`가 "큐레이션 여행 템플릿"과 "시스템 공지" 두 뜻으로
  동명 충돌(감사 D-01/D-04).
- **결정**: 사용자 대면 "추천/큐레이션 여행"은 **`app.curated_trip_plans`**(하위
  `curated_plan_pois`, `curated_plan_attachments`)로 개명한다. `app.notice_plans`는
  운영 공지 전용으로 한정한다. 스키마 정본화는 T-137.
- **후속**: T-137에서 ORM/Alembic과 `docs/architecture/notice-plans.md`,
  `docs/api/notice-plans.md`, `docs/data-model.md`, `docs/postgres-schema.md`를 정렬했다.
- **참조**: 감사 D-01/D-04.

## ADR-030: 외부 API 규약 정본

- **상태**: accepted
- **날짜**: 2026-06-06
- **결정자**: 사용자 (DEC-07)
- **컨텍스트**: envelope 4종·pagination 4종·좌표 4종·datetime 2종·버전 prefix 미확정이
  도메인마다 혼재(감사 A-03/04/07/08/10).
- **결정** (이후 모든 외부 API의 정본; `docs/api/common.md`가 단일 출처):
  - list 응답 = `{"data": [...], "meta": {...}}`(data는 배열). 단건 = `{"data": {...}}`.
  - 사용자 대면 list 페이지네이션 = **cursor**. Admin/S3 continuation은 예외로 명문.
  - 좌표 = `{"longitude": .., "latitude": ..}`(lng-first, 6자리). WS 포함 전 구간 동일.
  - datetime = ISO 8601 `+09:00`(KST). admin 포함 통일.
  - id 필드 = `<entity>_id`. 현재 사용자 객체는 `data.user`로 통일.
  - **URL 버전 prefix = `/v1` 노출**(라우터가 이미 `api/v1`).
  - 생성 성공 status = 영속 리소스 생성 시 `201`, 그 외 `200`.
  - 에러는 `common.md` 표준 taxonomy만 사용. 누락 코드(`DB_UNAVAILABLE`,
    `TRIPS_OWNED` 등)는 표에 등록하거나 표준 코드로 대체.
- **후속**: `common.md`/`api-contract.md` 정본화(본 PR 1차) + per-domain 일괄 정렬
  (T-123/T-124/T-126 등).
- **참조**: 감사 A-03/04/07/08/09/10/16/22, `docs/decisions-needed-2026-06-06.md` DEC-07.

## ADR-031: POI delete 정책(soft) + `trip_day_pois.feature_id` nullable

- **상태**: accepted
- **날짜**: 2026-06-06
- **결정자**: 사용자 권고 기본값 채택 (DEC-08/DEC-09)
- **컨텍스트**: POI delete가 pois.md "미정" vs admin.md "hard"로 충돌(감사 A-15);
  `trip_day_pois.feature_id` NOT NULL이라 kor_travel_map에 없는 자유 메모 장소를 일정에 못
  넣음(감사 D-18).
- **결정**:
  - POI delete는 **soft delete**(`deleted_at`)로 통일한다. 복구·공유 링크 안정성 우선.
  - `app.trip_day_pois.feature_id`를 **nullable**로 하고, feature 없이 사용자 좌표·
    이름만으로 POI를 추가하는 경로를 허용한다.
- **후속**: `docs/api/pois.md`/`admin.md` 정렬(T-126 인접), 스키마 변경(T-138 인접).
- **참조**: 감사 A-15/D-18, `docs/decisions-needed-2026-06-06.md` DEC-08/09.

## ADR-032: 인증 토큰 기준은 access JWT + httpOnly cookie

- **상태**: accepted
- **날짜**: 2026-06-06
- **결정자**: 구현 기준 백필 (T-151)
- **컨텍스트**: Sprint 1~2에서 회원가입/로그인/OAuth vertical slice가 먼저 구현됐지만,
  Sprint 문서에는 인증 토큰 모델이 번호 미배정 placeholder로 남아 있었다. 현재 구현은
  `apps/api/app/core/security.py`, `core/deps.py`, `api/v1/auth.py`에 박혀 있다.
- **결정**:
  - 비밀번호 저장은 Argon2id hash를 사용한다.
  - 인증 성공 시 `pinvi_access` httpOnly cookie에 HS256 access JWT를 저장한다.
    access JWT는 `sub`, `exp`, `iat`, `typ=access`를 담고, 권한 판단은 토큰 claim이
    아니라 서버 DB 조회로 수행한다.
  - `pinvi_refresh`는 opaque httpOnly cookie로 내려보내되, 서버 저장/회전/폐기와
    `POST /auth/refresh` 완성은 T-134의 명시 후속으로 둔다.
  - cookie는 `SameSite=Lax`, 운영 환경 `Secure=true`, access 15분, refresh 7일을
    기본값으로 한다.
  - 현재 활성 OAuth provider는 Google뿐이다. Naver/Kakao는 T-122 future provider로
    보류하며 현재 런타임에서 사용하지 않는다.
- **결과**: 사용자 API는 browser cookie 기반으로 단순하게 시작하고, refresh session
  저장소가 완성될 때까지 재발급/강제 세션 폐기 기능은 제한된다. Admin/RBAC는 access
  token의 `sub`로 사용자를 찾은 뒤 DB roles를 기준으로 판단한다.
- **후속**: T-134에서 `user_sessions` persistence, refresh token rotation, logout all,
  세션 목록/폐기 UI를 구현한다. OAuth provider 확장은 T-122에서 별도 PR로 다룬다.
- **참조**: `docs/api/auth.md`, `docs/integrations/social-login.md`,
  `apps/api/app/core/security.py`, `apps/api/app/api/v1/auth.py`.

## ADR-033: Admin 권한은 `users.roles[]` + 서버 dependency가 정본

- **상태**: accepted
- **날짜**: 2026-06-06
- **결정자**: 구현 기준 백필 (T-151)
- **컨텍스트**: Sprint 3 Admin 콘솔은 RBAC를 구현했지만, Sprint 문서에는 RBAC
  ADR 번호가 배정되지 않았다. 현재 구현은 `users.roles` 배열과 `require_role`
  dependency를 기준으로 한다.
- **결정**:
  - 사용자 권한은 `app.users.roles TEXT[]`에 저장한다. 기본값은 `user`다.
  - Admin API는 `require_role(...)` dependency로 현재 사용자 row를 다시 조회하고,
    허용 role이 없으면 Admin 리소스 존재를 숨기기 위해 404 `RESOURCE_NOT_FOUND`를
    반환한다.
  - 현재 role vocabulary는 `user`, `admin`, `operator`, `cpo`다. endpoint별 허용
    role은 서버 dependency가 정본이며, Next.js Admin guard는 UX 보조 수단이다.
  - 개인정보/위치/감사 관련 action은 role 통과 후에도 별도 사유 입력과 audit log를
    남긴다.
- **결과**: 권한 정책은 token claim이나 frontend route guard에 의존하지 않는다. 권한
  매트릭스 테이블은 아직 만들지 않고, endpoint dependency로 Sprint 3~4 범위를 버틴다.
- **후속**: role이 늘어나거나 세부 scope가 필요해지면 `docs/architecture/admin-rbac.md`
  와 권한 매트릭스 테이블을 별도 ADR로 추가한다.
- **참조**: `docs/api/admin.md`, `docs/runbooks/admin.md`,
  `apps/api/app/core/rbac.py`, `apps/api/app/models/user.py`.

## ADR-034: Admin 감사 로그는 append-only hash chain으로 남긴다

- **상태**: accepted
- **날짜**: 2026-06-06
- **결정자**: 구현 기준 백필 (T-151)
- **컨텍스트**: Sprint 3에서 `admin_audit_log` content hash chain과 위험 action
  사유 입력을 구현했으나, 해당 운영 기준의 ADR 번호가 없었다.
- **결정**:
  - Admin mutating action과 개인정보 열람 action은 `app.admin_audit_log`에 append-only로
    기록한다.
  - 각 row는 `prev_hash`와 `content_hash`를 저장한다. 신규 row의 `prev_hash`는 직전
    row의 `content_hash`이며, genesis 값에서 시작한다.
  - 감사 payload는 actor, action, resource type/id, before/after JSON, access reason,
    target PII fields, IP hash, user agent, request id, occurred_at을 포함한다.
  - 감사 로그는 삭제/수정 API를 만들지 않는다. 마스킹된 조회와 hash chain 검증만
    Admin 콘솔에 노출한다.
  - `prev_hash`는 unique constraint로 보호한다. 같은 head에서 두 row가 갈라지는 fork를
    DB가 거부한다.
  - `append_admin_audit()`는 마지막 row 조회 전에 PostgreSQL transaction-level advisory lock을
    획득해 병렬 admin action도 한 체인 head로 직렬화한다.
- **결과**: Admin 운영 행위의 추적성과 변조 감지 기준이 생긴다. 병렬 worker에서도
  app-level append 경로는 한 번에 하나의 head만 확정한다.
- **후속**: T-146의 location-audit async outbox와 함께 장기 보존/partitioning 정책을
  재검토한다.
- **참조**: `docs/api/admin.md`, `docs/compliance/pipa.md`,
  `apps/api/app/models/audit.py`, `apps/api/app/services/admin_audit.py`.

## ADR-035: Trip 실시간 협업은 단일 프로세스 in-memory WebSocket broker로 시작한다

- **상태**: accepted
- **날짜**: 2026-06-06
- **결정자**: 구현 기준 백필 (T-128)
- **컨텍스트**: Sprint 5 DoD는 `WS /ws/trips/{trip_id}` 기반 POI CRUD/reorder
  broadcast와 presence를 요구한다. 현재 운영 모델은 Odroid M1S/N150 단일 노드 가족
  베타이며, WebSocket 수평 확장보다 빠른 vertical slice와 명확한 HTTP optimistic lock
  계약이 우선이다.
- **결정**:
  - `apps/api/app/services/realtime_broker.py`에 process-local in-memory broker를 둔다.
    broker는 `trip_id -> connection set`을 관리한다.
  - `WS /ws/trips/{trip_id}`는 access JWT cookie 또는 query token으로 인증하고,
    `app.trips.owner_user_id` / `app.trip_companions.user_id` DB 조회로 권한을 확인한다.
  - Trip/POI HTTP mutation은 DB commit 후 `trip.updated`, `poi.created`,
    `poi.updated`, `poi.deleted`, `poi.reordered`를 같은 trip 채널에 publish한다.
  - presence는 `presence.heartbeat` 기반으로 `viewing_day`와 online 상태를 broadcast한다.
  - Sprint 5 운영에서는 WebSocket worker 1개 또는 sticky session을 전제로 한다.
  - 다중 worker fan-out, durable replay, restart 이후 presence 보존이 필요해지면 Redis
    Streams 또는 PostgreSQL LISTEN/NOTIFY 기반 broker ADR을 새로 쓴다.
- **결과**:
  - kor-travel-map HTTP feature read와 무관하게 Pinvi 자체 실시간 협업 slice를 검증할 수
    있다.
  - worker 간 broadcast는 아직 보장하지 않는다.
  - offline client replay와 event persistence는 제공하지 않는다.
- **후속**:
  - `apps/web/lib/websocket.ts`와 presence store / conflict dialog 연결.
  - `apps/api/app/services/optimistic_lock.py` 분리 여부는 Trip/POI version 정책이
    복잡해지는 시점에 재검토한다.
- **참조**: `docs/architecture/websocket-broker.md`, `docs/api/websocket.md`,
  `apps/api/app/api/v1/ws.py`, `apps/api/app/services/realtime_broker.py`.

## ADR-036: Curated trip plan은 자체 큐레이션과 kor_travel_map curated_features import를 모두 지원한다

- **상태**: accepted
- **날짜**: 2026-06-12
- **결정자**: 사용자
- **컨텍스트**: ADR-029는 추천 여행 템플릿의 이름을 `curated_trip_plans` 계열로
  정리했지만, curated POI와 kor_travel_map feature의 연결 정책은 모호하게 남았다. 특히
  Pinvi 내부에서 자유 메모/임시 장소 POI는 `feature_id` 없이 존재할 수 있어야
  하지만, kor-travel-map import처럼 이미 알고 있는 kor_travel_map `feature_id`가 함께 들어오는
  경우에는 POI를 feature-backed로 연결할 수 있다.
  또한 2026-06-12 기준 `kor-travel-map`에 `curated_features` 기능이 추가되어,
  Pinvi가 해당 REST API를 호출해 `curated_features`를 Pinvi
  `curated_trip_plans`로 1:1 복사하는 후속 흐름을 설계에 포함해야 한다. 단,
  `curated_features`의 상세 REST 계약과 구현은 아직 Pinvi에 붙지 않았다.
- **결정**:
  - Curated trip plan의 생성 소스는 둘 다 정식이다.
    1. **Pinvi-native 큐레이션**: Admin/운영자가 Pinvi 안에서 직접 기획/생성하는
       추천 plan.
    2. **kor_travel_map `curated_features` import**: Pinvi가 kor-travel-map REST API로
       curated feature 정보를 조회해 Pinvi `curated_trip_plans` /
       `curated_plan_pois`로 1:1 복사하는 추천 plan.
  - `app.trip_day_pois.feature_id`와 `app.curated_plan_pois.feature_id`는 nullable이다.
    POI는 feature 없이도 존재할 수 있다(ADR-031 유지).
  - Curated trip plan은 POI 묶음이며, 각 POI는 선택적으로 kor_travel_map feature에 연결된다.
    외래키는 두지 않고 `feature_id` 문자열만 저장한다(Pinvi ↔ kor_travel_map 책임 분리).
  - kor-travel-map import가 `feature_id`를 제공하는 경우 Pinvi는 같은 curated plan 안에서 해당
    feature-backed POI를 먼저 찾고, 없으면 새 `curated_plan_pois` row를 생성해 plan에
    연결한다. 이미 있으면 기존 POI를 재사용한다.
  - kor_travel_map `curated_features` import에서는 kor_travel_map curated feature 1건을 Pinvi
    curated trip plan 1건으로, 그 하위 항목/POI를 `curated_plan_pois`로 복사한다.
    kor_travel_map 항목이 `feature_id`를 제공하면 feature-backed POI로 저장하고, 제공하지 않거나
    Pinvi-native로 만든 자유 장소는 `feature_id = null`로 저장한다.
  - feature 없는 curated POI는 copy 시 feature 없는 사용자 `trip_day_pois`로 복사된다.
    임시 `curated:<id>` 같은 가짜 feature id를 만들지 않는다.
- **결과**: Pinvi가 자체적으로 만든 추천 plan과 kor_travel_map `curated_features`에서 가져온
  추천 plan이 같은 Pinvi 도메인 모델을 공유한다. 사람/Admin이 만든 자유 POI와
  kor-travel-map import가 만든 feature-backed POI가 같은 curated plan 안에 공존할 수 있고,
  kor_travel_map feature 표준화가 가능한 import 경로는 feature-backed 경로를 사용해 중복 POI 생성을
  줄인다.
- **후속**:
  - kor_travel_map `curated_features` import endpoint와 client를 유지하고, source version/etag
    provenance 컬럼을 갱신한다.
- **참조**: ADR-029, ADR-031, `docs/architecture/notice-plans.md`,
  `apps/api/app/services/notice_plan.py`.

## ADR-037: 로컬 고정 포트는 5432/12101/12105/12301/12501/12505로 재배정한다

- **상태**: superseded by ADR-042
- **날짜**: 2026-06-12
- **결정자**: 사용자
- **컨텍스트**: Sprint 1~4 동안 Pinvi dev/API/Web/RustFS/kor-travel-map 포트가 여러 차례
  바뀌었고, 일부 문서에는 kor_travel_map admin UI 포트와 admin API base가 섞여 남았다.
  2026-06-12 기준 Docker 설정도 새 포트로 다시 로드되었으므로, 저장소의 설정·런북·문서
  전체가 같은 고정값을 따라야 한다.
- **결정**:
  - PostgreSQL host/container 포트는 표준 `5432`를 사용한다.
  - RustFS API는 `12101`, RustFS console은 `12105`를 사용한다.
  - `kor-travel-map` API/Admin API는 `12301`을 사용한다. Pinvi의
    `PINVI_KOR_TRAVEL_MAP_API_BASE_URL`과 `PINVI_KOR_TRAVEL_MAP_ADMIN_BASE_URL` 기본값은
    모두 `http://localhost:12301`이다.
  - `kor-travel-concierge`는 `kor-travel-concierge`로 이름이 바뀌었고 Pinvi와의 직접 관계를
    끊는다. Pinvi는 agent API 포트를 예약하지 않고 `PINVI_AGENT_API_BASE_URL`도
    노출하지 않는다.
  - 본 저장소 Pinvi API는 `12501`, Web UI는 `12505`를 사용한다.
  - Dagster UI는 기존 고정 포트 `9023`을 유지한다.
- **결과**: 로컬 개발, Docker smoke, 문서 예시, 환경변수 기본값이 같은 포트 집합을
  공유한다. kor_travel_map admin API는 `12301`로 명확해져, 과거 admin UI 포트와 혼동하지 않는다.
- **참조**: `AGENTS.md`, `CLAUDE.md`, `.env.example`, `infra/docker-compose.yml`,
  `infra/docker-compose.app.yml`, `scripts/dev-up.sh`, `scripts/docker-app.sh`,
  `docs/runbooks/README.md`.

## ADR-038: HTTP rate limit은 운영에서 Postgres 고정-window 버킷을 사용한다

- **상태**: accepted
- **날짜**: 2026-06-13
- **결정자**: Codex
- **컨텍스트**: T-195는 `/public/*`, 인증 사용자 경로, 로그인/가입/재설정 같은 abuse
  표면에 공통 rate-limit를 요구한다. 단순 process-local memory limiter는 Uvicorn worker
  2개와 Odroid+N150 양 노드 운영에서 한도를 worker/node 수만큼 늘려 버린다. Redis는
  현재 Pinvi 운영 스택에 없고, Postgres는 이미 필수 의존이다.
- **결정**:
  - FastAPI 전역 `RateLimitMiddleware`를 둔다.
  - `PINVI_RATE_LIMIT_BACKEND=auto` 기본값은 `production`/`staging`에서 Postgres,
    `development`/`test`/`smoke`에서 memory를 사용한다.
  - 운영/staging Postgres backend는 `app.rate_limit_buckets`에 1분 fixed-window counter를
    atomic upsert로 저장한다.
  - bucket key는 정책명과 IP/user/token/email 식별자를 HMAC-SHA256으로 해시해 저장하고,
    원문 IP/email/token은 DB에 저장하지 않는다.
  - rate-limit 저장소 장애는 기본 fail-closed(`503 SERVICE_UNAVAILABLE`)다.
  - `/health`, `/health/db`, `/metrics`, `/docs`, `/redoc`, `/openapi.json`과 `OPTIONS`는
    rate-limit에서 제외한다.
- **결과**:
  - 운영에서 다중 worker/두 노드가 같은 한도를 공유한다.
  - Redis 없이도 Sprint 6 운영 배포 전 abuse guard를 닫을 수 있다.
  - 모든 요청에 Postgres hit가 생기므로 고트래픽 전환 시 Redis/token-bucket ADR을
    새로 검토한다.
- **후속**:
  - T-195 구현: `app.rate_limit_buckets` migration, `RateLimitMiddleware`, 단위 테스트,
    API 문서 갱신.
  - T-108 운영 배포 문서에서 production/staging은 `PINVI_RATE_LIMIT_BACKEND=postgres` 또는
    `auto` + `PINVI_ENVIRONMENT=production`을 강제한다.
- **참조**: `docs/api/common.md` §8, `docs/api/public.md`, `apps/api/app/middleware/rate_limit.py`.

## ADR-039: 운영 노드 간 Postgres streaming replication은 사용하지 않는다

- **상태**: accepted
- **날짜**: 2026-06-13
- **결정자**: 사용자
- **컨텍스트**: T-108 운영 배포 자동화 foundation에서 N150을 primary, Odroid를 replica/hot-standby로
  두고 Postgres streaming replication runbook과 doctor 점검을 추가하려 했다. 사용자는 현재 운영
  모델에서 streaming replication을 사용하지 않는다고 결정했다.
- **결정**:
  - N150/Odroid 병행 운영은 유지하되, Postgres streaming replication은 구성하지 않는다.
  - `pg_basebackup`, physical replication slot, `pg_is_in_recovery()` 기반 doctor,
    `pg_promote()` 기반 failover 절차를 Pinvi 운영 문서와 스크립트에 두지 않는다.
  - Odroid는 replica/hot-standby가 아니라 ARM64 smoke, backup/restore 훈련, 필요 시 수동
    대체 배포 노드로 둔다.
  - 장애 대응은 `docs/runbooks/backup-restore.md`의 snapshot/restore 절차와 수동
    Cloudflare/nginx 전환을 따른다.
- **근거**:
  - 현재 운영 규모에서는 live replication의 설정·감시·split-brain 위험이 이득보다 크다.
  - 이미 ADR-022에 backup/restore 핫스왑 정책이 있으므로, 우선 그 절차를 정본으로 삼는다.
- **결과 (긍정)**:
  - 운영 runbook과 doctor가 실제 운영 방식과 일치한다.
  - replica/promote 오조작으로 인한 split-brain 위험을 줄인다.
- **결과 (부정)**:
  - N150 장애 시 RPO/RTO는 최신 backup과 수동 복구 숙련도에 의존한다.
  - Odroid는 즉시 write 가능한 hot standby가 아니다.
- **후속**:
  - T-108 문서/스크립트에서 streaming replication 관련 내용과 코드를 제거한다.
  - 향후 live replication이 다시 필요해지면 새 ADR로 Patroni/repmgr/managed Postgres 등
    대안을 비교한다.
- **참조**: ADR-022, ADR-023, `docs/runbooks/deploy.md`,
  `docs/runbooks/backup-restore.md`.

## ADR-040: Docker 빌드/실행은 kor-travel-docker-manager를 1차 경로로 쓰고 docker-app.sh로 폴백한다

- **상태**: accepted
- **날짜**: 2026-06-13
- **결정자**: 사용자
- **컨텍스트**: Pinvi가 의존하는 Docker 인프라(통합 PostgreSQL/PostGIS, RustFS,
  Grafana, cAdvisor, Prometheus, `kor-travel-geo` API/Web)는 `kor-travel-map`,
  `kor-travel-concierge`, `kor-travel-geo`와 공용이다. 이 공용 인프라는 별도 저장소
  `kor-travel-docker-manager`가 `ktdctl` CLI / API / 대시보드와
  `config/docker-targets.yml` target registry로 일괄 관리한다(`docker compose up -d`
  + idempotent 초기화). 그동안 Pinvi 문서는 `scripts/docker-app.sh`만 Docker 진입으로
  안내해 공용 인프라와 앱 컨테이너 경로가 분리되지 않았다.
- **결정**:
  - **Docker 빌드/실행의 1차 경로는 `kor-travel-docker-manager`**다. 공용 의존 인프라와
    Pinvi API/Web 앱 컨테이너는 `ktdctl srv --build`로 올린다(`srv`는 `pinvi` target의
    짧은 별칭, db→storage→gra→cadv→prom→geo→conc→map→pinvi 누적).
  - **Pinvi 폴백 app smoke**는 `infra/docker-compose.app.yml` +
    `scripts/docker-app.sh build/up/smoke`가 맡는다. docker-manager가 없거나 Pinvi app만
    격리 검증해야 할 때 사용한다.
  - **폴백**: `kor-travel-docker-manager` 미설치/미기동, `ktdctl` 부재, WSL/네트워크
    문제 등으로 1차 경로를 쓸 수 없으면 `scripts/docker-app.sh`(공용 인프라 일부는
    `infra/docker-compose.yml`)로 진행한다. 폴백 시 포트 정책(ADR-042)을 유지한다.
- **결과**: 공용 인프라와 Pinvi 앱 컨테이너는 한 곳(`ktdctl`)에서 일관되게 올라가고,
  docker-manager가 없는 환경에서도 Pinvi 저장소 스크립트 폴백으로 막히지 않는다.
- **참조**: `docs/runbooks/docker-app.md` §0, `CLAUDE.md`, `AGENTS.md`,
  `kor-travel-docker-manager/docs/docker-management.md`, `scripts/docker-app.sh`,
  `infra/docker-compose.app.yml`.

## ADR-041: Expo `apps/mobile` 구조 스캐폴드를 추가하고 활성화는 Sprint M-1로 분리한다

- **상태**: accepted (2026-06-16 **활성화 완료**)
- **날짜**: 2026-06-13
- **결정자**: 사용자 + Claude
- **2026-06-16 활성화**: Sprint M-1 활성화 완료 — `apps/mobile`을 root `workspaces`에 등록하고
  Expo SDK 56 의존성을 설치(`package-lock.json` 갱신, `expo install --check`로 네이티브 모듈
  정합). 루트 `npm run typecheck`에 `apps/mobile`이 포함되며 전 workspace typecheck/lint/web
  build/Vitest(68) 통과. **의도적 CI-safe 유예는 종료** — web CI `npm ci`가 Expo 트리를 설치하고
  typecheck에 `apps/mobile`을 포함한다(web CI가 다소 무거워짐). 후속(2026-06-16): `expo-doctor`
  **21/21 통과**(빌드 준비) — `newArchEnabled` flag 제거(SDK 56 기본), metro hierarchical lookup
  복원, react 19.2.6 단일화. EAS 클라우드 빌드는 Expo 계정 로그인이 필요해 사용자가
  `eas login` / `eas init` / `eas build`를 수행한다.
- **컨텍스트**: ADR-011이 Next.js 웹 + Expo 모바일 공용 패키지 구조를 박았고,
  `packages/*`(schemas/api-client/state/design-tokens/hooks/i18n)는 처음부터 플랫폼
  무관 + 어댑터 주입형으로 작성됐다(frontend.md §2, §6). 남은 것은 `apps/mobile` Expo
  앱을 실제로 박는 일이다. 다만 CI(`.github/workflows/web.yml`)가 `npm ci`로 설치하므로,
  `apps/mobile`을 root `workspaces`에 넣으면 Expo/RN 의존성을 `package-lock.json`에
  커밋해야 하고(안 하면 `npm ci` 실패), 커밋하면 매 web CI가 무거운 Expo 트리를 설치하게
  된다.
- **결정**:
  - `apps/mobile`에 **Expo SDK 53 구조 스캐폴드**를 추가한다: `app/`(Expo Router 진입 +
    `(auth)` group), `lib/`(api/location/storage/stores 플랫폼 어댑터),
    app.json/babel/metro/tailwind(NativeWind)/tsconfig, 공용 패키지 import 검증. 공용
    로직·데이터는 `@pinvi/*`에서 그대로 가져오고 `apps/mobile`은 어댑터 + RN 화면만
    갖는다(frontend.md §2.1).
  - **CI-safe를 위해 스캐폴드는 install 그래프 밖에 둔다**: root `workspaces`에 등록하지
    않고 의존성도 설치하지 않는다(`package-lock.json` 미변경). 따라서 스캐폴드 추가 PR은
    web/api/etl CI를 트리거하지 않고 머지된다.
  - **활성화(workspaces 등록 + `npm install` + `expo install` 버전 정합 + development
    build 생성 + 화면 구현 + EAS)는 별도 Sprint M-1**에서 수행한다. 절차는
    `apps/mobile/README.md`이며, 런타임 기준선은 ADR-043을 따른다.
- **결과**: ADR-011의 모바일 구조가 코드로 박혔고, 활성화 비용(설치/화면)만 남았다. 공용
  패키지가 RN에서 import되는 wiring을 코드로 증명한다. 본 스캐폴드의 CI footprint는 0이다.
- **참조**: `apps/mobile/README.md`, `docs/architecture/frontend.md` (§2, §6, §8, §10),
  ADR-011, `.github/workflows/web.yml`, `.github/workflows/aggregate-ci.yml`.

## ADR-042: 로컬 포트 정책은 `kor-travel-docker-manager` target 대역을 따른다

- **상태**: accepted
- **날짜**: 2026-06-13
- **결정자**: 사용자 + Codex

### 컨텍스트

ADR-037은 Pinvi API/Web과 `kor-travel-map`을 각각 `12501`/`12505`/`12301`에 고정했다.
하지만 `kor-travel-docker-manager`가 TripMate 계열 공용 target registry와
`docs/ports.md`를 정리하면서 `db → storage → gra → cadv → prom → geo → conc → map → pinvi`
순서의 100 단위 포트 대역을 정본으로 제공한다. Pinvi가 예전 포트를 계속 쓰면
`kor-travel-geo`, `kor-travel-map`, 공용 observability와 충돌한다.

### 결정

- 로컬 포트 정책의 source of truth는 `kor-travel-docker-manager`
  `config/docker-targets.yml`과 `docs/ports.md`다.
- PostgreSQL host 포트는 표준 `5432`를 유지한다.
- RustFS host 포트는 API `12101`, console `12105`를 유지하되, 컨테이너 내부 포트는
  docker-manager와 같이 API `9000`, console `9001`을 사용한다.
- 공용 observability는 Grafana `12205`, cAdvisor `12301`, Prometheus `12401`을 사용한다.
- `kor-travel-geo`는 API `12501`, Web UI `12505`를 사용한다. Pinvi의
  `PINVI_KOR_TRAVEL_GEO_BASE_URL` 기본값은 `http://localhost:12501`이다.
- `kor-travel-concierge`는 API `12601`, MCP `12602`, Web UI `12605` 대역을 사용한다.
  Pinvi는 이 서비스를 직접 호출하지 않는다.
- `kor-travel-map`은 API/Admin API `12701`, Dagster `12702`, Web UI `12705`를 사용한다.
  Pinvi의 `PINVI_KOR_TRAVEL_MAP_API_BASE_URL`과
  `PINVI_KOR_TRAVEL_MAP_ADMIN_BASE_URL` 기본값은 `http://localhost:12701`이다.
- Pinvi 자체 로컬 포트는 API `12801`, Dagster dev `12802`, Web UI `12805`다.
  docker-manager가 현재 Pinvi Dagster를 관리하지 않으므로 Dagster는 Pinvi 대역의
  추가 service 포트(`+2`)로 배정한다.
- `kor-travel-docker-manager` 자체 Backend API와 Dashboard는 `12901`, `12905`를 사용한다.
- Docker 실행 1차 경로는 `ktdctl srv --build`이며, Pinvi 폴백 스크립트와 compose도 같은
  포트 계약을 따른다.

### 근거

- 모든 TripMate 계열 앱이 같은 포트 대역 규칙을 공유해야 동시 기동과 포트 점유 정리가
  예측 가능하다.
- Pinvi API가 `12501`을 계속 쓰면 새 `kor-travel-geo` API 대역과 충돌한다.
- `kor-travel-map` API/Admin API가 `12701`로 이동했으므로 Pinvi HTTP client 기본값도
  같은 host 포트를 바라봐야 한다.

### 결과

- ADR-037의 포트 고정값은 본 ADR이 supersede한다.
- `.env.example`, API settings, Web 기본 API URL, Playwright mock, Docker compose,
  dev/smoke/deploy scripts, runbook 문서가 `kor-travel-docker-manager` 대역과 정렬된다.
- 기존 로컬 `.env`에 예전 포트가 남아 있으면 새 기본값을 덮어쓰므로 수동 정리가 필요하다.

### 참조

- `kor-travel-docker-manager/config/docker-targets.yml`
- `kor-travel-docker-manager/docs/ports.md`
- `docs/runbooks/docker-app.md`
- `docs/runbooks/local-dev.md`
- `.env.example`
- `infra/docker-compose.yml`
- `infra/docker-compose.app.yml`

## ADR-043: 모바일 앱은 Expo Dev Client와 EAS Build를 기준으로 하고 Expo Go를 사용하지 않는다

- **상태**: accepted
- **날짜**: 2026-06-15
- **결정자**: 사용자 + Codex
- **2026-06-16 갱신**: 기준 Expo SDK를 **53 → 56**으로 상향한다(사용자 결정). RN 0.85 / React
  19.2 기준이며 `apps/mobile/package.json`·README·`frontend.md`·`expo-implementation-plan.md`와
  maplibre-vworld-react example(SDK 56)에 정합한다. Dev Client / EAS / New Architecture /
  Android minSdk 24 / VWorld 비번들 정책은 동일하게 유지한다.

### 컨텍스트

ADR-041로 `apps/mobile` Expo SDK 53 스캐폴드는 추가됐지만, 실제 모바일 실행 경로가
Expo Go인지, Expo Dev Client인지, EAS Build인지가 명시적으로 고정되지 않았다. Pinvi
모바일은 위치, SecureStore, 향후 VWorld 지도/토큰 발급, native map 계층, React Native
New Architecture 검증을 포함하므로 Expo Go의 고정 native runtime에 기대면 실제 운영
바이너리와 개발 검증이 갈라진다. 또한 Android 최소 SDK와 VWorld API key 처리 방식은
초기 스캐폴드 단계에서 기준선을 박아야 후속 Sprint M-1 구현이 흔들리지 않는다.

### 결정

- `apps/mobile`은 **Expo Dev Client**를 사용한다. development build에는
  `expo-dev-client`를 포함하고, Metro 실행은 `expo start --dev-client`를 기준으로 한다.
- **Expo Go는 사용하지 않는다.** README, npm script, 활성화 절차에서 Expo Go QR 실행 경로를
  안내하지 않는다.
- **EAS Build를 모바일 빌드 정본으로 둔다.** `apps/mobile/eas.json`에
  `development` / `preview` / `production` profile을 두며, `development` profile은
  `developmentClient: true`와 internal distribution을 사용한다.
- React Native는 **New Architecture 기준**이다. SDK 56(RN 0.85)에서 New Architecture가
  기본이며, `app.json`의 `newArchEnabled` flag는 SDK 56 app config 스키마에서 제거됐다(별도 설정
  불필요 — `expo-doctor`가 추가 property로 거부).
- Android는 **`minSdkVersion` 24 이상**을 기준으로 한다(Expo SDK 56의 `expo.modules.ui`가
  minSdk 24를 요구 — 2026-06-16 EAS 빌드 manifest merge 실패로 확인). Expo managed/CNG 흐름에서
  `expo-build-properties` config plugin으로 `android.minSdkVersion = 24`을 설정한다.
- 모바일 앱에는 `EXPO_PUBLIC_VWORLD_API_KEY`를 두지 않는다. 앱 설정에는 Pinvi API base와
  VWorld server-issued token endpoint 같은 public 설정만 둔다. 실제 VWorld API key/token은
  Pinvi API가 발급하고, 모바일 클라이언트는 그 endpoint를 호출해 단기 token 또는 proxy 세션을
  받아 사용한다.

### 근거

- Expo 공식 문서에서 development build는 `expo-dev-client`를 포함한 debug build이며,
  production-grade 앱은 Expo Go보다 development build가 적합하다고 설명한다.
- EAS Build의 기본 development profile은 `developmentClient: true` + internal distribution을
  기준으로 하므로 Pinvi의 장치 테스트/팀 배포 흐름과 맞다.
- Expo Go는 앱 native library set이 고정되어 있어 native config, custom plugin, key 발급형
  지도 구조를 검증하기 어렵다.
- native 앱에 VWorld key를 직접 번들하면 웹의 origin whitelist와 같은 보호가 불가능하다.
  모바일은 서버 발급/프록시 세션 방식으로 분리하는 편이 보안·폐기·rate-limit에 유리하다.

### 결과

- `apps/mobile/package.json`의 기본 start/android/ios script는 Dev Client 경로를 사용한다.
- `apps/mobile/eas.json`이 추가되어 EAS Build profile이 코드로 고정된다.
- `apps/mobile/app.json`은 `expo-dev-client`, `expo-build-properties`(minSdk 24),
  VWorld server-issued 설정을 갖는다(New Architecture는 SDK 56 기본).
- Sprint M-1에서 workspace 등록과 lockfile 갱신을 하더라도 Expo Go로 후퇴하지 않는다.

### 후속

- Sprint M-1 활성화 시 WSL ext4 미러에서 `npm install`과
  `npm --workspace @pinvi/mobile exec -- expo install --check`를 실행해 Expo SDK 56 호환
  버전을 lockfile에 반영한다.
- 모바일 지도 구현 전 Pinvi API에 VWorld 단기 token/proxy session 발급 endpoint를 추가하고,
  rate-limit/audit/redaction 정책을 문서화한다.
- 모바일 지도 엔진(`maplibre-react-native` 또는 WebView 임베드)은 별도 ADR로 확정한다.

### 참조

- ADR-011, ADR-041
- `apps/mobile/README.md`
- `docs/architecture/frontend.md`
- `docs/integrations/maplibre-vworld.md`

## ADR-044: 모바일 지도 엔진은 `maplibre-vworld-react`(`vworld-map-rn`)이며 vendored tarball로 소비한다

- **상태**: accepted
- **날짜**: 2026-06-16
- **결정자**: 사용자 + Claude

### 컨텍스트

ADR-043의 후속(“모바일 지도 엔진은 별도 ADR로 확정”). 모바일 지도는 별 저장소
`digitie/maplibre-vworld-react`(RN 패키지 `vworld-map-rn`, 공통 `vworld-map-core`)가 소유하며,
`@maplibre/maplibre-react-native` 위에서 VWorld 타일을 표출한다. 이 패키지들은 **의도적으로 npm에
발행하지 않는다**(maplibre-vworld-js와 동일 방침). 따라서 Pinvi가 소비하려면 발행 없이 설치
가능한 경로가 필요하고, npm은 workspace-symlink된 `vworld-map-core`를 단일 tarball로 번들하지
못하므로 `core` + `rn` **두 tarball을 함께 핀**해야 한다(해당 저장소 #2).

### 결정

- 모바일 지도 엔진은 `vworld-map-rn`으로 확정한다(WebView 임베드 대안 폐기).
- 소비는 **vendored tarball**(`apps/mobile/vendor/vworld-map-{core,rn}-<ver>.tgz`)을 `file:`
  의존으로 핀한다. `core`/`rn` 두 개를 함께 핀해 `rn`의 `vworld-map-core` 의존을 top-level에서
  만족시킨다. CI(`npm ci`)가 네트워크/외부 release asset에 의존하지 않고 self-contained.
- VWorld 키는 ADR-043대로 **server-issued** — `GET /mobile/vworld/token`으로 받아
  `VWorldMapView`의 `apiKey`로 주입한다. 앱에 키를 번들하지 않는다.
- `@maplibre/maplibre-react-native`는 네이티브 모듈이므로 config plugin을 `app.json`에 추가하고,
  지도 화면은 **EAS Dev Client 빌드에서만** 동작한다(Expo Go 미사용, ADR-043).
- 라이브러리 변경이 필요하면 `maplibre-vworld-react`에 이슈→PR→머지 후 tarball을 재pack해 핀을
  갱신한다(예: 본 라운드의 #21 markers color parity).

### 근거

- npm 미발행은 상위 라이브러리 방침이고, vendored tarball은 외부 release asset URL보다 CI
  재현성이 높다(블롭이 repo에 self-contained, lockfile integrity로 고정).
- `vworld-map-rn`은 `tileUrlTransform`(키 주입 훅)·controlled camera(`flyTo`/`fitBounds`)·
  도메인 프리미티브(Place/Price/Weather/Cluster)·Marker prop parity를 제공해 ADR-043 키 정책과
  Pinvi 마커 팔레트를 만족한다(해당 저장소 #3/#8/#5/#6/#10 해소 확인).

### 후속

- 트립 POI 16색 마커/클러스터·feature 검색(POI 추가)·VWorld token TTL 갱신을 후속 화면에서 연결.
- 라이브러리 버전 핀 갱신 시 `apps/mobile/vendor/` tarball + lockfile을 함께 갱신한다.

### 참조

- ADR-043, ADR-026(외부 계약), `digitie/maplibre-vworld-react`(#2 git/tarball 설치, #21 markers parity)
- `docs/architecture/expo-implementation-plan.md` §4, `apps/mobile/app/(app)/map.tsx`

## 다음 ADR 번호

- 다음 신규 ADR = **ADR-045**
- 사용자 정의 결정이 새로 발생하면 본 §끝에 추가.
