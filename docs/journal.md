# journal.md — 작업 일지 (역시간순)

가장 위가 가장 최근. 새 엔트리는 위에 append.

## 2026-05-26 02:00 (claude)

**작업**: v1 자산 전수 조사 + 누락 항목 일괄 반영 + 문서 일관성 정리 + AI agent
friendly 보강 (ADR-014).

**컨텍스트**: 사용자 요청. v2 골격 + SPEC V8 + frontend/location/notice 반영
이후, v1의 9개월 운영 자산을 빠짐없이 v2 문서로 가져오고 문서 일관성 정리.

**v1 전수 조사** (`docs/v1-to-v2-mapping.md`):

- v1 docs/ 84개 (api/architecture/data-sources/decisions/execplan/integrations/
  runbooks/skills/PROJECT_BRIEF), apps/api 80+, apps/web 30+, scripts 13, infra 2
- ✅ / 🚚 / 📋 / ⛔ / 🆕 상태로 매핑

**신규 작성** (본 PR — ~30 파일):

- `docs/api/` 11개: README / common / auth / users / trips / pois / features /
  notice-plans / storage / admin / public / regions / health / websocket
- `docs/integrations/` 9개: README / resend / social-login / gemini / telegram /
  kakao-map / sentry / loki
- `docs/runbooks/` 7개: README / local-dev / docker-app / etl / admin /
  file-storage / odroid-docker
- `docs/compliance/` 4개: README / lbs-act / pipa / data-policy
- `docs/conventions/` 6개: README / coding-style / database / testing /
  geospatial / normalization
- `docs/architecture/` 5개 추가: map-marker-design / youtube-travel-intelligence /
  mcp-tools / dagster-etl-bridge / api-contract
- `docs/data-sources/README.md` — cross-ref 인덱스
- `docs/v1-to-v2-mapping.md` — 매핑 매트릭스

**기존 문서 갱신**:

- `README.md` — 문서 인덱스 전면 강화 (역할별 그룹)
- `AGENTS.md` — "AI Agent 작업 진입 절차" 섹션 신규 + 작업 종류별 진입 문서표
- `CLAUDE.md` — §7 빠른 문서 검색 표 추가
- `docs/decisions.md` — ADR-014 박음

**결정**:

- v1 자산 cherry-pick X — 본 문서 + schema 정합성 기준으로 재작성 (특히
  notice_plans Sprint 2 재작성 결정 — ADR-013 mirror)
- v1의 `apps/api/app/etl/`, `dagster_etl/`, `core/{kex,kto}.py`,
  `services/krtour_map_*` 는 모두 폐기 (ADR-005 / ADR-006 mirror)
- v1 `docs/data-sources/*` 8개는 모두 라이브러리 위임 — 본 저장소는 인덱스만
- `pyXyz` 짧은 alias 사용 금지 (canonical `python-xyz-api`만)
- AI agent 진입 절차를 AGENTS.md / CLAUDE.md에 명시

**일관성 점검**:

- TripMate vs `python-krtour-map` 책임 분담을 모든 신규 문서에 명시
- WSL 미러 모델 (ADR-004)이 모든 runbook에 일관 반영
- 환경변수 `TRIPMATE_*` prefix 일관
- 좌표 lon-lat 순서 일관
- 시간 KST aware 일관
- audit log chain (content_hash) 일관
- 동의 4 분리 일관

**다음**: PR 작성 후 사용자 review.

## 2026-05-25 23:30 (claude)

**작업**: Frontend 스택 상세 + Expo 공용 패키지 + 위치 정보 사양 + v1 notice POI
도메인 보강.

**컨텍스트**: 사용자 요청 3가지:

1. Frontend는 React/Next.js/TanStack Query/Zod/Zustand/RHF/shadcn/ui/Tailwind 기반
   임을 상세 명시. DESIGN.md / palette HTML의 색상톤·UX 따름. 추후 Expo 대응을
   위해 주요 로직 + 데이터 정의 코드를 Next.js / Expo 공용으로 작성. Expo 프론트
   구성도 명시.
