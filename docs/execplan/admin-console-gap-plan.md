# Admin 콘솔 기능 보강 실행 계획

작성일: 2026-06-27
작성자: codex
상태: T-227 구현 완료 / PR 준비
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

- `apps/web/app/(admin)/admin/features/page.tsx` — T-209에서 read-only 목록/상세 구현 완료
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

| 메뉴        | Route                     | 소유                   | 목표                                                                 |
| ----------- | ------------------------- | ---------------------- | -------------------------------------------------------------------- |
| 대시보드    | `/admin`                  | Pinvi                  | Pinvi API/Web/Dagster, kor-travel-map 연결, 최근 오류/대기 작업 요약 |
| 회원        | `/admin/users`            | Pinvi                  | 기존 기능 유지 + 검색/상태/audit 동선 정리                           |
| 여행 계획   | `/admin/trips`            | Pinvi                  | 기존 기능 유지 + POI/notice plan 연결 drill-down                     |
| POI         | `/admin/pois`             | Pinvi                  | 기존 기능 유지 + feature link 상태와 upstream feature 상세 연결      |
| Notice plan | `/admin/notice-plans`     | Pinvi                  | curated import, attachment, 공개/숨김 운영                           |
| 제보/요청   | `/admin/feature-requests` | Pinvi + kor-travel-map | Pinvi 사용자 제보와 upstream change request 상태 연결                |
| Audit       | `/admin/audit`            | Pinvi                  | 기존 hash chain/audit 조회 유지                                      |

### 2. 지도 데이터 운영

| 메뉴            | Route                             | 소유                 | 목표                                                 |
| --------------- | --------------------------------- | -------------------- | ---------------------------------------------------- |
| Features        | `/admin/features`                 | kor-travel-map proxy | feature 목록/상세/상태/source/geometry/metadata 조회 |
| Change requests | `/admin/features/change-requests` | kor-travel-map proxy | 생성/수정/삭제 요청 approve/reject/apply             |
| Dedup review    | `/admin/dedup-review`             | kor-travel-map proxy | dedup 후보 비교 및 merge/reject                      |
| Provider sync   | `/admin/provider-sync`            | kor-travel-map proxy | provider별 최신 실행, run-now/cancel, 오류 확인      |
| Integrity       | `/admin/integrity`                | kor-travel-map proxy | consistency report/issue 조회와 상태 변경            |
| Debug logs      | `/admin/debug/logs`               | kor-travel-map proxy | upstream system/API logs, request timeline           |

### 3. Pinvi 시스템 운영

| 메뉴             | Route                     | 소유                        | 목표                                                               |
| ---------------- | ------------------------- | --------------------------- | ------------------------------------------------------------------ |
| ETL/Dagster      | `/admin/etl`              | Pinvi + kor-travel-map link | Pinvi Dagster 상태와 map provider job 요약                         |
| Grafana          | `/admin/grafana`          | Pinvi observability         | 기존 iframe route 유지, T-208에서 ETL/Observability 그룹 아래 배치 |
| API calls        | `/admin/api-calls`        | Pinvi                       | 기존 API call log 유지 + upstream request link                     |
| Emails           | `/admin/emails`           | Pinvi                       | queue 상태, resend/retry, 실패 사유                                |
| Backup           | `/admin/backup`           | Pinvi                       | snapshot/restore 핫스왑 유지                                       |
| RustFS           | `/admin/rustfs`           | Pinvi                       | bucket/object 상태                                                 |
| MCP tokens       | `/admin/mcp-tokens`       | Pinvi                       | token 발급/회수                                                    |
| Category mapping | `/admin/category-mapping` | Pinvi + map catalog         | Pinvi 표시 카테고리/마커 팔레트와 map category catalog 연결        |
| Seed             | `/admin/seed`             | dev-only Pinvi              | 개발/테스트 seed 실행, 운영 비활성                                 |
| Reset            | `/admin/reset`            | dev-only Pinvi              | 개발 DB reset/cleanup, 운영 비활성                                 |

## Task 분해

### T-207 — Admin 보강 실행 계획 문서화

범위: 본 문서, `docs/tasks.md`, `docs/resume.md`, `docs/journal.md` 갱신.

완료 기준:

- 현재 placeholder와 기능 격차가 문서화된다.
- `kor-travel-map` 참고 기능과 Pinvi 책임 경계가 명시된다.
- 이후 Task의 순서, 검증 방식, N150 묶음 게이트가 정리된다.
- 계획 PR을 먼저 merge하고, 다른 에이전트 리뷰 후 구현 Task로 진입한다.

### T-208 — Admin IA / 메뉴 / 대시보드 상태판 보강

상태: 완료(2026-06-27, codex). 구현 PR은 `/admin/system/summary`, 그룹형 sidebar, gap-aware
placeholder route, live matrix route 확장을 포함한다. N150 live 실행은 T-215 묶음 게이트에서 수행한다.

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

상태: 완료(2026-06-27, codex). 구현 PR은 `kor-travel-map` `/v1/admin/features` read-only
계약을 Pinvi `/admin/features` proxy와 Web 화면에 연결한다. N150 live 실행은 T-215 묶음
게이트에서 수행한다.

