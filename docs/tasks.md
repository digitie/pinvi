# tasks.md — 백로그

진행/예정(`[ ]`) task만 두는 백로그를 목표로 한다. 완료·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 현재 진척과 "다음 한 작업"은
[`docs/resume.md`](resume.md)가 정본이다. 작성·유지 규약은
[`docs/tasks-rule.md`](tasks-rule.md)를 따른다.

> 전환 메모(2026-06-28): `kor-travel-map`의 task 문서 분리 정책을 반영해
> `tasks-done.md`를 도입했다. 현재 Sprint 5 흐름의 완료 항목(T-232~T-235)은
> `tasks-done.md`로 옮겼고, 기존 legacy 완료 이력 전체 이관은
> `T-288-legacy-task-archive`로 분리한다.

> **2026-06-06 정합성 감사**: `docs/audit/2026-06-06-doc-impl-audit.md`에서
> 모순·불일치·누락을 전수 점검하고 후속 Task(T-123~~T-151)·ADR(ADR-027~~031)·결정
> (DEC-01~10)을 도출했다. 결정 결과는 `docs/decisions-needed-2026-06-06.md`,
> kor-travel-map 요구사항은 `docs/kor-travel-map-requirements.md`. 후속 백로그는 본 파일
> "감사 후속 백로그(2026-06-06)" 절.

## 진행 중

- T-259 — Release candidate gate / `v0.2.0`.
  2026-06-28 N150 후보 배포와 smoke, backup snapshot, 최신 main API CI는 통과했지만 Web clean
  CI/manual evidence, Admin live 2000/full credential, N150 Playwright system dependency, restore staging DB가
  남아 release/tag는 보류한다. `scripts/backup-db.sh`는 host `pg_dump` 부재 시 Docker fallback을
  지원하도록 보강했고 N150 재실행 증거까지 확보했다. 상세는
  `docs/execplan/v020-release-candidate-gate.md`.

## 다음 (우선순위 순)

- 다음 구현: T-259 release 차단 해소. N150 Playwright dependency, Admin live credential,
  restore staging DB, 최신 main Web clean CI/manual evidence를 확보한 뒤 `v0.2.0` tag/Release를 만든다.
- 신규 Task 진입 전 최근 2일 PR 리뷰 코멘트를 확인한다. 2026-06-28 T-256에서
  PR #238/#264 legal/ops 리뷰와 PR #265~#289 사람 리뷰 코멘트를 확인했고,
  후속은 `docs/execplan/legal-ops-review-gap-crosswalk.md` 및 T-289~T-292로 연결했다.
- v0.2.0 구현 게이트: app-owned ETL 추가 job, Loki/request timeline,
  backup/restore 1차 스테이징 훈련, legal/ops preflight crosswalk 완료. 남은 것은 T-259 release
  candidate gate다.
- Admin 콘솔 보강 프로그램: T-207~T-229 완료 상태로 정리했다. 상세 계획과 완료 감사는
  `docs/execplan/admin-console-gap-plan.md`.
- 운영 게이트 잔여: N150은 최신 main smoke와 backup snapshot을 확인했다. Restore staging
  drill은 T-259 release 차단 항목이며, Odroid 실제 노드 smoke는 T-108 설명처럼 Sprint 6
  운영 게이트로 남긴다.
- T-129 `/geo/*`·`/regions/*`, T-146 location-audit outbox/feature cache,
  T-195 공통 rate-limit middleware, T-108 운영 배포 자동화 foundation, T-200
  docker-manager 포트 대역 정렬, T-232 Trip WebSocket frontend client 1차 연결,
  T-236 WebSocket multi-client local/mock e2e, T-236a N150 live mutating e2e는 완료.

## v0.2.0 구현 게이트 (2026-06-27)

- [ ] T-287 — Trip Day optimistic lock API / conflict UX follow-up.
      `PATCH/DELETE /trips/{trip_id}/days/{day_index}`에 `If-Match` 기준을 도입할지 결정하고,
      도입 시 API 409 회귀, day rename/delete 충돌 다이얼로그, live e2e를 추가한다.
- [ ] T-259 — Release candidate gate / `v0.2.0`.
      N150 deploy/smoke와 backup snapshot은 통과했다. main CI, Admin live 2000/full,
      restore staging drill, release notes/tag를 완료한다.

## 최근 PR 리뷰 후속

- [ ] T-289 — WebSocket reconnect / invalidation follow-up.
      PR #265 사후 리뷰의 `4401` refresh tight loop, retry jitter, 수동 재연결 UX,
      TanStack Query invalidation 실제 배선 gap을 닫는다.
- [ ] T-290 — Trip conflict UX follow-up.
      PR #266 사후 리뷰의 Trip conflict field whitelist drift, 409 envelope current row,
      `ConflictDialog` Esc/focus 접근성 gap을 닫는다. Day rename/delete 409는 T-287로 유지한다.
- [ ] T-291 — ETL compliance SQL / failure notification follow-up.
      PR #271/#273 사후 리뷰의 Dagster failure sensor drift, app-owned ETL SQL statement
      integration/schema-compile smoke, audit retention 정책 분리 gap을 닫는다.
- [ ] T-292 — App integrity pagination / producer follow-up.
      PR #283 사후 리뷰의 `source=all` pagination starvation, persisted integrity producer/upsert
      테스트, Admin integrity action modal 접근성 gap을 닫는다.

## 문서 운영 후속

- [ ] T-288-legacy-task-archive — `tasks.md` legacy 완료 이력 이관.
      `Admin 콘솔 기능 보강 프로그램`, `완료`, `머지 히스토리`, 완료/보류 혼재 섹션을
      `docs/tasks-done.md`로 단계적으로 옮겨 `tasks.md`를 열린 backlog 중심으로 정리한다.

## Sprint 6 / v1.0.0 후속 Task 초안

- [ ] T-260 — Sprint 6 상세 실행 계획 / ADR 정리.
- [ ] T-261 — 경로 최적화 정책 / distance matrix.
- [ ] T-262 — 스마트 정렬 API / OR-Tools.
- [ ] T-263 — 스마트 정렬 UI.
- [ ] T-264 — Admin category mapping DB override.
- [ ] T-265 — Admin notice plan 작성기.
- [ ] T-266 — MCP 외부 인터페이스 운영 실증.
- [ ] T-267 — Backup/Restore UI hot-swap 완성.
- [ ] T-268 — 한국 전용 geofencing 3중 안전망.
- [ ] T-269 — LBS / 법무 4문서 / 동의 UX.
- [ ] T-270 — 성능 / 부하 / 보안 점검.
- [ ] T-271 — Odroid + N150 병행 운영. ARM image와 GHCR 배포는 제외하고 노드 로컬
      checkout/build/smoke 기준으로 진행한다.
- [ ] T-272 — AI companion 별도 서비스 분리.
- [ ] T-273 — v1.0.0 E2E / Live Gate.
- [ ] T-274 — v1.0.0 릴리즈.
- [ ] T-275 — PIPA security incident console.
      `/admin/incidents`, `app.security_incidents` query/notification/router/UI, CPO 30분 review,
      정보주체 통지, KISA/PIPC 72시간 신고 due date를 구현한다.
- [ ] T-276 — Retention execution / dashboard.
      PII delete/anonymize, location archive/delete, token/session cleanup, last_run/overdue dashboard,
      kill-switch와 evidence log를 구현한다.
- [ ] T-277 — Email deliverability / suppression enforcement.
      SPF/DKIM/DMARC/FROM domain verified 상태, Resend webhook hard-bounce/complaint,
      `users.email_status`/suppression enforcement와 alert를 구현한다.
- [ ] T-278 — DSR intake workflow.
      개인정보 열람/정정/삭제/처리정지 요청 접수, SLA, evidence, 완료 통지 workflow를 구현한다.
- [ ] T-279 — Content moderation / takedown workflow.
      trip/comment/attachment/share link report, hide/takedown/restore/appeal 흐름을 구현한다.
- [ ] T-280 — RBAC role grant/revoke / permission matrix.
      ADR-033 bootstrap role 모델을 운영 가능한 권한 부여/회수 UI/API와 permission matrix로 확장한다.
- [ ] T-281 — User lifecycle admin actions.
      force-resend-verify, sessions list/forced logout, force-password-reset, disable/reactivate,
      anonymize/delete account와 사용자 `DELETE /users/me` 흐름을 구현한다.
- [ ] T-282 — Rate-limit / abuse admin surface.
      ADR-038 bucket 상태, fail-closed 503, block/allow override, suspicious activity 조회를 구현한다.
- [ ] T-283 — Security review / threat model / penetration pass.
      auth/session/MCP/share token/rate-limit/storage/admin RBAC/incident 권한 threat model과 1차 점검을 수행한다.
- [ ] T-284 — Mobile v1.0 scope gate.
      `apps/mobile`은 활성 track이지만 v1.0 Web/API/Admin 출시 필수 범위에서 제외하고 Sprint M-1로 분리한다.
- [ ] T-285 — AI companion v1.0 scope gate.
      v1.0 user-facing AI companion은 제외하고 client contract/Admin status까지만 유지한다.
- [ ] T-286 — Cross-track review gap closure.
      cross-track #238 리뷰 44개 gap과 PR #264 리뷰 항목을 Task/문서/검증 케이스로 매핑한다.

## Admin 콘솔 기능 보강 프로그램 (2026-06-27)

