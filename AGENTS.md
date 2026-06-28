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

본 저장소(GitHub 이름 `pinvi`)는 **한국 여행 계획·기록·공유 애플리케이션**의
모노레포다. 백엔드(FastAPI) / 프론트엔드(Next.js) / 모바일 Expo Dev Client
앱(`apps/mobile`, 활성 — Sprint M-1, SDK 56 / minSdk 24) / ETL(Dagster) /
인프라 manifest / 문서가 들어 있다.

본 앱은 지도 feature 도메인을 직접 소유하지 않는다. 지도 feature(place /
event / notice / price / weather / route / area) 정규화·저장은 별 저장소
`kor-travel-map`이 소유하고, Pinvi는 최신 `kor-travel-map` **OpenAPI HTTP
계약**으로 조회·갱신 요청을 보낸다(ADR-026/ADR-027).

> **현황 (2026-06-06 감사, ADR-027)**: 이 HTTP 계약은 kor-travel-map이 **신규로 구축해야
> 할 목표**다(현재 kor-travel-map은 in-process 함수 라이브러리 + 인증 없는 debug-UI만 보유,
> 포트 12701/`openapi.user.json` 미존재). Pinvi 요구사항은
> `docs/kor-travel-map-requirements.md`, 종합 감사는 `docs/audit/2026-06-06-doc-impl-audit.md`.

이전(v1) 구현은 `v1` 브랜치에 보존되어 있다. master(main)는 v2 사양으로 처음부터
다시 구현한다(ADR-001).

## 식별자 (일동 방지)

| 항목 | 값 |
|------|----|
| GitHub 저장소 이름 | `pinvi` |
| 백엔드 import (계획) | `from pinvi.api import ...`, `from pinvi.etl import ...` |
| 프론트 패키지 (계획) | `apps/web` (Next.js App Router) |
| 환경변수 prefix | `PINVI_*` |
| PostgreSQL DB 이름 (개발) | `pinvi` |
| Postgres schema (자체) | `app`, `ops` (Pinvi 소유) |
| Postgres schema (`kor-travel-map` 소유) | `feature`, `provider_sync` |
| 객체 저장소 | RustFS (S3 호환) — `app` 도메인 첨부 + `feature` 미디어 분리 버킷 |
| Dagster code location | `apps/etl` |
| Admin 콘솔 | `apps/web/app/admin/` |
| 운영 노드 | N150 16GB + Odroid M1S 병행 (ADR-023, Docker Compose) |

## 의존 라이브러리 (별 저장소)

| 저장소 | 역할 |
|--------|------|
| `kor-travel-map` | 지도 feature 정규화·저장 + OpenAPI API/Admin |
| `python-kraddr-base` | 한국 행정구역 / 카테고리 base |
| `kor-travel-geo` | 주소 · 법정동 · 지오코딩 |
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
| `maplibre-vworld-react` | **Pinvi 지도 클라이언트** — VWorld + MapLibre 선언형 React 계열. Web은 `vworld-map-web`을 `apps/web/vendor/*.tgz` `file:` 핀으로 소비하고, 공통 `vworld-map-core`는 기존 `apps/mobile/vendor/*.tgz` pin을 공유한다(ADR-046). Mobile은 `vworld-map-rn` + `vworld-map-core`를 `apps/mobile/vendor/*.tgz` `file:` 핀으로 소비한다(ADR-044). Place/Price/Weather 마커 + `PolygonArea` + `RouteLine` + `ClusterLayer` + `Popup` generic primitive 제공 (Pinvi 도메인 wrapper / 16색 팔레트 상수는 라이브러리에 없음 — `apps/web/lib`에서 직접 구현). wrapper 금지 — 부족 기능은 라이브러리 PR (ADR-005 mirror) |