범위:

- 구현 시작 전 `kor-travel-map` 최신 OpenAPI/Admin 계약을 확인하고, Pinvi proxy가 사용할
  endpoint/path/response envelope를 기록한다.
- `KorTravelMapAdminClient`에 feature list/detail 조회와 공통 error mapping을 추가한다.
- Pinvi API에 `/admin/features` proxy router를 추가한다.
- `packages/api-client`와 Web query hook을 추가한다.
- `/admin/features` placeholder를 검색/필터/table/detail inspector로 교체한다.

확인한 upstream 계약:

- `GET /v1/admin/features`
  - query: `q`, 반복 `kind`, `category`, `status`, `provider`, `dataset_key`, `issue_type`,
    `has_coord`, `has_issue`, `updated_from`, `updated_to`, `page_size`, `cursor`, `sort`, `order`
  - response envelope: `data.items[]`, `meta.page.next_cursor`, `meta.duration_ms`
- `GET /v1/admin/features/{feature_id}`
  - response envelope: `data.feature`, `data.sources`, `data.issues`, `data.overrides`,
    `data.versions`, `data.change_requests`, `data.files`

구현:

- `KorTravelMapAdminClient.list_features()` / `get_feature_detail()` read method 추가.
- Pinvi API `/admin/features` / `/admin/features/{feature_id}` 추가. admin/operator read-only이며
  Pinvi DB `feature.*`를 직접 조회하지 않는다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 Admin feature 목록/상세 계약 추가.
- Web `/admin/features`를 검색어, kind/status/provider/category/issue, sort/order,
  page_size, cursor 기반 table과 detail inspector로 교체.
- `admin-live-matrix.live.ts`에서 `/admin/features`를 placeholder가 아닌 table route로 전환하고
  feature filter/sort live case를 추가했다.

금지:

- Pinvi DB에 `feature.*` raw table을 직접 query하지 않는다.
- feature 수정은 직접 update가 아니라 upstream change request API로만 보낸다.

검증:

- `httpx.MockTransport` 기반 admin client unit.
- FastAPI integration에서 upstream fake dependency로 list/detail/error mapping 검증.
- Web typecheck/lint/build, schemas/api-client typecheck, schemas Vitest, admin live catalog/list와
  catalog assertion.
- local Playwright table/detail navigation은 WSL Playwright Chromium 바이너리 부재로 실행 전
  실패했다. mock e2e 테스트케이스는 추가했고 CI/Windows 또는 N150 묶음 게이트에서 실행한다.

### T-210 — Feature request / change request 운영 통합

상태: 완료(2026-06-27, codex). 구현 PR은 기존 Pinvi 사용자 feature 제안 검토 큐와
`kor-travel-map` feature change request 큐를 Admin에서 이어 볼 수 있게 하고, upstream
approve/reject 결과를 Pinvi audit에 남긴다. N150 live 실행은 T-215 묶음 게이트에서 수행한다.

범위:

- 기존 Pinvi 사용자 제보(`/admin/feature-requests`)와 upstream change request 상태를 연결한다.
- `/admin/features/change-requests`를 추가해 pending/applied/rejected 큐를 운영한다. 최초 계획의
  `failed` 상태는 2026-06-27 확인한 `kor-travel-map` `origin/main` OpenAPI(`c3d6385`)에는 아직
  없으므로, upstream 계약이 추가되면 Pinvi 필터만 확장한다.
- approve/reject/apply action은 reason 입력, audit 기록, optimistic UI rollback을 갖춘다.

확인한 upstream 계약:

- `GET /v1/admin/features/change-requests`
  - query: 반복 `status`(`pending`/`applied`/`rejected`), 반복 `action`(`add`/`update`/`delete`),
    `q`, `page_size`
  - response envelope: `data.items[]`, `data.review_mode`
- `POST /v1/admin/features/change-requests/{request_id}/approve`
- `POST /v1/admin/features/change-requests/{request_id}/reject`
  - body: `operator`, `reason`
  - response envelope: `data.request`

구현:

- `KorTravelMapAdminClient.list_change_requests()`에 status/action/q filter를 추가했다.
- Pinvi API `/admin/features/change-requests`, `/approve`, `/reject` proxy endpoint를 추가했다.
  mutation은 admin 전용이며 upstream 성공 후 `feature_change_request.*` audit을 commit한다.
- upstream 409 중 `LOCK_BUSY`는 rate-limit 계열로, 그 외 상태 충돌은 `409 INVALID_STATE`로 보존한다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 change request 목록/액션 계약을 추가했다.
- Web `/admin/features/change-requests` placeholder를 filter/table/detail/payload/action 화면으로 교체했다.
  pending row는 reason 입력 후 approve/reject 가능하며 실패 시 optimistic 상태를 rollback한다.
- 기존 `/admin/feature-requests`는 upstream `request_id`가 있으면 change request 큐로 이동하는 링크를 제공한다.

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

