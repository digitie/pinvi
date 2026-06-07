# SKILL — TripMate 에이전트 매뉴얼

> 이 파일은 당신(AI 에이전트 — Claude / Codex / Antigravity / Cursor / Copilot
> 누구든)이 작업을 시작하기 전 반드시 읽어야 한다. 1회만 읽으면 30분 이상의
> 디버깅을 줄일 수 있다.
>
> 도구별 1차 진입:
> - **Claude** — `CLAUDE.md` → `AGENTS.md` → 본 파일
> - **Codex / Antigravity** — `AGENTS.md` → 본 파일
> - 두 진입 파일(`AGENTS.md` + `CLAUDE.md`)은 항상 같은 결정을 반영 (ADR-016).

## 1. 정체성

본 저장소(GitHub 이름 `tripmate`)는 **한국 여행 계획·기록·공유 애플리케이션**의
모노레포다. 백엔드(FastAPI) + 프론트(Next.js) + ETL(Dagster) + 인프라 manifest +
문서가 들어 있다.

지도 feature(place / event / notice / price / weather / route / area) 정규화·
저장은 본 저장소가 아니라 별 저장소 `python-krtour-map`이 소유한다. TripMate ↔
`python-krtour-map`은 최신 **OpenAPI HTTP 계약**으로 통신한다(ADR-026).

이전(v1) 구현은 `v1` 브랜치에 보존되어 있다. master(main)는 v2 사양으로 처음부터
다시 구현한다(ADR-001).

### 식별자 매핑

| 항목 | 값 |
|------|----|
| GitHub 저장소 | `tripmate` |
| 백엔드 import (계획) | `from tripmate.api import ...`, `from tripmate.etl import ...` |
| 프론트 패키지 (계획) | `apps/web` (Next.js App Router) |
| 환경변수 prefix | `TRIPMATE_*` |
| PostgreSQL DB 이름 (개발) | `tripmate` |
| Postgres schema (자체) | `app`, `ops` |
| Postgres schema (`python-krtour-map` 소유) | `feature`, `provider_sync` |
| Dagster code location | `apps/etl` |
| Admin 콘솔 | `apps/web/app/admin/` |
| 운영 노드 | N150 16GB + Odroid M1S 병행 (ADR-023, Docker Compose) |

### 개발 환경 (PC, WSL) — ADR-024

- **git / 편집 / commit / PR**: NTFS worktree (`F:/dev/tripmate-<agent>`)에서
  **Windows git(`git.exe`)으로만**. 여기가 git source of truth.
- **의존성 설치 / `pytest` / `docker` / 장기 실행**: WSL ext4 **일회용 테스트
  미러** (`~/tripmate-workspaces/tripmate-<agent>`). 미러에서 commit/push 금지.
- **rsync는 NTFS → ext4 단방향**. 수정은 NTFS worktree에 반영 후 다시 단방향 sync.
- **데이터(`dataset/`, `refdocs/`)**: NTFS 원본. ext4 미러는 심볼릭 링크/절대경로 참조.
- 절차·함정 전체는 `docs/dev-environment.md` + `docs/agent-workflow.md`,
  반복 실패는 `docs/agent-failure-patterns.md`.

## 2. 빠른 시작 (코드 작성 단계 이후)

```bash
cd ~/tripmate-workspaces/tripmate-claude                    # WSL ext4 테스트 미러 (의존성/테스트 전용; git은 NTFS worktree)
sudo apt install -y libgdal-dev gdal-bin libpq-dev          # 시스템 의존성

# 백엔드 (uv 권장)
uv venv && uv pip install -e "apps/api[dev]"

# 프론트
npm install
scripts/dev-up.sh                                           # API 9021 / Web 9022 / Dagster 9023

# 인프라 (RustFS API 9003 / console 9004)
docker compose -f infra/docker-compose.yml up -d postgres rustfs

# Docker app build/run/smoke
npm run docker:app:smoke

# krtour-map 독립 프로그램은 별 저장소에서 실행 (API 9011 / admin 9012)

# Alembic (app schema만)
uv run --package apps/api alembic upgrade head

# python-krtour-map alembic은 별 저장소에서 실행 (feature schema 소유)

# 단위 테스트
pytest apps/api/tests -q

# 통합 테스트 (PostGIS 필요)
pytest apps/api/tests/integration -q
```

현재 저장소는 Sprint 1~3 산출물과 Sprint 4 준비/진행용 구현이 함께 존재한다.
실행 전에는 `docs/resume.md`, `docs/runbooks/local-dev.md`, 관련 Sprint 문서를
먼저 확인한다.

## 3. 디렉토리 지도 (계획)