2. v1에서 notice POI 관련 문서/코드 확인해서 보강.
3. 웹/앱에서 사용자 위치 정보 획득을 기능 사양에 명시.

v1 탐색 결과: `notice_plans` 도메인은 SPEC V8 D-10의 `notice` feature와 **완전히
다른 개념**. v1 `notice_plans`는 Admin이 작성한 **추천 여행 plan** (사용자가 자기
trip으로 copy 가능). 같은 단어를 쓰는 두 개념이 v2에서 혼동되지 않도록 명명을
분리.

**신규 파일**:

- `docs/architecture/frontend.md` — Next.js + Expo 공용 monorepo 구조,
  `packages/{schemas,api-client,state,design-tokens,hooks,i18n}`, shadcn/ui +
  Tailwind 통합, Airbnb 톤 디자인 토큰, 컴포넌트별 가이드, React Native
  Compatibility 룰
- `docs/architecture/user-location.md` — `navigator.geolocation` /
  `expo-location` 어댑터 추상화, `useUserLocation` 공용 hook, 4 분리 동의
  연계, content_hash chain 적재, fallback chain, UI 가이드
- `docs/architecture/notice-plans.md` — 추천 여행 plan 도메인 (v1에서 가져옴),
  `notice_plans` + `notice_pois` + `plan_poi_attachments` 단일 테이블 4 대상,
  copy 흐름, RustFS 정합, "notice plan ≠ notice feature" 명명 분리

**갱신**:

- `docs/decisions.md` — ADR-011 (Frontend 스택 + Expo 공용), ADR-012 (위치
  정보), ADR-013 (Notice plan 이전 + 명명 분리)
- `docs/spec/v8/03-frontend.md` — 스택 표 갱신 (shadcn/ui 명시) + 새 문서
  cross-reference
- `docs/sprints/SPRINT-1.md` — `packages/*` skeleton 등록 항목 박음
- `docs/sprints/SPRINT-2.md` — notice_plans / plan_poi_attachments Alembic,
  공용 schema/api-client/state/hooks 활성화, 4 분리 동의 UI + 위치 audit
- `docs/sprints/SPRINT-4.md` — 사용자 notice plan listing + copy 다이얼로그 +
  지도 "내 위치로 이동" 버튼
- `docs/sprints/SPRINT-6.md` — Admin notice plan 작성기 UI
- `README.md`, `SKILL.md` — 새 문서 cross-reference + 도메인 어휘
  (Notice plan / Notice feature / Plan POI attachment)
- `docs/architecture.md` §2.2 — Frontend 섹션을 새 `architecture/frontend.md`
  로 위임 + 공용 패키지 + 위치 hook 명시

**v1에서 확인한 자산** (`v1` 브랜치):

- `apps/api/alembic/versions/20260521_0027_notice_plans.py`
- `apps/api/alembic/versions/20260522_0028_plan_poi_attachments.py`
- `apps/api/app/models/trip.py` (`NoticePlan`, `NoticePoi`, `PlanPoiAttachment`)
- `apps/api/app/schemas/notice.py`
- `apps/api/app/services/notice_plan.py` (copy 흐름)
- `apps/api/app/services/plan_poi_attachment.py`
- `apps/api/app/api/routes/notice.py`
- `apps/api/tests/test_notice_plans_api.py`
- `docs/architecture/plan-poi-attachments.md`

**결정**:

- shadcn/ui + Tailwind 채택 — DESIGN.md Airbnb 톤을 컴포넌트 레벨에서 customizing
- `packages/*` 공용 패키지를 v1.0 단계부터 박아 Expo 추가 비용 최소화
- 좌표 서버 전송 시 audit chain 자동 적재. 좌표 정밀도는 UI에 4자리 (~10m) 까지만
- v1 notice plan 도메인은 cherry-pick 안 함 — schema 정합성 위해 재작성 (Sprint 2)
- "notice plan" (TripMate) vs "notice feature" (라이브러리) 명명 명시 분리