상태: 완료(2026-06-27, codex). 구현 PR은 `kor-travel-map` dedup review,
consistency issue/report, sanitized system/API logs read proxy와 Web 운영 화면을 포함한다.
dedup verdict, integrity issue 상태 변경/fix 같은 mutation은 reason/audit/idempotency/
kill-switch 기준이 필요해 T-226으로 분리한다.

범위:

- 구현 시작 전 `kor-travel-map` 최신 OpenAPI/Admin dedup/integrity/log 계약을 확인한다.
- `/admin/dedup-review`, `/admin/integrity`, `/admin/debug/logs` route를 추가한다.
- dedup 후보 비교, consistency issue/report 조회, system/API logs 필터를 제공한다.
- API call log에서 upstream request id를 표시해 후속 debug timeline 연결을 준비한다.

구현:

- `KorTravelMapAdminClient`에 `list_dedup_reviews`, `list_integrity_issues`,
  `list_consistency_reports`, `list_system_logs`, `list_ops_api_call_logs`를 추가했다.
- Pinvi API에 `GET /admin/dedup-review`, `GET /admin/integrity/issues`,
  `GET /admin/integrity/reports`, `GET /admin/debug/logs/system`,
  `GET /admin/debug/logs/api-calls`를 추가했다.
- provider sync와 새 ops route가 같은 upstream error mapping을 쓰도록 공통 `ops_proxy`
  helper를 도입했다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 dedup/integrity/debug read 계약을 추가했다.
- Web `/admin/dedup-review`는 status/search/min score 필터, 후보 table, feature A/B detail panel을
  제공한다.
- Web `/admin/integrity`는 issue status/severity/provider 필터와 report severity 필터,
  issue/report table을 제공한다.
- Web `/admin/debug/logs`는 system log level/source/q 필터와 upstream API call method/min status/path
  필터를 제공한다.
- `admin-live-matrix.live.ts`에서 세 route를 placeholder가 아닌 table route로 전환하고 filter/sort
  live case를 추가했다.

검증:

- API unit/integration: upstream path/query, pagination cursor, route RBAC, error mapping.
- UI e2e: candidate row/detail, issue/report 필터, system/API log 필터 query 전달.

### T-226 — Dedup verdict mutation

추가 요청에서 T-212에 포함됐던 위험 action 후속.

상태: 완료(2026-06-27, codex). `kor-travel-map` 최신 OpenAPI 확인 결과 dedup verdict는
`PATCH /v1/admin/dedup-reviews/{review_id}` 계약이 존재하고, consistency issue 상태 변경/fix는
GET-only라 T-227로 분리했다.

범위:

- `kor-travel-map` dedup review verdict API의 최신 OpenAPI 계약을 재확인한다.
- `/admin/dedup-review/{review_id}/verdict` relay를 upstream PATCH 계약에 맞춰 추가한다.
- mutation은 `access_reason`, Pinvi `admin_audit_log`, upstream reason 전달, upstream 404/409/429/503
  error mapping을 포함한다.
- Web은 후보 비교 detail panel에서 reason 입력, master feature 선택, 실패 사유, 성공 notice를 제공한다.

구현:

- `KorTravelMapAdminClient.decide_dedup_review`를 추가하고 upstream
  `PATCH /v1/admin/dedup-reviews/{review_id}`를 호출한다.
- Pinvi API `POST /admin/dedup-review/{review_id}/verdict`가 `decision`, `access_reason`,
  `kor_travel_map_reason`, `master_feature_id`를 검증하고, 성공 시 `dedup_review.decide` audit을
  남긴다.
- 공통 `ops_proxy` error mapping에 upstream 404/409와 `X-Request-Id` UUID parsing을 추가했다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 dedup verdict 계약과 list invalidate key를
  추가했다.
- Web `/admin/dedup-review` detail panel에 pending 후보 판정 form을 추가했다.

검증:

- API unit/integration: upstream PATCH body, merged master 필수 검증, audit append, 404/409/429/503
  mapping.
- UI e2e: pending 후보 선택, reason 입력, verdict submit, body 검증, 성공 notice.

### T-227 — Integrity issue status mutation

상태: 완료(2026-06-27, codex). 확인 결과 `kor-travel-map`의
`/v1/ops/consistency/issues`와 `/v1/ops/consistency/reports`는 read-only지만, 운영자 조치용
계약은 이미 `PATCH /v1/admin/issues/{issue_id}`에 존재한다. Pinvi는 자체 상태를 만들지 않고 이
admin issue 계약의 status action만 relay한다.

범위:

- upstream `resolve` / `ignore` / `reopen` action을 Pinvi
  `POST /admin/integrity/issues/{issue_id}/action`으로 노출한다.
- 모든 mutation은 `access_reason`, Pinvi `admin_audit_log`, upstream operator/reason 전달,
  upstream 404/409/429/503 error mapping을 포함한다.
- Web은 issue table의 조치 버튼에서 status action dialog, reason validation, 성공 notice,
  list invalidate/refetch를 제공한다.
- upstream의 `retry_geocode`, `retry_reverse_geocode`, `apply_kor_travel_geo_address`,
  `manual_override` 같은 주소/좌표 수동 보정 action은 `kor-travel-map` Admin 책임으로 남기고
  Pinvi에서는 이번 범위에 노출하지 않는다.

