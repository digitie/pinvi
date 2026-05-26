# AGENTS.md

## AI 에이전트 도구 지원 — `AGENTS.md` 단일 진실

본 저장소는 **여러 AI 코딩 도구를 모두 지원**한다:

| 도구 | 1차 진입 파일 |
|------|-------------|
| **Claude Code / Claude Agent SDK** | `CLAUDE.md` → `AGENTS.md` → `SKILL.md` |
| **OpenAI Codex (CLI)** | `AGENTS.md` |
| **Google Antigravity (Gemini)** | `AGENTS.md` |
| **Cursor / Copilot (도메인 작업)** | `AGENTS.md` + `SKILL.md` |

각 도구가 처음 읽는 파일이 다르므로 **두 파일 (`AGENTS.md` + `CLAUDE.md`)이 항상
같은 결정·룰·식별자를 반영**해야 한다 (ADR-016).

- `AGENTS.md` 갱신 시 `CLAUDE.md`의 "1쪽 진입 요약" 동기 갱신 — 필수
- `CLAUDE.md` 갱신 시 `AGENTS.md` 본문 + 진입 절차표 동기 갱신 — 필수
- `SKILL.md` (도메인 어휘 / DO NOT)는 같은 갱신 PR에 포함될 가능성 높음 — 함께 검토

**ADR-016 핵심**: 어떤 AI 도구가 진입하더라도 같은 결정을 적용할 수 있도록 두
파일 사이의 fact drift 방지.

## 문서 언어 정책

본 저장소의 모든 Markdown 문서는 한국어로 작성한다. 공식 API 필드명, 코드 식별자,
명령, URL, 라이브러리·제공자 영어, 환경변수처럼 그대로 보존해야 하는 값만 영어를
유지한다. 신규 문서는 기존 문서 모두 동일 규칙을 우선한다.

## 정체성

본 저장소(GitHub 이름 `tripmate`)는 **한국 여행 계획·기록·공유 애플리케이션**의
모노레포다. 백엔드(FastAPI) / 프론트엔드(Next.js) / ETL(Dagster) / 인프라
manifest / 문서가 들어 있다.

본 앱은 지도 feature 도메인을 직접 소유하지 않는다. 지도 feature(place /
event / notice / price / weather / route / area) 정규화·저장은 별 저장소
`python-krtour-map`이 소유하고, TripMate는 그 라이브러리를 **함수 직접 호출**
(REST 없음)로 사용한다.

이전(v1) 구현은 `v1` 브랜치에 보존되어 있다. master(main)는 v2 사양으로 처음부터
다시 구현한다(ADR-001).

## 식별자 (일동 방지)

| 항목 | 값 |
|------|----|
| GitHub 저장소 이름 | `tripmate` |
| 백엔드 import (계획) | `from tripmate.api import ...`, `from tripmate.etl import ...` |
| 프론트 패키지 (계획) | `apps/web` (Next.js App Router) |
| 환경변수 prefix | `TRIPMATE_*` |
| PostgreSQL DB 이름 (개발) | `tripmate` |
| Postgres schema (자체) | `app`, `ops` (TripMate 소유) |
| Postgres schema (`python-krtour-map` 소유) | `feature`, `provider_sync` |
| 객체 저장소 | RustFS (S3 호환) — `app` 도메인 첨부 + `feature` 미디어 분리 버킷 |
| Dagster code location | `apps/etl` |
| Admin 콘솔 | `apps/web/app/admin/` |
| 운영 노드 | Odroid M1S (Ubuntu 24.04 + Docker Compose) |

## 의존 라이브러리 (별 저장소)