모바일 앱 기준선은 ADR-043: `apps/mobile`은 Expo SDK 56 + Expo Router + **Expo Dev
Client** + EAS Build + React Native New Architecture를 사용한다. Expo Go는 사용하지
않고, Android `minSdkVersion`은 24 이상이며(SDK 56 요구), VWorld API key는 앱에 번들하지 않고
`GET /mobile/vworld/token`으로 server-issued 발급한다. 이 발급은 ADR-045의 인터림 정책을 따른다
— 현 단계는 인증 게이트 + 감사 로깅(키 원본 미로깅)의 "문서화된 운영 제한"이며, 공개 배포 전에는
opaque 단기 token 또는 tile proxy로 대체한다. 모바일 지도 엔진은 ADR-044: 별 저장소
`maplibre-vworld-react`의 `vworld-map-rn`을 **vendored tarball**(`apps/mobile/vendor/*.tgz`
`file:` 핀)로 소비하고, `@maplibre/maplibre-react-native` config plugin이 필요해 EAS Dev Client
빌드에서만 동작한다.

상세 사용 정책은 `kor-travel-map`의 `docs/external-apis.md`와 본 저장소의
`docs/kor-travel-map-integration.md`.

## 개발 환경 정책 (Linux / WSL / N150)

### Worktree + CodeGraph (ADR-017)

본 저장소는 AI 도구마다 **고정 worktree**를 둔다. trunk(`/mnt/f/dev/pinvi` 또는
`~/pinvi-workspaces/pinvi`)는 사람이 직접 만지는 checkout이며, AI 도구는 trunk를
절대 편집하지 않는다.

| AI 도구 | worktree 이름 | 예시 경로 | idle branch |
|---------|--------------|----------|-------------|
| Claude Code | `pinvi-claude` | `/mnt/f/dev/pinvi-claude` | `agent/claude-idle` |
| OpenAI Codex (CLI / VS Code) | `pinvi-codex` | `/mnt/f/dev/pinvi-codex` | `agent/codex-idle` |
| Google Antigravity 2.0 | `pinvi-antigravity` | `/mnt/f/dev/pinvi-antigravity` | `agent/antigravity-idle` |

- **worktree는 영속** — 작업마다 새로 만들지 않는다.
- **작업마다 브랜치만 새로**: `git fetch && git switch -c agent/<agent>-<task> origin/main`
  (로컬 `main` ref는 trunk가 점유하므로 worktree에서는 `origin/main`을 직접 사용 —
  `docs/runbooks/codegraph-worktrees.md` §3.3).
- **CodeGraph** (`colbymchenry/codegraph`) 인덱스는 worktree마다 1회
  `codegraph init -i`, 이후 task 시작 시 `codegraph sync`.
- `.codegraph/` 디렉터리는 `.gitignore` 박힘 (로컬 SQLite, 머신/worktree마다 별개).
- **Git 실행**: git / branch / commit / push / PR은 **Linux git**으로 실행한다
  (ADR-051). 기존 `/mnt/f/...` worktree에 Windows `F:/...` 포인터가 남아 있으면
  Linux에서 `git worktree repair <path>`로 고친 뒤 사용한다. 같은 worktree를
  Windows `git.exe`로 다시 조작하지 않는다.
- **Frontend 실행**: `apps/web` dev server, lint, typecheck, build, Vitest는
  Linux에서 실행한다. Playwright는 N150에서 먼저 실행하고, N150 runtime/권한 문제로
  불가능할 때만 Windows runner를 fallback으로 쓴다.
- **dev/prod 분리 + 고정 12xxx 포트 (ADR-047)**: 별도 지시가 없으면 대상은 **dev**다.
  dev는 이 worktree에서 직접 띄우고 **내부 주소 `127.0.0.1`의 12xxx 고정 포트**만 쓴다:
  PostgreSQL `5432`, API `12801`, 웹 `12805`, Dagster `12802`,
  kor-travel-map API/Admin API `12701`, RustFS API `12101`, RustFS console `12105`.
  prod는 `kor-travel-docker-manager`(`ktdctl`)로 컨테이너를 올리고 **공식 도메인**
  (gitignore `infra/.env.prod`)을 적용한다. **포트 충돌 시 새 포트로 바꾸지 않고**,
  prod/dev 무관하게 **강제종료 여부를 사용자에게 묻는다**. 거부하면(또는 비대화형 기본)
  `scripts/dev-up.sh`는 **중지**한다(`PINVI_DEV_FORCE_KILL=1`로만 비대화형 강제종료).
  `scripts/dev-down.sh`는 명시적 종료다. Docker 빌드/실행은 `ktdctl` 1차 + 불가 시
  `scripts/docker-app.sh` 폴백 (Docker 진입 경로 ADR-040, 포트 정책 ADR-042,
  `docs/runbooks/docker-app.md` §0).