구현:

- `KorTravelMapAdminClient.patch_admin_issue()`가 `PATCH /v1/admin/issues/{issue_id}`에
  `{action, reason, operator}`를 전달한다.
- Pinvi API `POST /admin/integrity/issues/{issue_id}/action`은 admin 전용으로 action body를
  검증하고, upstream 성공 후 `integrity_issue.action` audit을 기록한다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 issue action 요청/응답 계약을 추가했다.
- Web `/admin/integrity` table에 해결/무시/재오픈 action 버튼과 reason dialog를 추가했다.

검증:

- API unit: upstream PATCH path/body.
- API integration: status mutation, audit append, request id, upstream body.
- UI e2e: action dialog, reason body, 성공 notice, issue/report 필터 query.

### T-228 — Admin sidebar 확장/축소 토글 정정

추가 요청 정정(2026-06-27): 왼쪽 메뉴는 아이콘으로만 고정하는 것이 아니라, 필요할 때
아이콘 전용으로 축소할 수 있어야 한다.

상태: 완료(2026-06-27, codex).

범위:

- Admin sidebar 기본 상태는 아이콘 + 메뉴 라벨을 표시한다.
- 데스크톱에서 토글 버튼으로 compact icon-only 상태와 expanded 상태를 전환한다.
- 사용자의 sidebar 선호는 browser localStorage에 저장한다.
- 기존 active route 판정과 nav test id는 유지한다.

검증:

- UI e2e: sidebar 기본 expanded, toggle 후 collapsed, 다시 expanded.
- Web typecheck/lint/Prettier.

### T-213 — Category mapping 실제 기능

상태: 완료(2026-06-27, codex). Source of truth는 `kor-travel-map` `/v1/categories`로 결정했다.
Pinvi는 category taxonomy/`maki_icon`을 저장하지 않고, 16색 팔레트 fallback과 drift를 운영자가
확인하는 read-only 화면만 제공한다.

범위:

- Pinvi 표시 카테고리, marker palette, upstream map category catalog의 연결 규칙을 정리한다.
- read-only catalog 확인부터 시작하고, Pinvi가 소유해야 할 mapping 저장소가 필요하면
  별도 migration/ADR 여부를 먼저 판단한다.
- UI는 category search, unmapped count, marker preview, export/import 초안을 제공한다.

결정:

- category catalog/source of truth는 `kor-travel-map` `/v1/categories`.
- Pinvi `packages/domain`의 `CATEGORY_MARKER`와 16색 palette는 preview/fallback/drift 확인용.
- PUT/import mutation과 Pinvi-owned override table은 이번 범위에서 제외한다. 필요성이 확정되면
  별도 ADR/DB migration/audit 포함 Task로 진행한다.

구현:

- Pinvi API `GET /admin/category-mappings`를 추가해 upstream `/v1/categories`를 service client로
  조회하고, `include_counts`, `active_only`, 로컬 `q` 필터와 운영 summary를 제공한다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 admin category mappings read 계약을 추가했다.
- Web `/admin/category-mapping`을 placeholder에서 실제 table route로 교체했다. summary, search,
  active/count filter, marker swatch preview, fallback/icon drift 표시, JSON export 초안을 제공한다.
- `admin-live-matrix.live.ts`에서 route를 placeholder가 아닌 table route로 전환했다.

검증:

- API integration: upstream query forwarding, local q filtering, DB count 보존, RBAC 숨김.
- UI e2e: summary/table/marker preview, query forwarding.
- mutation 도입 시 DB migration + API integration + UI e2e를 포함한다.

### T-214 — Seed / reset dev-only 안전장치

상태: 완료(2026-06-27, codex). 실제 DB reset/seed 실행은 노출하지 않고, dev/staging 전용
dry-run + audit으로 placeholder를 교체했다. production에서는 router include를 하지 않고, endpoint
guard도 404를 반환한다.

범위:

- `/admin/seed`, `/admin/reset` placeholder를 제거하되, 운영에서는 명시적으로 비활성화한다.
- `PINVI_ENVIRONMENT`가 production이면 seed/reset router를 include하지 않고 API는 404만
  반환한다. UI는 destructive action을 렌더링하지 않는다.
- dev/smoke에서는 confirmation phrase, reason, audit, dry-run, 대상 범위를 제공한다.

구현:

- Pinvi API `GET /admin/seed/scenarios`, `POST /admin/seed/scenarios/{scenario_key}`,
  `GET /admin/reset/status`, `POST /admin/reset`을 추가했다.
- dev/staging route는 `dry_run=true`만 지원하고, `false`는 `422 DRY_RUN_ONLY`로 거절한다.
- seed scenario는 scenario별 `RUN <scenario_key>`, reset은 `RESET` 확인 문구를 요구한다.
- 성공한 dry-run은 `dev_seed.dry_run` 또는 `dev_reset.dry_run` audit을 남긴다.
- Web `/admin/seed`, `/admin/reset`을 실제 dry-run 화면으로 교체하고 production 404 응답에서는
  action을 렌더링하지 않는다.
