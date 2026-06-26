# Admin 콘솔 기능 보강 실행 계획

작성일: 2026-06-27
작성자: codex
상태: 리뷰 대기
관련 문서: `docs/api/admin.md`, `docs/runbooks/admin.md`, `docs/spec/v8/04-admin.md`,
`docs/architecture/frontend.md`, `docs/conventions/testing.md`,
`docs/kor-travel-map-integration.md`

## 목적

현재 Admin 콘솔은 Sprint 3에서 v1 골격을 이식했지만, 실제 운영에 필요한 화면과 기능이
여러 곳에서 메뉴/placeholder 수준에 머물러 있다. 특히 `features`, `etl`,
`category-mapping`, `seed`, `reset` 페이지는 Web route만 존재하고 기능이 비어 있으며,
`kor-travel-map`이 이미 가진 feature 운영, dedup, provider sync, integrity, debug/log
화면과 비교하면 Pinvi Admin의 운영 동선이 충분하지 않다.

이 계획은 구현을 시작하기 전에 필요한 메뉴 구조, API 경계, 세부 Task, 검증 게이트를
정리한다. 다른 에이전트가 이 문서를 리뷰한 뒤 Task 단위 PR로 순차 구현한다.

## 작업 원칙

- Pinvi는 `feature` / `provider_sync` schema를 직접 소유하지 않는다. 지도 feature 정규화,
  dedup, provider sync 원천 저장은 `kor-travel-map` 책임이며, Pinvi Admin은 최신
  `kor-travel-map` OpenAPI/Admin HTTP 계약을 통해 조회/명령한다.
- Pinvi가 직접 소유하는 것은 사용자, 여행 계획, POI attachment, notice plan import,
  email, audit, backup, RustFS, MCP token, Pinvi API 운영 기능이다.
- 운영 도메인, SSH target, 사설 IP, token, API key, 실제 비밀번호는 tracked 문서와 로그에
  남기지 않는다. N150 접속/배포 세부값은 gitignore된 local runbook과 원격 env에서만 읽고,
  PR 본문과 journal에는 placeholder 또는 "N150"만 적는다.
- Task는 하나의 사용자 가치 단위로 쪼개고, 각 Task는 별도 branch, 별도 PR, merge 후 다음
  Task 진입을 원칙으로 한다.
- 단위 기능 검증은 로컬 WSL ext4 미러에서 수행한다. 여러 기능이 모인 뒤 N150에서 묶음
  live API/UI/e2e 게이트를 수행한다.

## 현재 상태 요약

### 이미 구현된 Pinvi Admin 영역

- Backend router: `users`, `trips`, `pois`, `feature_requests`, `notice_plans`, `audit`,
  `api_calls`, `stats`, `emails`, `backup`, `mcp_tokens`, `rustfs`
- Web page: dashboard, users, trips, POIs, feature requests, notice plans, audit, API calls,
  emails, backup, MCP tokens, RustFS 등
- Live e2e foundation: Admin route matrix와 N150 live authenticated run 기반은 T-203에서
  추가됐다.
- Bootstrap admin: T-206으로 `PINVI_BOOTSTRAP_ADMIN_PASSWORD` 기반 startup 생성/복구
  경로가 main에 들어왔다.

### 기능적으로 비어 있는 영역

- `apps/web/app/(admin)/admin/features/page.tsx`
- `apps/web/app/(admin)/admin/etl/page.tsx`
- `apps/web/app/(admin)/admin/category-mapping/page.tsx`
- `apps/web/app/(admin)/admin/seed/page.tsx`
- `apps/web/app/(admin)/admin/reset/page.tsx`
- `packages/api-client/src/endpoints/admin.ts`에는 위 화면을 받칠 proxy/operation endpoint가
  거의 없다.
- `apps/api/app/clients/kor_travel_map_admin.py`는 feature change request 일부만 감싸며,
  feature list/detail, dedup, provider ops, consistency, system/api logs 등은 아직 없다.
- `apps/web/e2e/admin-live-matrix.live.ts`는 placeholder route를 placeholder로 인정하는
  케이스를 갖고 있어, 실제 기능 누락을 실패로 잡지 못한다.

## `kor-travel-map` Admin에서 참고할 기능

Pinvi에 그대로 복제하지 않고, 운영 동선과 정보 구조를 참고한다.