- 절차 상세는 `docs/runbooks/codegraph-worktrees.md` (ADR-017).

#### CodeGraph Commands

| 명령 | 용도 | 주기 |
|------|------|------|
| `codegraph init -i` | 인덱싱 초기화 (interactive) | worktree마다 1회 |
| `codegraph sync` | 변경 incremental 반영 | 새 task 시작 시 |
| `codegraph status` | 동기화 상태 확인 (last_sync, count) | 의심될 때 |
| `codegraph query <name>` | 심볼 빠른 lookup | 수시 |

#### Code Style & Rules — 영향도 먼저, 수정은 나중에

**컴포넌트 / 함수 / 서비스를 수정하기 전 반드시 CodeGraph의 `codegraph_explore`
도구로 영향도를 먼저 평가**한다. grep / Read fan-out 대신 한 번의 MCP 호출로
관련 심볼 source + 호출 관계를 가져온다.

| 의도 | 1차 도구 |
|------|---------|
| 컴포넌트를 만지기 전 주변 파악 | `codegraph_explore` |
| 이 함수 바꾸면 무엇이 깨지나 | `codegraph_impact` |
| X가 Y에 어떻게 도달하나 | `codegraph_trace` |
| 단일 심볼 정의 / 호출자 | `codegraph_context` |
| 심볼 이름 lookup | `codegraph_search` |

답이 인덱스에서 나오면 파일을 다시 Read 하지 않는다 (반환된 소스가 권위).
세부 표·트러블슈팅은 `docs/runbooks/codegraph-worktrees.md` §1.6.

### Linux-only 개발 환경 (ADR-051)

환경 모델은 **Linux worktree = source of truth**다. ADR-024의 NTFS source / WSL
테스트 미러 모델과 ADR-017의 Windows `git.exe` amendment는 ADR-051이 supersede한다.

- **git / 편집 / commit / push / PR**: Linux git으로만 수행한다. 기존 worktree가
  `F:/...` 포인터를 들고 있으면 Linux에서 `git worktree repair <path>`를 먼저 실행한다.
- **CodeGraph**: Linux native `codegraph`만 사용한다. `command -v codegraph`가
  `/mnt/c/...`, `.exe`, `.cmd`를 가리키면 중지하고 PATH/설치를 고친다.
- **의존성 설치·`pytest`·`docker`·장기 실행·프론트 dev/lint/typecheck/build/Vitest**:
  모두 Linux worktree에서 실행한다. 별도 rsync 미러를 source of truth로 쓰지 않는다.
- **Playwright**: N150에서 먼저 실행한다. N150 브라우저 runtime/권한/네트워크 문제로
  불가능할 때만 Windows runner를 fallback으로 사용하고, 사유와 명령을 journal/PR에 남긴다.
- **데이터(`dataset/`, `refdocs/`)**: 변경 금지 원본은 절대경로 또는 심볼릭 링크로
  참조하고 git에 커밋하지 않는다.
- **Linux PATH 오염 금지**: `npm`/`node`/`git`/`rg`/`codegraph`가 `/mnt/c/...`
  Windows shim으로 잡히면 안 된다(`command -v`로 확인).
- **Frontend 실행**: `apps/web` dev server / lint / typecheck / build / Vitest는
  Linux에서 실행한다.
- **고정 dev 포트**: PostgreSQL `5432`, API `12801`, 웹 `12805`, Dagster `12802`,
  kor-travel-map API/Admin API `12701`, RustFS API `12101`, RustFS console `12105`.
  포트가 점유돼 있으면 기존 프로세스를 종료하고 같은 포트로 재기동한다
  (`npm run dev:up` / `npm run dev:down`, Linux worktree). Docker 빌드/실행은
  `kor-travel-docker-manager`(`ktdctl`) 1차 + `scripts/docker-app.sh` 폴백
  (Docker 진입 경로 ADR-040, 포트 정책 ADR-042, `docs/runbooks/docker-app.md` §0).

절차·명령·함정 전체는 `docs/dev-environment.md`(ADR-051), worktree 생성·CodeGraph·
git 포인터 복구는 `docs/runbooks/codegraph-worktrees.md`(ADR-017/051)가 1차 reference다.

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

## 릴리즈 로드맵