> 상세 실행 계획: `docs/execplan/admin-console-gap-plan.md`. 단위 기능 검증은 로컬 WSL
> ext4 미러에서 수행하고, N150은 기능 묶음 단위 live API/UI/e2e 게이트로 사용한다.

- [x] T-207 — Admin 보강 실행 계획 문서화 (완료: 2026-06-27, codex).
      `kor-travel-map` Admin 기능을 참고해 Pinvi 메뉴/세부 기능/책임 경계/API·UI·e2e 검증
      계획을 문서화했다. 다른 에이전트 리뷰의 차단 이슈를 반영해 공개 credential 조합 표현을
      제거하고 seed/reset production 정책을 router 미등록/404로 고정한 뒤 구현에 진입한다.
- [x] T-208 — Admin IA / 메뉴 / 대시보드 상태판 보강 (완료: 2026-06-27, codex).
      Admin sidebar를 Pinvi 운영 / 지도 데이터 / 시스템 운영 그룹으로 재정렬하고,
      `Features`, 변경 요청, dedup review, provider sync, integrity, debug logs placeholder route를
      추가했다. `/admin/system/summary` read-only API와 대시보드 상태 보드가 Pinvi API, DB,
      Web, Dagster, `kor-travel-map` API, RustFS 상태를 secret/raw URL 없이 요약한다.
- [x] T-209 — `kor-travel-map` Admin proxy foundation + `/admin/features` 실제 화면
      (완료: 2026-06-27, codex). `GET /v1/admin/features`와
      `GET /v1/admin/features/{feature_id}` admin read 계약을 Pinvi `/admin/features` proxy로
      연결하고, Web 화면을 검색/필터/table/detail inspector로 교체했다. live matrix는
      `/admin/features`를 table route로 전환하고 feature filter/sort case를 추가했다. N150 live는
      T-215 묶음 게이트에서 수행한다.
- [x] T-216 — Trip Admin 상세 운영성 보강 (완료: 2026-06-27, codex).
      Admin 좌측 메뉴 active state를 가장 구체적인 route 기준으로 고쳤고, sidebar compact 처리는
      T-228에서 기본 expanded + 선택적 icon-only 토글로 정정했다. `/admin/trips/{trip_id}`는
      여행계획명을 제목으로 표시하고, owner/가입 동반자/POI 추가자를 `/admin/users/{user_id}`로
      연결한다. 미가입 초대자는 별도 상태로 표시하며, 상세 계획의 day/POI listing과 POI 지도
      dialog 및 `/admin/pois/{poi_id}` 링크를 추가했다.
- [x] T-217 — 여행계획 Admin 직접 생성 (완료: 2026-06-27, codex).
      Admin 여행 목록에서 owner 검색/선택 기반 inline 생성 dialog를 제공하고,
      `POST /admin/trips`가 `trip.create` audit과 같은 transaction으로 여행계획을 생성한다.
      owner email 원문은 응답/감사 로그에 남기지 않고 마스킹 값만 사용한다.
- [x] T-219 — POI Admin 직접 생성 (완료: 2026-06-27, codex).
      Admin POI 목록에서 trip 검색/선택 기반 생성 dialog를 제공하고, `POST /admin/pois`가
      `poi.create` audit과 같은 transaction으로 `app.trip_day_pois` attachment 행을 생성한다.
      feature 정규화·저장은 계속 `kor-travel-map` 책임으로 두고 snapshot만 Pinvi POI에 저장한다.
- [x] T-223 — 사용자 아바타 / RustFS 이미지 관리 (완료: 2026-06-27, codex).
      `users`에 RustFS 아바타 객체 메타를 추가하고, `storage_settings` 단일 행으로
      전역 아바타 최대 업로드 크기를 관리한다. 사용자는 `/profile`에서 이미지 업로드/교체/삭제와
      조회가 가능하고, Admin은 `/admin/users/{user_id}`에서 대상 사용자 아바타와 전역 크기 제한을
      관리하며 `user.avatar_*` / `settings.avatar_update` audit을 남긴다.
- [x] T-224 — 여행/날짜/POI 파일 업로드와 용량 정책 (완료: 2026-06-27, codex).
      Trip/day/POI 첨부 metadata와 `/users/me/files`, `/trips/{trip_id}/files`,
      `/admin/files` 파일 라이브러리를 추가했다. 전역 파일 용량 정책과 사용자별 override를
      DB/API/Admin UI로 관리하고, quota 초과는 upload-url/metadata 등록 단계에서 차단한다.
- [x] T-225 — 여행계획/날짜/POI 복사·이동·삭제 오케스트레이션
      (완료: 2026-06-27, codex). Admin 여행/날짜/POI operation impact와 copy/move/delete API를
      추가하고, orphan 불가 정책을 API/UI에 사유와 함께 노출했다. 상세 화면 dialog에서 대상
      여행 검색, 대상 day 입력, 하위 항목 move/delete 정책, reason, 결과/audit refresh를 처리하며,
      API integration과 Windows Playwright e2e로 검증했다.
- [x] T-210 — Pinvi feature request와 upstream change request 운영 통합
      (완료: 2026-06-27, codex). `/admin/features/change-requests` proxy/API와 Web 운영 화면을
      추가해 `kor-travel-map` feature change request 큐를 상태/액션/검색 필터로 조회하고,
      approve/reject mutation은 upstream 성공 후 `feature_change_request.*` audit을 남긴다.
      기존 `/admin/feature-requests`는 upstream request id가 있으면 변경 요청 큐로 이어진다.
      Web mutation은 optimistic update와 실패 rollback을 갖추고, API integration과 Windows
      Playwright mock e2e로 검증한다.
- [x] T-220 — `/admin/etl` + provider sync + Dagster 운영 화면
      (완료: 2026-06-27, codex). Pinvi ETL registry와 `kor-travel-map` `/v1/ops/*`
      read proxy를 연결하고, `/admin/etl`과 `/admin/provider-sync` placeholder를 실제 상태/필터/table
      화면으로 교체했다. `/admin/etl/summary`는 upstream 일부 장애를 graceful degrade하고,
      live matrix는 두 route를 table route로 전환했다. API integration과 Windows Playwright mock
      e2e로 검증했다.
- [x] T-212 — Dedup review / integrity / debug logs 운영 화면
      (완료: 2026-06-27, codex). `kor-travel-map` dedup review, consistency issue/report,
      sanitized system/API logs read proxy를 추가하고 `/admin/dedup-review`, `/admin/integrity`,
      `/admin/debug/logs`를 실제 필터/table/detail 화면으로 교체했다. mutation은 T-226으로 분리했다.
- [x] T-226 — Dedup verdict mutation
      (완료: 2026-06-27, codex). `kor-travel-map` `PATCH /v1/admin/dedup-reviews/{review_id}`
      계약을 Pinvi `POST /admin/dedup-review/{review_id}/verdict`로 relay하고,
      `access_reason`, upstream reason, master feature 검증, `dedup_review.decide` audit,
      Web pending 후보 판정 form을 추가했다. integrity mutation은 upstream OpenAPI가 GET-only라
      T-227로 분리했다.
- [x] T-213 — Category mapping 실제 기능 및 source of truth 결정
      (완료: 2026-06-27, codex). category taxonomy/`maki_icon` 정본은 `kor-travel-map`
      `/v1/categories`로 결정하고, Pinvi는 `GET /admin/category-mappings` read-only proxy와
      `/admin/category-mapping` 운영 화면에서 16색 팔레트 fallback, unmapped count, icon drift,
      JSON export 초안을 제공한다. Pinvi-owned override table/PUT/import는 별도 ADR/migration이
      필요한 후속으로 남긴다.
- [x] T-227 — Integrity issue status mutation
      (완료: 2026-06-27, codex). `kor-travel-map`의 기존
      `PATCH /v1/admin/issues/{issue_id}` 계약(resolve/ignore/reopen)을 Pinvi
      `POST /admin/integrity/issues/{issue_id}/action`으로 relay하고, upstream 성공 후
      `integrity_issue.action` audit을 남긴다. `/admin/integrity`는 issue table에서 해결/무시/재오픈
      조치 다이얼로그를 제공하며, status/fix 중 feature 주소/좌표 수동 보정류 action은 upstream
      admin 화면 책임으로 남긴다.
- [x] T-214 — Seed / reset dev-only 안전장치와 운영 비활성화
      (완료: 2026-06-27, codex). dev/staging 전용 seed/reset dry-run API와 UI를 추가하고,
      production에서는 router 미등록 + endpoint guard 404 정책을 적용했다. 실제 DB reset/seed 실행은
      노출하지 않고, 확인 문구, 운영 사유, dry-run 결과, `dev_seed.dry_run`/`dev_reset.dry_run`
      audit만 제공한다.
- [x] T-218 — prod Grafana 주소 반영
      (완료: 2026-06-27, codex). Web Docker build/runtime stage와 app compose build args에
      `NEXT_PUBLIC_GRAFANA_URL`, `NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH`를 추가하고,
      Grafana 컨테이너 `GF_SERVER_ROOT_URL`도 같은 public origin으로 주입한다.
      `infra/.env.prod.example`과 runbook에는 `grafana.example.com` placeholder만 남겨
      실제 운영 도메인은 gitignore된 `infra/.env.prod`에서만 다루도록 했다.