- Feature 운영: `/v1/admin/features` 기반 목록/상세, status/kind/source/category 검색,
  detail inspector, source/geometry/metadata 확인, change request로 수정 명령.
- Change/update request: feature 생성/수정/삭제 요청, approve/reject/apply 상태 전이,
  실패 사유 확인.
- Dedup review: 후보 목록, confidence/상태 필터, survivor/duplicate 비교, merge/reject action.
- Provider/ETL ops: provider별 상태, import job, run-now/cancel, 최근 실행/오류, Dagster 링크.
- Integrity/consistency: issue 목록, report 단위 drill-down, severity/status 필터, resolution action.
- Debug/logs: system logs, API call logs, request timeline, upstream error payload 확인.
- UI 패턴: 좌측 운영 메뉴, 필터 toolbar, data table, detail side panel, bulk action, 상태 badge,
  mutation confirmation, audit reason 입력.

## 목표 메뉴 구조

### 1. Pinvi 운영

| 메뉴 | Route | 소유 | 목표 |
|------|-------|------|------|
| 대시보드 | `/admin` | Pinvi | Pinvi API/Web/Dagster, kor-travel-map 연결, 최근 오류/대기 작업 요약 |
| 회원 | `/admin/users` | Pinvi | 기존 기능 유지 + 검색/상태/audit 동선 정리 |
| 여행 계획 | `/admin/trips` | Pinvi | 기존 기능 유지 + POI/notice plan 연결 drill-down |
| POI | `/admin/pois` | Pinvi | 기존 기능 유지 + feature link 상태와 upstream feature 상세 연결 |
| Notice plan | `/admin/notice-plans` | Pinvi | curated import, attachment, 공개/숨김 운영 |
| 제보/요청 | `/admin/feature-requests` | Pinvi + kor-travel-map | Pinvi 사용자 제보와 upstream change request 상태 연결 |
| Audit | `/admin/audit` | Pinvi | 기존 hash chain/audit 조회 유지 |

### 2. 지도 데이터 운영

| 메뉴 | Route | 소유 | 목표 |
|------|-------|------|------|
| Features | `/admin/features` | kor-travel-map proxy | feature 목록/상세/상태/source/geometry/metadata 조회 |
| Change requests | `/admin/features/change-requests` | kor-travel-map proxy | 생성/수정/삭제 요청 approve/reject/apply |
| Dedup review | `/admin/dedup-review` | kor-travel-map proxy | dedup 후보 비교 및 merge/reject |
| Provider sync | `/admin/provider-sync` | kor-travel-map proxy | provider별 최신 실행, run-now/cancel, 오류 확인 |
| Integrity | `/admin/integrity` | kor-travel-map proxy | consistency report/issue 조회와 상태 변경 |
| Debug logs | `/admin/debug/logs` | kor-travel-map proxy | upstream system/API logs, request timeline |

### 3. Pinvi 시스템 운영

| 메뉴 | Route | 소유 | 목표 |
|------|-------|------|------|
| ETL/Dagster | `/admin/etl` | Pinvi + kor-travel-map link | Pinvi Dagster 상태와 map provider job 요약 |
| Grafana | `/admin/grafana` | Pinvi observability | 기존 iframe route 유지, T-208에서 ETL/Observability 그룹 아래 배치 |
| API calls | `/admin/api-calls` | Pinvi | 기존 API call log 유지 + upstream request link |
| Emails | `/admin/emails` | Pinvi | queue 상태, resend/retry, 실패 사유 |
| Backup | `/admin/backup` | Pinvi | snapshot/restore 핫스왑 유지 |
| RustFS | `/admin/rustfs` | Pinvi | bucket/object 상태 |
| MCP tokens | `/admin/mcp-tokens` | Pinvi | token 발급/회수 |
| Category mapping | `/admin/category-mapping` | Pinvi + map catalog | Pinvi 표시 카테고리/마커 팔레트와 map category catalog 연결 |
| Seed | `/admin/seed` | dev-only Pinvi | 개발/테스트 seed 실행, 운영 비활성 |
| Reset | `/admin/reset` | dev-only Pinvi | 개발 DB reset/cleanup, 운영 비활성 |

## Task 분해

### T-207 — Admin 보강 실행 계획 문서화

범위: 본 문서, `docs/tasks.md`, `docs/resume.md`, `docs/journal.md` 갱신.

완료 기준:

- 현재 placeholder와 기능 격차가 문서화된다.
- `kor-travel-map` 참고 기능과 Pinvi 책임 경계가 명시된다.
- 이후 Task의 순서, 검증 방식, N150 묶음 게이트가 정리된다.
- 계획 PR을 먼저 merge하고, 다른 에이전트 리뷰 후 구현 Task로 진입한다.

### T-208 — Admin IA / 메뉴 / 대시보드 상태판 보강

범위:

- Admin sidebar/menu를 위 목표 구조로 재정렬한다.
- placeholder route는 "준비 중"으로 숨기지 말고, 기능 gap과 다음 Task 링크를 보여준다.
- `/admin` dashboard에 Pinvi API, DB, Web, Dagster, kor-travel-map API, RustFS 연결 상태와
  최근 오류/대기 작업 count를 노출한다.
- `admin-live-matrix.live.ts`에서 route 그룹과 placeholder 정책을 새 구조에 맞춘다.

API:

- 기존 `/admin/stats`, `/health`, `/health/db` 활용.
- 필요한 경우 `/admin/system/summary`를 추가하되, secret/env raw value는 노출하지 않는다.

검증:

- 로컬 API unit/integration, Web typecheck/lint/Vitest.
- 로컬 Playwright로 dashboard/menu navigation 확인.

### T-209 — `kor-travel-map` Admin proxy foundation + Features 화면

범위:

- 구현 시작 전 `kor-travel-map` 최신 OpenAPI/Admin 계약을 확인하고, Pinvi proxy가 사용할
  endpoint/path/response envelope를 기록한다.
- `KorTravelMapAdminClient`에 feature list/detail 조회와 공통 error mapping을 추가한다.
- Pinvi API에 `/admin/features` proxy router를 추가한다.
- `packages/api-client`와 Web query hook을 추가한다.
- `/admin/features` placeholder를 검색/필터/table/detail inspector로 교체한다.

금지:

- Pinvi DB에 `feature.*` raw table을 직접 query하지 않는다.
- feature 수정은 직접 update가 아니라 upstream change request API로만 보낸다.

검증:

- `httpx.MockTransport` 기반 admin client unit.
- FastAPI integration에서 upstream fake dependency로 list/detail/error mapping 검증.
- Web component/Vitest + local Playwright table/detail navigation.

### T-210 — Feature request / change request 운영 통합

범위:

- 기존 Pinvi 사용자 제보(`/admin/feature-requests`)와 upstream change request 상태를 연결한다.
- `/admin/features/change-requests`를 추가해 pending/applied/rejected/failed 큐를 운영한다.
- approve/reject/apply action은 reason 입력, audit 기록, optimistic UI rollback을 갖춘다.

검증:

- API integration: Pinvi request 상태 전이, upstream fake apply/reject, audit append.
- UI e2e: approve/reject confirmation, 실패 메시지, detail refresh.

### T-211 — ETL / provider sync / Dagster 운영 화면

범위:

- 구현 시작 전 `kor-travel-map` 최신 OpenAPI/Admin ops 계약을 확인한다.
- `/admin/etl` placeholder를 제거한다.
- `kor-travel-map` `/v1/ops/metrics`, `/v1/ops/providers`, import job 계열 API를 proxy한다.
- provider별 최신 실행, 실패 사유, run-now/cancel, Dagster 링크를 제공한다.
- Pinvi 자체 Dagster health와 map provider ops를 한 화면에서 구분한다.
- run-now/cancel 같은 mutation은 reason 입력, audit 기록, upstream kill-switch 확인,
  idempotency key 또는 중복 실행 방지 기준을 완료조건에 포함한다.

검증:

- API client unit + FastAPI upstream fake.
- UI e2e: provider filter, run-now disabled/confirm, failure detail.

### T-212 — Dedup / integrity / debug logs

범위:

- 구현 시작 전 `kor-travel-map` 최신 OpenAPI/Admin dedup/integrity/log 계약을 확인한다.
- `/admin/dedup-review`, `/admin/integrity`, `/admin/debug/logs` route를 추가한다.
- dedup 후보 비교, merge/reject action, consistency issue 상태 변경, system/API logs 필터를
  제공한다.
- API call log에서 upstream request id가 있으면 debug timeline으로 연결한다.
- merge/reject/status mutation은 reason 입력, audit 기록, upstream kill-switch 확인,
  idempotency key 또는 중복 처리 방지 기준을 완료조건에 포함한다.