```
apps/
  api/                       ← FastAPI 백엔드 (uv, pyproject.toml)
    app/
      api/routes/            ← FastAPI 라우터
      core/                  ← 설정, 의존성 등
      models/                ← SQLAlchemy 매핑 (app schema만)
      schemas/               ← Pydantic v2
      services/              ← 비즈니스 로직
      etl_bridge/            ← python-krtour-map 클라이언트 주입
    alembic/                 ← app schema migration (feature schema는 별 저장소)
    tests/
  web/                       ← Next.js App Router + admin
    app/
    public/
    tests/
  etl/                       ← Dagster definitions/jobs/schedules
    definitions.py
    assets/                  ← TripMate 자체 Dagster job / 외부 갱신 trigger

packages/                    ← 공유 TS 패키지 (필요 시)
  ui/
  schemas/                   ← Zod schema 공용
  api-client/                ← fetch wrapper + query keys
  design-tokens/             ← 16색 팔레트 + Tailwind preset
  hooks/                     ← useUserLocation 등 공용 React hook

infra/
  docker-compose.yml         ← 개발용
  docker-compose.app.yml     ← 운영용
  odroid/                    ← Odroid M1S 배포 manifest

docs/
  architecture.md
  agent-guide.md
  dev-environment.md
  data-model.md              ← app 도메인 (사용자/여행계획/POI)
  postgres-schema.md
  decisions.md
  journal.md
  resume.md
  tasks.md
  test-strategy.md
  krtour-map-integration.md
  sprints/
    README.md
    SPRINT-1.md
    ...

dataset/                     ← NTFS 보관 (.gitignore)
refdocs/                     ← 외부 spec/문서 (.gitignore)
```

본 저장소의 의존 방향(계획): **schemas → models → services → routes**.
`tripmate.etl`은 `tripmate.api.services`와 분리된 코드 위치이며 같은 DB schema
(`app`)에 책을 댄다.

`apps/api`는 `TRIPMATE_KRTOUR_MAP_API_BASE_URL`의 OpenAPI HTTP 계약으로 feature를
조회한다. `apps/etl`은 TripMate 자체 job과 외부 서비스 갱신 trigger를 담당한다.

## 4. 절대 하지 말 것 (DO NOT)

1. **main에 직접 push 금지** — feature branch + PR (ADR-001 후속).
2. **`feature`/`provider_sync` schema에 TripMate가 직접 DDL/migration 작성 금지** —
   해당 schema는 `python-krtour-map`이 소유. TripMate는 `app` schema와 자체
   도메인만 관리.
3. **provider raw → DTO 변환 직접 작성 금지** — `python-krtour-map.providers`에
   위임. 새 provider는 그쪽 저장소에 PR.
4. **TripMate 사용자 경로에서 `python-krtour-map` import 금지** — 최신
   `openapi.user.json` 기반 HTTP client만 사용한다.
5. **`feature` 도메인 wrapper 신규 생성 금지** — HTTP client는 transport 역할만.
   provider 변환, feature 정규화, dedup 같은 도메인 로직은 krtour-map 저장소에서
   처리한다.
6. **NTFS에서 직접 `pytest`/`docker`/`npm` 실행 금지** — WSL ext4 미러에서
   실행. 단 **git은 예외** — NTFS worktree에서 Windows `git.exe`로만 (ADR-024).
   ext4 미러에서 commit/push 금지. PowerShell `rg.exe` 금지 (WSL native `rg`만).

### Telegram 완료 알림 MCP (모든 agent)

각 worktree에는 `mcp-telegram` MCP 설정(`claude.json`/`.codex/config.toml`/
`.gemini/mcp.json`/`antigravity.json`)과 로컬 `.env.mcp-telegram` credential
(`API_ID`/`API_HASH`, gitignore)이 있다. **단위 작업을 PR로 마무리하면 최종 응답 전
`send_message`로 완료 요약 + PR 링크를 Telegram에 보낸다.** GitHub secret/워크플로는
쓰지 않는다. 셋업·로그인은 `docs/runbooks/codegraph-worktrees.md` §3.7.
7. **좌표 순서 혼동 금지** — 모든 외부 인터페이스는 `(lon, lat)`. 라이브러리
   DTO와 동일.
8. **카테고리/마커 매핑 하드코드 금지** — `python-krtour-map`의 카테고리 표 사용.
   TripMate UI는 그 표에서 읽어 maki/icon 매핑.
9. **외부 API 키 평문 커밋 금지** — `SecretStr`. `.env` 권한 600 또는 systemd
   `EnvironmentFile`/vault.
10. **시간 직접 사용 금지** — 모든 datetime은 KST aware (`Asia/Seoul`). naive
    datetime을 DTO/DB에 넣지 않는다. `python-krtour-map`의 `kst_now()` 또는
    동등 helper 사용.
11. **데이터/원천 파일을 git에 커밋 금지** — `dataset/`, `refdocs/`, `data/`,
    `artifacts/`는 `.gitignore`. NTFS 보관.