| 버전 | Sprint | 핵심 |
|------|--------|------|
| `v0.1.0` | Sprint 4 | 지도 + `vworld-map-web` 전환 + CI/CD 재활성 (ADR-021/046) |
| `v0.2.0` | Sprint 5 | 실시간 + ETL + Grafana embed + Backup 1차 (ADR-022) |
| `v1.0.0` | Sprint 6 | MCP 외부 인터페이스 (ADR-019) + Backup UI 핫스왑 + Korean geofencing (ADR-018) + T108 N150 병행 (ADR-023) + LBS + 법무 |
| `v1.1.0+` | post-Sprint 6 | PWA / 푸시 / `kor-travel-concierge` (ADR-020) |

자세히는 `docs/sprints/README.md`.

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
| `kor-travel-map` OpenAPI 호출 — feature 데이터 | `docs/kor-travel-map-integration.md` → 라이브러리 저장소 `docs/pinvi-rest-api.md` |
| Geocoding (주소/좌표/행정구역) — kor-travel-geo v2 REST 직접 | `docs/integrations/kor-travel-geo.md` (ADR-025) → `docs/architecture/geocoding-open-decisions.md` |
| 외부 통합 (Resend/OAuth/Telegram/AI companion 호출 계약) | `docs/integrations/<service>.md` → `docs/compliance/data-policy.md` |
| Frontend UI | `docs/architecture/frontend.md` → `docs/design/marker-palette.md` → 루트 `DESIGN.md` |
| Admin 콘솔 | `docs/api/admin.md` → `docs/runbooks/admin.md` → `docs/spec/v8/04-admin.md` |
| ETL asset | `docs/runbooks/etl.md` → `docs/architecture/dagster-etl-bridge.md` |
| 인프라 / 배포 | `docs/runbooks/{local-dev,docker-app,odroid-docker}.md` |
| 개발 환경 셋업 / 검증 실행 (Linux git + CodeGraph) | `docs/agent-workflow.md` (런북) → `docs/dev-environment.md` (ADR-051) → `docs/runbooks/codegraph-worktrees.md` (ADR-017/051) |
| 환경/도구 실패가 의심될 때 | `docs/agent-failure-patterns.md` (git 포인터·PATH shim·런처·escape·통합테스트 함정) |
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
외부 API key 없이 5분마다 열린 PR을 감시하고, 최신 head SHA review reminder 마커가
없는 PR에 리뷰 필요 알림을 남긴다. 실제 리뷰는 에이전트 또는 사람이 수행한다.

- 리뷰 후 상세 코멘트를 남기고, 필요한 코드 수정까지 직접 수행한다.
- 변경량 최소화보다 Sprint 1~4를 버틸 장기 설계 정합성을 우선한다.
- 올바른 수정 위치가 `kor-travel-map`, `maplibre-vworld-react`, `python-kraddr-base / kor-travel-geo / python-kraddr-gop`,
  provider 라이브러리라면 해당 저장소 PR을 먼저 만들고 머지한 뒤 Pinvi를 sync한다.
- Pinvi PR merge는 차단 코멘트, 검증, 문서/journal/resume, 기반 라이브러리 sync가
  끝난 뒤 수행한다.

### 운영 도메인 / 시크릿 비노출 (ADR-047)

이 repo는 **공개**다. 운영 도메인(개인 dynamic-DNS)·시크릿·운영 노드 접근(IP/SSH/hostname)을
추적 파일에 커밋하지 않는다. 실제 값은 gitignore된 `infra/.env.prod`(템플릿
`infra/.env.prod.example`)와 운영 노드의 `kor-travel-docker-manager/.env`에만 둔다. 추적 문서/예시는
`*.example.com` placeholder로만 쓴다. CI 빌드의 `NEXT_PUBLIC_PINVI_API_URL`은
`secrets.NEXT_PUBLIC_PINVI_API_URL`에서 받는다. Dagster webserver는 12802 고정(`apps/etl/Dockerfile`,
compose profile `etl`). 운영 배포는 GHCR 없이 운영 노드에서 `ktdctl pinvi --build`(로컬 빌드)로
한다(`docs/runbooks/deploy.md`).

#### prod 배포 & 민감 운영 노트 (LOCAL ONLY)