| 저장소 | 역할 |
|--------|------|
| `python-krtour-map` | 지도 feature 정규화·저장 (함수 라이브러리) |
| `python-kraddr-base` | 한국 행정구역 / 카테고리 base |
| `python-kraddr-geo` | 주소 · 법정동 · 지오코딩 |
| `python-visitkorea-api` | 한국관광공사 API (축제·관광지·국가유산 후보) |
| `python-kma-api` | 기상청 단기/중기/실황/특보 |
| `python-airkorea-api` | 환경공단 대기질 |
| `python-opinet-api` | 한국석유공사 유가 |
| `python-krex-api` | 한국도로공사 휴게소·고속도로 |
| `python-khoa-api` | 국립해양조사원 해양 지수 / 해수욕장 |
| `python-knps-api` | 국립공원공단 트래킹 / 안전 |
| `python-krmois-api` | 행정안전부 지방행정 / 인허가 LOCALDATA |
| `python-krforest-api` | 산림청 휴양림 / 수목원 |
| `python-krheritage-api` | 국가유산청 문화재 |
| `python-kasi-api` | 한국천문연구원 일출·일몰·달 |
| `python-krbluelink-api` | 블루링크 (차량) |
| `python-mcst-api` | 문화체육관광부 |
| `python-mois-api` | 행정안전부 base |
| `python-datagokr-api` | data.go.kr generic |
| `python-vworld-api` | VWorld geocoder / 경계 |
| `python-krairport-api` | 한국공항공사 공항 / 항공편 |
| `python-kraddr-gop` | 우편번호 / 도로명 base |
| `maplibre-vworld-js` | **TripMate 지도 클라이언트** — VWorld + MapLibre GL JS 선언형 React (ADR-015). Place/Price/Weather 마커 + `PolygonArea` + `RouteLine` + `ClusterLayer` + `Popup` generic primitive 제공 (TripMate 도메인 wrapper / 16색 팔레트 상수는 라이브러리에 없음 — `apps/web/lib`에서 직접 구현). `apps/web`이 npm 또는 git URL pin으로 직접 import. wrapper 금지 — 부족 기능은 라이브러리 PR (ADR-005 mirror) |

상세 사용 정책은 `python-krtour-map`의 `docs/external-apis.md`와 본 저장소의
`docs/krtour-map-integration.md`.

## 개발 환경 정책 (PC, WSL)

### Worktree + CodeGraph (ADR-017)

본 저장소는 AI 도구마다 **고정 worktree**를 둔다. trunk(`F:/dev/tripmate` 또는
`~/tripmate-workspaces/tripmate`)는 사람이 직접 만지는 checkout이며, AI 도구는
trunk를 절대 편집하지 않는다.

| AI 도구 | worktree 이름 | 예시 경로 |
|---------|--------------|----------|
| Claude Code | `geo-claude` | `F:/dev/tripmate-geo-claude` |
| OpenAI Codex (CLI / VS Code) | `geo-codex` | `F:/dev/tripmate-geo-codex` |
| Google Antigravity 2.0 | `geo-antigravity` | `F:/dev/tripmate-geo-antigravity` |

- **worktree는 영속** — 작업마다 새로 만들지 않는다.
- **작업마다 브랜치만 새로**: `git fetch && git switch -c agent/<agent>-<task> main`.
- **CodeGraph** (`colbymchenry/codegraph`) 인덱스는 worktree마다 1회
  `codegraph init -i`, 이후 task 시작 시 `codegraph sync`.
- `.codegraph/` 디렉터리는 `.gitignore` 박힘 (로컬 SQLite, 머신/worktree마다 별개).
- 절차 상세는 `docs/runbooks/codegraph-worktrees.md` (ADR-017).

### WSL ext4 미러

PC 개발은 **WSL ext4** 또는 **WSL 미러 디렉토리**에서 수행한다. NTFS 마운트에서
직접 `git`/`pytest`/`docker`/`npm`을 실행하지 않는다 — 파일 권한, inotify,
심볼릭 링크, 빠른 I/O 성능 모두 저하된다.

- **코드/가상환경/git**: WSL ext4 미러 (`~/tripmate-workspaces/tripmate/`).
- **데이터(`dataset/`, `refdocs/`)**: NTFS의 프로젝트 디렉토리 (예:
  `/mnt/f/dev/tripmate/dataset/`). MOIS localdata zip, krheritage SHP, fixture
  대용량은 모두 NTFS. ext4 작업 디렉토리에는 심볼릭 링크 또는 NTFS 직접 참조.
- **테스트**: 단위 테스트 픽스처는 소량으로 ext4. 통합/e2e는 NTFS `dataset/`/
  `refdocs/`를 reference.
- **카피 정책**: 작업이 끝나면 ext4 → NTFS로 rsync. Git source of truth는 ext4.

자세한 절차는 `docs/dev-environment.md`. Windows 재설치 후 옵션 인수인계는
`docs/windows-reinstall-recovery.md`에 함께 둔다 (코드 작성 단계 진입 시 작성).

작업 흐름:

- WSL2 미러 디렉토리(`~/tripmate-workspaces/tripmate`)에서 실행할 명령은
  `wsl.exe -e bash -lc "cd ~/tripmate-workspaces/tripmate && ..."` 형태로 감싼다.
- 명령 실행 전후로 현재 프로젝트 디렉토리(`F:\dev\tripmate`)와 WSL 미러를 동기한다.
- PowerShell `rg.exe`를 사용하지 않는다. 권한 문제와 WindowsApps 경로 오염을 피하기
  위해 `wsl.exe -e bash -lc "... rg ..."`로 WSL native `rg`만 사용한다.