- `admin-live-matrix.live.ts`에서 seed/reset을 placeholder에서 실제 route로 전환했다.

검증:

- API integration: production 404, dev dry-run, confirmation mismatch, audit append.
- UI e2e: production hidden/404-safe, dev confirm flow.

### T-215 — Admin live e2e 확장 + N150 묶음 게이트

상태: 완료(2026-06-27, codex). 최신 Admin 구현 묶음을 N150에서 live authenticated
Playwright gate로 검증했고, 테스트 하네스의 운영 세션 만료/다중 테이블/시스템 화면 ready marker
정책을 보강했다.

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

2026-06-27 결과:

- Windows Playwright runner에서 N150 운영 Web URL을 대상으로 `PINVI_ADMIN_LIVE_CASE_LIMIT=2000`
  묶음 실행을 완료했다. 로그인 검증 2건 + catalog sanity 1건 + matrix 2000건, 총 2003건이
  통과했다(3.1h).
- 전체 catalog는 `6176 tests in 1 file`이다. 실제 UI matrix는 6173건이고, 로그인 검증 2건과
  catalog sanity 1건이 별도 포함된다.
- 실행 전후 N150 smoke에서 API `/health`, API `/health/db`, Web `/admin/login`, Dagster,
  upstream `kor-travel-map` health, Pinvi 컨테이너 healthy 상태를 확인했다.
- `provider-sync`, `integrity`, `debug/logs`처럼 한 route에 여러 AdminTable이 있는 화면은 첫
  `admin-table-scroll`을 route ready 기준으로 삼는다.
- `/admin/system`은 AdminTable route가 아니라 `admin-system-containers` ready marker로 검증하고,
  정렬 matrix에서는 제외한다.
- 긴 live run 도중 access token/cookie TTL을 넘는 경우를 대비해 기본 auth refresh를 5분으로
  줄이고, route 진입/navigation 직후 로그인 화면이면 재로그인 후 원래 route로 복귀한다.

### T-216 — Trip Admin 상세 운영성 보강

추가 요청(2026-06-27) 1~4번, 11번.

범위:

- Admin 좌측 메뉴 active state가 현재 route와 무관하게 dashboard로 고정되는 문제를 고친다.
- 좌측 메뉴를 icon-only compact view로 표현해 본문 공간을 확보한다. 아이콘에는 tooltip/aria label을
  제공해 접근성을 유지한다.
- `/admin/trips/{trip_id}` 상세 화면 제목에 여행계획명을 명확히 표시한다.
- 상세 화면의 owner, 동반자, 초대 이메일 등 사용자 관련 표시를 클릭 가능한 Admin user
  동선으로 연결한다. 가입 사용자는 `/admin/users/{user_id}`로 이동하고, 미가입 초대자는 이메일
  마스킹과 초대 상태를 별도 표시한다.
- 상세 화면에 날짜(day)와 등록 POI를 함께 listing한다.
- POI row 클릭 시 같은 화면 안에서 상세 dialog를 띄우고, dialog에는 POI 상세정보, 지도뷰,
  `/admin/pois/{poi_id}` 상세 페이지 링크를 포함한다.

검증:

- API integration: trip detail 응답이 companions/share links 외 day/POI summary와 미가입 초대자 정보를
  포함하는지 확인.
- UI e2e: 제목, 사용자 링크, 초대자 표시, POI dialog, POI 상세 링크 확인.

### T-217 — Trip Admin 직접 생성

추가 요청(2026-06-27) 5번.

상태: 구현 완료(PR 예정).

범위:

- Admin이 여행계획 목록에서 inline create dialog로 여행계획을 직접 생성한다.
- owner user 선택, 제목, 날짜, 공개범위, 상태를 입력받고 생성 사유를 audit에 남긴다.
- 사용자 flow와 충돌하지 않도록 Admin 생성 출처를 audit/action으로 구분한다.
- owner 선택은 `/admin/users` 검색 결과를 재사용하며 email은 마스킹 표시만 사용한다.
- API는 `POST /admin/trips`이며 `trip.create` audit을 같은 transaction에 기록한다.

검증:

- API integration: admin 권한, owner 존재 검증, audit append, audit 실패 rollback.
- UI e2e: owner 검색/선택, 생성 성공, 생성 후 상세 이동.

### T-218 — Grafana prod 주소 반영

추가 요청(2026-06-27) 6번.

상태: 구현 완료(PR 예정).

범위:

- prod 환경 Grafana embed 주소 주입 경로를 확인하고, tracked 파일에는 실제 운영 도메인을 쓰지 않는다.
- `infra/.env.prod.example`과 runbook에는 placeholder만 둔다.
- Web `/admin/grafana`가 prod env에서 올바른 public URL을 사용하도록 env 이름과 fallback을 정리한다.
- Web Docker build/runtime stage와 app compose build args가 `NEXT_PUBLIC_GRAFANA_URL`,
  `NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH`를 전달하고, Grafana `GF_SERVER_ROOT_URL`도 같은
  public origin으로 설정한다.

검증:

- Web unit/typecheck/lint/build.
- compose config parse.
- Windows Playwright `admin-grafana.e2e.ts` + admin-live catalog.
- tracked diff secret/domain scan.

### T-219 — POI Admin 직접 생성

추가 요청(2026-06-27) 7번.

상태: 구현 완료(PR 예정).

범위:

- Admin이 특정 trip/day에 POI를 직접 추가하는 API/UI를 제공한다.
- feature_id 또는 custom POI 입력, 날짜/순서/메모/예산/URL/마커 override를 입력받는다.
- 생성 사유를 audit에 남기고, feature 정규화·저장은 kor-travel-map에 위임한다.
- UI는 `/admin/pois` 목록에서 trip 검색/선택 후 POI 이름/좌표/주소를 snapshot으로 조립한다.
- API는 `POST /admin/pois`이며 `poi.create` audit을 같은 transaction에 기록한다.

검증:

- API integration: trip 존재 검증, day 자동 생성, feature snapshot, KASI rise/set 초기 row,
  audit append, audit 실패 rollback.
- UI e2e: 생성 dialog, trip 검색/선택, 생성 POST body, 생성 후 상세 이동.

### T-220 — ETL 실제 구동 상태 화면

추가 요청(2026-06-27) 8번. 기존 T-211의 ETL/provider sync 구현 범위를 이 Task와 통합한다.

상태: 완료(2026-06-27, codex). 구현 PR은 Pinvi ETL registry와 `kor-travel-map`
`/v1/ops/*` read proxy, `/admin/etl`, `/admin/provider-sync` 실제 화면, API integration,
Windows Playwright mock e2e를 포함한다. run-now/cancel mutation은 reason/audit/idempotency/
kill-switch 기준이 필요한 별도 후속 범위로 유지한다.

범위:

- `/admin/etl`에 현재 구동 중인 Pinvi ETL job과 Dagster 상태를 표시한다.
- 현재 구현된 KASI job뿐 아니라 실제 등록된 asset/job 목록을 API에서 읽어 보여준다.
- kor-travel-map provider sync는 별도 upstream proxy 섹션으로 구분한다.

구현:

- `KorTravelMapAdminClient`에 `get_ops_dagster_summary`, `get_ops_metrics`,
  `list_ops_providers`, `get_ops_provider`, `list_ops_import_jobs`를 추가했다.
- Pinvi API에 `GET /admin/etl/summary`, `GET /admin/provider-sync`,
  `GET /admin/provider-sync/import-jobs`를 추가했다.
- `/admin/etl/summary`는 Pinvi app-owned ETL 정의(`pinvi_kasi_special_days`,
  `kasi_special_days_job`, `kasi_poi_rise_set_job`, `kasi_special_days_schedule`)와
  `kor-travel-map` Dagster/metrics/provider/import job 요약을 결합한다. upstream 일부 장애는
  `kor_travel_map.status=degraded|down`으로 강등해 화면을 막지 않는다.
- Web `/admin/etl`은 Pinvi Dagster 상태, asset/job/schedule 목록, map Dagster counts,
  recent runs, provider import job status filter/table을 표시한다.
- Web `/admin/provider-sync`는 provider/dataset 상태 검색, import job status filter/table을 표시한다.
- `admin-live-matrix.live.ts`에서 두 route를 placeholder가 아닌 table route로 전환하고
  provider/ETL filter case와 sort case를 추가했다.

검증:

- API unit/integration: upstream ops path/query, Dagster 응답/장애 mapping,
  provider key filter, import job status/cursor proxy.
- UI e2e: job 목록, 상태 필터, provider key filter, import job query 전달.

### T-221 — Dashboard 운영 현황 그래프 / 부하 / 용량

추가 요청(2026-06-27) 9번.

상태: 완료(2026-06-27, codex). Docker/container 상세 상태는 T-222 System view에서 분리해
구현한다.

범위:

- `/admin` dashboard에 운영 현황 상세보기와 간단한 그래프뷰를 추가했다.
- `GET /admin/stats/overview`는 생성 시각, API 실패율/P95, 최근 24시간 hourly series,
  서버 load average, 첨부 저장소 사용량, 전역 quota, 사용자 quota override count,
  백업 경로 기준 디스크 사용량 snapshot을 반환한다.
- Web `/admin`은 API 호출/실패와 가입/여행 생성 막대 그래프, 서버 부하, 디스크 사용률,
  첨부 저장소 사용량/한도 요약을 표시한다.
- raw 운영 경로, 운영 도메인, secret은 API 응답과 화면에 노출하지 않는다.

검증:

- API integration: 통계 count, API 실패율/P95, 24h series, 첨부/스토리지 quota, 디스크 snapshot.
- UI e2e: 그래프 패널, 부하 패널, 디스크/첨부 용량 패널.
- WSL: API ruff, 앱 코드 mypy, Web Prettier/typecheck/lint/Vitest/build.
- Windows: Playwright dashboard mock e2e.

### T-222 — System view Docker / 의존 API 상태

추가 요청(2026-06-27) 10번.