검증:

- API integration: pagination/filter/action/error mapping.
- UI e2e: candidate comparison, issue status filter, log detail drawer.

### T-213 — Category mapping 실제 기능

범위:

- Pinvi 표시 카테고리, marker palette, upstream map category catalog의 연결 규칙을 정리한다.
- read-only catalog 확인부터 시작하고, Pinvi가 소유해야 할 mapping 저장소가 필요하면
  별도 migration/ADR 여부를 먼저 판단한다.
- UI는 category search, unmapped count, marker preview, export/import 초안을 제공한다.

결정 필요:

- mapping source of truth가 Pinvi `app` schema인지, `kor-travel-map` catalog인지, 혹은
  양쪽 계약인지 리뷰 후 확정한다.

검증:

- 결정 전에는 read-only 테스트만 작성한다.
- mutation 도입 시 DB migration + API integration + UI e2e를 포함한다.

### T-214 — Seed / reset dev-only 안전장치

범위:

- `/admin/seed`, `/admin/reset` placeholder를 제거하되, 운영에서는 명시적으로 비활성화한다.
- `PINVI_ENVIRONMENT`가 production이면 seed/reset router를 include하지 않고 API는 404만
  반환한다. UI는 destructive action을 렌더링하지 않는다.
- dev/smoke에서는 confirmation phrase, reason, audit, dry-run, 대상 범위를 제공한다.

검증:

- API integration: production 404, dev dry-run, confirmation mismatch, audit append.
- UI e2e: production hidden/404-safe, dev confirm flow.

### T-215 — Admin live e2e 확장 + N150 묶음 게이트

범위:

- placeholder를 허용하던 live matrix 정책을 새 구현 상태 기준으로 조정한다.
- API-level live smoke, UI route matrix, authenticated workflows를 묶음으로 실행한다.
- N150 실행은 기능 2~3개 또는 메뉴 그룹 하나가 모인 뒤 수행한다.

N150 게이트:

- 단위 Task마다 N150 재배포하지 않는다.
- 묶음 게이트에서만 `ktdctl pinvi --build` 또는 해당 시점의 운영 배포 절차를 사용한다.
- 실행 전후 컨테이너 health, API `/health`, `/health/db`, Web `/admin/login`, 주요 admin route,
  upstream `kor-travel-map` health를 확인한다.
- 실제 운영 도메인/SSH target/env 값은 출력하지 않는다.

## 구현 순서

1. T-207 계획 PR merge.
2. 다른 에이전트 계획 리뷰 반영.
3. T-208 IA/dashboard PR.
4. T-209 feature proxy/read UI PR.
5. T-210 change request 운영 PR.
6. T-211 ETL/provider sync PR.
7. T-212 dedup/integrity/debug PR.
8. T-213 category mapping PR.
9. T-214 seed/reset dev-only PR.
10. T-215 묶음 live e2e/N150 게이트 PR 또는 release-gate PR.

## 검증 정책

### 로컬 단위 검증

- API 변경: 관련 `pytest` integration/unit, `ruff check`, 필요한 경우 `mypy`.
- API client/schema 변경: package test/typecheck.
- UI 변경: Web typecheck, lint, Vitest, local Playwright focused e2e.
- 문서만 변경: `git diff --check`, tracked secret scan.

### N150 묶음 검증

- 기능별 PR마다 N150을 쓰지 않는다.
- 메뉴 그룹 또는 여러 Task가 합쳐진 시점에 live API/UI/e2e를 실행한다.
- N150 테스트 전후로 운영 컨테이너 health를 확인하고, 실패 시 원복/재기동 절차를 먼저
  수행한다.
- 테스트 결과에는 command, 환경, pass/fail, 알려진 제약만 기록하고 민감값은 제외한다.

## 리뷰 포인트

- Pinvi가 `kor-travel-map` 책임을 침범하는 메뉴/기능이 있는가?
- placeholder 제거 순서가 운영자에게 실제 가치를 주는 순서인가?
- Category mapping source of truth 결정이 ADR 없이 진행돼도 되는가?
- Seed/reset을 운영에서 숨기는 정책이 충분히 보수적인가?
- N150 묶음 게이트 주기가 너무 잦거나 너무 느슨하지 않은가?