- [x] T-221 — Dashboard 운영 현황 그래프/부하/용량 상세보기
      (완료: 2026-06-27, codex). `/admin/stats/overview`에 생성 시각, API 실패율/P95,
      최근 24시간 hourly series, 서버 load average, 첨부/RustFS quota 집계, 백업 경로 기준
      디스크 용량 snapshot을 추가했다. `/admin` 대시보드는 API 호출/실패와 가입/여행 생성
      막대 그래프, 부하, 디스크, 첨부 저장소 요약을 표시하며 raw 운영 경로/도메인/secret은
      응답하지 않는다.
- [x] T-222 — System view Docker / 의존 API 상태
      (완료: 2026-06-27, codex). `/admin/system/detail` read-only API와 `/admin/system`
      운영 화면을 추가했다. 의존 API health와 Docker collector 상태, container name/image/state/health/
      compose service를 표시한다. Docker socket이 없거나 권한이 없으면 endpoint는 실패하지 않고
      `unknown`/`down` 상태와 빈 container 목록으로 강등한다.
- [x] T-215 — Admin live e2e 확장 + N150 묶음 게이트
      (완료: 2026-06-27, codex). 최신 Admin 구현 묶음을 N150 대상으로 Windows Playwright
      live authenticated gate에서 검증했다. `PINVI_ADMIN_LIVE_CASE_LIMIT=2000` 기준 로그인 2건,
      catalog 1건, matrix 2000건 총 2003건이 통과했고(3.1h), 전체 catalog는 6176건이다.
      테스트 하네스는 다중 AdminTable route, `/admin/system` ready marker, 5분 auth refresh와
      mid-run 재로그인 복귀를 반영했다. 실행 전후 N150 API/DB/Web/Dagster/upstream health와
      Pinvi 컨테이너 healthy 상태를 확인했다.
- [x] T-228 — Admin sidebar 확장/축소 토글 정정
      (완료: 2026-06-27, codex). 왼쪽 메뉴를 아이콘 전용으로 고정하지 않고, 기본은 아이콘+라벨
      expanded sidebar로 표시한다. 데스크톱에서 토글 버튼으로 compact icon-only 상태와 expanded
      상태를 전환하며, 선호 상태는 browser localStorage에 저장한다. 기존 active route 판정과
      nav test id는 유지했다.
- [x] T-229 — Admin 완료 감사 / 추적 문서 최신화
      (완료: 2026-06-27, codex). T-207~~T-228 구현·PR merge·N150 배포 상태를 실행 계획,
      tasks/resume/journal에 반영하고, 사용자 명시 요구사항 1~~14번을 완료 Task와 API/UI/e2e
      증거에 매핑했다. sidebar 요구사항은 기본 expanded + 선택적 compact icon-only 토글로
      문서 전반에서 정정했으며, 운영 도메인/secret 원문은 추가하지 않았다.
- [x] T-230 — v0.1.0 릴리즈 상태 정합화
      (완료: 2026-06-27, codex). GitHub에 이미 존재하는 `v0.1.0` tag/Release
      (2026-06-13, `2f8da02345581fd3065e9d818352bc187f65b3a9`)를 확인하고,
      `CHANGELOG.md`, Sprint 문서, AGENTS/CLAUDE 진입 요약, tasks/resume/journal의
      "tag 대기" 표현을 실제 릴리즈 완료 상태로 정리했다. 최신 main
      `d35f49e1faafa61380d9c2c0e2d6a1cb36d29108` 기준 N150 API/DB/Web/Dagster/
      `kor-travel-map` smoke는 모두 200을 반환했다.
- [x] T-231 — v0.2.0 후보 범위 정리
      (완료: 2026-06-27, codex). `CHANGELOG.md`의 `Unreleased`를 `v0.2.0` 후보로
      명시하고, Sprint 5 문서에 post-v0.1.0으로 이미 반영된 Admin/ETL/Grafana/System
      항목과 남은 release gate(WebSocket, app-owned ETL 추가 job, Loki/request timeline,
      backup/restore 스테이징 훈련)를 분리했다. sidebar 설명도 기본 expanded + 선택적
      compact icon-only 기준으로 재정렬했다.

## 완료

- [x] T-206 — N150 bootstrap admin 생성/복구 경로 추가 (완료: 2026-06-27, codex).
      운영 DB에 admin 계정이 없으면 `PINVI_BOOTSTRAP_ADMIN_PASSWORD` 기반 startup bootstrap이
      bootstrap 대상 계정을 생성/복구한다. 운영 compose env 전달, admin/deploy 런북,
      quote 실패 패턴 문서, 원격 Docker Python helper, 통합 테스트를 추가했다.
- [x] T-205 — 로컬 env Pinvi 키 반영 + OAuth 설정 판정 보강 (완료: 2026-06-25, codex).
      로컬 `.env`의 legacy `TRIPMATE_*` 값을 현재 `PINVI_*`/`NEXT_PUBLIC_PINVI_*` 키로 복사하고,
      dev URL은 ADR-047 고정 포트(`12801`/`12805`/`12802`)로 보정했다. access token 기본값은
      10분으로 낮추고, Google OAuth는 client id와 secret이 모두 있을 때만 enabled로 표시한다.
- [x] T-204 — 회원가입 이메일 outbox worker 연결 (완료: 2026-06-25, codex).
      가입 인증/비밀번호 재설정/초대 이메일이 `app.email_queue`에만 적재되고 실제 drain되지 않는
      문제를 고쳤다. FastAPI lifespan에서 `email_outbox_worker_lifespan`을 실행하고,
      worker 설정/env 문서와 lifespan 테스트를 추가했다.
- [x] T-203 — Admin live UI e2e 매트릭스와 N150 재배포 검증 기반 추가 (완료: 2026-06-24, codex).
      `apps/web`에 live 전용 Playwright config와 3233개 Admin UI 케이스를 추가하고,
      `ktdctl` 기반 N150 재빌드/재기동 절차와 운영 Web API URL 보정 내용을 runbook으로 문서화했다.
      최종 live authenticated run은 2001개 matrix 제한 기준 2004개 테스트가 모두 통과했다(2.8h).
- [x] T-202 — `kor-travel-geo` v2 공개 API key 계약 대응 (완료: 2026-06-24, codex).
      최신 `kor-travel-geo` v2 REST가 `key` query를 검증하므로 Pinvi geocoding client가
      서버 `PINVI_VWORLD_API_KEY`를 모든 v2 POST에 붙이도록 변경했다. 별도 geo key env는 두지
      않고, 공개 API key hash 저장/검증은 `kor-travel-geo`가 소유한다(ADR-048).
- [x] T-201 — Web 지도 클라이언트 `vworld-map-web` 전환 (완료: 2026-06-18, codex).
      기존 `maplibre-vworld-js`/`maplibre-vworld` tarball 의존성을 제거하고,
      `maplibre-vworld-react`의 웹 패키지 `vworld-map-web`(+ `vworld-map-core`) vendored
      tarball로 `apps/web` 지도뷰를 전환했다. ADR-046 추가, `docs/integrations/maplibre-vworld.md`
      정합화, Web typecheck/lint/build/Vitest 검증.
- [x] T-000 — git v1 보존 + main v2 재시작 (완료: 2026-05-25)
- [x] T-112 — Pinvi MCP 외부 인터페이스 서빙 (완료: 2026-06-09) —
      `app.mcp_tokens`, `/users/me/mcp-tokens`, `/admin/mcp-tokens`, `/mcp/sse`,
      `/mcp/tools/{tool_name}`, 사용자/admin 토큰 UI, 5개 read-only tool.
- [x] T-001 — README / CLAUDE / AGENTS / SKILL (완료: 2026-05-25)
- [x] T-002 — docs/architecture / agent-guide / dev-environment (완료: 2026-05-25)
- [x] T-003 — docs/decisions (ADR-001 ~ ADR-010) (완료: 2026-05-25)
- [x] T-004 — docs/journal / resume / tasks (완료: 2026-05-25)
- [x] T-005 — docs/data-model / postgres-schema / test-strategy (완료: 2026-05-25)
- [x] T-006 — docs/kor-travel-map-integration (완료: 2026-05-25)
- [x] T-007 — docs/sprints/README + SPRINT-1~6 (완료: 2026-05-25)
- [x] T-008 — docs/spec/v8/ 6편 적용 노트 (완료: 2026-05-25)
- [x] T-009 — docs/design/marker-palette + 루트 DESIGN.md/airbnb-marker-palette.html 복원 (완료: 2026-05-25)
- [x] T-010 — docs/architecture/frontend.md (Next.js + Expo 공용 monorepo) (완료: 2026-05-25)
- [x] T-011 — docs/architecture/user-location.md (Geolocation + expo-location) (완료: 2026-05-25)
- [x] T-012 — docs/architecture/notice-plans.md (v1 추천 plan 이전) (완료: 2026-05-25)
- [x] T-013 — v1 자산 전수 조사 + 매핑 매트릭스 (`docs/v1-to-v2-mapping.md`) (완료: 2026-05-26)
- [x] T-014 — docs/api/ 11개 + README + common (완료: 2026-05-26)
- [x] T-015 — docs/integrations/ 9개 + README (완료: 2026-05-26)
- [x] T-016 — docs/runbooks/ 7개 + README (완료: 2026-05-26)
- [x] T-017 — docs/compliance/ 4개 + README (완료: 2026-05-26)
- [x] T-018 — docs/conventions/ 6개 + README (완료: 2026-05-26)
- [x] T-019 — docs/architecture/ 5개 추가 + data-sources/README (완료: 2026-05-26)
- [x] T-020 — AI agent 진입 절차 강화 (README/AGENTS/CLAUDE) (완료: 2026-05-26)
- [x] T-021 — `docs/integrations/maplibre-vworld.md` 신규 + Kakao 전면 교체 (ADR-015) (완료: 2026-05-26)
- [x] T-022 — `AGENTS.md` ↔ `CLAUDE.md` 동기 룰 (ADR-016 — Codex/Antigravity 대응) (완료: 2026-05-26)
- [x] T-023 — Sprint 4까지 PR 리뷰·수정·머지 운영 runbook + 5분 주기 PR 감시 (완료: 2026-05-25,
      2026-06-02부터 API key 없는 review reminder 방식)