상태: 완료(2026-06-27, codex). Docker socket은 compose에 기본 mount하지 않으며, 실제
container 수집은 host-local override가 socket 접근을 부여한 환경에서만 활성화된다.

범위:

- `/admin/system` 화면과 `GET /admin/system/detail` API를 추가했다.
- 의존 API health와 Docker collector 상태, container name/image/state/status/health/compose
  service를 표시한다.
- Docker socket이 없거나 권한이 없으면 endpoint는 실패하지 않고 `unknown`/`down` 상태와 빈
  container 목록으로 강등한다.
- prod 접근 정보, SSH target, 실제 운영 도메인/IP, raw Docker labels/env/secret은 노출하지 않는다.

검증:

- API integration: dependency probe, Docker collector 응답 shape, non-admin 404.
- UI e2e: dependency 상태 카드, Docker collector 상태, container table.
- WSL: API ruff/mypy/pytest, Web Prettier/typecheck/lint/Vitest/build.
- Windows: Playwright system mock e2e.

### T-223 — 사용자 아바타 / RustFS 이미지 관리

추가 요청(2026-06-27) 12번.

상태: 완료(2026-06-27, codex). 명시적 삭제는 현재 RustFS object 삭제 후 DB 메타를 비우며,
교체 후 과거 object cleanup queue/재시도 정책은 T-224 파일 용량 정책에서 함께 확장한다.

범위:

- 사용자가 프로필 아바타 이미지를 업로드·조회·교체·삭제할 수 있게 한다. 원본 이미지는
  RustFS에 저장하고 DB에는 storage ref와 안전한 metadata만 둔다.
- 각 사용자와 Admin은 해당 사용자의 아바타 이미지를 볼 수 있어야 한다. Admin은 사용자 상세에서
  이미지 삭제/교체를 수행할 수 있다.
- Admin 전역 설정에 아바타 허용 이미지 크기/용량/형식 정책을 추가한다. 설정값은 추적 파일에
  실제 운영 bucket/endpoint/secret을 노출하지 않고 DB/env placeholder로만 문서화한다.
- 삭제/교체는 audit log를 남기고, 기존 객체 cleanup 실패는 재시도 가능한 storage cleanup queue로
  남기는지 검토한다.

검증:

- API integration: upload URL 발급, metadata 확정, 교체 시 이전 객체 cleanup 예약, 삭제 후 조회
  fallback, 권한 거부.
- UI e2e: 사용자 프로필과 Admin 사용자 상세에서 업로드/교체/삭제, 이미지 미리보기.
- 보안: content-type/확장자/크기 제한, RustFS object key prefix, secret/raw endpoint 비노출.

### T-224 — 여행/날짜/POI 파일 업로드와 용량 정책

추가 요청(2026-06-27) 13번.

상태: 완료(2026-06-27, codex). 여행/날짜/POI 첨부 metadata와 사용자/Admin 파일 라이브러리,
전역 파일 용량 정책, 사용자별 quota override를 구현했다. 삭제는 metadata soft delete이며,
RustFS orphan object cleanup/reconcile은 별도 후속 후보로 남긴다.

범위:

- 사용자가 각 여행계획, 날짜, 세부 장소(POI)에 파일을 업로드·삭제할 수 있게 한다. Admin도 같은
  첨부를 조회·관리할 수 있다.
- 사용자와 Admin 모두 업로드한 파일을 모아 보는 파일 라이브러리 화면을 제공한다. 사용자 화면은
  본인/권한 있는 여행 범위만, Admin 화면은 검색/필터/삭제/audit 중심으로 둔다.
- Admin 전역 설정에 개별 파일 최대 용량, 계획별 총 용량, 사용자별 기본 총량을 둔다.
- Admin은 개별 사용자에게 파일/계획 총량 override를 부여할 수 있고, override가 있으면 전역
  설정보다 우선한다.
- 용량 계산은 RustFS metadata만 신뢰하지 않고 DB attachment metadata 기준으로 계산하며, orphan
  객체 cleanup/reconcile task를 별도 후속으로 분리할 수 있다.

검증:

- API integration: trip/day/POI upload URL 발급, metadata 확정, 삭제, 권한, 전역 quota, 사용자
  override 우선순위, 계획별 총량 초과.
- UI e2e: 사용자 파일 모아보기, Admin 파일 관리, quota 초과 메시지, 삭제/복구 불가 확인 dialog.
- 저장소 보안: object key prefix, presigned URL 만료, content-type/size 검증, secret/raw endpoint
  비노출.

구현:

- `app.storage_settings`에 파일 정책 3종을 추가하고, `app.users`에 사용자별 override 3종을 추가했다.
- `app.curated_plan_attachments`는 Trip day 첨부를 위해 `trip_day_index`를 갖고,
  `trip_id + trip_day_index` FK로 day target을 표현한다.
- 사용자 API는 `/users/me/files`, 여행 API는 `/trips/{trip_id}/files`와
  `/trips/{trip_id}/days/{day_index}/attachments*`를 제공한다.
- Admin API는 `/admin/settings/files`, `/admin/users/{user_id}/file-quota`,
  `/admin/files`를 제공하고 변경/삭제 audit을 기록한다.