- Windows PowerShell로 한국어 문서를 읽을 때는 `Get-Content -Encoding UTF8`을 명시한다.

## 지시 우선순위

1. **`docs/decisions.md`의 accepted ADR** — 이미 박힌 결정. 충돌하면 멈추고
   ADR을 superseded로 갱신할지 사용자에게 묻는다.
2. **본 파일 `AGENTS.md`** — 작업 규칙.
3. **`SKILL.md`** — 도메인 어휘, DO NOT.
4. **`docs/agent-guide.md`** — 작업·문서화 가이드 (커밋/PR/체크리스트).
5. **`docs/sprints/SPRINT-N.md`** — 현재 Sprint의 진입/산출물/DoD.
6. **개별 문서** — `docs/architecture.md`, `docs/data-model.md`, ...
7. **이전 작업 일지 (`docs/journal.md`)** — 컨텍스트.

본 우선순위가 충돌하면 1번이 이긴다. 새 결정은 ADR로 박는다.

## AI Agent 작업 진입 절차

새 세션 시작 시 정확히 이 순서로:

1. **`CLAUDE.md`** — 1쪽 진입 요약 (저장소 정체성 + 현 단계)
2. **본 파일 `AGENTS.md`** — 작업 룰, DO NOT, 책임 경계
3. **`SKILL.md`** — 도메인 어휘 + 자주 묻는 작업 표
4. **`docs/agent-guide.md`** — 결정·기록 5종 + ADR 규약 + PR 워크플로
5. **`docs/sprints/README.md`** — 현재 Sprint 위치 확인
6. **`docs/resume.md`** — "다음 한 작업" + 진척도
7. **`docs/journal.md` 최신 3건** — 직전 컨텍스트

작업 종류별 다음 진입 문서:

| 작업 종류 | 추가 진입 문서 |
|----------|----------------|
| API endpoint 신규/수정 | `docs/api/<domain>.md` → `docs/api/common.md` → `docs/data-model.md` |
| DB schema 변경 | `docs/postgres-schema.md` → `docs/conventions/database.md` → `docs/data-model.md` |
| 라이브러리 (`python-krtour-map`) 호출 | `docs/krtour-map-integration.md` → 라이브러리 저장소 `docs/agent-guide.md` |
| 외부 통합 (Resend/OAuth/Telegram/Gemini) | `docs/integrations/<service>.md` → `docs/compliance/data-policy.md` |
| Frontend UI | `docs/architecture/frontend.md` → `docs/design/marker-palette.md` → 루트 `DESIGN.md` |
| Admin 콘솔 | `docs/api/admin.md` → `docs/runbooks/admin.md` → `docs/spec/v8/04-admin.md` |
| ETL asset | `docs/runbooks/etl.md` → `docs/architecture/dagster-etl-bridge.md` |
| 인프라 / 배포 | `docs/runbooks/{local-dev,docker-app,odroid-docker}.md` |
| 컴플라이언스 (PII/위치) | `docs/compliance/{lbs-act,pipa}.md` → `docs/architecture/user-location.md` |
| 테스트 작성 | `docs/conventions/testing.md` → 해당 도메인 문서 |

## 작업 단위 / 커밋 / PR

`docs/agent-guide.md` §7 (변경 분류별 체크리스트)과 §7.5 (PR 워크플로) 따른다.
**main 직접 push 금지** (ADR-001 후속). 모든 변경은 feature branch + PR.

브랜치 명명: `feat/<topic>` / `fix/<topic>` / `chore/<topic>` / `docs/<topic>` /
`refactor/<topic>` / `adr/<short>` / `agent/<agent>-<topic>` (ADR-017 worktree
정책 — `agent` = `claude` / `codex` / `antigravity`).

### Sprint 4까지 PR 리뷰·수정·머지 운영

Sprint 4 완료 전까지 새 PR이 올라오거나 draft가 `ready_for_review`로 전환되면
`docs/runbooks/pr-review-sprint4.md`를 따른다. `.github/workflows/codex-pr-monitor.yml`은
5분마다 열린 PR을 감시하고, 최신 head SHA 리뷰 마커가 없는 PR을 다시 리뷰한다.