- [x] T-030 — Sprint 1 monorepo 루트 + packages/\* skeleton (완료: 2026-05-26)
- [x] T-031 — Sprint 1 apps/api FastAPI + Alembic + Auth 뼈대 (완료: 2026-05-26)
- [x] T-032 — Sprint 1 apps/web Next.js + auth 화면 (완료: 2026-05-26)
- [x] T-033 — Sprint 1 apps/etl Dagster placeholder (완료: 2026-05-26)
- [x] T-034 — Sprint 1 infra/docker-compose + scripts + CI workflow 3개 (완료: 2026-05-26)
- [x] T-035 — Sprint 1 PR 생성 (완료: 2026-05-26)
- [x] T-050 — Sprint 3 진입 PR (Admin 콘솔 + RBAC + audit chain integration + seed) (완료: 2026-05-26)
- [x] T-061 — Sprint 4 진행 추적 문서 정합화 (`resume.md` / `tasks.md` / `journal.md`) (완료: 2026-06-01)
- [x] T-060 — Sprint 4 진입 PR/기능 게이트 (완료: 2026-06-11): 지도 UI,
      `maplibre-vworld-js`, kor_travel_map live feature read, trip 상세 HTTP batch, Admin feature-request
      릴레이, drift gate, CI/CD 재활성까지 머지. `v0.1.0` tag/Release는 2026-06-13 완료.
- [x] T-062 — GitHub Actions secret / branch protection 적용 상태 확인 (완료:
      2026-06-02, Actions secret 0개 정책 확인 + `main-pr-only` ruleset 적용)
- [x] T-064 — 최신 main 기준 문서 충돌 정정 (ADR-015/024/025 반영) (완료: 2026-06-02)
- [x] T-068 — 최신 kor-travel-map/kor-travel-geo/KASI 계약 문서 반영 (완료: 2026-06-04,
      ADR-026 + KASI 특일/출몰시각 저장 계약)
- [x] T-069 — production API/Web URL + OAuth/CORS 보안 문서화 (완료: 2026-06-05,
      API `https://pinvi-api.example.com`, Web `https://pinvi.example.com`)
- [x] T-067 — KASI 특일/POI 출몰시각 Dagster 구현 (완료: 2026-06-05,
      `app.kasi_special_days` / `app.trip_poi_rise_sets` + Dagster asset/job)
- [x] T-070 — Sprint 2 잔여 마감: `email_queue` SKIP LOCKED worker +
      비밀번호 재설정 메일 흐름, `api_call_log` 미들웨어 통합 테스트,
      `api.yml` integration step 추가 (완료: 2026-06-05)
- [x] T-063 — `maplibre-vworld-js` 선행 PR 및 consumer sync 체크리스트 정리
      (완료: 2026-06-05, `maplibre-vworld-js` PR #46 merge `f1dd74b9` +
      Pinvi `docs/integrations/maplibre-vworld.md` §6/§11.1 sync)
- [x] T-065 — 항상 실행되는 aggregate CI gate 설계 후 required status check 적용
      (완료: 2026-06-05, `.github/workflows/aggregate-ci.yml` + `main-pr-only` ruleset
      required status check `Aggregate CI gate`)
- [x] T-071 — Google OAuth 로그인 UI + API client 연결
      (완료: 2026-06-05, `/auth/oauth/google/start` envelope 응답, provider 목록 기반
      로그인 버튼, PKCE verifier 재생성)
- [x] T-072 — Google OAuth callback 실패 redirect UX
      (완료: 2026-06-05, callback 실패 303 `/login?error=...` redirect +
      로그인 화면 code 기반 인라인 메시지)
- [x] T-073 — Google OAuth profile 연결/해제 UI
      (완료: 2026-06-05, `/auth/me` OAuth identity 노출 + `/profile` Google 연결/해제 +
      소셜-only unlink 차단)
- [x] T-074 — PR-C frontend 지도 shell
      (완료: 2026-06-05, `maplibre-vworld` `f1dd74b9...` tarball pin + `/trips/map-shell`
      `VWorldMap` import + Windows Playwright e2e, kor-travel-map feature 조회 제외)
- [x] T-075 — Trip 대시보드 / notice plan 사용자 shell
      (완료: 2026-06-05, `/trips` / `/notice-plans` 사용자 route + navigation + 빈 상태 +
      API client 연결, `/features/*` / kor-travel-map API `12701` 미호출 e2e)