- Web은 사용자 `/files`, Admin `/admin/files`, Admin 사용자 상세 quota override,
  Trip detail의 날짜/POI attachment 패널을 추가했다.

### T-225 — 여행계획/날짜/POI 복사·이동·삭제 오케스트레이션

상태: 완료(2026-06-27, codex). 구현 PR은 Admin 여행/날짜/POI 운영 작업 API,
공유 schema/client, 상세 화면 dialog, API integration, Windows Playwright mock e2e를 포함한다.

추가 요청(2026-06-27) 14번.

범위:

- Admin에서 여행계획, 세부 날짜, POI를 복사·이동·삭제할 수 있게 한다.
- 계획/날짜 조작 시 하위 day/POI/첨부/댓글/공유링크 등 하위 아이템을 함께 처리할지, 삭제할지,
  orphan으로 둘지, 다른 대상으로 옮길지 선택하게 한다.
- 삭제/이동 dialog는 대상 검색과 이동 실행을 같은 UI에서 처리한다. 다른 곳으로 옮기는 경우
  destination trip/day/POI 후보 검색, 사전 영향도 요약, confirm action, audit 기록을 포함한다.
- orphan 정책은 실제 DB FK/도메인 제약과 충돌하지 않아야 하며, orphan 허용이 불가능한 하위
  아이템은 UI에서 선택지를 비활성화하고 이유를 표시한다.
- 사용자 경로의 협업/권한/optimistic lock과 충돌하지 않도록 버전 증가, audit, rollback 전략을
  API 수준에서 먼저 고정한다.

구현:

- `/admin/trips/{trip_id}/operation-impact`, `/copy`, `/move`, `DELETE /admin/trips/{trip_id}`를
  추가했다. 여행계획 copy는 기존 사용자 복사 흐름을 commit 옵션으로 재사용하되 admin audit과
  같은 transaction으로 묶었다. move는 현 스키마에서 owner 이전으로 정의했고, delete는 trip
  soft delete와 선택적 하위 POI/첨부/댓글 soft delete, share revoke를 수행한다.
- `/admin/trips/{trip_id}/days/{day_index}/operation-impact`, `/copy`, `/move`,
  `DELETE /admin/trips/{trip_id}/days/{day_index}`를 추가했다. 날짜 copy/move는 대상
  여행/day를 받아 POI/첨부/댓글을 이동 또는 삭제하며, 대상 day가 없으면 생성한다.
- `/admin/pois/{poi_id}/operation-impact`, `/copy`, `/move`, `DELETE /admin/pois/{poi_id}`를
  추가했다. POI copy/move/delete는 첨부/댓글 정책을 함께 처리하고 audit을 남긴다.
- `trip_days`/`trip_day_pois`/POI 첨부 FK 구조 때문에 day/POI/첨부 orphan은 허용하지 않는다.
  impact API가 `orphan` 옵션을 `allowed=false`와 사유로 내려주고, Web dialog는 이를 비활성
  설명으로 표시한다.
- Admin `/admin/trips/{trip_id}`와 `/admin/pois/{poi_id}` 상세에 copy/move/delete dialog를
  추가했다. dialog는 대상 여행 검색, 대상 day 입력, 영향도 요약, 정책 선택, reason 입력,
  실행 결과와 audit refresh를 포함한다.

검증:

- API integration: trip copy/delete, day move, POI copy/move/delete, orphan 비활성 impact,
  attachment/comment/share 영향도, audit 기록을 검증했다.
- UI e2e: Windows Playwright에서 여행 상세 날짜 이동 dialog와 POI 이동 dialog의 대상
  검색/선택/실행, 영향도 요약, API body, audit refresh를 검증했다.
- 데이터 정합: 하위 attachment/comment/share link count, orphan 불가 사유, 삭제 후 soft delete
  metadata를 focused integration에서 검증했다.

## 구현 순서

1. T-207 계획 PR merge.
2. 다른 에이전트 계획 리뷰 반영.
3. T-208 IA/dashboard PR.
4. T-209 feature proxy/read UI PR.
5. T-216 trip 상세 운영성 보강 PR.
6. T-217 trip admin 생성 PR.
7. T-219 POI admin 생성 PR.
8. T-223 사용자 아바타/RustFS 이미지 관리 PR.
9. T-224 여행/날짜/POI 파일 업로드와 용량 정책 PR.
10. T-225 여행계획/날짜/POI 복사·이동·삭제 오케스트레이션 PR.
11. T-210 change request 운영 PR.
12. T-220 ETL/provider sync PR.
13. T-212 dedup/integrity/debug read-only PR.
14. T-226 dedup verdict mutation PR.
15. T-213 category mapping PR.
16. T-227 integrity issue status mutation PR(`kor-travel-map` 기존 admin issue 계약 사용).
17. T-214 seed/reset dev-only PR.
18. T-218 Grafana prod 주소 PR.
19. T-221 dashboard 운영 현황 PR.
20. T-222 system view Docker/API 상태 PR.
21. T-215 묶음 live e2e/N150 게이트 PR.
22. T-228 sidebar 확장/축소 정정 PR.

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