**prod(n150) 배포 절차·접속·반복 함정의 정본은 `docs/deploy-runbook.local.md`**(gitignore된 로컬
전용, 민감정보 포함)에 있다. 운영 노드 접근(IP/SSH/hostname)·실 도메인·반복된 배포 실수를 상세
기록한다. 배포/운영 작업 전 반드시 먼저 읽고, 새 배포 실수는 그 incident log에 append한다. 이 런북은
커밋되지 않으므로 **각 git worktree에도 같은 경로로 복사**해 둔다(`.env.mcp-telegram`과 같은
per-worktree 로컬 파일 운영). kor-travel-concierge `docs/deploy-runbook.local.md`와 동일 패턴.

#### remote 푸시 전 보안 감사 (필수 절차)

`git push` / PR 생성 **직전 반드시** 아래를 수행한다(WSL bash). **하나라도 걸리면 푸시 중지** 후 원인 제거.

1. **스테이징 파일 점검**: `git diff --cached --name-only`에 `*.local.md`, `.env`(`.env.example` 제외),
   `.env.prod`/`.env.production`, `.env.mcp-telegram`, 키/시크릿/덤프 파일이 **없어야** 한다.
2. **diff 비밀 스캔**(이 파일은 커밋되므로 **실제 호스트/도메인/IP/비밀번호 같은 구체 값을 여기 적지 않는다**):
   ```bash
   git diff --cached -U0 | grep -nEi '(api[_-]?key|secret|password|passwd|token|pbkdf2_sha256|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY)' && echo '⛔ 의심 항목 — 푸시 중지' || echo '✅ 일반 비밀 패턴 없음'
   ```
   - 매칭이 나오면 placeholder인지 실제 값인지 확인하고, 실제 값이면 제거하거나 `*.local.md`/`.env`로 옮긴다.
   - **프로젝트별 민감 문자열**(prod 호스트 IP·라우터·도메인·SSH 사용자 등)은 `docs/deploy-runbook.local.md`의
     "푸시 전 추가 스캔" 패턴으로 함께 검색한다(그 값들은 런북에만 두고 커밋 파일엔 절대 적지 않는다).
3. **`*.example`은 placeholder만**, 신규 파일이 로그/덤프/백업 같은 비밀 운반체가 아닌지 확인.
4. 통과하면 푸시. 이 절차는 매 푸시 전 실행하며 자동화/생략하지 않는다(kor-travel-concierge AGENTS.md 동일 패턴).

### Telegram 작업 완료 알림 MCP

각 에이전트 worktree의 MCP 설정(`claude.json` / `.codex/config.toml` /
`.gemini/mcp.json` / `antigravity.json`)에는 `mcp-telegram` 서버를 등록한다. Telegram
credential은 각 worktree 루트의 로컬 파일 `.env.mcp-telegram`(`API_ID` / `API_HASH`)
에만 저장하고, 이 파일은 `.gitignore`로 커밋하지 않는다(형식은 `.env.mcp-telegram.example`).
tracked 설정은 `scripts/mcp_telegram_start.py` wrapper를 통해 로컬 env 파일을 읽는다.
GitHub Actions secret/워크플로는 쓰지 않는다(T-062 0-secret 정책 유지).