**다음**: PR #5에 추가 커밋 후 push. Sprint 1 진입 승인 시 `apps/` + `packages/`
scaffolding.

## 2026-05-25 22:00 (claude)

**작업**: SPEC V8 6편 반영 + v1 자산 일부 복원.

**컨텍스트**: 사용자가 외부 docx 6편(`spec_v8_0_infrastructure` ~ `spec_v8_5_execution`)
제공하면서 "TripMate에 반영할 것들도 문서화"와 "v1에서 색상맵 html과 DESIGN.md를
v2로 끌고 와" 지시. SPEC V8은 v1 시점에 작성되었지만 후속 메모(M~R)에 이미
`python-krtour-map` 책임 분리가 반영되어 있어, 본 저장소의 v2 골격(ADR-001~009)과
정합되게 적용 노트만 작성하면 됨.

**신규 파일**:

- `docs/spec/v8/README.md` — 6편 인덱스 + 책임 매핑
- `docs/spec/v8/00-infrastructure.md` — Odroid M1S, RustFS, Sentry, Loki, 위치정보법
- `docs/spec/v8/01-data.md` — 7 Feature, PostGIS, Record Linkage (라이브러리 위임)
- `docs/spec/v8/02-backend.md` — FastAPI 스택, JWT/OAuth, Resend, OR-Tools
- `docs/spec/v8/03-frontend.md` — Next.js 15, 16색 팔레트, 우클릭, 실시간
- `docs/spec/v8/04-admin.md` — 13 페이지, RBAC, audit chain, debug 콘솔
- `docs/spec/v8/05-execution.md` — 결정 6건, Sprint 1~6
- `docs/design/marker-palette.md` — P-01~P-16 + 카테고리 매핑
- `docs/sprints/SPRINT-2.md` — 도메인 API + DB
- `docs/sprints/SPRINT-3.md` — Admin 데이터 디버그 (Sprint 4 전)
- `docs/sprints/SPRINT-4.md` — 지도 + 사용자 UI
- `docs/sprints/SPRINT-5.md` — 실시간 + ETL + Loki
- `docs/sprints/SPRINT-6.md` — 일정 최적화 + LBS 신고 + 법무

**복원 (v1 → v2)**:

- `airbnb-marker-palette.html` (저장소 루트, 색상 시각 reference)
- `DESIGN.md` (저장소 루트, Airbnb 디자인 토큰 가이드 — 브랜드 확정 전 임시)

**갱신**:

- `docs/decisions.md` ADR-010 추가 (SPEC V8 채택)
- `docs/sprints/README.md` — Sprint 2~6 인덱스 추가
- `docs/sprints/SPRINT-1.md` — SPEC V8 cross-ref §8

**결정**:

- SPEC V8 N-7.2의 "ext4 직접 작업본 + NTFS export" 모델은 ADR-004로 정정 유지
- SPEC V8 D~E (feature schema)는 `python-krtour-map`이 소유 (ADR-003)
- SPEC V8 M-14의 `users.role` RBAC를 따름 (`is_admin BOOLEAN` 정정)
- LBS 사업자 신고는 Sprint 6에 박음 (출시 전 필수)
- Sprint 3 (Admin) ≺ Sprint 4 (지도) 순서 유지

**발견**: SPEC V8 원본의 후속 메모(2026-05-16 ~ 05-20)가 이미 `python-krtour-map`
분리와 wrapper 금지 원칙을 명시 — v2 골격의 ADR-001/002/003/005와 자연스럽게
정합. 별도 충돌 해소 불필요.

**다음**: PR 갱신 (`docs/bootstrap-v2-skeleton` 브랜치에 추가 커밋 후 push).

## 2026-05-25 19:30 (claude)

**작업**: v2 재시작 — v1 보존 + main 골격 재작성.