12. **공간 쿼리 술어에서 `ST_Transform` 금지** — 입력 좌표는 CTE/파라미터로
    한 번만 변환. 술어는 `ST_DWithin(t.coord_5179, p.geom, :radius_m)`처럼
    인덱스 있는 컬럼을 그대로 둔다. **반경 검색은 `coord_5179`(meter) 기준**.
13. **SQLAlchemy bulk `insert().values(rows)` 파라미터 폭주 금지** — 한 쿼리당
    65,535개 한도. row × column이 ~30,000 이상이면 `psycopg.copy_*` 또는
    `gdal.VectorTranslate(... PG_USE_COPY=YES)` 전환.
14. **작업 큐 상태를 in-memory만 신뢰 금지** — `app.import_jobs` 또는 동등
    영속 테이블 사용. 다중 워커는 `pg_try_advisory_lock` + `FOR UPDATE SKIP
    LOCKED`.
15. **`Feature.detail`을 자유 dict로 사용 금지** — `python-krtour-map`의
    `PlaceDetail`/`EventDetail` 등 Pydantic 모델 인스턴스 → `.model_dump()`.
16. **사용자 데이터를 클라이언트 응답에 평문으로 다 노출 금지** — 권한 별로
    필드 마스킹. 토큰/세션/이메일/전화는 보안 정책에 따른다.
17. **Admin 권한 체크를 클라이언트만 신뢰 금지** — 모든 보호 라우터는 서버
    middleware/dependency에서 권한 검증. UI 라우팅은 보조.
18. **Telegram/Resend/AI companion webhook payload 무검증 금지** —
    HMAC/signature/idempotency 검증 후 처리.
19. **Dagster asset이 `python-krtour-map`의 `infra/`/`providers/`를 직접 부르지
    말 것** — krtour-map provider 적재는 그 저장소의 API/Admin/Dagster가 소유한다.
20. **`apps/web`에서 외부 API 키 직접 호출 금지** — 모든 외부 호출은 백엔드
    경유. 클라이언트는 TripMate API만 호출.
21. **컴포넌트 / 함수 / 서비스를 영향도 평가 없이 수정 금지** (ADR-017) — 수정
    전 `codegraph_explore`로 관련 심볼 source + 호출 관계를 한 번에 본다. 보조:
    `codegraph_impact` (반경) / `codegraph_callers` (호출자) / `codegraph_trace`
    (경로). grep / Read fan-out으로 같은 일을 재현하지 않는다.

전체 룰은 추가될 수 있다. 작업 중 발견하면 ADR과 함께 본 §4에 추가.

## 5. 자주 묻는 작업

| 작업 | 시작 파일 |
|------|-----------|
| 새 사용자 도메인 필드 추가 | `packages/schemas/src/<entity>.ts` (Zod) + `apps/api/app/schemas/<entity>.py` → `models/<entity>.py` → `services/<entity>.py` → `api/routes/<entity>.py` + Alembic |
| 새 Admin CRUD 추가 | `services/admin_entity_crud.py`에 entity 등록 → 라우터 + UI `apps/web/app/admin/<entity>/page.tsx` (shadcn/ui DataTable) |
| 새 외부 API 통합 (provider) | **`python-krtour-map`에 PR** (raw → DTO + 적재). 본 저장소는 필요 시 갱신 요청 API만 호출 |
| 새 Dagster asset 추가 | TripMate `app` schema 소유 job만 추가. krtour-map feature 적재 job은 그 저장소에서 처리 |
| 새 알림 채널 추가 (Telegram/이메일/푸시) | `apps/api/app/services/<channel>.py` + webhook 라우터 + 환경변수 |
| Postgres `app` schema 변경 | `apps/api/alembic/versions/...` migration + `docs/postgres-schema.md` 갱신 |
| `feature`/`provider_sync` schema 변경 | **`python-krtour-map`에서 작업**. 본 저장소는 사용 측 코드만 갱신 |
| 새 RustFS 버킷 추가 | `apps/api/app/services/file_storage.py` + 환경변수 + Admin UI |
| 새 frontend 화면 추가 | `packages/schemas/`에 Zod → `packages/api-client/`에 endpoint → `apps/web/app/<route>/page.tsx` (shadcn/ui + Airbnb 톤 — `docs/architecture/frontend.md`) |
| 위치 정보 사용처 추가 | `packages/hooks/src/useUserLocation.ts` 활용 + 동의 확인 + `app.location_access_log` 자동 적재 (`docs/architecture/user-location.md`) |
| 새 notice plan 카테고리 / POI 컴포넌트 | `docs/architecture/notice-plans.md` 참고. **notice plan ≠ notice feature** |
| 기존 함수 / 컴포넌트 수정 (영향도 평가) | **`codegraph_explore`** 1차 → 필요 시 `codegraph_impact` (반경) / `codegraph_callers` (호출자). 답이 인덱스에서 나오면 Read 생략 (ADR-017) |
| CodeGraph 인덱스가 stale로 의심 | `codegraph status` → `codegraph sync` → 안 풀리면 `codegraph index --force` |