- 리뷰 후 상세 코멘트를 남기고, 필요한 코드 수정까지 직접 수행한다.
- 변경량 최소화보다 Sprint 1~4를 버틸 장기 설계 정합성을 우선한다.
- 올바른 수정 위치가 `python-krtour-map`, `maplibre-vworld-js`, `python-kraddr-*`,
  provider 라이브러리라면 해당 저장소 PR을 먼저 만들고 머지한 뒤 TripMate를 sync한다.
- TripMate PR merge는 차단 코멘트, 검증, 문서/journal/resume, 기반 라이브러리 sync가
  끝난 뒤 수행한다.

## 코드 작성 금지 (현 단계)

설계·문서화 단계에서는 `apps/`, `packages/`, `infra/`에 코드를 작성하지 않는다.
허용되는 변경:

- `docs/` 신규/수정
- `AGENTS.md`, `SKILL.md`, `CLAUDE.md`, `README.md`
- `.env.example` 추가
- `.gitignore`, `.gitattributes`, `LICENSE`
- Sprint 1 진입 PR에 한해 `apps/` scaffolding과 `packages/` placeholder 허용

코드 작성 요청이 들어오면:

1. 사용자 의도 명확화 (어떤 컴포넌트/계층/엔드포인트인지)
2. ADR이 필요한지 확인
3. 테스트 우선 작성 (`docs/test-strategy.md` 참고)
4. 구현
5. 통합 테스트 + (DB 닿는 경우) EXPLAIN 검증
6. journal + resume + decisions/CHANGELOG (해당 시)

## 작업 흐름 룰 요약

- 명확한 의도가 없으면 추측하지 말고 `AskUserQuestion`(4지선다 + Other) 사용.
- 여러 파일·DB schema·서비스 경계를 건드리면 `docs/execplan/<task-name>.md`를
  작성/갱신한다.
- 의미 있는 변경은 테스트와 문서 갱신을 포함하고, 실행한 검사 명령과 환경
  (WSL2/Windows)을 보고한다.
- 유사한 실수가 반복되면 원인과 재발방지 기준을 관련 문서/runbook/skill에 남긴다.
- Docker, Compose, PostgreSQL/PostGIS, Dagster, backend test, Alembic 검증은
  WSL2에서 실행한다.
- 보안/인증/DB/공간/Dagster/Telegram/외부 API/PWA/Gemini/소셜 로그인 변경은
  관련 문서와 모듈 경계를 먼저 읽는다.
- 제품 의사결정이 저장소에서 추론 불가능할 때만 멈추고 묻고, 그 외에는 안전한
  가정을 문서에 남긴다.
- 정합성 게이트(Coverage, OpenAPI drift, lint, mypy, lint-imports)는 코드 작성
  단계 진입 후 CI에 박는다.

## 책임 경계 (TripMate vs `python-krtour-map`)

### TripMate 책임 (본 저장소)

- 사용자/세션/인증 (이메일·소셜·OAuth)
- 여행 계획 도메인 (Trip, Day, POI 첨부, Notice plan, 공유)
- Admin 콘솔 (사용자/엔티티/콘텐츠/파일)
- 사용자 대면 UI (Next.js + maplibre-vworld 기반 지도)
- Dagster orchestration (`python-krtour-map`의 collect/load 함수를 asset으로 호출)
- 파일 스토리지(RustFS) 운영 API
- 외부 통합 (Telegram, Gemini, Resend, 소셜 로그인 provider)

### `python-krtour-map` 책임 (별 저장소, 함수 라이브러리)

- Feature 정규화 / `feature_id` 생성 / SourceRecord 관리
- Postgres schema `feature` / `provider_sync` 의 DDL과 raw SQL
- Provider 원천 → DTO 변환 (KMA, VisitKorea, OpiNet, MOIS, ...)
- Record Linkage / dedup queue
- 지도 좌표·CRS 정책 (`coord_5179` 반경 검색 등)
- Coverage / 정합성 / OpenAPI gate (자체 CI)

본 저장소의 코드가 위 책임을 침범하지 않는지 모든 PR에서 자가 검토한다.

## 신규 ADR 작성 시

`docs/decisions.md`에 ADR-NNN 추가. `python-krtour-map`의 ADR과 충돌·연계가
있으면 양쪽 ADR이 서로 참조한다 (예: `참조: krtour-map ADR-022`). 본 저장소의
ADR 다음 번호는 `docs/decisions.md` 끝을 참고.

## 참고

- Skill 라우팅, 커밋 규약, PR 본문, 핸드오프 프로토콜은 `docs/agent-guide.md`.
- 자주 묻는 작업, 도메인 어휘, DO NOT 22항은 `SKILL.md`.
- 한 줄 진입 요약은 `CLAUDE.md`.