**컨텍스트**: 사용자 지시. v1은 9개월 운영하면서 책임 경계가 흐려지고 WSL/NTFS
작업 흐름이 두 번 흔들렸다. 사용자 결정으로 (1) `codex/wsl-test-mirror-docs`
브랜치의 unstaged 변경을 마지막 v1 commit으로 박음, (2) v1 브랜치를 main과 동일
시점에서 분기 + origin push, (3) main에서 모든 추적 파일 git rm + 캐시/빌드 정리,
(4) `python-krtour-map`의 문서 구조(README/CLAUDE/AGENTS/SKILL/docs/) 패턴을 본
저장소 컨텍스트로 미러링.

**변경 파일** (신규):

- `.gitignore` — `python-krtour-map` 패턴 + TripMate dataset/refdocs 보존 정책
- `.gitattributes` — text=auto eol=lf + binary 분류
- `README.md` — 정체성, 빠른 시작, 문서 지도
- `CLAUDE.md` — 1쪽 진입 요약 (Claude Code 우선 진입)
- `AGENTS.md` — 작업 룰, 식별자, 책임 경계
- `SKILL.md` — 도메인 어휘, DO NOT 20항, 자주 묻는 작업
- `docs/architecture.md` — 큰 그림, 의존 방향, TripMate ↔ krtour-map
- `docs/agent-guide.md` — 결정·기록 5종, ADR 규약, PR 워크플로
- `docs/dev-environment.md` — WSL 미러 단일 모델, rsync 절차, 부트스트랩
- `docs/decisions.md` — ADR-001 ~ ADR-009 (v2 시작 결정)
- `docs/journal.md` — 본 파일
- `docs/resume.md` — 다음 한 작업
- `docs/tasks.md` — 백로그
- `docs/data-model.md` — app 도메인 (사용자/여행계획/POI 첨부)
- `docs/postgres-schema.md` — app schema DDL/인덱스 골격
- `docs/test-strategy.md` — 단위/통합/e2e 경계
- `docs/krtour-map-integration.md` — DI helper 패턴 + Dagster asset 사용
- `docs/sprints/README.md` — Sprint 1~N 개요
- `docs/sprints/SPRINT-1.md` — 코드 작성 단계 진입 PR plan

**삭제**:

- `.codex/`, `.dockerignore`, `AGENTS.md`(구), `DESIGN.md`, `README.md`(구),
  `airbnb-marker-palette.html`, `apps/`, `config/`, `docs/`(구), `infra/`,
  `package-lock.json`, `package.json`, `scripts/`, `skills/`
- (보존) `.gitattributes`, `.gitignore` (재작성), `.claude/`, `.env`, `dataset/`,
  `refdocs/` (`.gitignore` 보호 항목)

**Git 흐름**:

1. `codex/wsl-test-mirror-docs` 브랜치의 unstaged 변경 16개 → `bc83fb1 Mirror docs
   back to WSL test mirror workflow` 커밋 + origin push.
2. `main`을 codex tip(`bc83fb1`)으로 fast-forward.
3. `v1` 브랜치 생성(main의 현재 시점) + origin push.
4. main에서 v2 골격 신규 작성 (본 PR).

**ADR 적용**:

- ADR-001 — v1 보존 + v2 재시작
- ADR-002 — TripMate ↔ `python-krtour-map` 함수 직접 호출
- ADR-003 — schema 책임 분담 (`app`/`ops` = TripMate, `feature`/`provider_sync`
  = `python-krtour-map`)
- ADR-004 — WSL 미러 단일 모델
- ADR-005 — provider 어댑터 wrapper 금지
- ADR-006 — Dagster code location 분리 (`apps/etl`)
- ADR-007 — PR-only workflow + main branch protection
- ADR-008 — Postgres extension `x_extension` schema 분리
- ADR-009 — 한국어 문서 정책

**다음**:

- 사용자 review → v2 골격 PR로 main에 push (현재 작업 디렉토리에서 작성된 결과).
- Sprint 1 진입 승인 시 `apps/{api,web,etl}` + `infra/` + `packages/` scaffolding
  첫 PR (`docs/sprints/SPRINT-1.md` 참고).
- v1의 자산(Resend 통합, 소셜 로그인, Notice plan, RustFS Storage API 등)은 v2에서
  한 건씩 ADR로 결정하고 가져온다.