- [x] T-100 — v1의 Resend 이메일 통합 v2로 이식 (Sprint 2 완료, PR #10)
- [x] T-101 — v1의 소셜 로그인 기반 schema/model v2 이전 (현재 활성은 Google-only,
      Naver/Kakao provider 구현은 T-122 미래 작업)
- [x] T-102 — v1의 Notice plan 도메인 v2로 이식 (Sprint 2 schema/model 완료, 라우터
      Sprint 6)
- [x] T-103 — v1의 RustFS Storage API v2로 이식 (Sprint 2 완료, presigned PUT)
- [x] T-104 — v1의 Admin 콘솔 (`apps/web/app/admin/`) v2로 이식 (Sprint 3 완료, PR #11)
- [x] T-110 — Admin Grafana iframe embed
      (완료: 2026-06-05, `/admin/grafana` iframe shell + `NEXT_PUBLIC_GRAFANA_*` env +
      Web `frame-src` CSP + admin guard e2e)
- [x] T-109 — 한국 전용 geofencing FastAPI fallback
      (완료: 2026-06-05, `PINVI_GEOFENCE_*` env + `CF-IPCountry` 기반 451 middleware +
      health/docs 우회 + DB roles 운영자 우회 단위 테스트. T-142에서 token roles claim 신뢰 제거)
- [x] T-115 — Backup snapshot foundation + `/admin/backup` 1차 UI
      (완료: 2026-06-06, `scripts/backup-db.sh` / `scripts/restore-db.sh` +
      `GET /admin/backup/snapshots` + `POST /admin/backup/snapshot` + admin snapshot page.
      핫스왑 restore는 T-111에서 완료)
- [x] T-116 — OAuth provider 범위 Google-only 정리
      (완료: 2026-06-06, `/auth/oauth/providers`가 Google만 반환. Naver/Kakao는 future
      provider로 보류)
- [x] T-117 — 회원가입 약관 동의 화면 + `user_consents` 저장 보강
      (완료: 2026-06-06, `POST /auth/register` 필수 4종 동의 요구 +
      `app.user_consents` 동시 저장 + `/signup` 필수/선택 동의 UI + e2e)
- [x] T-118 — Google OAuth 계정 매칭 / profile 연결 UX 보강
      (완료: 2026-06-06, 같은 이메일 자동 연결 금지 + `OAUTH_ACCOUNT_LINK_REQUIRED` /
      `OAUTH_EMAIL_UNVERIFIED` 안내 + profile link-mode 충돌 redirect + Naver/Kakao 제외 e2e)
- [x] T-119 — 회원 관리 Admin 보강
      (완료: 2026-06-06, `/admin/users` `q` 검색 + 상태 필터 결합, 상세 기본 이메일
      마스킹, 사유 기반 원본 조회 audit, 최근 audit UX + 통합/e2e 테스트)
- [x] T-120 — 여행계획 Admin 목록/상세/상태 관리
      (완료: 2026-06-06, `/admin/trips` 검색 + 상태/공개범위 필터, 상세 companion/share
      metadata, 상태 변경 `trip.update_status` audit, Web 목록/상세 + 통합/e2e 테스트)
- [x] T-121 — POI Admin 목록/상세/연결 상태 관리
      (완료: 2026-06-06, `/admin/pois` 검색 + `feature_link_broken_at` 필터, 상세
      snapshot/일정/비용/최근 audit, 연결 상태 변경 `poi.update_link_status` audit,
      Web 목록/상세 + 통합/e2e 테스트. feature re-link는 kor-travel-map client 준비 후)
- [x] T-123 — 문서 정합 일괄 정정
      (완료: 2026-06-06, README/API index의 `GET /search`·`/health/external` 보강,
      OAuth Google-only/future provider 표현 정리, share link URL을
      `PINVI_WEB_BASE_URL` 기반으로 수정, zoom 하한 5 정합, dangling
      `release-plan.md` 링크 제거, `kor-travel-geo` 오타 정정, agent-guide 잔여
      bullet/trailer 정리)
- [x] T-149 — Gemini 책임 목록 정정
      (완료: 2026-06-06, README/AGENTS/CLAUDE/SKILL 및 integrations index의 현재 책임
      표현을 ADR-020 기준 `AI companion 호출 계약`으로 정리. Gemini/Claude/Codex provider
      구현은 별도 `kor-travel-concierge` repo 책임)
- [x] T-150 — 계획/추적 문서 정합화
      (완료: 2026-06-06, Sprint 1/3/4/5 status를 최신 main과 맞추고, Sprint 5 ETL
      provider asset 목록을 kor-travel-map 책임으로 정정, `resume.md` ADR-031까지 박힌 ADR
      목록 갱신, T-111 중복/보류·완료 혼재 상태 점검, merge history PR #55 추가)
- [x] T-152 — Telegram 완료 알림 MCP (모든 agent)
      (완료: 2026-06-07, kor-travel-map PR #229 패턴 미러. `scripts/mcp_telegram_start.py` +
      `mcp-telegram` 서버를 claude/codex/antigravity/gemini MCP 설정에 등록 +
      `.env.mcp-telegram` gitignore + AGENTS/CLAUDE/SKILL/runbook 정책. GitHub secret 미사용
      (T-062 유지). 실제 전송 검증 완료. PR 후 `send_message`로 요약+링크 발송 규칙.)
- [x] T-153 — PR 리뷰 모니터 MCP 알림 보강
      (완료: 2026-06-07, `scripts/pr_review_monitor.py`로 PR 이벤트/예약 감시 로직 단일화,
      `synchronize`/`reopened` 즉시 알림 추가, 알림 본문에 `kor-travel-map`식 MCP 진입
      CodeGraph/Playwright/Sequential Thinking/Telegram 기준 반영. GitHub secret 미사용.)

## 보류

- [x] T-066 — kor-travel-map OpenAPI HTTP client **구현 완료** (2026-06-11, #170 user client
      `clients/kor_travel_map.py` + #173 admin client `clients/kor_travel_map_admin.py`). kor_travel_map가 운영급
      `:12701 /v1` HTTP 서비스를 신설해 ADR-027/DEC-01=B 전제 충족. **drift gate는 T-210e로 분리**(잔여).
      → **v0.1.0 게이트(DEC-06: 라이브 feature read) 충족** — 릴리즈 가능.
- [ ] ~~T-107~~ — **Gemini 통합 — 보류 (deferred)**. 별 repo
      `kor-travel-concierge`으로 분리 (ADR-020). 본 저장소는 호출 컨트랙트 문서만
      (`docs/integrations/ai-companion.md`, Sprint 6 진입 시).
- [x] T-108 — 운영 배포 자동화 foundation (완료: 2026-06-13, Codex) —
      Odroid M1S + N150 16GB 양쪽(ADR-023) deploy/smoke script, N150/Odroid doctor,
      노드별 배포 runbook을 추가했다. 이후 2026-06-26 운영 결정으로 GHCR/multi-platform
      image 배포는 폐기하고 노드 로컬 checkout + 로컬 Docker build 기준으로 전환했다.
      ADR-039에 따라 노드 간 DB live sync는 사용하지 않는다. 실제 노드 smoke와
      backup/restore 복구 훈련은 Sprint 6 운영 게이트로 남는다.
- [ ] T-122 — Naver/Kakao OAuth provider 구현 — **미래 작업**
      (현재는 사용하지 않음. Google OAuth 안정화 후 별도 PR에서 provider별 start /
      callback / link / unlink / 버튼 활성화)

### Sprint 5~6 (v0.2.0 / v1.0) 신규 backlog

- [x] T-111 — Backup/Restore UI 핫스왑 (ADR-022, Sprint 6) — `/admin/backup`
  - RestoreHotswapDialog. Sprint 5의 backup script + endpoint 위에 UI + 핫스왑
    워크플로 finalize.
- [x] T-132 — trip 하위 리소스(days/day-items/members/shared/attachments/copy/optimize)
      구현 분할 (완료: 2026-06-09, trip delete/transfer, copy, day CRUD, shared view,
      trip/POI attachment metadata, distance matrix, nearest-neighbor optimize API +
      schemas/api-client/tests)
- [x] T-112 — Pinvi MCP 외부 인터페이스 서빙 (ADR-019, Sprint 6) —
      `apps/api/app/mcp/` + `/mcp/sse` + 토큰 발급 / 회수 UI + 5개 read-only tool.
- [ ] T-113 — `kor-travel-concierge` 별 repo 신설 (ADR-020) — T-107 후속.
      사용자가 repo 명 / provider 확정 후 진입.
- [x] T-114 — GitHub Actions CI/CD 복원 (ADR-021, Sprint 4) — workflow 파일 복원 완료.
      운영 확인은 T-062에서 완료. required status check 후속은 T-065.

### 감사 후속 백로그 (2026-06-06)

> 출처: `docs/audit/2026-06-06-doc-impl-audit.md` §8.1. 괄호 안은 감사 증거 ID.
> 다수가 ADR-027~~031 / DEC-01~~10 확정에 의존한다.

- [x] T-123 — 문서 정합 일괄 정정(README index/머지표/오타/dangling link/OAuth·share 문서화) (A-14,C-20,C-21,P-10,P-13,P-17,P-18)
- [x] T-124 — `/features/*` 코드↔문서 계약 정렬(in-bounds 파라미터·응답, 필드명) (C-07,C-10,C-11,C-15) (완료: 2026-06-11, #171 — 셰입 정합 + `docs/api/features.md` 갱신. trips 페이지네이션은 별개 T-169로 완료)
- [x] T-125 — feature_id 문자열化(코드의 UUID 가정 제거) (C-09; ADR-028)
- [x] T-126 — POI 생성 경로 단일화(`/trips/{id}/pois` 정본) (A-01,C-16)
- [x] T-127 — MCP 외부 인터페이스 정본화(mcp-server.md 권위, status enum, 토큰 엔드포인트) (A-02,A-06,A-12)
- [x] T-128 — 실시간 협업 백엔드 설계 + WS 계층(presence/충돌해소, Sprint 5) (C-03,D-05)
- [x] T-129 — `/search` 통합 + `/geo/*`·`/regions/*` 명세·구현 (A-13,C-02,C-13) (완료: 2026-06-09): kor-travel-geo v2 REST client(`apps/api/app/clients/kor_travel_geo.py`, ADR-025) + config + `GET /geo/{geocode,reverse,search}` + `GET /regions/{within-radius,covering-point}`(`api/v1/geo.py`) + **통합 `GET /search`**(feature[kor_travel_map]+address[kor_travel_geo]+내 POI[DB], 소스별 graceful degrade, `api/v1/search.py`, C-13) + frontend Zod(`packages/schemas/src/geo.ts`) + 계약/통합 테스트. 좌표 매핑(`lon`/`lat`)·router cutover(T-173)는 별개.
- [x] T-130 — `/public/*` 구현 — **완료(2026-06-12, Codex / kor_travel_map T-222c)**:
      kor_travel_map `openapi.user.json`의 `/v1/public/beaches*`, `/v1/public/festivals*` 6개 표면을
      vendor 스냅샷에 동기화하고, Pinvi `KorTravelMapClient` + `/public/*` 라우터 +
      Pydantic/Zod/API client schema를 연결했다. 목록은 `meta.cursor/has_more/total/limit`로
      cursor pagination을 노출하고, 상세/marker layer는 kor_travel_map public view를 그대로 투영한다.
      앱 내부 공통 rate-limit 미들웨어는 T-195로 분리한다. (C-04)
- [x] T-131 — `GET /trips/{id}`에 `build_trip_view` 연결 (C-05)
- [x] T-132 — trip 하위 리소스(days/day-items/members/shared/attachments/copy/optimize) 구현 분할 (C-06,D-06)
- [x] T-133 — Admin priority-3 엔드포인트·페이지 실구현(or 상태 강등) (C-08,C-17)
- [x] T-134 — `POST /auth/refresh` + `user_sessions` 영속화 (C-14)
- [x] T-135 — POI 응답 `rise_set` 노출 (C-18)
- [x] T-136 — Resend webhook Svix 서명 검증 (C-22)
- [x] T-137 — notice/curated-plan 스키마 정본화(`curated_trip_plans` 분리) (D-01,D-04; ADR-029)
- [x] T-138 — `users` 누락 컬럼 + `security_incidents` 테이블 추가 (D-02,D-03,D-09)
- [x] T-139 — 동반자 초대 흐름 + 댓글 모델/`visibility` 정리 (D-06)
- [x] T-140 — 여행 예산(budget/currency) 도메인 + 복사 흐름 (D-10)
- [x] T-141 — trip↔지역 구조적 연결(POI 좌표 유도 or region code) (D-11)
- [x] T-142 — geofence admin 우회 RBAC 소스 정정 + nginx 티어 정리 (D-13,D-24)
- [x] T-143 — 지도/소셜 문서 정정(Kakao 어댑터 제거, Google-only, kor-travel-geo stack 추가) (D-15,D-21,D-22)
- [x] T-144 — 여행/장소 검색 UX + 내보내기(PDF/GPX/print) 설계 (D-16,D-17)
- [x] T-145 — backup 핫스왑 동일호스트 schema-swap 확정(2×DB 폐기) (D-19)
- [x] T-146 — location-audit async outbox + feature 캐시(N+1 제거) (D-20,D-26) (완료: 2026-06-09). **D-20**: `app.location_audit_outbox`(migration 0017) + 미들웨어 요청경로 fast append + 단일 writer `drain_location_audit_outbox`(advisory xact lock) + 백그라운드 worker. **D-26**: `services/feature_cache.py` process-local TTL/LRU 캐시 — `trip_view_builder`가 miss만 kor*travel_map 재조회(반복 trip view hotspot 완화), config `pinvi_feature_cache*\*`. 단위/통합 테스트(캐시 hit/miss/LRU/TTL + 2-build cache-hit).
- [x] T-147 — 잔여 문서 정정(rise/set 정책, gemini.md partial unique index 문법) (D-23,D-25)
- [x] T-148 — SPRINT-4 backend 재작성(HTTP 경계 반영) (P-01; ADR-027) (완료: 2026-06-11, #171/#172 — feature read·trip view 전부 kor_travel_map HTTP client 경유, `etl_bridge` 제거)
- [x] T-149 — Gemini 책임 목록 정정(README/AGENTS/SKILL) (P-03)
- [x] T-150 — 계획/추적 문서 정합화(sprint status/보류·완료 재분류/ADR refs/resume "박힌 ADR" 갱신) (P-04~21)
- [x] T-151 — 미기록 ADR 백필(auth-token/RBAC/audit-chain) + SPRINT placeholder 번호 할당 (P-07,P-08)

### kor-travel-map ADR-045 Phase 6 (Pinvi 몫) 대응

kor-travel-map의 ADR-045 standalone 계획 Phase 6(T-210a~e) 중 Pinvi 저장소가
처리할 항목 매핑:

- [x] **T-210c (Pinvi 부분)** — `apps/etl` ETL 경계 정합 (완료: 2026-06-06).
      코드 측은 이관할 feature/provider Dagster **스켈레톤이 없음**(apps/etl은 KASI 등
      `app` schema 소유 job만 보유) → 이관/삭제 불필요. 문서 측 phantom 스켈레톤
      (`dagster-etl-bridge.md`/`runbooks/etl.md`가 미존재 파일 나열)을 현재 구현 vs
      계획으로 정합화 + `assets/__init__.py` 경계 가드 docstring 추가.
- [x] **T-210b (Pinvi 부분)** — 문서 OpenAPI HTTP supersede: ADR-026(T-068) +
      ADR-027(감사 PR #47)로 사실상 완료(architecture/kor-travel-map-integration/etl 문서 전환).
- [x] **T-210d** = 본 저장소 **T-066**(httpx OpenAPI client) — **완료(2026-06-11, #170/#173)**.
- [x] **T-210e** — drift gate (완료: 2026-06-11): kor_travel_map `openapi.user.json` 스냅샷 vendor
      (`apps/api/tests/contract/kor-travel-map-openapi-user.json`) + 계약 정합 테스트
      (`tests/unit/test_kor_travel_map_contract.py` — client 경로·매핑 응답 필드 ⊆ 스냅샷 + 로컬 핀 신선도
      검사). 수기 client는 kor_travel_map 권고대로 유지. `openapi-typescript` codegen은 선택(미도입, 후속).

### Codex PR 사후 리뷰 후속 (2026-06-07)

정본 종합: `docs/reviews/2026-06-07-codex-pr-review.md` (PR #50~#71 codex 20건 리뷰).
긴급성 [높음] 항목만 backlog로 승격:

- [x] T-154 — **resend webhook C-22 완결**: secret 미설정 fail-closed + `_decode_svix_secret`
      표준 base64 교정(운영 서명 mismatch 버그) (PR #70; C-22 재오픈)
- [x] T-155 — admin `access_reason` PII를 query→header/body 전환(URL 로깅 제거) (PR #50)
- [x] T-156 — 비밀번호 재설정 시 기존 refresh session 전부 폐기 (PR #71)
- [x] T-157 — geofence fallback에 Cloudflare 발신 검증(header spoof + nginx 강등 우회 차단) (PR #60)
- [x] T-158 — Trip WebSocket rate limit + cursor 증폭 차단 + broadcast backpressure + 연결 수 캡 (PR #63)
- [x] T-159 — 응답 money 필드 Zod 타입 정합(`Decimal`→string vs `z.number()` 파싱 reject) (PR #67)
- [x] T-160 — admin 상태변경 status+audit 단일 트랜잭션(원자성, 해시체인) — #50/#52/#53 횡단 (PR #53)
- [x] T-161 — README `GET /search` 앵커 `#26`→`#27` 등 [중간] 정합 일괄 (PR #54 외)

[중간]/[낮음] 세부는 종합 문서 §1 참조(필요 시 개별 task로 분해).

### Codex PR 사후 리뷰 2라운드 후속 (2026-06-08)

정본 종합: `docs/reviews/2026-06-08-codex-pr-review.md` (PR #73~#83 codex 11건 리뷰).
직전 [높음] T-154~T-161은 모두 구현 확인(✅). 이번 라운드 신규 [높음] 없음 — 아래는
잔존 [중간](보안/무결성/가용성) 승격분:

- [x] T-162 — resend 운영 fail-open 잔존: 환경 문자열 게이트(기본 `development`)를 opt-in
      플래그 또는 prod secret 강제로 반전 (PR #74)
- [x] T-163 — 비밀번호 재설정 시 access JWT(15분) 무효화(token version/jti denylist) +
      refresh 회전 race(row lock/조건부 UPDATE) (PR #76)
- [x] T-164 — geofence outage 풋건 startup 가드 + shared-secret 외 IP allowlist/mTLS 방어심화 (PR #77)
- [x] T-165 — WS rate-limit grace 슬롯 점유 cap 우회 차단 + `publish_event` broadcast 비동기 분리 (PR #78)
- [x] T-166 — admin 감사 hash-chain head 직렬화(prev_hash unique/advisory lock) (PR #80)
- [x] T-167 — money 표현 통일(admin union→decimal-string) + `packages/schemas` round-trip 테스트 (PR #79)
- [x] T-168 — storage `AttachmentResponse` 필드 호환 정책을 notice-plans와 통일 (PR #73)
- [x] T-169 — MCP `list_trips` bucket/cursor parity + search_features HTTP 표현 정리 (PR #83)

[낮음] 세부는 종합 문서 §1 참조.

### kor-travel-map 연동(붙이기) 작업 (2026-06-08)

정본 계약: `docs/integrations/kor-travel-map-rest-api.md`. kor-travel-map이 운영 HTTP API(포트
12701, `openapi.user.json`)를 **이미 구축**했으므로(ADR-026/027/DEC-01=B 충족), 이제 Pinvi가
실제 연결한다. 권장 순서 A→B→C 먼저, 이후 D~H 병행.

> **✅ 연동 루프 완료 (2026-06-11)**: T-170/171/181(client) + T-172~T-176/T-178(feature read
> cutover, #171) + T-175(trip view batch + `etl_bridge` 제거, #172) + T-180(admin client, #173) +
> T-179(admin 검토→승인 릴레이 BE #174 + web UI #175). **→ v0.1.0 게이트(DEC-06) 충족.**
> ✅ T-210e drift gate(#178) + ✅ §7 합의 5건 확정(kor_travel_map T-217c, 2026-06-11 — Pinvi 반영:
> 출처 태깅 operator 고정 `"pinvi-admin"` + reason `[suggestion:<id>]` prefix).
> ✅ T-130 `/public/*`(2026-06-12 — kor_travel_map public beach/festival 표면 소비 연결).
> 앱 내부 공통 rate-limit만 T-195 후속.

- [x] T-170 — [A] httpx client 신설 (완료: 2026-06-09, `apps/api/app/clients/kor_travel_map.py`
      — features in-bounds/get/batch/nearby/search/weather/categories/healthz + 도메인 예외
  - 재시도(transient 백오프) + 서비스 토큰 헤더 + lifespan/dependency + MockTransport 계약
    테스트 10개. 라우터 cutover/stub 제거는 T-173)
- [x] T-171 — [B] config 배선 (완료: 2026-06-09, `Settings`에 `pinvi_kor_travel_map_*` 필드
      추가 + `.env.example`/`apps/api/.env.example` 블록. 기존엔 필드 없어 env silently ignored)
- [x] T-172 — [C] feature_id 문자열 정합 마감(#87/T-125 후속, 잔여 uuid 캐스트·`@version` 가정 제거) (완료: 2026-06-11, #171 — 라우터·schema·trip_view 전부 불투명 문자열)
- [x] T-173 — [D] 응답 셰입 정렬(name/평면 lon,lat/구조화 address/weather metric 그룹핑/cluster 셰입) (완료: 2026-06-11, #171 — Pydantic+Zod+api-client+web+docs 일괄)
- [x] T-174 — [E] 클러스터링 서버 위임(`cluster_unit`) + `services/cluster_query.py`(feature schema 직접 SQL — 경계 위반) 제거 (완료: 2026-06-11, #171)
- [x] T-175 — [F] `GET /trips/{id}`에 trip_view_builder 연결 + `POST /v1/features/batch`(string, cap 200, 응답 `{found,missing}`) 배선. inactive feature는 `found`+status로 옴 — "철회/폐업" 표시 분기(kor_travel_map D-12) (완료: 2026-06-11, #172 — `get_features` 연결 + `etl_bridge` 제거)
- [x] T-176 — [G] 검색/날씨/카테고리/근접 라우터 실연결 (완료: 2026-06-11 — in-bounds/nearby/search/get/weather #171 + `GET /features/categories` 카탈로그 추가)
- [x] T-177 — [H1] 사용자 feature 제안 큐(DEC-05 확정): `app.feature_suggestions` + `POST /features/requests`(즉시 201) + `GET /features/requests/{id}` 실구현(C-12 실체화) + rate-limit/dedup. kor_travel_map 직접 호출 X (완료: 2026-06-09)
- [x] T-179 — [H2] Admin 검사/승인 → kor_travel_map **feature change**(DEC-05) — **완료: 2026-06-11 (#174 백엔드 + #175 web UI)** — **actionable**(K-15 = kor_travel_map PR #317로 구현, kor_travel_map ADR-051(2026-06-10)이 이 흐름을 전송 구간 정본으로 승인): `/admin/feature-requests` 검사 + approve/reject 시 kor_travel_map `POST/PATCH/DELETE /v1/admin/features*` 호출, 결과 `feature_id`/`request_id`/state를 `feature_suggestions`에 저장, RBAC(admin/operator)+audit. 합의 5건(review_mode 등)은 kor_travel_map T-217c 회신으로 확정. 재적재와 무관
- [x] T-180 — kor_travel_map **admin HTTP client(API 12701 `/v1/admin/*`)** — **완료: 2026-06-11 (#173)** — §2.9 feature change(`POST/PATCH/DELETE /v1/admin/features*`) + 운영자 재적재(`/v1/admin/feature-update-requests`) proxy 호출 client. T-170 user client와 base 동일(12701), 경로/토큰 정책만 분리 — `pinvi_kor_travel_map_admin_base_url` 기본값도 12701로 고정 + 서비스 토큰 + MockTransport 계약 테스트. (T-179 의존)
- [x] T-178 — [공통] 에러/저하 정책(503 FEATURE_SERVICE_UNAVAILABLE + snapshot fallback, Retry-After 존중) (완료: 2026-06-11, #171 — `_map_kor_travel_map_errors` 가드: 5xx/timeout→503, 429/409→Retry-After, 404)
- [x] T-181 — [표준 추종] ADR-048 외부 `/v1` hard cutover — **완료(2026-06-11, #170 client 잔여까지 머지)**: — **라이브 계약분 완료(2026-06-09)**: kor_travel_map `origin/main`(`openapi.user.json` title `kor-travel-map-user 0.2.0-dev`, kor_travel_map PR #318/#319/#321)이 외부 `/v1` clean cut + batch `/pinvi/features/batch`→`/v1/features/batch`(#318) + 파라미터 개명(`search` bbox CSV→`min_lon/min_lat/max_lon/max_lat`, `page_size`/`cursor`)을 머지함. **T-170 client(`apps/api/app/clients/kor_travel_map.py`) 일괄 교체 완료** — 전 feature/category 경로 `/v1` prefix(`/health`만 비버전), batch 경로/검색 파라미터 갱신 + MCP `_search_features` 호출부 + MockTransport 계약 테스트. **잔여 — 대기 해제(2026-06-10, kor_travel_map `0e45bd7` T-216a~g 머지 확인)**: ① problem+json(`_error_code`를 top-level `code` 파싱으로) ② envelope payload/meta 분리(`meta.page.next_cursor` threading) ③ batch 응답 `items`→**`found`** 교체(현재 전 결과 silent-missing) ④ in-bounds `limit`→`max_items` — **즉시 실행 가능**. frontend codegen은 T-210e.
- [x] T-182 — [결정] DEC-07 좌표 필드명 정렬(ADR-048 B) (완료: 2026-06-09): **`lon`/`lat` 채택**(kor_travel_map 정렬·terse). `Coord`(Pydantic) + `CoordSchema`(Zod) `longitude`/`latitude`→`lon`/`lat`, 전 API 요청/응답·query 파라미터(geo)·ws presence.cursor 출력·frontend(useUserLocation/locationAdapter 출력)·전 테스트·docs/api 예시 일괄 정렬. 외부 kor_travel_map DTO/snapshot tolerant reader·브라우저 Geolocation `position.coords.*`·KASI DB 컬럼은 keep.
- [x] T-211 — kor_travel_map `curated_features` → Pinvi `curated_trip_plans` 1:1 import
      (완료: 2026-06-12, Codex / kor_travel_map T-223d; ADR-049로 admin detail-snapshot 전환):
      `KorTravelMapAdminClient`가
      `/v1/admin/curated-features/{curated_feature_id}/detail-snapshot`을 소비하고,
      `/admin/notice-plans/imports/kor-travel-map-curated-features`가 `create` / `upsert` / `refresh`
      mode로 Pinvi curated plan/POI를 생성·갱신한다. `source_system`,
      `source_curated_feature_id`, `source_curated_feature_version`, `source_etag`,
      `source_imported_at`, source item id provenance 컬럼을 저장한다.
- [x] T-196 — `kor-travel-concierge` 잔여 Pinvi 설정 제거 (완료: 2026-06-12, Codex):
      프로젝트가 `kor-travel-concierge`로 rename되고 Pinvi와 직접 관계를 끊는 결정에 따라
      `PINVI_AGENT_API_BASE_URL`, 12401 포트 예약, Docker/env/runbook 노출을 제거했다.
- [x] T-197 — Prometheus 성능 모니터링 추가 (완료: 2026-06-13, Codex):
      FastAPI `/metrics` + route-template 기반 request counter/latency histogram/in-flight gauge를
      추가하고, Docker multi-worker용 Prometheus multiprocess 설정을 넣었다. `observability`
      profile은 Prometheus `12401`, cAdvisor `12301`, Grafana `12205`를 사용하며, Grafana
      datasource/dashboard provisioning과 `/admin/grafana` 기본 URL을 같은 포트 정책으로 정렬했다.
- [x] T-198 — 프로젝트명/GitHub repo `pinvi` 변경 (완료: 2026-06-13, Codex):
      제품/문서 표기와 GitHub 저장소 식별자를 `Pinvi`/`pinvi`로 정렬하고, npm workspace
      scope를 `@pinvi/*`, Python package metadata를 `pinvi-api`/`pinvi-etl`로 변경했다.
      ETL package path는 `apps/etl/pinvi`/`pinvi.etl`로 이전했다.
- [x] T-199 — 런타임 계약/외부 서비스명 hard cutover (완료: 2026-06-13, Codex):
      호환 별칭 없이 env/settings/cookie/DB/RustFS/API field를 `PINVI_*`/`pinvi_*` 기준으로
      정리했다. 개발 DB/사용자/compose 이름은 `pinvi`/`pinvi-*`, RustFS bucket은
      `pinvi-media`로 맞췄다. 이전 지도 서비스명은 `kor-travel-map`/`kor_travel_map`,
      이전 주소/지오코딩 서비스명은 `kor-travel-geo`/`kor_travel_geo`, 이전 agent 계열은
      `kor-travel-concierge`로 정리했다.
- [x] T-200 — `kor-travel-docker-manager` 포트 대역 정렬 (완료: 2026-06-13, Codex):
      ADR-042를 추가해 로컬 포트 source of truth를 docker-manager `config/docker-targets.yml` /
      `docs/ports.md`로 고정했다. Pinvi API/Web/Dagster는 `12801`/`12805`/`12802`,
      kor-travel-map API/Admin API는 `12701`, kor-travel-geo API는 `12501`,
      Grafana/cAdvisor/Prometheus는 `12205`/`12301`/`12401`을 사용한다. env/settings/Web
      defaults/e2e/compose/scripts/runbook을 같은 정책으로 정렬했다.

### Codex PR 3라운드 사후 리뷰 후속 (2026-06-09, `docs/reviews/2026-06-09-codex-pr-review.md`)

- [x] T-183 — [높음] #100 backup hotswap 무결성/가용성: `scripts/restore-hotswap.sh`
      GRANT 복원 + FK 적재순서(`session_replication_role=replica`), `services/backup_service.py`
      restore_id ms/uuid + 프로세스 내부 lock + DB `pg_try_advisory_lock`, API-trigger self-kill
      drain 회피, cut-over audit previous-schema reflection 보강. **완료: 2026-06-09.**
- [x] T-184 — [중간] #101/#85 trip 권한·PII·첨부검증·shared rate limit: companion 쓰기권한
      read-only 강제(day/attachment/optimize), `invited_email` PII 비-owner 마스킹, 첨부 metadata
      입력검증(`public_url` 서버파생/bucket allowlist), shared GET throttle. **완료: 2026-06-09,
      PR #109.**
- [x] T-185 — [중간] #91 websocket: `api/v1/ws.py` grace 윈도우 raw 소켓 누수(FD/mem DoS)
      차단, `services/realtime_broker.py` per-connection `send_json` 직렬화. **완료: 2026-06-09,
      PR #109.**
- [x] T-186 — [중간] #96 trip list cursor: offset→keyset(`updated_at`,`trip_id`) 전환,
      무필터 기본 bucket 의미 회귀 점검, `q` strip 재검증, `ilike` `%`/`_` 이스케이프.
      **완료: 2026-06-09, PR #109.**
- [x] T-187 — [중간] #90/#107: `middleware/geofence.py` mTLS 단일헤더 약점 →
      network CIDR 병행 강제/문서화, `api/v1/admin/audit.py` 위치감사 chain 풀스캔 →
      반환 윈도우만 검증. **완료: 2026-06-09, PR #109.**
- [x] T-188 — [중간] #108 후속: `POST /features/requests`에 `type`(new_place|correction|closure) + `target_feature_id` 노출(테이블·모델은 갖췄으나 API 미노출 → new_place만 가능했음). correction/closure는 target 필수·new_place는 금지(422), dedup 유니크 키에 type+target 포함(마이그레이션 0015), 응답 노출, frontend Zod + 회귀 테스트. (완료 2026-06-09, PR #108 리뷰 반영)
- [x] T-189 — [낮음 묶음] 리뷰 잔여 정리(2026-06-09): (a) 사용자 제안 kind를 `place`/`event`로 좁힘(#108 — notice/price/weather/route/area는 운영 데이터, `FeatureSuggestionKind` + Zod) (b) 제안 rate-limit이 `rejected`/`duplicate` 제외하고 `pending`/`approved`/`added`만 카운트(거절 다수 사용자 정당 제안 차단 방지). **잔여(후속)**: `app.feature_suggestions.requester_user_id` FK RESTRICT의 PIPA 파기 정책(사용자 hard-delete 시 익명화/cascade — T-142 인접), #99 `poi_rise_set_to_dict` model_validate·#93 money quantize(저위험 가설, 미반영).

### Claude PR 사후 리뷰 후속 (2026-06-10, `docs/reviews/2026-06-10-claude-pr-review.md`)

- [x] T-190 — [높음] #116 location-audit outbox 인증 주체/요청 ID 정합: 인증 의존성이
      `request.state.user_id`를 저장하고, 미들웨어는 spoof 가능한 `X-User-Id` 대신 state 값을 사용.
      `RequestIdMiddleware`의 생성 request id도 state/extensions에 보존하며, `/features/requests`
      body 좌표를 outbox에 남김. **완료: 2026-06-10.**
- [x] T-191 — [높음] #120/#121 trip/POI 첨부 metadata storage ref 검증:
      `bucket == PINVI_RUSTFS_BUCKET` + `user-uploads/{trip_attachment|poi_attachment}/{current_user_id}/`
      prefix만 허용, 위반 시 `422 INVALID_ATTACHMENT_STORAGE_REF`. **완료: 2026-06-10.**
- [x] T-192 — [높음] #123 admin 큐레이션 첨부 metadata storage ref 검증:
      `user-uploads/{curated_plan_attachment|curated_poi_attachment}/{admin_user_id}/` prefix만 허용.
      **완료: 2026-06-10.**
- [x] T-193 — [중간] #123 `/storage/upload-urls` curated 목적 admin gate:
      `curated_plan_attachment` / `curated_poi_attachment` presigned 발급은 admin만 허용하고
      비권한은 404로 숨김. **완료: 2026-06-10.**
- [x] T-194 — [중간] #119 `/features/nearby` query `lon`/`lat` 정렬:
      legacy `lng`를 거부하고 kor_travel_map/DEC-07 정본 `lon`으로 통일. **완료: 2026-06-10.**
- [x] T-195 — [중간] public/API 공통 rate-limit 미들웨어 (완료: 2026-06-13, Codex):
      `RateLimitMiddleware`를 전역 적용하고 `/public/*` IP 60/min, 인증 사용자 경로
      user/token 60/min, 로그인/가입/재설정 5/min, OAuth 10/min, storage upload 30/min,
      공유 토큰 60/min 정책을 구현했다. ADR-038에 따라 production/staging은 Postgres
      `app.rate_limit_buckets` fixed-window bucket, dev/test/smoke는 memory backend를 쓴다.

### Claude T-105 첨부 도메인 + RustFS (2026-06-10)

- [x] T-105 — Trip/POI/admin 첨부 도메인 완성. 하드닝(개수 제한+재정렬, #120), presigned
      download URL(#121), `/admin/rustfs/*` 객체 관리 boto3(#122), admin 큐레이션 첨부 §5.3/5.4(#123).
      부수: test-harness 잠재 버그 수정(`core/deps.py` get_db 동적 세션팩토리 참조). **완료: 2026-06-10.**
- [x] RustFS presigned 실서명 활성화(#125) — `make_upload_url`/`make_download_url` boto3 SigV4
      query auth(public endpoint, path-style). presigned + admin 경로 전부 실서명/실호출. **완료: 2026-06-10.**

### Claude Sprint 4 PR-C 프론트 (2026-06-10)

> 검증: web build / `tsc --noEmit` / `next lint` / vitest. 실 지도·업로드 E2E(VWorld 키 +
> RustFS + 브라우저)는 별도 인프라 게이트.

- [x] 지도 실 feature 로딩 + 16색 팔레트(#126) — viewport→`/features/in-bounds`, `markerPalette`/`featureBounds`.
- [x] trip `[tripId]` 메인 지도 + POI 사이드패널 양방향(#127) — `tripMapPoints`, `TripMapView`.
- [x] 지도 검색/내 위치/우클릭 메뉴(#128) — `MapSearchBox`/`UserLocationMarker`/`MapContextMenu`.
- [x] POI 추가/재정렬(D&D)/마커 편집/삭제(#129) — `poiRank`, optimistic lock.
- [x] 위치 동의 흐름(LBS/PIPA) + day CRUD(#130) — `userApi.getConsents/putConsents/withdrawConsent`.
- [x] 마커 우클릭 편집 + 설정 동의 철회 페이지(#131).
- [x] notice-plan copy 다이얼로그(#132).
- [x] trip 공유 링크 관리(#133) / 첨부 업로드 presigned PUT(#134) / feature 제안 폼(#135).
- [x] trip 댓글(#136) / 동반자 초대·관리(#137) / 일자 동선 최적화(#138) / POI 상세 편집(#139).
- [x] `maplibre-vworld` 핀 v0.1.3 동기화(최신, src/dist 무변경 docs 릴리스). **완료: 2026-06-10.**

## 머지 히스토리 (참고)

| PR           | 제목                                                                                    | merge 일   | 비고                                   |
| ------------ | --------------------------------------------------------------------------------------- | ---------- | -------------------------------------- |
| PR #9        | Sprint 1 진입 PR                                                                        | 2026-05-26 | T-030 ~ T-035                          |
| PR #10       | Sprint 2 진입 PR                                                                        | 2026-05-26 | 사용자/Trip/POI/동의/Storage           |
| PR #11       | Sprint 3 진입 PR                                                                        | 2026-05-26 | Admin + RBAC + audit chain             |
| PR #14       | docs: Sprint 4~~6 plan + ADR-018~~023                                                   | 2026-05-27 | 릴리즈 마일스톤 정리                   |
| PR #15       | ci: GitHub Actions workflow 복원 (Sprint 4 PR-A)                                        | 2026-06-05 | T-114/T-065                            |
| PR #16       | feat: 백엔드 features API + kor-travel-map Protocol + cluster + trip view (PR-B)        | 2026-06-05 | T-060 일부 (client는 stub — 감사 C-01) |
| PR #52       | feat: add admin trip management                                                         | 2026-06-06 | T-120                                  |
| PR #53       | feat: add admin POI management                                                          | 2026-06-06 | T-121                                  |
| PR #54       | docs: fix T-123 consistency gaps                                                        | 2026-06-06 | T-123                                  |
| PR #55       | docs: align Gemini responsibility boundary                                              | 2026-06-06 | T-149                                  |
| PR #56       | docs: align tracking docs with merged work                                              | 2026-06-06 | T-150                                  |
| PR #57       | docs: backfill auth rbac audit ADRs                                                     | 2026-06-06 | T-151                                  |
| PR #58       | docs: align map social kor-travel-geo docs                                              | 2026-06-06 | T-143                                  |
| PR #59       | docs: fix rise set and gemini SQL docs                                                  | 2026-06-06 | T-147                                  |
| PR #60       | fix: use db roles for geofence admin bypass                                             | 2026-06-06 | T-142                                  |
| PR #61       | docs: define trip search and export UX                                                  | 2026-06-06 | T-144                                  |
| PR #62       | docs: finalize backup schema-swap restore                                               | 2026-06-06 | T-145                                  |
| PR #63       | feat: add trip realtime websocket broker                                                | 2026-06-06 | T-128                                  |
| PR #64       | feat: add security incidents schema                                                     | 2026-06-06 | T-138                                  |
| PR #65       | feat: add trip companion comments flow                                                  | 2026-06-06 | T-139                                  |
| PR #67       | feat: add trip budget constraints                                                       | 2026-06-06 | T-140                                  |
| PR #69       | feat: add trip primary region                                                           | 2026-06-07 | T-141                                  |
| PR #70       | feat: verify resend webhook signatures                                                  | 2026-06-07 | T-136                                  |
| PR #71       | feat: persist refresh sessions                                                          | 2026-06-07 | T-134                                  |
| PR #120~#123 | feat: T-105 첨부 도메인(하드닝/download URL/rustfs boto3/admin 큐레이션)                | 2026-06-10 | T-105                                  |
| PR #125      | feat: RustFS presigned 실서명 활성화                                                    | 2026-06-10 | storage                                |
| PR #126~#131 | feat: Sprint 4 PR-C 지도 프론트(실데이터/trip맵/검색·위치·우클릭/POI편집/동의·day/잔여) | 2026-06-10 | T-060                                  |
| PR #132~#135 | feat: notice copy / 공유 링크 / 첨부 업로드 / feature 제안                              | 2026-06-10 | T-060                                  |
| PR #136~#139 | feat: 댓글 / 동반자 / 동선 최적화 / POI 상세 편집                                       | 2026-06-10 | T-060                                  |