단위 작업이 완료되어 PR을 만들면, 최종 응답 전 `mcp-telegram` MCP의 `send_message`로
Telegram에 간단한 완료 요약과 PR 링크를 보낸다. PR이 없는 문서/로컬 셋업 작업이면 PR
링크 대신 브랜치/커밋 또는 "PR 없음"을 명시한다. 설치·로그인 절차는
`docs/runbooks/codegraph-worktrees.md`, 발송 시점은 `docs/agent-workflow.md` §6.
(kor-travel-map PR #229 동일 패턴.)

## 현재 단계 정책

초기 v2 bootstrap 시기의 "코드 작성 금지" 규칙은 Sprint 1 진입 전까지의 임시
제약이었다. 현재 기준선은 **Sprint 1~4 완료 및 `v0.1.0` 릴리즈 완료
(2026-06-13 tag/GitHub Release), 이후 post-v0.1.0 `Unreleased` 보강 진행 단계**다.

- `apps/`, `packages/`, `infra/`, `docs/` 변경이 모두 가능하다.
- 다만 변경 범위는 accepted ADR, 현재 Sprint 목표, 책임 경계(Pinvi vs
  `kor-travel-map`)를 넘지 않아야 한다.
- 문서만 바꾸는 PR이라도 `docs/journal.md`, `docs/resume.md`, `docs/tasks.md`
  중 관련 추적 문서를 함께 갱신한다.

코드 작성 요청이 들어오면:

1. 사용자 의도와 대상 계층 확인
2. 관련 ADR / Sprint 문서 / 도메인 문서 확인
3. 영향 범위 평가 (`codegraph_explore` 우선)
4. 테스트 추가 또는 기존 테스트 보강
5. 구현
6. 검증 + journal/resume/tasks/decisions/CHANGELOG 해당 항목 갱신

## 작업 흐름 룰 요약

- 명확한 의도가 없으면 추측하지 말고 `AskUserQuestion`(4지선다 + Other) 사용.
- 여러 파일·DB schema·서비스 경계를 건드리면 `docs/execplan/<task-name>.md`를
  작성/갱신한다.
- 의미 있는 변경은 테스트와 문서 갱신을 포함하고, 실행한 검사 명령과 환경
  (Linux / N150 / Windows fallback)을 보고한다.
- 유사한 실수가 반복되면 원인과 재발방지 기준을 관련 문서/runbook/skill에 남긴다.
- Docker, Compose, PostgreSQL/PostGIS, Dagster, backend test, Alembic 검증은
  Linux에서 실행한다.
- 보안/인증/DB/공간/Dagster/Telegram/외부 API/PWA/AI companion/소셜 로그인 변경은
  관련 문서와 모듈 경계를 먼저 읽는다.
- 제품 의사결정이 저장소에서 추론 불가능할 때만 멈추고 묻고, 그 외에는 안전한
  가정을 문서에 남긴다.
- 정합성 게이트(Coverage, OpenAPI drift, lint, mypy, lint-imports)는 코드 작성
  단계 진입 후 CI에 박는다.

## 책임 경계 (Pinvi vs `kor-travel-map`)

### Pinvi 책임 (본 저장소)

- 사용자/세션/인증 (이메일·소셜·OAuth)
- 여행 계획 도메인 (Trip, Day, POI 첨부, curated trip plan/Notice plan 호환 API,
  Pinvi-native 큐레이션, kor_travel_map `curated_features` 1:1 import 소비, 공유)
- Admin 콘솔 (사용자/엔티티/콘텐츠/파일)
- 사용자 대면 UI (Next.js + `vworld-map-web` 기반 지도)
- Dagster orchestration (Pinvi 자체 `app` schema job + 외부 서비스 갱신 트리거, ADR-050
  app-owned job 표준)
- 파일 스토리지(RustFS) 운영 API
- 외부 통합 (Telegram, Resend, 소셜 로그인 provider, AI companion 호출 계약)

### `kor-travel-map` 책임 (별 저장소, OpenAPI API/Admin)

- Feature 정규화 / `feature_id` 생성 / SourceRecord 관리
- Postgres schema `feature` / `provider_sync` 의 DDL과 raw SQL
- Provider 원천 → DTO 변환 (KMA, VisitKorea, OpiNet, MOIS, ...)
- Record Linkage / dedup queue
- 지도 좌표·CRS 정책 (`coord_5179` 반경 검색 등)
- Coverage / 정합성 / OpenAPI gate (자체 CI)

본 저장소의 코드가 위 책임을 침범하지 않는지 모든 PR에서 자가 검토한다.

## 신규 ADR 작성 시

`docs/decisions.md`에 ADR-NNN 추가. `kor-travel-map`의 ADR과 충돌·연계가
있으면 양쪽 ADR이 서로 참조한다 (예: `참조: kor-travel-map ADR-022`). 본 저장소의
현재 ADR 범위와 다음 번호는 `docs/decisions.md` 끝을 기준으로 하고, `CLAUDE.md`
1쪽 요약의 ADR 현황도 같은 PR에서 동기화한다.

## 참고

- Skill 라우팅, 커밋 규약, PR 본문, 핸드오프 프로토콜은 `docs/agent-guide.md`.
- 자주 묻는 작업, 도메인 어휘, DO NOT 22항은 `SKILL.md`.
- 한 줄 진입 요약은 `CLAUDE.md`.