## 6. 도메인 어휘

| 약어 | 의미 |
|------|------|
| Trip | 사용자 여행 계획 (시작·종료 일자, 동행자, POI 목록) |
| TripDay | Trip의 일자별 분할 (이동 경로 / POI 순서) |
| POI Attachment | TripDay의 POI 첨부 — `feature_id` reference + 사용자 메모/사진 |
| Notice Plan | Admin이 운영하는 공지 (일반 / 점검 / 이벤트) — 기간/대상/우선순위 |
| Library API | 본 저장소가 `python-krtour-map`을 호출할 때 거치는 thin facade (DI helper) |
| Feature | `python-krtour-map`의 단일 객체 — TripMate는 `feature_id`로 참조만 |
| feature_id | `python-krtour-map`이 발급한 결정적 PK. 포맷 `f_{bjd_code}_{kind[0]}_{sha1(...)[:16]}` |
| Provider | 한국 공공 API의 데이터 공급자 (KMA, VisitKorea, OpiNet, MOIS, ...) |
| Dataset key | provider 내 sub-dataset 식별자 (`search_list`, `gis_spca`, ...) |
| `app` schema | TripMate 도메인 (사용자/여행계획/공지/첨부) |
| `feature` schema | `python-krtour-map` 소유 (Feature/SourceRecord/SourceLink/...) |
| Notice plan | Admin이 만든 추천 여행 plan (`app.notice_plans`). 사용자 trip으로 copy 가능 |
| Notice feature | 지도 위 공지·자연현상 feature (라이브러리 소유, kind=notice). **Notice plan과 별개 개념** |
| Plan POI attachment | 단일 테이블 `plan_poi_attachments` (trip / trip_poi / notice_plan / notice_poi 중 정확히 하나 채움) |
| RustFS | S3 호환 객체 저장소. TripMate `app` 첨부 + `python-krtour-map` 미디어 분리 |
| Soak test | ETL 장시간(20시간±) 검증. `scripts/etl-soak-*.sh` (v1 자산, v2에서 재정비) |
| WSL 테스트 미러 | `~/tripmate-workspaces/tripmate-<agent>` — ext4 일회용 실행 사본(테스트/docker). git은 NTFS worktree (ADR-024) |

추가 도메인 어휘는 `docs/data-model.md` §용어 사전에 정렬.

## 7. 작업 후 체크리스트

- [ ] `pytest apps/api/tests -q` 통과 (단위 + 일부 통합)
- [ ] `ruff check apps/api` / `mypy --strict apps/api/app` 통과
- [ ] `npm run lint` / `npm run typecheck` / `npm run build` (`apps/web`)
- [ ] `docs/journal.md`에 작업 항목 추가 (역시간순)
- [ ] `docs/resume.md`의 진척도 갱신
- [ ] 의사결정이 있었다면 `docs/decisions.md`에 ADR 추가
- [ ] 사용자 가시 변경이면 `CHANGELOG.md` 갱신 (코드 작성 단계 진입 후)
- [ ] DTO/스키마 변경이면 OpenAPI export 재실행 (코드 작성 단계 진입 후)

## 8. 첫 5분 진입 프로토콜

새 세션이 들어오면 이 순서로 읽는다:

1. 도구별 1차 진입 파일
   - Claude: `CLAUDE.md`
   - Codex / Antigravity / Cursor / Copilot: `AGENTS.md`
2. `AGENTS.md` — 작업 룰
3. 본 파일 `SKILL.md` — DO NOT, 도메인 어휘
4. `docs/agent-guide.md` — 기록·ADR·PR 워크플로
5. `docs/sprints/README.md` — Sprint 1~N 계획
6. `docs/resume.md` — 현재 상태와 다음 한 작업
7. `docs/journal.md` 최신 3건 — 직전 컨텍스트
8. `README.md` — 저장소 정체성과 문서 지도
9. 관련 ADR (`docs/decisions.md`)

## 9. 현재 단계 메모

초기 문서화 단계의 "코드 작성 금지" 규칙은 더 이상 현재 상태를 설명하지 않는다.
현 기준선은 Sprint 1~3 머지 완료, Sprint 4 준비/진행 단계다.

- 코드 변경 가능 범위와 책임 경계는 `AGENTS.md`의 "현재 단계 정책"을 따른다.
- 구현 우선순위는 `docs/resume.md`, `docs/tasks.md`, `docs/sprints/SPRINT-4.md`를
  함께 본다.
- `python-krtour-map` 책임 범위를 넘는 기능은 이 저장소에서 직접 구현하지 않는다.
