# Admin API (`/admin/*`)

Admin 콘솔의 모든 endpoint. 13개 페이지 인덱스는 [`docs/spec/v8/04-admin.md`](../spec/v8/04-admin.md).
RBAC 상세는 [`docs/architecture/admin-rbac.md`](../architecture/admin-rbac.md).
공통 규약 [`common.md`](./common.md).

## 1. 인증 / 권한

- 사용자와 동일한 cookie 인증 (`pinvi_access`, `pinvi_refresh`)
- 권한 검사는 `app.users.roles` 배열에 `admin` / `operator` / `cpo` 포함 여부
- 미권한 사용자 → **`404 Not Found`** (존재 자체 숨김 — `403` 대신)
- 모든 mutating 액션은 `app.admin_audit_log`에 자동 기록 (`prev_hash` unique +
  advisory lock 기반 chain)
- 위험 액션은 `access_reason` 입력 강제 (request body 또는 별도 헤더)

자세히는 SPEC V8 M-4 / O-6.

## 2. 인덱스

| Path                                                              | 용도                                                   | Sprint |
| ----------------------------------------------------------------- | ------------------------------------------------------ | ------ |
| `GET /admin/stats/overview`                                       | 대시보드 운영 통계/그래프 지표                         | 3      |
| `GET /admin/system/summary` / `detail`                            | 의존 API / Docker container 상태                       | 4      |
| `GET /admin/users` / `{user_id}` / `PATCH`                        | 사용자 목록 / 상세 / 편집                              | 3      |
| `POST /admin/users/{id}/roles/grant\|revoke`                      | 사용자 role 부여 / 회수 + 감사                         | 6      |
| `POST /admin/users/{id}/force-verify`                             | 강제 verify (디버그)                                   | 3      |
| `GET /admin/users/{id}/sessions`                                  | 사용자 세션 목록(IP hash만 노출)                       | 6      |
| `POST /admin/users/{id}/sessions/*`                               | 세션 단건/전체 강제 로그아웃                           | 6      |
| `POST /admin/users/{id}/lifecycle/*`                              | 인증 재발송 / reset / 재활성화 / 삭제 대기 / 익명화    | 6      |
| `POST /admin/users/{id}/disable`                                  | 비활성화 (refresh 전부 revoke, token version 증가)     | 3      |
| `POST/PUT/GET/DELETE /admin/users/{id}/avatar*`                   | 사용자 아바타 업로드 URL / 교체 / 조회 URL / 삭제      | 4      |
| `GET/PUT /admin/settings/avatar`                                  | 전역 아바타 업로드 크기 제한                           | 4      |
| `PUT /admin/users/{id}/file-quota`                                | 사용자별 파일 용량 override                            | 4      |
| `GET/PUT /admin/settings/files`                                   | 전역 파일 용량 정책                                    | 4      |
| `GET/DELETE /admin/files[/{attachment_id}]`                       | 여행/날짜/POI 파일 검색 / 다운로드 URL / 삭제          | 4      |
| `GET /admin/trips` / `{trip_id}`                                  | trip 목록 / 상세                                       | 3      |
| `GET/POST/DELETE /admin/trips/{trip_id}/operation*`               | trip/day 복사·이동·삭제와 영향도 조회                  | 4      |
| `GET /admin/features` / `{feature_id}`                            | kor-travel-map admin feature 검색 / 상세 (read-only)   | 4      |
| `GET/POST /admin/features/change-requests[/{id}/approve\|reject]` | kor-travel-map feature 변경 요청 큐 검수 / audit       | 4      |
| `GET /admin/pois` / `{poi_id}`                                    | 여행 POI 검색 / 상세 (`feature_link_broken_at` 필터)   | 3      |
| `PATCH /admin/pois/{poi_id}/link-status`                          | POI feature 연결 상태 로컬 표시                        | 3      |
| `GET/POST/DELETE /admin/pois/{poi_id}/operation*`                 | POI 복사·이동·삭제와 영향도 조회                       | 4      |
| `GET /admin/datasets`                                             | dataset 카탈로그                                       | 3      |
| `GET /admin/datasets/{table_name}/rows`                           | row 조회 (검색/필터/정렬/page)                         | 3      |
| `GET/POST/PATCH/DELETE /admin/entities/{entity}[/{item_id}]`      | 통합 엔티티 CRUD                                       | 3      |
| `GET /admin/api-calls`                                            | 외부 API 호출 로그 (`api_call_log`)                    | 3      |
| `GET /admin/emails`                                               | 이메일 발송 큐 (`email_queue`)                         | 3      |
| `GET /admin/emails/deliverability`                                | Resend 발송 가능 상태 / suppression 상태판             | 6      |
| `POST /admin/emails/{id}/resend`                                  | 재발송                                                 | 3      |
| `GET /admin/audit`                                                | `admin_audit_log` (read-only, chain 검증)              | 3      |
| `GET /admin/audit/location`                                       | `location_access_log` (CPO 권한만)                     | 3      |
| `GET/POST /admin/incidents[/{id}/...]`                            | PIPA 침해사고 CPO workflow                             | 6      |
| `GET/POST /admin/dsr[/{id}/...]`                                  | 개인정보 권리행사 DSR CPO workflow                     | 6      |
| `GET/POST /admin/moderation/reports[/{id}/...]`                   | 콘텐츠 신고 심사 / 숨김 / 게시중단 / 복구              | 6      |
| `GET/POST /admin/retention/*`                                     | PII/위치 로그 보존기간 dry-run/execute                 | 6      |
| `GET/POST /admin/notice-plans[/{plan_id}]` / `PATCH` / `DELETE`   | Notice plan CRUD                                       | 6      |
| `POST /admin/notice-plans/{plan_id}/pois[/reorder]`               | Notice POI                                             | 6      |
| `GET /admin/feature-requests`                                     | 사용자 feature 제안 검토 큐 (§8.4)                     | 8      |
| `POST /admin/feature-requests/{id}/approve\|reject`               | 검토 → kor_travel_map `/v1/admin/features*` 릴레이     | 8      |
| `GET /admin/category-mappings`                                    | kor-travel-map category catalog + Pinvi marker preview | 6      |
| `GET /admin/etl/summary`                                          | Pinvi ETL registry + kor-travel-map ops 요약           | 5      |
| `GET /admin/dedup-review`                                         | Record Linkage 후보 조회                               | 5      |
| `POST /admin/dedup-review/{review_id}/verdict`                    | Record Linkage 후보 판정 + audit                       | 5      |
| `GET /admin/features/{id}/sources`                                | source_links                                           | 5      |
| `GET /admin/features/{id}/overrides`                              | feature_overrides                                      | 5      |
| `GET /admin/features/{id}/weather-values`                         | weather timeline                                       | 5      |
| `GET /admin/provider-sync` / `import-jobs`                        | provider/dataset sync 상태와 import job 조회           | 5      |
| `GET /admin/integrity/issues` / `reports`                         | kor-travel-map consistency issue/report 조회           | 5      |
| `GET /admin/debug/logs/system` / `api-calls`                      | kor-travel-map sanitized system/API logs 조회          | 5      |
| `GET /admin/grafana/health`                                       | Grafana embed origin health probe                      | 5      |
| `GET /admin/backup/snapshots`                                     | `app` schema backup snapshot 목록                      | 5      |
| `POST /admin/backup/snapshot`                                     | 수동 backup snapshot 생성 + audit                      | 5      |
| `GET/POST /admin/mcp-tokens` / `{token_id}/revoke`                | MCP 토큰 검색 / 대리 발급 / 강제 회수                  | 6      |
| `GET /admin/rbac/permission-matrix`                               | Admin role별 endpoint 권한 matrix                      | 6      |
| `GET /admin/rustfs/objects` / `DELETE`                            | RustFS 객체 관리                                       | 2      |
| `GET/POST /admin/seed/scenarios[/{scenario_key}]`                 | dev/staging seed scenario dry-run                      | 3      |
| `GET /admin/reset/status` / `POST /admin/reset`                   | dev/staging reset dry-run                              | 3      |

## 2.0 Admin RBAC / Permission Matrix

`app.users.roles` 배열이 Admin 권한의 정본이다. token claim은 표시용으로만 쓰고,
`require_role(...)` dependency가 매 요청마다 DB 사용자 row를 다시 읽어 `admin` / `operator` /
`cpo` 포함 여부를 검사한다. 권한이 없으면 endpoint 존재를 숨기기 위해 `404 RESOURCE_NOT_FOUND`를
반환한다.

```http
GET /admin/rbac/permission-matrix
```

- 권한: `admin` / `operator` / `cpo`
- 응답: role 설명 map과 endpoint 권한 matrix
- `access_reason_required`와 `audit_required`는 UI 표시와 운영 점검용이다. 최종 권한 정본은 각
  FastAPI route의 `require_role(...)`와 mutation service guard다.

응답 예:

```jsonc
{
  "data": {
    "roles": {
      "user": "일반 사용자",
      "admin": "전체 운영 mutation과 위험 action",
      "operator": "운영 조회와 데이터 운영 일부 mutation",
      "cpo": "개인정보/위치/보안 사고 처리",
    },
    "entries": [
      {
        "resource": "admin.users",
        "action": "role_grant_revoke",
        "route": "/admin/users/{user_id}/roles/{grant|revoke}",
        "roles": ["admin"],
        "access_reason_required": true,
        "audit_required": true,
        "notes": "user role 회수, 자기 admin 회수, 마지막 admin 회수를 차단한다.",
      },
    ],
  },
}
```

## 2.1 PIPA Security Incidents

`/admin/incidents`는 `app.security_incidents`를 CPO 운영 workflow로 노출한다. 상태 모델은
`detected` → `triage` → `notification_decision` → `reported` → `closed`이며, CPO 30분 내부
review due와 개인정보보호위원회/KISA 72시간 신고 due를 `detected_at` 기준으로 계산한다.

권한:

- `GET /admin/incidents`: `admin` / `cpo`
- `POST /admin/incidents`: `admin` / `cpo`
- `POST /admin/incidents/{incident_id}/triage`: `cpo`
- `POST /admin/incidents/{incident_id}/notification-decision`: `cpo`
- `POST /admin/incidents/{incident_id}/notify`: `cpo`
- `POST /admin/incidents/{incident_id}/report`: `cpo`
- `POST /admin/incidents/{incident_id}/close`: `cpo`

`cpo` 전용 mutation은 기존 Admin RBAC 정책과 같이 권한 없음을 `404 RESOURCE_NOT_FOUND`로
숨긴다. 모든 mutation은 `access_reason`을 요구하고 `admin_audit_log`에
`security_incident.*` action으로 남긴다. Incident 생성 시 CPO/Admin Telegram system outbox에
`category="security_incident"` row를 적재하고 `cpo_notified_at`을 기록한다.

조회:

```http
GET /admin/incidents?status=detected&severity=high&overdue=cpo_review&page_size=50
```

Query:

| 이름        | 설명                                                                    |
| ----------- | ----------------------------------------------------------------------- |
| `status`    | `detected` / `triage` / `notification_decision` / `reported` / `closed` |
| `severity`  | `low` / `medium` / `high` / `critical`                                  |
| `overdue`   | `cpo_review` 또는 `external_report`                                     |
| `page_size` | 1~200, 기본 50                                                          |

응답 `data.items[]` 핵심 필드:

```jsonc
{
  "incident_id": "00000000-0000-0000-0000-000000000000",
  "incident_type": "admin_export_anomaly",
  "severity": "high",
  "status": "detected",
  "summary": "1시간 내 개인정보 export 임계치 초과",
  "affected_user_count": 1200,
  "notification_required": false,
  "detected_at": "2026-06-28T13:00:00Z",
  "cpo_review_due_at": "2026-06-28T13:30:00Z",
  "external_report_due_at": "2026-07-01T13:00:00Z",
  "cpo_review_overdue": false,
  "external_report_overdue": false,
  "next_action": "triage",
}
```

생성:

```http
POST /admin/incidents
```

```jsonc
{
  "incident_type": "admin_export_anomaly",
  "severity": "high",
  "source": "admin_audit_log",
  "summary": "1시간 내 개인정보 export 임계치 초과",
  "details": { "exported_rows": 1200 },
  "affected_user_count": 1200,
  "access_reason": "침해사고 수동 등록",
}
```

상태 전이:

```http
POST /admin/incidents/{incident_id}/triage
POST /admin/incidents/{incident_id}/notification-decision
POST /admin/incidents/{incident_id}/notify
POST /admin/incidents/{incident_id}/report
POST /admin/incidents/{incident_id}/close
```

- `triage`: `{"access_reason": "..."}`
- `notification-decision`:
  `{"notification_required": true, "decision_reason": "...", "access_reason": "..."}`
- `notify`: `message`, `access_reason`, 선택 `recipient_email`, `subject`. `recipient_email`이
  있으면 `email_queue.template='security_incident_notice'` row를 만들고
  `notification_payload_hash`를 incident와 email payload 양쪽에 남긴다.
- `report`: `receipt_ref`, `access_reason`. 개인정보보호위원회/KISA 접수번호를
  `external_report_receipt_ref`에 저장하고 `kisa_reported_at`을 기록한다.
- `close`: `closure_note`, `access_reason`. `reported` 상태이거나 통지 불필요 판정이 있어야 한다.

## 2.2 DSR Requests

`/admin/dsr`는 `app.dsr_requests`를 CPO 운영 workflow로 노출한다. 사용자 접수는
`/users/me/dsr-requests`와 `/settings/dsr`에서 만들고, Admin은 본인 확인, 처리 시작, 완료/거절
통지를 담당한다. 상태 모델은 `received` → `identity_check` → `processing` →
`completed` / `rejected` / `withdrawn`이며, 접수 시각 기준 10일 `due_at`을 계산한다.

권한:

- `GET /admin/dsr`: `admin` / `cpo`
- `POST /admin/dsr/{request_id}/identity-check`: `cpo`
- `POST /admin/dsr/{request_id}/process`: `cpo`
- `POST /admin/dsr/{request_id}/complete`: `cpo`
- `POST /admin/dsr/{request_id}/reject`: `cpo`

모든 mutation은 `access_reason`을 요구하고 `admin_audit_log`에 `dsr.*` action으로 남긴다.
`complete`와 `reject`는 `email_queue.template='dsr_result_notice'` row를 만들며,
`result_notice_hash`와 `result_notice_email_id`를 DSR 행에 기록한다. DSR 행은 원문 이메일을
저장하지 않고 `requester_email_hash` / `requester_email_masked`만 보존한다.

조회:

```http
GET /admin/dsr?status=received&request_type=access&overdue=true&page_size=50
```

Query:

| 이름           | 설명                                                                                  |
| -------------- | ------------------------------------------------------------------------------------- |
| `status`       | `received` / `identity_check` / `processing` / `completed` / `rejected` / `withdrawn` |
| `request_type` | `access` / `correction` / `delete` / `suspend`                                        |
| `overdue`      | `true`면 open 상태 중 `due_at` 초과 요청만 조회                                       |
| `page_size`    | 1~200, 기본 50                                                                        |

상태 조치 body:

```jsonc
// identity-check
{
  "access_reason": "본인 확인",
  "identity_verified": true,
  "identity_note": "인증 세션과 계정 이메일 일치"
}

// process
{
  "access_reason": "처리 시작",
  "processing_note": "자료 추출 시작"
}

// complete
{
  "access_reason": "결과 통지",
  "result_summary": "프로필과 위치 접근 로그 export 제공",
  "export_manifest": { "files": ["profile.json"], "masked_fields": ["email"] },
  "partial_response": false
}

// reject
{
  "access_reason": "거절 통지",
  "rejection_reason": "본인 확인을 완료할 수 없음"
}
```

자세한 운영 절차는 [`docs/runbooks/dsr.md`](../runbooks/dsr.md).

## 2.3 Content Moderation

`/admin/moderation`은 `app.content_reports`와 `app.content_moderation_actions`를 운영자
심사 큐로 노출한다. 사용자 접수는 `/users/me/content-reports`와 `/settings/moderation`에서 만들고,
Admin은 검토 시작, 숨김, 게시중단, 복구, 기각을 수행한다.

권한:

- `GET /admin/moderation/reports`: `admin` / `operator`
- `POST /admin/moderation/reports/{report_id}/review`: `admin` / `operator`
- `POST /admin/moderation/reports/{report_id}/hide`: `admin` / `operator`
- `POST /admin/moderation/reports/{report_id}/takedown`: `admin` / `operator`
- `POST /admin/moderation/reports/{report_id}/restore`: `admin` / `operator`
- `POST /admin/moderation/reports/{report_id}/reject`: `admin` / `operator`

조회:

```http
GET /admin/moderation/reports?status=received&target_type=comment&page_size=50
```

Query:

| 이름          | 설명                                                                                      |
| ------------- | ----------------------------------------------------------------------------------------- |
| `status`      | `received` / `reviewing` / `hidden` / `taken_down` / `rejected` / `appealed` / `restored` |
| `target_type` | `trip` / `comment` / `attachment` / `share_link`                                          |
| `page_size`   | 1~200, 기본 50                                                                            |

Mutation body는 모든 조치가 동일하다.

```jsonc
{
  "access_reason": "privacy report action",
  "resolution_summary": "개인정보 포함 댓글 숨김",
}
```

상태 전이:

| 현재 상태    | 가능한 admin 조치                         |
| ------------ | ----------------------------------------- |
| `received`   | `review` / `hide` / `takedown` / `reject` |
| `reviewing`  | `hide` / `takedown` / `reject`            |
| `hidden`     | `restore`                                 |
| `taken_down` | `restore`                                 |
| `appealed`   | `restore` / `takedown` / `reject`         |
| `rejected`   | 사용자 appeal 가능, admin 직접 조치 없음  |
| `restored`   | 재신고 시 새 report로 처리                |

실제 대상 조치:

- `trip`: `hide`는 `visibility='private'`, `takedown`은 `status='archived'` + `deleted_at`,
  `restore`는 접수 시 snapshot의 `status` / `visibility`를 복원한다.
- `comment`: `hide` / `takedown`은 `trip_comments.deleted_at`, `restore`는 `NULL`.
- `attachment`: `hide` / `takedown`은 `curated_plan_attachments.deleted_at`, `restore`는 `NULL`.
- `share_link`: `hide` / `takedown`은 `trip_share_links.revoked_at`, `restore`는 `NULL`.

모든 admin mutation은 `admin_audit_log.action='content_moderation.*'`, `access_reason`,
`target_pii_fields=['user_content']`를 남긴다. 사용자 appeal은 admin audit이 아니라
`content_moderation_actions.action='appeal'`로 report 이력에 남긴다.

자세한 운영 절차는 [`docs/runbooks/content-moderation.md`](../runbooks/content-moderation.md).

## 2.4 Retention Execution

`/admin/retention`은 T-240/T-241 dry-run 집계를 운영자가 승인·실행·감사할 수 있는 콘솔이다.
실제 파괴 작업은 기본 비활성 kill-switch 뒤에 있고, 모든 run은 `app.retention_runs`에 후보
snapshot과 result evidence를 남긴다.

권한:

- `GET /admin/retention/summary`: `admin` / `operator` / `cpo`
- `GET /admin/retention/runs`: `admin` / `operator` / `cpo`
- `POST /admin/retention/dry-run`: `admin` / `operator` / `cpo`
- `POST /admin/retention/execute`: `admin` / `cpo`

엔드포인트:

```http
GET /admin/retention/summary
GET /admin/retention/runs?page_size=20
POST /admin/retention/dry-run
POST /admin/retention/execute
```

`summary`는 `pinvi_pii_retention` / `pinvi_location_log_archive`와 같은 bounded count를 반환하며,
`execute_enabled`, `confirm_phrase`, `latest_runs`를 함께 포함한다. 사용자 이메일, 좌표 원문,
host path, 운영 도메인/secret은 응답에 넣지 않는다.

Mutation body:

```jsonc
{
  "scope": "all", // all | pii | location
  "access_reason": "보존기간 만료 데이터 정리",
}
```

`execute`는 추가로 confirm phrase를 요구한다.

```jsonc
{
  "scope": "all",
  "access_reason": "보존기간 만료 데이터 정리",
  "confirm_phrase": "EXECUTE RETENTION",
}
```

실행 정책:

- `PINVI_RETENTION_EXECUTE_ENABLED=false`이면 `409 RETENTION_KILL_SWITCH_DISABLED`.
- confirm phrase가 다르면 `422 RETENTION_CONFIRM_PHRASE_INVALID`.
- `location_audit_outbox`에 cutoff 이전 pending row가 있거나 archive tail과 active head의
  hash-chain bridge가 맞지 않으면 `409 RETENTION_PRECHECK_FAILED`.
- PII scope는 삭제 후 grace가 지난 일반 사용자 PII를 익명화하고 OAuth identity, 만료
  verification/session/OAuth transient row를 삭제한다.
- location scope는 6개월 초과 `location_access_log` row를 `app.location_access_log_archive`에
  복사한 뒤 active table에서 삭제한다. trigger는 retention transaction의
  `app.retention_location_delete_allowed=on` 설정에서만 이 DELETE를 허용한다.
- `admin_audit_log` PII 후보는 append-only 감사 원장이라 삭제하지 않고
  `skipped_admin_audit_pii_over_retention` result로 기록한다.

응답 `AdminRetentionRun` 핵심 필드:

```jsonc
{
  "run_id": "00000000-0000-0000-0000-000000000000",
  "mode": "execute",
  "scope": "all",
  "status": "completed",
  "candidate_snapshot": {},
  "result": {
    "pii": { "anonymized_users": 1, "deleted_oauth_identities": 1 },
    "location": { "archived_rows": 1, "deleted_active_rows": 1 },
    "skipped_admin_audit_pii_over_retention": 1,
  },
  "kill_switch_enabled": true,
  "access_reason": "보존기간 만료 데이터 정리",
  "actor_user_id": "00000000-0000-0000-0000-000000000000",
  "started_at": "2026-06-28T13:00:00Z",
  "completed_at": "2026-06-28T13:01:00Z",
}
```

## 3. 대시보드

### 3.1 `GET /admin/stats/overview`

Pinvi app schema에서 계산 가능한 운영 지표를 즉시 반환한다. 응답에는 raw 운영 경로,
운영 도메인, secret을 넣지 않는다. 디스크 사용량은 `PINVI_BACKUP_DIR`의 가장 가까운
존재 경로 기준 숫자만 반환한다. Docker/container 상세 상태는 `/admin/system` 후속 화면에서
분리한다.

응답 200:

```jsonc
{
  "data": {
    "generated_at": "2026-06-27T06:00:00Z",
    "users_total": 1234,
    "users_24h": 42,
    "users_pending_verification": 18,
    "trips_total": 567,
    "trips_active": 234,
    "pois_total": 789,
    "email_queue_pending": 3,
    "api_calls_24h": 91,
    "api_calls_failed_24h": 2,
    "api_failure_rate_pct": 2.2,
    "api_latency_p95_ms": 312,
    "features_by_kind": {},
    "etl_last_24h": { "success": 0, "failed": 0 },
    "series_24h": [
      {
        "bucket_start": "2026-06-26T07:00:00Z",
        "users_created": 0,
        "trips_created": 1,
        "api_calls": 7,
        "api_failures": 0,
      },
    ],
    "load": {
      "cpu_count": 4,
      "load_1m": 0.62,
      "load_5m": 0.51,
      "load_15m": 0.44,
    },
    "capacity": {
      "attachments_total_bytes": 20971520,
      "attachments_count": 8,
      "trip_attachment_quota_bytes": 104857600,
      "user_attachment_quota_bytes": 1073741824,
      "attachment_max_upload_bytes": 10485760,
      "avatar_max_upload_bytes": 2097152,
      "users_with_quota_override": 2,
      "disk_total_bytes": 107374182400,
      "disk_used_bytes": 32212254720,
      "disk_free_bytes": 75161927680,
    },
  },
}
```

권한: `admin` / `operator`.

### 3.2 `GET /admin/system/detail`

Admin 시스템 화면용 read-only 상태를 반환한다. Docker socket은 기본 compose에 mount하지 않으며,
socket이 없거나 권한이 없으면 `docker.status`를 `unknown` 또는 `down`으로 강등하고 빈
`containers`를 반환한다. 응답에는 SSH target, 운영 도메인/IP, raw Docker labels/env, secret을
넣지 않는다.

응답 200:

```jsonc
{
  "data": {
    "generated_at": "2026-06-27T06:30:00Z",
    "dependencies": [
      {
        "key": "pinvi_api",
        "label": "Pinvi API",
        "status": "ok",
        "message": "admin route 응답 정상",
        "latency_ms": 0,
      },
    ],
    "docker": {
      "key": "docker",
      "label": "Docker",
      "status": "ok",
      "message": "3개 container 수집",
      "latency_ms": 8,
    },
    "containers": [
      {
        "container_id": "abc123",
        "name": "pinvi-api-latest",
        "image": "pinvi-api:latest-main",
        "state": "running",
        "status": "Up 1 minute (healthy)",
        "health": "healthy",
        "compose_project": "pinvi",
        "compose_service": "pinvi-api",
      },
    ],
  },
}
```

권한: `admin` / `operator`.

### 3.3 `GET /admin/grafana/health`

Admin Grafana iframe이 참조하는 Grafana origin의 `/api/health`를 Next route handler가 서버
측에서 probe한다. 서버사이드 probe URL은 `PINVI_GRAFANA_HEALTH_URL`이 있으면 그 origin을,
없으면 `NEXT_PUBLIC_GRAFANA_URL` origin을 사용한다. 응답은 `ok` 또는 `degraded`만 구분하며,
credential이나 dashboard URL query secret은 반환하지 않는다.

응답 200 또는 503:

```jsonc
{
  "status": "ok",
  "origin": "https://grafana.example.com",
  "status_code": 200,
  "message": "Grafana health 확인",
}
```

권한: Admin UI route 아래에 있으나 route handler 자체는 health 신호만 반환한다. 운영
reverse proxy에서는 `/admin/*` 접근 정책을 동일하게 적용한다.

## 4. 통합 엔티티 CRUD (`/admin/entities/{entity}`)

SPEC V8 M-8 패턴. v1의 `admin_entity_crud.py` 이전.

`entity`: `users` | `features`(read-only) | `trips` | `pois` | `notice-plans` | `notice-pois` |
`feature-requests`.

`category-mappings`는 통합 CRUD entity가 아니다. 정본은 `kor-travel-map` `/v1/categories`이며,
Pinvi Admin은 `GET /admin/category-mappings` read-only 운영 뷰만 제공한다.

### 4.1 `GET /admin/entities/{entity}`

```http
GET /admin/entities/users?q=email:gmail.com+-status:disabled&sort=-created_at&page=1&limit=100
```

검색 문법은 SPEC V8 M-9 — [`common.md`](./common.md) §7.

### 4.2 `POST /admin/entities/{entity}` (생성 가능 entity만)

- `users` — ✗ (가입 흐름 사용)
- `features` — ✗ (라이브러리에 요청)
- `trips` — ✗ (사용자 흐름)
- `notice-plans` / `notice-pois` / `feature-requests` — ✓

### 4.3 `PATCH /admin/entities/{entity}/{item_id}`

- `If-Match: <version>` 필수
- `access_reason` body 또는 `X-Access-Reason` 헤더 (위험 액션 시). PII 원본 조회처럼
  자유 텍스트 사유가 필요한 액션은 URL과 header에 남기지 않고 JSON body만 허용한다.
- `admin_audit_log` 자동 기록 (before/after diff)

### 4.4 `DELETE /admin/entities/{entity}/{item_id}`

| Entity             | 동작                                                                           |
| ------------------ | ------------------------------------------------------------------------------ |
| `users`            | `status = 'deleted'`, `is_active = false` (soft, 30일 후 hard delete schedule) |
| `features`         | (라이브러리에 요청 — `feature.status='hidden'`)                                |
| `trips`            | `status = 'archived'`, `deleted_at = now()` (soft)                             |
| `pois`             | hard delete                                                                    |
| `notice-plans`     | soft delete                                                                    |
| `notice-pois`      | soft delete                                                                    |
| `feature-requests` | hard delete (`status='rejected'` 권장)                                         |

자기 자신 disable / admin 권한 박탈 차단 — `403 PERMISSION_DENIED`
(`details.reason: "cannot_modify_self"`).

## 5. Dataset 브라우저

v1 `admin_data_browser.py` 이전. kor-travel-map 소유 schema가 분리됐으므로 일부 dataset
은 kor-travel-map admin/ops OpenAPI 경유.

### 5.1 `GET /admin/datasets`

```jsonc
{
  "data": {
    "datasets": [
      { "schema": "app", "table_name": "curated_trip_plans", "owner": "pinvi", "row_count": 42 },
      {
        "schema": "feature",
        "table_name": "features",
        "owner": "kor-travel-map",
        "row_count": 12345,
      },
      {
        "schema": "feature",
        "table_name": "source_records",
        "owner": "kor-travel-map",
        "row_count": 67890,
      },
      {
        "schema": "provider_sync",
        "table_name": "state",
        "owner": "kor-travel-map",
        "row_count": 12,
      },
    ],
  },
}
```

**제외**: `users`, `user_sessions`, `user_email_verifications`, `user_oauth_identities`,
`trips`, `trip_days`, `trip_day_pois`, `user_consents`, `location_access_log`,
`admin_audit_log`. PII / 보안 민감 테이블은 `/admin/entities/users`로만 접근.

### 5.2 `GET /admin/datasets/{table_name}/rows`

```http
GET /admin/datasets/curated_trip_plans/rows?search=부산&sort_by=updated_at&sort_dir=desc&limit=100&filter.is_published=true
```

- `limit`: `50` / `100` / `200` / `500`
- 정렬: `sort_by` + `sort_dir` (`asc` / `desc`)
- 필드별 필터: `filter.<column>=<value>` (부분 일치 LIKE)
- 자유 텍스트 검색: `search=...` (텍스트 컬럼 OR ILIKE)
- 응답: `data.rows` 배열 + `meta.total` + `meta.has_more`

geometry는 `ST_AsText`로 직렬화. JSONB는 그대로 반환. kor-travel-map 소유 schema는
Pinvi가 직접 table browse하지 않고 kor-travel-map admin/offline/ops OpenAPI로
조회한다.

## 6. 사용자 관리

### 6.0 `GET /admin/users`

```http
GET /admin/users?q=kim&status_filter=active&page=1&limit=50
```

- `q`: 이메일 / 닉네임 부분 일치, `user_id` UUID 정확 일치
- `status_filter`: `pending_verification` / `pending_profile` / `active` / `disabled` /
  `pending_delete` / `deleted`
- 목록 응답은 항상 `email_masked`만 제공하고 원본 이메일은 포함하지 않는다.
- 필터가 없으면 최종 익명화된 `deleted` 사용자는 기본 목록에서 제외하지만, `pending_delete` 사용자는
  후속 운영을 위해 표시한다. `status_filter=deleted`를 명시하면 익명화된 계정도 조회할 수 있다.

### 6.1 `POST /admin/users/{user_id}/force-verify`

```http
POST /admin/users/<user_id>/force-verify
Content-Type: application/json
X-Access-Reason: "고객 문의 처리 (TICKET-1234)"

{}
```

- `users.email_verified_at = now()`, `status = 'pending_profile'`
- `admin_audit_log` + Resend webhook 없이 강제 진입 표시
- 응답 200: 갱신된 user

### 6.2 `POST /admin/users/{user_id}/lifecycle/resend-verify`

- 권한: `admin`
- body: `{ "access_reason": "가입 인증 메일 재발송 요청" }`
- 미인증 + 삭제/비활성 상태가 아닌 사용자에 한해 새 signup verify 토큰을 발급하고, 기존 미사용
  signup 토큰은 `used_at = now()`로 폐기한다.
- `email_queue.template='verify_email'` row를 생성하고
  `admin_audit_log.action="user.verification_resend"`를 기록한다.

### 6.3 `POST /admin/users/{user_id}/disable`

- `users.status = 'disabled'`, `is_active = false`
- 모든 `user_sessions.revoked_at = now()`
- `users.access_token_version`을 증가시켜 기존 access token도 즉시 무효화한다.
- 응답 200: 갱신된 user + 최근 audit

### 6.4 사용자 lifecycle / 세션 강제 종료

```http
GET  /admin/users/<user_id>/sessions
POST /admin/users/<user_id>/sessions/<session_id>/revoke
POST /admin/users/<user_id>/sessions/revoke-all
POST /admin/users/<user_id>/lifecycle/force-password-reset
POST /admin/users/<user_id>/lifecycle/reactivate
POST /admin/users/<user_id>/lifecycle/delete
POST /admin/users/<user_id>/lifecycle/anonymize
```

- 세션 목록은 `session_id`, `expires_at`, `revoked_at`, `user_agent`, `ip_hash`, `is_active`만
  제공한다. IP 원문은 응답하지 않는다.
- 세션 단건/전체 강제 로그아웃은 active session의 `revoked_at`을 설정하고
  `users.access_token_version`을 증가시킨다. 감사 action은 `user.session_revoke` /
  `user.session_revoke_all`.
- `force-password-reset`은 기존 password reset 토큰을 폐기하고 새 reset 토큰 + email queue row를
  만들며, `password_hash=NULL`, active session revoke, `access_token_version` 증가를 같은
  transaction에 묶는다. 감사 action은 `user.password_reset_force`.
- `reactivate`는 `disabled` 또는 `pending_delete`만 허용하며 `deleted_at=NULL`,
  `is_active=true`, 상태를 `active` / `pending_profile` / `pending_verification` 중 복원 가능한
  값으로 되돌린다. 자기 자신 대상은 `404`.
- `delete`는 body에 `{ "access_reason": "...", "confirm": "DELETE" }`를 요구한다.
  `status='pending_delete'`, `is_active=false`, `deleted_at=now()`, session revoke,
  `access_token_version` 증가를 수행한다. 권한 계정(`admin`/`operator`/`cpo`)은 role 회수 후
  실행해야 하며 아니면 `403`.
- `anonymize`는 body에 `{ "access_reason": "...", "confirm": "ANONYMIZE" }`를 요구한다.
  OAuth identity를 삭제하고 이메일을 `deleted+<user_id>@deleted.pinvi.local`로 바꾸며 profile,
  password, avatar, demographic PII를 비운 뒤 `status='deleted'`로 고정한다.

### 6.5 `POST /admin/users/{user_id}/roles/grant|revoke`

Admin은 사용자 상세 화면에서 `admin` / `operator` / `cpo` role을 부여하거나 회수할 수 있다.
`user` role은 기본 role이므로 mutation 대상이 아니다.

```http
POST /admin/users/<user_id>/roles/grant
POST /admin/users/<user_id>/roles/revoke
Content-Type: application/json

{
  "role": "operator",
  "access_reason": "운영 담당자 지정"
}
```

- 권한: `admin`
- 성공 응답: 갱신된 `AdminUserDetail` + 최근 audit
- 감사: `user.role_grant` / `user.role_revoke`, `before_state.roles`, `after_state.roles`,
  `access_reason`, `request_id`
- role 배열은 `user`, `admin`, `operator`, `cpo` 순서로 정규화한다.
- role 변경은 active session을 revoke하고 `users.access_token_version`을 증가시킨다.
- 중복 부여 또는 미보유 role 회수는 `409 INVALID_STATE`.
- 자기 자신의 `admin` role 회수와 마지막 `admin` role 회수는 `403 PERMISSION_DENIED`.
- 권한 없는 사용자는 ADR-033 정책에 따라 `404 RESOURCE_NOT_FOUND`.

### 6.6 PII 마스킹

`GET /admin/users` 목록 응답:

- `email_masked`: `a***@gmail.com`
- `nickname`: 그대로
- `birth_year_month`: 그대로 (선택 동의 받은 경우만)
- `residence_sigungu_code`: 그대로 (선택 동의 받은 경우만)

상세 `GET /admin/users/{user_id}`:

- 기본 마스킹. `?reveal=true`는 legacy misuse로 보고 `422`로 거부한다.
- 상세 응답은 `recent_audit` 최근 10건을 포함한다.

원본 이메일 조회:

```http
POST /admin/users/<user_id>/reveal-pii
Content-Type: application/json

{ "access_reason": "고객 문의 확인" }
```

- 응답 200: 원본 이메일 포함 상세 + `email_revealed=true`.
- `admin_audit_log`에 `action = "user.reveal_pii"`,
  `target_pii_fields = ["email"]`, `access_reason` 기록.
- 사유는 URL query/header가 아닌 JSON body로만 전달한다.

### 6.7 사용자 아바타 관리

Admin은 사용자 상세에서 대상 사용자의 RustFS 아바타를 조회/교체/삭제할 수 있다.

```http
POST /admin/users/<user_id>/avatar/upload-url
Content-Type: application/json

{
  "filename": "avatar.png",
  "content_type": "image/png",
  "content_length": 524288
}
```

- 권한: upload URL / download URL은 `admin` / `operator`, 교체/삭제는 `admin`
- upload URL은 대상 사용자 prefix `user-uploads/avatar/{user_id}/`로 발급된다.
- `PUT /admin/users/{user_id}/avatar` body는 사용자 `PUT /users/me/avatar`와 같고,
  `access_reason`을 추가로 요구한다.
- `DELETE /admin/users/{user_id}/avatar` body:

```jsonc
{ "access_reason": "사용자 요청 대행 삭제" }
```

- 교체/삭제는 `admin_audit_log`에 각각 `user.avatar_replace`, `user.avatar_delete`를 기록하고
  `target_pii_fields = ["avatar"]`로 표시한다.

전역 아바타 크기 제한:

```http
GET /admin/settings/avatar
PUT /admin/settings/avatar
Content-Type: application/json

{
  "avatar_max_upload_bytes": 2097152,
  "access_reason": "운영 정책 조정"
}
```

- 권한: 조회 `admin` / `operator`, 변경 `admin`
- 기본값은 2MiB다.
- 변경은 `admin_audit_log`에 `settings.avatar_update`로 기록한다.

### 6.7 사용자 파일 용량 override

Admin은 사용자 상세에서 여행/날짜/POI 첨부 파일 quota override를 설정할 수 있다. `null`이면
전역 설정을 사용하고, 값이 있으면 전역 설정보다 우선한다.

```http
PUT /admin/users/<user_id>/file-quota
Content-Type: application/json

{
  "attachment_max_upload_bytes_override": 10485760,
  "trip_attachment_quota_bytes_override": 104857600,
  "user_attachment_quota_bytes_override": 1073741824,
  "access_reason": "고객별 용량 상향"
}
```

- 권한: `admin`
- 응답 `file_quota`에는 override 값과 effective 값
  (`effective_attachment_max_upload_bytes`, `effective_trip_attachment_quota_bytes`,
  `effective_user_attachment_quota_bytes`)을 함께 포함한다.
- 변경은 `admin_audit_log`에 `user.file_quota_update`로 기록한다.

### 6.8 전역 파일 용량 정책

```http
GET /admin/settings/files
PUT /admin/settings/files
Content-Type: application/json

{
  "attachment_max_upload_bytes": 10485760,
  "trip_attachment_quota_bytes": 104857600,
  "user_attachment_quota_bytes": 1073741824,
  "access_reason": "운영 정책 조정"
}
```

- 권한: 조회 `admin` / `operator`, 변경 `admin`
- 기본값은 개별 파일 10MiB, 여행계획 총량 100MiB, 사용자 총량 1GiB다.
- 변경은 `admin_audit_log`에 `settings.files_update`로 기록한다.

### 6.9 파일 관리

```http
GET /admin/files?q=receipt&scope=trip&user_id=<uuid>&trip_id=<uuid>&page=1&limit=50
GET /admin/files/<attachment_id>/download-url
DELETE /admin/files/<attachment_id>
Content-Type: application/json

{ "access_reason": "사용자 요청 파일 삭제" }
```

- 권한: 목록/다운로드 URL은 `admin` / `operator`, 삭제는 `admin`
- `scope`: `trip` / `day` / `poi` / `curated_plan` / `curated_poi`
- 목록 응답은 `AttachmentLibraryPage`이며 업로더 이메일은 `uploaded_by_email_masked`만 포함한다.
- 삭제는 metadata soft delete이며, RustFS object를 즉시 지우지 않는다.
- 삭제는 `admin_audit_log`에 `attachment.delete`로 기록한다.

## 7. 여행계획 관리

### 7.1 `GET /admin/trips`

```http
GET /admin/trips?q=busan&status_filter=planned&visibility_filter=private&page=1&limit=50
```

- 권한: `admin` / `operator`
- `q`: 제목 / 지역 힌트 / `primary_region_code` / owner 이메일 부분 일치,
  `trip_id` 또는 `owner_user_id` UUID 정확 일치
- `status_filter`: `draft` / `planned` / `in_progress` / `completed` / `archived`
- `visibility_filter`: `private` / `unlisted` / `public`
- `owner_user_id`: 특정 소유자 UUID
- 목록 응답은 owner 이메일 원본을 포함하지 않고 `owner_email_masked`만 제공한다.
- 각 row는 `day_count`, `poi_count`, `companion_count`, `share_link_count`를 포함한다.
- 각 row는 `region_hint`와 함께 구조화 지역 키
  `primary_region_code`/`primary_region_source`를 포함한다.

### 7.2 `GET /admin/trips/{trip_id}`

- 권한: `admin` / `operator`
- 기본 여행 필드 + `description`
- `companions`: 초대 이메일은 `invited_email_masked`로만 제공
- `days`: `day_index`, `date`, `title`, `note`, `poi_count`를 포함해 상세 계획의 날짜 구성을
  표시한다.
- `pois`: 여행에 등록된 `trip_day_pois` attachment 목록을 날짜/순서대로 반환한다. 각 POI는
  `feature_id`, snapshot 기반 `feature_label`/주소/좌표, 일정 시간, 메모, 비용, 사용자 URL,
  추가자 마스킹 정보를 포함한다. 좌표는 snapshot에서 방어적으로 추출하며 없으면 `null`이다.
- `share_links`: token 원문/해시는 반환하지 않고 share row metadata만 제공
- `attachments`: 여행/날짜/POI 첨부 파일 모음(`AttachmentLibraryItem`), admin 파일 관리 화면과
  같은 scope/파일 metadata를 사용한다.
- `recent_audit`: 해당 trip의 최근 `admin_audit_log` 10건

### 7.3 `POST /admin/trips`

```http
POST /admin/trips
Content-Type: application/json

{
  "owner_user_id": "uuid",
  "title": "부산 가족 여행",
  "description": "고객센터 대행 생성",
  "region_hint": "부산",
  "primary_region_code": "26",
  "start_date": "2026-07-01",
  "end_date": "2026-07-03",
  "visibility": "private",
  "status": "draft",
  "access_reason": "고객 요청 대행"
}
```

- 권한: `admin`
- `owner_user_id`는 삭제/비활성 사용자가 아니어야 한다.
- `start_date`와 `end_date`는 둘 다 비우거나 둘 다 채운다.
- `primary_region_code`가 있으면 `primary_region_source = "manual"`로 저장한다.
- `admin_audit_log`에 `action = "trip.create"`를 기록하며 owner email 원문은 감사 로그에 남기지 않는다.

### 7.4 `PATCH /admin/trips/{trip_id}/status`

```http
PATCH /admin/trips/<trip_id>/status
Content-Type: application/json

{
  "status": "archived",
  "access_reason": "운영 정책 위반 처리"
}
```

- 권한: `admin`
- `access_reason` 필수
- `trips.status`를 변경하고 `version`을 1 증가시킨다.
- `admin_audit_log`에 `action = "trip.update_status"`를 기록한다.

### 7.5 여행계획 / 날짜 운영 작업

운영자가 여행계획과 날짜를 복사·이동·삭제할 때 사용하는 endpoint다. 모든 mutation은
`admin` 전용이고 `access_reason`을 JSON body로 받는다. 결과는 `AdminOperationResult`
형태이며 `affected`에 `days`, `pois`, `attachments`, `comments`, `share_links` 등 영향을 받은
row 수를 담는다.

```http
GET    /admin/trips/<trip_id>/operation-impact
POST   /admin/trips/<trip_id>/copy
POST   /admin/trips/<trip_id>/move
DELETE /admin/trips/<trip_id>

GET    /admin/trips/<trip_id>/days/<day_index>/operation-impact
POST   /admin/trips/<trip_id>/days/<day_index>/copy
POST   /admin/trips/<trip_id>/days/<day_index>/move
DELETE /admin/trips/<trip_id>/days/<day_index>
```

`operation-impact`는 `admin` / `operator` read-only이며, 대상 하위 항목 수와 선택 가능한
정책을 반환한다. 현 DB 제약에서 날짜/POI/첨부 orphan은 허용하지 않는다. `trip_days`와
`trip_day_pois`, POI 첨부 FK가 필수이므로 API는 `policy_options.*.allowed = false`와 사유를
반환하고, Web은 해당 선택지를 비활성 설명으로 표시한다.

여행계획 복사:

```jsonc
{
  "title": "부산 가족 여행 copy",
  "owner_user_id": "uuid-or-null",
  "scope": "all",
  "day_index": null,
  "start_day_index": null,
  "end_day_index": null,
  "date_shift_days": 0,
  "target_trip_id": null,
  "access_reason": "고객 요청 복사",
}
```

- `target_trip_id`가 없으면 새 여행계획을 만들고, 있으면 대상 여행계획에 day/POI/첨부를
  병합한다.
- `scope`는 `all` / `day` / `range`이며 사용자 복사 흐름과 같은 day 선택 규칙을 쓴다.
- 생성/병합 결과와 `trip.copy` audit은 같은 transaction으로 commit한다.

여행계획 이동은 현재 소유자 이전이다.

```jsonc
{ "owner_user_id": "new-owner-uuid", "access_reason": "고객 요청 소유자 이전" }
```

- `trips.owner_user_id`를 변경하고 `version`을 증가시킨다.
- `admin_audit_log.action = "trip.move_owner"`.

여행계획 삭제:

```jsonc
{ "child_policy": "delete", "access_reason": "운영 정책 삭제" }
```

- `child_policy = keep`이면 여행계획만 `archived` + `deleted_at` 처리한다.
- `child_policy = delete`이면 POI, 첨부, 댓글을 soft delete하고 공유 링크를 revoke한 뒤
  여행계획을 soft delete한다. RustFS object는 즉시 삭제하지 않는다.
- `admin_audit_log.action = "trip.delete"`.

날짜 복사:

```jsonc
{
  "target_trip_id": "uuid",
  "target_day_index": 3,
  "include_pois": true,
  "include_attachments": true,
  "access_reason": "일정 복사",
}
```

날짜 이동:

```jsonc
{
  "target_trip_id": "uuid",
  "target_day_index": 3,
  "poi_policy": "move",
  "attachment_policy": "move",
  "comment_policy": "move",
  "access_reason": "일정 통합",
}
```

- 대상 day가 없으면 원본 day의 date/title/note를 복제해 생성한다.
- `poi_policy`, `attachment_policy`, `comment_policy`는 `move` 또는 `delete`만 허용한다.
  orphan은 FK와 조회 정합성 때문에 허용하지 않는다.
- 이동 후 원본 `trip_days` row는 삭제된다. `move` 정책의 POI/첨부/댓글은 대상 여행/날짜로
  retarget되고, `delete` 정책 항목은 삭제 처리된다.
- audit action은 `trip_day.copy`, `trip_day.move`, `trip_day.delete`.

## 8. Feature 조회 (kor-travel-map Admin proxy)

Pinvi는 `feature` / `provider_sync` schema를 소유하지 않는다. Admin feature 조회는
`kor-travel-map` Admin HTTP 계약을 Pinvi API가 proxy하고, Web은 Pinvi API(`12801`)만 호출한다.
브라우저가 `kor-travel-map` Admin 포트로 직접 접근하지 않는다.

### 8.1 `GET /admin/features`

upstream: `kor-travel-map` `GET /v1/admin/features`.

권한: `admin` / `operator`

Query:

| 이름                         | 설명                                                                            |
| ---------------------------- | ------------------------------------------------------------------------------- |
| `q`                          | name/address/feature/source 검색                                                |
| `kind`                       | 반복 가능. `place`, `event`, `notice`, `price`, `weather`, `route`, `area`      |
| `category`                   | 반복 가능 category code                                                         |
| `status`                     | 반복 가능 feature status. 미지정 시 upstream 기본 `active`                      |
| `provider`                   | 반복 가능 primary provider                                                      |
| `dataset_key`                | 반복 가능 primary dataset key                                                   |
| `has_coord`                  | 좌표 보유 여부                                                                  |
| `has_issue`                  | integrity issue 보유 여부                                                       |
| `issue_type`                 | 반복 가능 issue type                                                            |
| `updated_from`, `updated_to` | ISO-8601 timestamp                                                              |
| `page_size`                  | 1~500, 기본 50                                                                  |
| `cursor`                     | keyset cursor                                                                   |
| `sort`                       | `name`, `updated_at`, `created_at`, `kind`, `status`, `provider`, `issue_count` |
| `order`                      | `asc` / `desc`                                                                  |

응답 `data`:

```jsonc
{
  "items": [
    {
      "feature_id": "f_place_...",
      "kind": "place",
      "name": "해운대 카페",
      "category": "01070100",
      "status": "active",
      "lon": 129.163,
      "lat": 35.158,
      "address_label": "부산 해운대구",
      "primary_provider": "visitkorea",
      "primary_dataset_key": "places",
      "issue_count": 0,
      "issues": [],
      "created_at": "2026-06-11T00:00:00+09:00",
      "updated_at": "2026-06-12T00:00:00+09:00",
    },
  ],
  "page_size": 50,
  "next_cursor": null,
  "duration_ms": 7,
}
```

### 8.2 `GET /admin/features/{feature_id}`

upstream: `kor-travel-map` `GET /v1/admin/features/{feature_id}`.

권한: `admin` / `operator`

응답 `data`:

```jsonc
{
  "feature": {
    "feature_id": "f_place_...",
    "kind": "place",
    "name": "해운대 카페",
    "category": "01070100",
    "status": "active",
    "address": {},
    "detail": {},
    "urls": {},
    "raw_refs": [],
    "created_at": "2026-06-11T00:00:00+09:00",
    "updated_at": "2026-06-12T00:00:00+09:00",
  },
  "sources": [],
  "issues": [],
  "overrides": [],
  "versions": [],
  "change_requests": [],
  "files": [],
}
```

### 8.3 Feature detail subpages

권한: `admin` / `operator`

Pinvi는 detail subpage를 위해 `kor-travel-map` 데이터를 read-only로 투영한다. `sources`와
`overrides`는 `GET /v1/admin/features/{feature_id}` detail payload에서 필요한 list만 잘라
반환하고, `weather-values`는 기존 사용자 feature weather card 계약
`GET /v1/features/{feature_id}/weather`의 `metrics`를 Admin tab용 `items`로 반환한다. Pinvi는
`feature.*` 또는 `provider_sync.*` 테이블을 직접 조회하거나 override mutation을 만들지 않는다.

#### `GET /admin/features/{feature_id}/sources`

응답 `data`:

```jsonc
{
  "feature_id": "f_place_...",
  "items": [
    {
      "source_record_key": "visitkorea:places:1",
      "provider": "visitkorea",
      "dataset_key": "places",
      "source_role": "primary",
      "match_method": "natural_key",
      "confidence": 100,
      "is_primary_source": true,
      "fetched_at": "2026-06-11T00:00:00+09:00",
      "imported_at": "2026-06-11T00:01:00+09:00",
      "linked_at": "2026-06-11T00:02:00+09:00",
    },
  ],
}
```

#### `GET /admin/features/{feature_id}/overrides`

응답 `data`:

```jsonc
{
  "feature_id": "f_place_...",
  "items": [
    {
      "override_id": "ovr-1",
      "source_record_key": "visitkorea:places:1",
      "field_path": "detail.phone",
      "source_value": "051-111-1111",
      "override_value": "051-000-0000",
      "prevent_provider_reactivation": true,
      "status": "active",
      "reason": "운영 검수",
      "created_by": "pinvi-admin",
      "created_at": "2026-06-12T00:10:00+09:00",
    },
  ],
}
```

#### `GET /admin/features/{feature_id}/weather-values`

Query:

| 이름   | 설명                                              |
| ------ | ------------------------------------------------- |
| `asof` | 선택. ISO-8601 기준 시각. 미지정 시 upstream 최신 |

응답 `data`:

```jsonc
{
  "feature_id": "f_weather_...",
  "asof": "2026-06-12T10:00:00+09:00",
  "latest_at": "2026-06-12T09:30:00+09:00",
  "is_stale": false,
  "source_styles": ["nowcast", "short"],
  "items": [
    {
      "metric_key": "T1H",
      "metric_name": "기온",
      "forecast_style": "nowcast",
      "timeline_bucket": "current",
      "valid_at": "2026-06-12T10:00:00+09:00",
      "value_number": 24.5,
      "value_text": null,
      "unit": "℃",
      "severity": "normal",
    },
  ],
}
```

### 8.4 `GET /admin/features/change-requests`

upstream: `kor-travel-map` `GET /v1/admin/features/change-requests`.

권한: `admin` / `operator`

Pinvi는 `ops.feature_change_requests` 또는 `feature.*` 테이블을 직접 조회하지 않는다. 이 endpoint는
`kor-travel-map` Admin HTTP 계약을 proxy해 운영 검수 큐를 보여주며, Web은 Pinvi API만 호출한다.

Query:

| 이름        | 설명                                                             |
| ----------- | ---------------------------------------------------------------- |
| `status`    | 반복 가능. 최신 upstream 계약은 `pending`, `applied`, `rejected` |
| `action`    | 반복 가능. `add`, `update`, `delete`                             |
| `q`         | request id, feature id, reason 등 upstream 검색어                |
| `page_size` | 1~500, 기본 100                                                  |

응답 `data`:

```jsonc
{
  "items": [
    {
      "request_id": "krq_...",
      "feature_id": "f_place_...",
      "action": "add",
      "status": "pending",
      "review_mode": "require_review",
      "payload": { "name": "해운대 카페" },
      "reason": "사용자 제안 승인",
      "requested_by": "pinvi-admin",
      "reviewed_by": null,
      "reviewed_at": null,
      "applied_at": null,
      "created_at": "2026-06-12T00:00:00+09:00",
    },
  ],
  "review_mode": "require_review",
  "page_size": 100,
}
```

### 8.5 `POST /admin/features/change-requests/{request_id}/approve`

upstream: `kor-travel-map`
`POST /v1/admin/features/change-requests/{request_id}/approve`.

권한: `admin`

요청:

```jsonc
{
  "access_reason": "Pinvi 운영 검수 완료",
  "kor_travel_map_reason": "원천 확인 완료",
}
```

- `access_reason`은 Pinvi `admin_audit_log.action = "feature_change_request.approve"`에 남긴다.
- upstream에는 `operator = "pinvi-admin"`과 `reason = kor_travel_map_reason || access_reason`을 전달한다.
- upstream 성공 후에만 Pinvi audit을 commit한다.
- 응답은 `AdminFeatureChangeRequestRecord` 단건이다.

### 8.6 `POST /admin/features/change-requests/{request_id}/reject`

upstream: `kor-travel-map`
`POST /v1/admin/features/change-requests/{request_id}/reject`.

권한: `admin`

요청/응답과 audit 규칙은 approve와 같고, audit action은
`feature_change_request.reject`다.

오류 매핑:

- upstream 404 → `404 RESOURCE_NOT_FOUND`
- upstream 429 → `429 RATE_LIMITED` + `Retry-After` 전달
- upstream 409 `LOCK_BUSY` → `429 RATE_LIMITED` + `Retry-After` 전달
- upstream 409 상태 충돌 → `409 INVALID_STATE` 또는 upstream `code`
- upstream 4xx → `422 VALIDATION_ERROR` 또는 upstream `code`
- upstream timeout/5xx → `503 FEATURE_SERVICE_UNAVAILABLE`
- upstream envelope drift → `502 FEATURE_SERVICE_BAD_GATEWAY`

## 9. POI 관리

POI Admin은 Pinvi 소유 `app.trip_day_pois` 첨부 행만 관리한다. `feature_id`
재연결이나 feature 원천 데이터 수정은 kor-travel-map OpenAPI client 준비 후 별도 작업으로
진행한다.

### 9.1 `GET /admin/pois`

```http
GET /admin/pois?q=haeundae&has_broken_link=false&page=1&limit=50
```

- 권한: `admin` / `operator`
- `q`: `feature_id`, `feature_snapshot` JSON, trip 제목, owner 이메일 부분 일치,
  `attachment_id` / `trip_id` / `owner_user_id` UUID 정확 일치
- `trip_id`: 특정 여행 UUID
- `has_broken_link`: `true`면 `feature_link_broken_at IS NOT NULL`, `false`면 정상
  연결 표시 행만 조회
- 목록 응답은 owner 이메일 원본을 포함하지 않고 `owner_email_masked`만 제공한다.

응답 row:

```jsonc
{
  "attachment_id": "uuid",
  "trip_id": "uuid",
  "trip_title": "부산 가족 여행",
  "owner_user_id": "uuid",
  "owner_email_masked": "o***@example.com",
  "day_index": 1,
  "sort_order": "a0",
  "feature_id": "place-haeundae",
  "feature_label": "해운대 해수욕장",
  "feature_link_broken_at": null,
  "version": 1,
  "created_at": "2026-06-06T10:00:00+09:00",
  "updated_at": "2026-06-06T11:00:00+09:00",
}
```

### 9.2 `GET /admin/pois/{poi_id}`

- 권한: `admin` / `operator`
- 목록 row + `added_by_email_masked`, `feature_snapshot`, marker override, 예정 시각,
  메모, 예산/실사용 금액, 사용자 URL, 최근 `admin_audit_log` 10건을 반환한다.
- owner / added_by 이메일은 항상 마스킹한다.

### 9.3 `POST /admin/pois`

```http
POST /admin/pois
Content-Type: application/json

{
  "trip_id": "uuid",
  "day_index": 1,
  "sort_order": "a0",
  "feature_id": "place-haeundae",
  "feature_snapshot": {
    "name": "해운대 해수욕장",
    "coord": { "lon": 129.1604, "lat": 35.1587 },
    "address_label": "부산 해운대구"
  },
  "custom_marker_color": "P-08",
  "custom_marker_icon": "beach",
  "planned_arrival_at": "2026-07-01T10:00:00+09:00",
  "planned_departure_at": "2026-07-01T11:00:00+09:00",
  "user_note": "운영자 대행 등록",
  "budget_amount": "12000.00",
  "currency": "KRW",
  "user_url": "https://example.com/poi",
  "access_reason": "고객 요청 대행"
}
```

- 권한: `admin`
- Pinvi 소유 `app.trip_day_pois` attachment 행을 생성한다. feature 원천 정규화·저장은
  kor-travel-map 책임이다.
- `day_index`의 `trip_day`가 없으면 기존 사용자 POI 생성 흐름처럼 해당 날짜 row를 생성한다.
- `added_by_user_id`는 작업 admin 사용자로 기록한다.
- snapshot에 지역 코드가 있고 trip의 `primary_region_code`가 비어 있으면
  `primary_region_source = "poi_snapshot"`으로 보정한다.
- `admin_audit_log`에 `action = "poi.create"`를 같은 transaction으로 기록한다.

### 9.4 `PATCH /admin/pois/{poi_id}/link-status`

```http
PATCH /admin/pois/<poi_id>/link-status
Content-Type: application/json

{
  "broken": true,
  "access_reason": "feature_id 점검 결과 끊김"
}
```

- 권한: `admin`
- `access_reason` 필수
- `broken = true`면 `feature_link_broken_at`을 현재 시각으로 설정하고, `false`면
  `NULL`로 되돌린다.
- 실제 값이 바뀐 경우 `trip_day_pois.version`을 1 증가시킨다.
- `admin_audit_log`에 `action = "poi.update_link_status"`를 기록한다.

### 9.5 POI 운영 작업

```http
GET    /admin/pois/<poi_id>/operation-impact
POST   /admin/pois/<poi_id>/copy
POST   /admin/pois/<poi_id>/move
DELETE /admin/pois/<poi_id>
```

- `operation-impact`는 `admin` / `operator`, mutation은 `admin` 전용이다.
- 모든 mutation body는 `access_reason` 필수이며 `admin_audit_log`에 `poi.copy`,
  `poi.move`, `poi.delete`로 기록한다.
- POI orphan은 허용하지 않는다. POI 첨부와 댓글은 POI 문맥이 필요하므로 impact 응답에서
  `orphan` 정책을 `allowed = false`로 반환한다.

POI 복사:

```jsonc
{
  "target_trip_id": "uuid",
  "target_day_index": 2,
  "include_attachments": true,
  "access_reason": "POI 복제",
}
```

- 대상 day가 없으면 생성한다.
- POI row를 새 `attachment_id`로 복제하고, `include_attachments = true`이면 POI 첨부 metadata를
  `source_attachment_id`로 연결해 복제한다. RustFS object는 복제하지 않고 같은 object reference를
  공유한다.

POI 이동:

```jsonc
{
  "target_trip_id": "uuid",
  "target_day_index": 3,
  "attachment_policy": "move",
  "comment_policy": "move",
  "access_reason": "POI 일정 조정",
}
```

- 대상 day가 없으면 생성한다.
- POI의 `trip_id`, `day_index`, `sort_order`, `version`을 갱신한다.
- `attachment_policy` / `comment_policy`는 `move` 또는 `delete`만 허용한다.

POI 삭제:

```jsonc
{
  "attachment_policy": "delete",
  "comment_policy": "delete",
  "access_reason": "복사본 정리",
}
```

- POI는 `deleted_at` soft delete이며, POI 첨부/댓글도 soft delete한다.
- RustFS object는 즉시 삭제하지 않는다.

### 9.6 사용자 feature 제안 검토 큐 (T-179)

사용자 제안(`app.feature_suggestions`, T-177)을 Admin이 검토해 승인/거절한다. 승인 시
kor_travel_map `/v1/admin/features*` change API(전송 client = T-180, `:12701 /v1/admin/*`)로 전달한다.
**Pinvi는 신규 수신 API를 만들지 않고 kor_travel_map 기존 change API를 전송 구간으로 쓴다**
(kor_travel_map ADR-051). `apps/api/app/api/v1/admin/feature_requests.py`.

```
GET    /admin/feature-requests?status=pending&page=&limit=     # admin/operator, 이메일 마스킹, FIFO
POST   /admin/feature-requests/{request_id}/approve            # admin
POST   /admin/feature-requests/{request_id}/reject             # admin
```

- **approve** (`access_reason` 필수 + audit): `suggestion_type`별 분기 —
  - `new_place` → kor_travel_map `POST /v1/admin/features` (`category`(8자리 코드)/`marker_color`/
    `marker_icon`은 사용자 제안에 없어 **Admin이 검토하며 body로 채운다** — 누락 시 422).
  - `correction` → `PATCH /v1/admin/features/{target_feature_id}` (override 일부).
  - `closure` → `DELETE /v1/admin/features/{target_feature_id}` (soft).
  - kor_travel_map 호출을 **먼저** 하고 성공 시에만 commit한다(실패 시 제안 `pending` 유지 → 재시도).
    반환 `feature_id`/`request_id`/state를 `kor_travel_map_ref`에 저장하고 상태를 `applied`면 `added`,
    그 외(require_review 큐 적재)면 `approved`로 둔다. `idempotency_key = request_id`,
    출처 태깅 `operator = pinvi-admin:{admin_id}`(익명, D-11).
- **reject**: kor_travel_map 호출 없이 `status = rejected` + audit.
- **§7 미확정**(kor_travel_map T-217c): review_mode/idempotency/출처태깅/admin인증/closure 합의는 문서화된
  기본값으로 진행하며 확정 시 조정한다.

## 9. API 호출 로그

### 9.1 `GET /admin/api-calls`

```http
GET /admin/api-calls?provider=kma&status_code=200&error_class=Timeout&limit=100
```

- 권한: `admin` / `operator`
- `app.api_call_log`를 `occurred_at DESC, log_id DESC`로 반환한다.
- 필터: `provider`, `status_code`, `error_class`, `limit(1~500)`
- 응답 row: `log_id`, `provider`, `endpoint`, `status_code`, `latency_ms`,
  `error_class`, `error_message`, `request_id`, `occurred_at`
- T-253 기준 production httpx client는 `kor_travel_map`, `kor_travel_map_admin`,
  `kor_travel_geo`, `telegram`, `google_oauth` provider tag를 `ApiCallTracker` event hook에
  부착한다. query `key`/`token`/`secret` 계열 값과 Telegram bot token path는 저장 전에
  `***`로 mask한다.
- T-277 기준 Resend 발송도 `ResendClient` REST 경로로 전환되어
  `api_call_log.provider='resend'`와 canonical endpoint(`https://api.resend.com/emails`)를 남긴다.
  API key는 Authorization header로만 전달되고 `api_call_log.endpoint`에는 저장되지 않는다.

## 9.2 `GET /admin/emails/deliverability`

```http
GET /admin/emails/deliverability
```

- 권한: `admin` / `operator`
- Resend API key configured 여부만 boolean으로 반환한다. key 원문, hint, webhook secret 원문은 노출하지
  않는다.
- `PINVI_RESEND_FROM_EMAIL`에서 `from_domain`을 파싱하고, API key가 있으면 Resend `GET /domains`의
  같은 domain `status` / `capabilities.sending`을 조회한다. `verified`가 아니거나 domain mismatch면
  `status='degraded'`다.
- webhook health는 secret configured/unsigned opt-in, 최근 24시간 `app.resend_webhook_events`
  event count, latest processed time을 반환한다.
- suppression health는 `app.email_suppressions` active/released count와 `users.email_status` count를
  반환한다.
- queue health는 `pending`, `sent`, `delivered`, `delivery_delayed`, `bounced`, `complained`,
  `suppressed`, `failed` count를 반환한다.
- SPF/DKIM/DMARC는 Resend DNS record 세부 상태가 API에서 안정적으로 주어지지 않을 수 있어
  `manual check required` checklist로 표시한다.

## 10. 위치 감사 로그 (CPO 권한)

### 10.1 `GET /admin/audit/location`

```http
GET /admin/audit/location?user_id=<uid>&from=2026-05-01&to=2026-05-31&limit=100
```

- `cpo` 역할만 SELECT
- content_hash chain 자동 검증 — 깨진 row가 있으면 응답 헤더 `X-Chain-Broken: true`
  - Sentry alert
- 응답에는 좌표 정밀도 4자리로 mask (raw 6자리 표시는 별도 endpoint, 더 강한 사유 검증)

## 11. 상태 강등 / 후속 결선

- `/admin/features`: feature read/edit는 `kor-travel-map` admin API 기준으로 결선한다.
  Pinvi가 feature 정규화·저장 책임을 가져오지 않는다.
- `/admin/etl`: Pinvi app-owned Dagster registry와 `kor-travel-map` ops 요약은
  `/admin/etl/summary`로 결선됐다. run-now/cancel mutation은 후속 provider sync Task에서
  reason/audit/idempotency/kill-switch 기준을 확정한 뒤 추가한다.
- `/admin/seed`, `/admin/reset`: dev/staging 전용 안전장치(운영 라우트 미등록, 확인 키워드,
  audit)가 들어갈 때까지 운영 기능으로 취급하지 않는다.

### 11.1 `GET /admin/category-mappings`

upstream: `kor-travel-map` `GET /v1/categories`.

권한: `admin` / `operator`

Pinvi는 category taxonomy를 저장하거나 수정하지 않는다. `kor-travel-map` 카탈로그를
source of truth로 보고, Admin UI는 Pinvi 마커 팔레트 fallback/색상 preview와 drift 확인만 제공한다.

Query:

| 이름             | 설명                                               |
| ---------------- | -------------------------------------------------- |
| `q`              | code, label, path, tier name, maki icon 로컬 필터  |
| `include_counts` | upstream `db_feature_count` 포함 요청. 기본 `true` |
| `active_only`    | active category만 upstream에 요청. 기본 `false`    |

응답 `data`:

```jsonc
{
  "source_of_truth": "kor-travel-map:/v1/categories",
  "mode": "read_only",
  "include_counts": true,
  "active_only": false,
  "total_count": 2,
  "filtered_count": 1,
  "active_count": 1,
  "inactive_count": 0,
  "db_feature_total": 12,
  "items": [
    {
      "code": "01070100",
      "label": "해수욕장",
      "parent_code": "010701",
      "depth": 3,
      "path": ["자연", "해안", "해수욕장"],
      "maki_icon": "swimming",
      "is_active": true,
      "sort_order": 5,
      "tier1_code": "01",
      "tier1_name": "자연",
      "tier2_code": "0107",
      "tier2_name": "해안",
      "tier3_code": "010701",
      "tier3_name": "해수욕",
      "tier4_code": "01070100",
      "tier4_name": "해수욕장",
      "db_active": true,
      "db_feature_count": 12,
    },
  ],
}
```

PUT/import mutation은 제공하지 않는다. Pinvi-owned override 저장소가 필요하다는 제품 결정이
확정되면 별도 ADR/DB migration과 `access_reason`/audit을 포함한 후속 Task로 진행한다.

## 12. Notice Plan 관리

자세히는 [`notice-plans.md`](./notice-plans.md) Admin 섹션.

## 13. ETL / Record Linkage / 데이터 일관성

SPEC V8 M-10 ~ M-11.

### 13.0 `GET /admin/etl/summary`

Pinvi app-owned ETL 정의와 `kor-travel-map` provider ETL 운영 상태를 한 응답으로 합쳐
반환한다. Pinvi는 `feature` / `provider_sync` schema를 직접 조회하지 않고,
`kor-travel-map` `/v1/ops/dagster/summary`, `/v1/ops/metrics`, `/v1/ops/providers`,
`/v1/ops/import-jobs`를 서비스 토큰으로 호출한다. upstream 일부가 실패해도 화면은 열 수 있도록
`kor_travel_map.status = degraded | down`과 `errors[]`로 강등한다.

Pinvi 자체 Dagster는 `PINVI_DAGSTER_BASE_URL`의 `/server_info`와 `/graphql`을 읽어
code location repository/job/asset/schedule, 최근 run 상태를 live snapshot으로 노출한다.
GraphQL 조회가 실패하면 `pinvi.status = degraded`로 강등하되 static registry
(`assets` / `jobs` / `schedules`)와 app-owned outbox/retention summary는 계속 반환한다.

권한: `admin` / `operator`

응답 `data`:

```jsonc
{
  "generated_at": "2026-06-27T00:00:00Z",
  "pinvi": {
    "status": "ok",
    "message": "Dagster server_info/live snapshot 정상",
    "latency_ms": 11,
    "checked_at": "2026-06-27T00:00:00Z",
    "dagster_version": "1.13.11",
    "dagster_webserver_version": "1.13.11",
    "dagster_graphql_version": "1.13.11",
    "repository_count": 1,
    "job_count": 6,
    "asset_count": 5,
    "schedule_count": 5,
    "sensor_count": 0,
    "repositories": [
      {
        "name": "__repository__",
        "location_name": "pinvi.etl.definitions",
        "jobs": [{ "name": "pinvi_email_outbox_job", "is_job": true }],
        "schedules": [
          {
            "name": "pinvi_email_outbox_schedule",
            "job_name": "pinvi_email_outbox_job",
            "cron_schedule": "*/15 * * * *",
            "execution_timezone": "Asia/Seoul",
            "status": "RUNNING",
          },
        ],
        "sensors": [],
        "asset_count": 5,
        "asset_groups": ["pinvi_email", "pinvi_kasi", "pinvi_retention", "pinvi_telegram"],
      },
    ],
    "recent_runs": [
      {
        "run_id": "pinvi-run-1",
        "status": "SUCCESS",
        "job_name": "pinvi_email_outbox_job",
        "start_time": 1781190000,
        "end_time": 1781190010,
        "update_time": 1781190010,
        "tags": {},
      },
    ],
    "assets": [
      { "key": "pinvi_kasi_special_days", "group_name": "pinvi_kasi" },
      { "key": "pinvi_email_outbox", "group_name": "pinvi_email" },
      { "key": "pinvi_telegram_system_outbox", "group_name": "pinvi_telegram" },
      { "key": "pinvi_pii_retention", "group_name": "pinvi_retention" },
      { "key": "pinvi_location_log_archive", "group_name": "pinvi_retention" },
    ],
    "jobs": [
      { "name": "kasi_special_days_job", "trigger": "schedule" },
      { "name": "kasi_poi_rise_set_job", "trigger": "on_demand" },
      { "name": "pinvi_email_outbox_job", "trigger": "schedule" },
      { "name": "pinvi_telegram_system_outbox_job", "trigger": "schedule" },
      { "name": "pinvi_pii_retention_job", "trigger": "schedule" },
      { "name": "pinvi_location_log_archive_job", "trigger": "schedule" },
    ],
    "schedules": [
      {
        "name": "kasi_special_days_schedule",
        "job_name": "kasi_special_days_job",
        "cron_schedule": "30 3 * * *",
        "execution_timezone": "Asia/Seoul",
        "status": "configured",
      },
      {
        "name": "pinvi_email_outbox_schedule",
        "job_name": "pinvi_email_outbox_job",
        "cron_schedule": "*/15 * * * *",
        "execution_timezone": "Asia/Seoul",
        "status": "configured",
      },
      {
        "name": "pinvi_telegram_system_outbox_schedule",
        "job_name": "pinvi_telegram_system_outbox_job",
        "cron_schedule": "*/15 * * * *",
        "execution_timezone": "Asia/Seoul",
        "status": "configured",
      },
      {
        "name": "pinvi_pii_retention_schedule",
        "job_name": "pinvi_pii_retention_job",
        "cron_schedule": "15 4 * * *",
        "execution_timezone": "Asia/Seoul",
        "status": "configured",
      },
      {
        "name": "pinvi_location_log_archive_schedule",
        "job_name": "pinvi_location_log_archive_job",
        "cron_schedule": "30 4 * * *",
        "execution_timezone": "Asia/Seoul",
        "status": "configured",
      },
    ],
    "sensors": [],
    "email_outbox": {
      "total": 4,
      "pending_total": 2,
      "pending_due": 1,
      "pending_backoff": 1,
      "stuck_pending": 1,
      "failed": 1,
      "bounced": 1,
      "complained": 0,
      "retry_exhausted": 1,
      "oldest_pending_scheduled_at": "2026-06-27T23:45:00Z",
      "stuck_threshold_minutes": 15,
      "max_attempts": 5,
      "template_window_hours": 24,
      "template_stats": [
        {
          "template": "verify_email",
          "total": 3,
          "pending": 2,
          "sent": 0,
          "delivered": 0,
          "failed": 1,
          "bounced": 0,
          "complained": 0,
          "failure_count": 1,
          "failure_rate": 0.3333,
        },
      ],
    },
    "telegram_outbox": {
      "total": 5,
      "pending_total": 2,
      "pending_due": 1,
      "pending_backoff": 1,
      "stuck_pending": 1,
      "sent": 1,
      "skipped": 1,
      "failed": 1,
      "retry_exhausted": 1,
      "oldest_pending_scheduled_at": "2026-06-27T23:45:00Z",
      "stuck_threshold_minutes": 15,
      "max_attempts": 5,
      "category_window_hours": 24,
      "category_stats": [
        {
          "category": "trip_created",
          "total": 4,
          "pending": 2,
          "sent": 0,
          "skipped": 1,
          "failed": 1,
          "retry_exhausted": 1,
          "retry_exhausted_rate": 0.25,
        },
      ],
    },
    "pii_retention": {
      "dry_run": true,
      "generated_at": "2026-06-27T00:00:00Z",
      "user_pii_cutoff": "2026-05-28T00:00:00Z",
      "session_cutoff": "2026-05-28T00:00:00Z",
      "location_cutoff": "2025-12-27T00:00:00Z",
      "user_pii_grace_days": 30,
      "session_grace_days": 30,
      "location_retention_months": 6,
      "total_candidates": 10,
      "deleted_user_pii_candidates": 1,
      "deleted_user_oauth_identity_candidates": 1,
      "excluded_privileged_deleted_users": 1,
      "expired_signup_verifications": 1,
      "expired_password_reset_tokens": 1,
      "old_revoked_sessions": 1,
      "old_expired_sessions": 1,
      "expired_oauth_login_states": 1,
      "expired_mobile_oauth_exchanges": 1,
      "location_access_logs_over_retention": 1,
      "admin_audit_pii_over_retention": 1,
    },
    "location_log_archive": {
      "dry_run": true,
      "generated_at": "2026-06-27T00:00:00Z",
      "archive_cutoff": "2025-12-27T00:00:00Z",
      "location_retention_months": 6,
      "total_candidates": 1,
      "oldest_candidate_at": "2025-12-26T00:00:00Z",
      "newest_candidate_at": "2025-12-26T00:00:00Z",
      "archive_tail_log_id": 10,
      "active_head_log_id": 11,
      "active_rows_after_cutoff": 1,
      "chain_bridge_required": true,
      "bridge_anchor_matches": true,
      "pending_outbox_total": 1,
      "pending_outbox_before_cutoff": 0,
      "archive_blocked_by_pending_outbox": false,
      "oldest_pending_outbox_at": "2026-06-26T00:00:00Z",
      "purpose_stats": [{ "purpose": "nearby_attractions", "total": 1 }],
    },
  },
  "kor_travel_map": {
    "status": "ok",
    "dagster_status": "ok",
    "repository_count": 1,
    "job_count": 3,
    "asset_count": 8,
    "schedule_count": 2,
    "sensor_count": 0,
    "run_counts": { "STARTED": 1 },
    "features_total": 42,
    "source_records_total": 77,
    "import_jobs_by_status": { "running": 1 },
    "dedup_queue_by_status": { "pending": 2 },
    "provider_dataset_count": 1,
    "provider_failure_count": 0,
    "recent_import_jobs": [],
    "errors": [],
  },
}
```

### 13.1 `GET /admin/dedup-review`

upstream: `kor-travel-map` `GET /v1/admin/dedup-reviews`.

권한: `admin` / `operator`

Query:

| 이름          | 설명                                                                  |
| ------------- | --------------------------------------------------------------------- |
| `status`      | 반복 가능. `pending` / `accepted` / `rejected` / `merged` / `ignored` |
| `provider`    | 반복 가능 provider filter                                             |
| `dataset_key` | 반복 가능 dataset key filter                                          |
| `kind`        | 반복 가능 feature kind                                                |
| `category`    | 반복 가능 category filter                                             |
| `min_score`   | 0~100                                                                 |
| `max_score`   | 0~100                                                                 |
| `q`           | feature 이름/provider/source 검색어                                   |
| `page_size`   | 1~500, 기본 50                                                        |
| `cursor`      | upstream cursor                                                       |

응답 `data`:

```jsonc
{
  "items": [
    {
      "review_id": "review-1",
      "status": "pending",
      "total_score": 91.4,
      "name_score": 94,
      "spatial_score": 88,
      "category_score": 92,
      "distance_m": 32.7,
      "feature_a": {
        "feature_id": "feature-a",
        "name": "서울타워",
        "kind": "place",
        "category": "tourism",
        "lon": 126.9882,
        "lat": 37.5512,
        "provider": "visitkorea",
        "dataset_key": "attractions",
      },
      "feature_b": {
        "feature_id": "feature-b",
        "name": "남산서울타워",
        "kind": "place",
        "category": "tourism",
        "lon": 126.9881,
        "lat": 37.5513,
        "provider": "kma",
        "dataset_key": "poi_weather",
      },
      "decision_reason": null,
      "reviewed_at": null,
      "reviewed_by": null,
      "created_at": "2026-06-12T00:00:00+09:00",
    },
  ],
  "page_size": 50,
  "next_cursor": null,
}
```

### 13.2 `POST /admin/dedup-review/{review_id}/verdict`

upstream: `kor-travel-map` `PATCH /v1/admin/dedup-reviews/{review_id}`.

권한: `admin`

요청:

```jsonc
{
  "decision": "merged",
  "access_reason": "운영자가 확인한 중복 후보 병합",
  "kor_travel_map_reason": "동일 장소 확인",
  "master_feature_id": "feature-a",
}
```

| 이름                    | 설명                                                      |
| ----------------------- | --------------------------------------------------------- |
| `decision`              | `accepted` / `rejected` / `merged` / `ignored`            |
| `access_reason`         | Pinvi `admin_audit_log`에 남길 운영 사유. 필수, 1~500자   |
| `kor_travel_map_reason` | upstream decision reason. 생략하면 `access_reason`을 전달 |
| `master_feature_id`     | `decision=merged`일 때 필수. survivor feature id          |

응답 `data`:

```jsonc
{
  "review_id": "review-1",
  "decision": "merged",
  "changed": true,
  "master_feature_id": "feature-a",
  "loser_feature_id": "feature-b",
  "merge_id": "merge-1",
  "source_links_moved": 2,
  "source_links_dropped": 0,
}
```

성공 시 Pinvi는 같은 transaction에서 `admin_audit_log`에 `dedup_review.decide`를 기록한다.
`X-Request-Id`가 UUID이면 audit `request_id`로 보존하고, 없으면 새 UUID를 생성한다.
잘못된 UUID는 422로 거절한다. upstream 404는 `RESOURCE_NOT_FOUND`, 409는 upstream `code`
또는 `INVALID_STATE`로 보존한다.

### 13.3 `GET /admin/provider-sync`

upstream: `kor-travel-map` `GET /v1/ops/providers`.

권한: `admin` / `operator`

Query:

| 이름  | 설명                             |
| ----- | -------------------------------- |
| `key` | provider 또는 dataset key 검색어 |

응답 `data`:

```jsonc
{
  "data": {
    "items": [
      {
        "provider": "kma",
        "dataset_key": "special_days",
        "sync_scope": "daily",
        "status": "healthy",
        "last_success_at": "2026-06-12T00:00:00+09:00",
        "last_failure_at": null,
        "consecutive_failures": 0,
        "next_run_after": "2026-06-13T03:30:00+09:00",
        "links": [],
        "refresh_policy": { "enabled": true },
      },
    ],
    "total": 1,
  },
}
```

### 13.4 `GET /admin/provider-sync/import-jobs`

upstream: `kor-travel-map` `GET /v1/ops/import-jobs`.

권한: `admin` / `operator`

Query:

| 이름            | 설명                                                   |
| --------------- | ------------------------------------------------------ |
| `status`        | `queued` / `running` / `done` / `failed` / `cancelled` |
| `kind`          | upstream import job kind                               |
| `load_batch_id` | load batch UUID                                        |
| `parent_job_id` | parent job UUID                                        |
| `page_size`     | 1~200, 기본 50                                         |
| `cursor`        | upstream cursor                                        |

응답 `data`:

```jsonc
{
  "items": [
    {
      "job_id": "uuid",
      "kind": "provider_import",
      "status": "running",
      "progress": 0.5,
      "payload": {},
      "current_stage": "normalize",
      "error_message": null,
      "created_at": "2026-06-12T00:00:00+09:00",
      "started_at": "2026-06-12T00:01:00+09:00",
      "heartbeat_at": "2026-06-12T00:02:00+09:00",
      "finished_at": null,
      "links": [],
    },
  ],
  "page_size": 50,
  "next_cursor": null,
}
```

### 13.4.1 `POST /admin/provider-sync/import-jobs/{job_id}/cancel`

upstream: `kor-travel-map` `POST /v1/ops/import-jobs/{job_id}/cancel`.

권한: `admin` 전용. `operator`는 조회만 가능하다.

요청 body:

| 이름                    | 설명                                           |
| ----------------------- | ---------------------------------------------- |
| `access_reason`         | Pinvi `admin_audit_log`에 남기는 운영 사유     |
| `kor_travel_map_reason` | upstream cancel reason. 없으면 `access_reason` |

응답 `data`는 취소 후 upstream import job record다. Pinvi는 성공한 cancel만
`provider_import_job.cancel` audit으로 기록하고, upstream 404/409/503은 각각
`RESOURCE_NOT_FOUND` / upstream code 또는 `INVALID_STATE` / `FEATURE_SERVICE_UNAVAILABLE`로
전달한다.

provider run-now/pause/resume/reset cursor mutation은 아직 노출하지 않는다. 2026-06-28 기준
upstream `kor-travel-map` OpenAPI에는 import job cancel과 feature-update-request `run-now`만 있고,
provider 자체 pause/resume 계약은 없다. Pinvi-owned override mutation은 별도 ADR 또는 upstream
계약 전까지 추가하지 않는다.

### 13.5 `GET /admin/integrity/issues`

Pinvi app-owned issue와 upstream `kor-travel-map` consistency issue를 같은 목록
contract로 반환한다. `source=kor_travel_map` 행은 upstream
`GET /v1/ops/consistency/issues`에서 오고, `source=pinvi_app` 행은
`app.data_integrity_violations`와 Pinvi가 계산한 known app integrity rule에서 온다.

권한: `admin` / `operator`

Query:

| 이름             | 설명                                                                |
| ---------------- | ------------------------------------------------------------------- |
| `source`         | `all` / `kor_travel_map` / `pinvi_app`, 기본 `all`                  |
| `status`         | `open` / `acknowledged` / `resolved` / `ignored`, 기본 `open`       |
| `severity`       | `info` / `warning` / `error` / `critical`                           |
| `violation_type` | violation type 또는 Pinvi `rule_key`                                |
| `provider`       | `kor_travel_map` 전용 provider filter. 지정 시 Pinvi app row는 제외 |
| `dataset_key`    | `kor_travel_map` 전용 dataset filter. 지정 시 Pinvi app row는 제외  |
| `feature_id`     | feature id                                                          |
| `page_size`      | 1~200, 기본 50                                                      |
| `cursor`         | upstream cursor. cursor가 있으면 Pinvi app row는 반복하지 않는다.   |

응답 `data.items[]`는 `issue_id`, `source`, `violation_type`, `severity`, `message`, `payload`,
`status`, `detected_at`, `provider`, `dataset_key`, `feature_id`, `source_record_key`,
`resolved_at`을 포함한다.

Pinvi app source의 계산 rule:

| `violation_type`                    | 설명                                                        |
| ----------------------------------- | ----------------------------------------------------------- |
| `broken_poi_feature_link`           | `trip_day_pois.feature_link_broken_at`이 남은 활성 여행 POI |
| `trip_day_poi_sort_order_duplicate` | 활성 여행 날짜 안의 `sort_order` 중복                       |
| `invalid_trip_day_poi_marker_color` | `P-01`~`P-16` 범위를 벗어난 POI marker color                |
| `curated_import_source_drift`       | curated plan과 curated POI의 원본 curated feature id 불일치 |
| `active_attachment_deleted_target`  | 활성 첨부가 soft-delete된 trip/POI/curated 대상에 연결      |

### 13.6 `GET /admin/integrity/reports`

upstream: `kor-travel-map` `GET /v1/ops/consistency/reports`.

권한: `admin` / `operator`

Query:

| 이름           | 설명                    |
| -------------- | ----------------------- |
| `severity_max` | `OK` / `WARN` / `ERROR` |
| `page_size`    | 1~200, 기본 50          |
| `cursor`       | upstream cursor         |

응답 `data.items[]`는 `report_id`, `batch_id`, `started_at`, `finished_at`, `severity_max`,
`cases`, `summary`를 포함한다.

### 13.7 `POST /admin/integrity/issues/{issue_id}/action`

`source=kor_travel_map` issue만 상태 조치 relay를 지원한다. `admin` 전용이며
`access_reason`은 필수다. Pinvi는 upstream 성공 후 `integrity_issue.action` audit을 기록한다.
`pinvi_app:` issue id는 현재 read-only이며 409
`PINVI_APP_INTEGRITY_ACTION_UNSUPPORTED`를 반환한다. Pinvi app-owned resolve/fix workflow는
후속 ADR 또는 별도 task에서 lock/idempotency/fix 정책과 함께 설계한다.

## 14. 디버그 콘솔

### 14.1 `GET /admin/debug/logs/system`

upstream: `kor-travel-map` `GET /v1/ops/system-logs`.

권한: `admin` / `operator`

Query:

| 이름         | 설명                                                |
| ------------ | --------------------------------------------------- |
| `level`      | `debug` / `info` / `warning` / `error` / `critical` |
| `source`     | sanitized log source                                |
| `q`          | message/event 검색어                                |
| `request_id` | upstream request id 문자열                          |
| `page_size`  | 1~200, 기본 50                                      |
| `cursor`     | upstream cursor                                     |

응답 `data.items[]`는 `log_id`, `level`, `source`, `event`, `message`, `detail`,
`request_id`, `created_at`을 포함한다. raw secret, Authorization header, 운영 도메인/IP는
upstream sanitization 이후 값만 표시한다.

### 14.2 `GET /admin/debug/logs/api-calls`

upstream: `kor-travel-map` `GET /v1/ops/api-call-logs`.

권한: `admin` / `operator`

Query:

| 이름         | 설명                       |
| ------------ | -------------------------- |
| `method`     | HTTP method                |
| `min_status` | 100~599                    |
| `path`       | path prefix/search         |
| `request_id` | upstream request id 문자열 |
| `page_size`  | 1~200, 기본 50             |
| `cursor`     | upstream cursor            |

응답 `data.items[]`는 `log_id`, `method`, `path`, `status_code`, `duration_ms`,
`request_id`, `error_code`, `created_at`을 포함한다.

### 14.3 `GET /admin/debug/logs/stream/status`

v0.2.0 Admin debug live mode를 반환한다. Sprint 5에서는 Loki/Promtail을 필수 운영 구성으로
올리지 않고, N150 부담을 줄이기 위해 기존 `kor-travel-map` sanitized system/API log endpoint를
짧은 interval로 polling하는 fallback을 선택한다. raw stdout/stderr stream이나 LogQL endpoint는
노출하지 않는다.

권한: `admin` / `operator`

응답 200:

```jsonc
{
  "data": {
    "mode": "polling",
    "status": "ok",
    "poll_interval_ms": 5000,
    "sources": ["kor_travel_map_system_logs", "kor_travel_map_api_call_logs"],
    "loki_enabled": false,
    "sse_enabled": false,
    "message": "sanitized polling fallback",
  },
}
```

UI는 이 값을 기준으로 `/admin/debug/logs/system`과 `/admin/debug/logs/api-calls`를 재조회한다.
Live toggle은 polling을 켜고, pause/resume은 polling interval만 멈추거나 재개한다. 필터(`level`,
`source`, `q`, `method`, `min_status`, `path`, `request_id`)는 기존 endpoint query 그대로 유지한다.

Loki/Promtail/LogQL WebSocket stream은 운영 용량과 retention 정책이 확정된 뒤 별도 PR에서
추가한다.

### 14.4 `GET /admin/debug/request/{request_id}`

Pinvi `X-Request-Id` UUID 중심 timeline을 반환한다. `kor-travel-map` system/API logs는
같은 request id로 필터한 보조 event source로만 붙이며, Pinvi timeline의 source of truth로
섞지 않는다.

Pinvi admin client는 현재 요청의 `X-Request-Id`를 `kor-travel-map` admin/ops HTTP 호출에도
전달한다. 따라서 `/admin/debug/logs`에서 발생한 read-only upstream 조회도 같은 request id로
`/admin/debug/request/{request_id}`에서 추적할 수 있다.

권한: `admin` / `operator`

응답 200:

```jsonc
{
  "data": {
    "request_id": "11111111-2222-4333-8444-555555555555",
    "generated_at": "2026-06-28T04:30:00Z",
    "status": "ok", // ok | partial
    "started_at": "2026-06-28T04:29:59Z",
    "finished_at": "2026-06-28T04:30:00Z",
    "duration_ms": 1000,
    "sources": [
      { "source": "pinvi_api_call_log", "status": "ok", "event_count": 1, "message": null },
      { "source": "kor_travel_map_system_logs", "status": "ok", "event_count": 1, "message": null },
    ],
    "events": [
      {
        "event_id": "pinvi_api_call:1",
        "occurred_at": "2026-06-28T04:29:59Z",
        "source": "pinvi_api_call_log",
        "title": "kor_travel_map API call",
        "status": "503",
        "duration_ms": 321,
        "error_code": "UPSTREAM_TIMEOUT",
        "detail": {
          "provider": "kor_travel_map",
          "endpoint": "/v1/features?token=%5Bmasked%5D",
          "has_error_message": true,
        },
      },
    ],
  },
}
```

로컬 source:

- `app.api_call_log` — provider, path-only endpoint, status, latency, error class.
- `app.admin_audit_log` — action/resource와 before/after 존재 여부만. `access_reason` 원문과
  before/after payload는 반환하지 않는다.
- `app.location_access_log` / `app.location_audit_outbox` — endpoint path와 purpose만.
  user id, 좌표, IP hash는 반환하지 않는다.
- `app.email_queue` — `payload.request_id`가 같은 경우 template/status/attempts만.
  수신자, 제목, payload, `last_error` 원문은 반환하지 않는다.

오류:

- invalid UUID path → 422 `VALIDATION_ERROR`
- 모든 source가 정상이고 event가 없으면 404 `RESOURCE_NOT_FOUND`
- upstream 보조 source 조회 실패는 HTTP 200 `data.status="partial"`과 source
  `status="degraded"`로 반환한다.

Loki LogQL WebSocket stream은 T-245에서 polling fallback으로 닫고, 실제 Loki 도입은 운영 선택
계층으로 남긴다.

## 15. Backup / Restore

ADR-022 범위. 본 API는 Pinvi 소유 `app` schema backup snapshot과 동일 DB
schema-swap restore만 다룬다. `feature` / `provider_sync` schema는
`kor-travel-map` 책임이다.

### 15.1 `GET /admin/backup/snapshots`

```http
GET /admin/backup/snapshots?limit=50
```

- 권한: `admin` / `operator` / `cpo`
- 저장 위치: `PINVI_BACKUP_DIR`의 `*.dump`
- `.sha256` 파일이 있고 실제 dump checksum과 일치하면 `status="verified"`, 없거나 불일치하면
  `status="available"`
- 응답의 `path`는 host 절대경로를 노출하지 않고 `backup://<filename>` 형식으로 mask한다.

응답 200:

```jsonc
{
  "data": [
    {
      "snapshot_id": "pinvi-app-20260606-003000",
      "filename": "pinvi-app-20260606-003000.dump",
      "path": "backup://pinvi-app-20260606-003000.dump",
      "size_bytes": 2097152,
      "checksum_sha256": "b...",
      "status": "verified",
      "created_at": "2026-06-06T00:30:00Z",
    },
  ],
}
```

### 15.2 `POST /admin/backup/snapshot`

```http
POST /admin/backup/snapshot
Content-Type: application/json

{ "access_reason": "배포 전 수동 snapshot" }
```

- 권한: `admin`
- 동작: `PINVI_BACKUP_SCRIPT_PATH`를 subprocess로 실행하고 `BACKUP_FILE=...`
  출력 또는 새 dump 파일을 snapshot으로 인식한다. 실행 전 `PINVI_BACKUP_MIN_FREE_BYTES`
  disk guard를 확인하고, script는 custom dump 생성 후 sha256 sidecar를 검증한다.
- 신규 `.sha256` sidecar는 dump basename 기준으로 생성한다. restore 계열 스크립트는 sidecar의
  첫 checksum 값과 실제 dump hash를 직접 비교하므로 운영 snapshot을 staging 디렉터리로
  옮겨도 dump와 sidecar를 함께 두면 검증할 수 있다.
- audit: 성공 시 `app.admin_audit_log`에 `action="backup.snapshot"`, 실패 시
  `action="backup.snapshot_failed"`를 기록한다. audit/error message는 DB URL credential과
  host 절대경로를 mask한다.
- 실패: `503 SERVICE_UNAVAILABLE`, `error.code="BACKUP_FAILED"` 또는
  `BACKUP_DISK_GUARD_FAILED`

응답 201: `GET /admin/backup/snapshots` 항목과 동일한 snapshot 객체.

### 15.3 `POST /admin/backup/restore-hotswap`

```http
POST /admin/backup/restore-hotswap
Content-Type: application/json

{
  "snapshot_id": "pinvi-app-20260606-003000",
  "access_reason": "운영 복구 훈련",
  "confirm_schema_swap": true
}
```

- 권한: `admin`
- 동작: `PINVI_RESTORE_HOTSWAP_SCRIPT_PATH`를 subprocess로 실행한다.
  기본 스크립트는 `PINVI_RESTORE_HOTSWAP_EXECUTE=1` 가드 뒤에서 custom dump를
  `app_restore_<ts>`로 remap restore하고, 검증 후 `app` → `app_previous_<ts>`,
  `app_restore_<ts>` → `app` schema rename을 수행한다.
- `PINVI_RESTORE_DRAIN_COMMAND`가 있으면 switch 전 write drain 단계에서 실행한다.
  없으면 `PINVI_RESTORE_ALLOW_NO_DRAIN=1`일 때만 drain을 skip할 수 있다.
- Web `/admin/backup`의 Restore 버튼은
  `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=1`로 빌드된 staging/운영 검증 이미지에서만
  활성화된다. production 기본값은 `0`이며, API endpoint의 서버 측 실행 가드는 별도로 유지한다.
- audit: 성공 시 `action="backup.restore_hotswap"`, 실패 시
  `action="backup.restore_hotswap_failed"` 기록
- 실패: snapshot 없음 `404 BACKUP_SNAPSHOT_NOT_FOUND`, 스크립트 실패
  `503 BACKUP_FAILED`, `confirm_schema_swap=false`는 `422 VALIDATION_ERROR`

응답 200:

```jsonc
{
  "data": {
    "restore_id": "20260608093000",
    "snapshot_id": "pinvi-app-20260606-003000",
    "snapshot_path": "backup://pinvi-app-20260606-003000.dump",
    "restore_schema": "app_restore_20260608093000",
    "previous_schema": "app_previous_20260608093000",
    "status": "succeeded",
    "phases": [
      { "name": "preparing", "status": "success", "message": "snapshot verified" },
      { "name": "restoring", "status": "success", "message": "restored" },
      { "name": "validating", "status": "success", "message": "validated" },
      { "name": "draining", "status": "success", "message": "drained" },
      { "name": "switching", "status": "success", "message": "schema-swap completed" },
    ],
    "started_at": "2026-06-08T09:30:00Z",
    "completed_at": "2026-06-08T09:31:00Z",
  },
}
```

단순 restore와 Sprint 5 staging drill은 API가 아니라 `scripts/restore-db.sh`,
`scripts/restore-staging-drill.sh`와
[`docs/runbooks/backup-restore.md`](../runbooks/backup-restore.md) 절차로 수행한다.

## 16. MCP 토큰 관리 (ADR-019, Sprint 6)

### 16.1 `GET /admin/mcp-tokens`

```http
GET /admin/mcp-tokens?user_id=<uuid>&status=active&q=Claude
```

- 권한: `admin` / `operator` / `cpo`
- `status`: `active` | `expired` | `revoked`
- 응답은 토큰 원문 없이 마스킹 값과 metadata만 반환한다.

### 16.2 `POST /admin/mcp-tokens`

```jsonc
{
  "user_id": "uuid",
  "name": "사용자 대리 발급",
  "expires_at": "2026-07-07T00:00:00Z",
  "access_reason": "고객 지원 요청",
}
```

- 권한: `admin`
- `scopes`는 1차 구현에서 `["mcp:read"]`만 허용한다.
- `app.admin_audit_log`에 `action="mcp_token.issue"` 기록.
- 응답은 발급 직후 1회만 `token` 원문을 포함한다.

### 16.3 `POST /admin/mcp-tokens/{token_id}/revoke`

```jsonc
{ "access_reason": "토큰 유출 의심" }
```

- 권한: `admin`
- `revoked_at = now()` 설정.
- `app.admin_audit_log`에 `action="mcp_token.revoke"` 기록.

## 17. Seed / Reset (dev/staging only)

### 17.1 `GET /admin/seed/scenarios`

권한: `admin`

운영 환경에서는 router를 include하지 않으며, 방어적으로 endpoint guard도 404만 반환한다.
dev/staging에서는 dry-run 전용 scenario catalog를 반환한다. 실제 seed 실행은 아직 제공하지 않는다.

응답 `data`:

```jsonc
{
  "environment": "development",
  "enabled": false,
  "mode": "dry_run_only",
  "scenarios": [
    {
      "key": "new_user_first_trip",
      "title": "새 사용자와 첫 여행",
      "description": "가입 직후 첫 여행, day, POI, 공유 토큰 후보를 준비한다.",
      "destructive": false,
      "confirm_phrase": "RUN new_user_first_trip",
      "steps": ["사용자 샘플 확인", "여행/day/POI 생성 계획"],
    },
  ],
}
```

### 17.2 `POST /admin/seed/scenarios/{scenario_key}`

`scenario_key`: SPEC V8 M-13 8 시나리오 키 (`new_user_first_trip` 등).

요청:

```jsonc
{
  "confirm": "RUN new_user_first_trip",
  "access_reason": "개발 smoke dry-run",
  "dry_run": true,
}
```

- 권한: `admin`
- `dry_run=true`만 지원한다. `false`는 `422 DRY_RUN_ONLY`.
- `confirm`은 scenario별 `confirm_phrase`와 정확히 일치해야 한다.
- 성공 시 `admin_audit_log`에 `dev_seed.dry_run`을 기록한다.

응답 202:

```jsonc
{
  "data": {
    "action": "dev_seed.dry_run",
    "target": "new_user_first_trip",
    "status": "dry_run",
    "dry_run": true,
    "audit_log_id": 101,
    "would_execute": ["사용자 샘플 확인", "여행/day/POI 생성 계획"],
    "message": "seed scenario dry-run을 기록했습니다.",
  },
}
```

### 17.3 `GET /admin/reset/status`

권한: `admin`

운영 환경에서는 router를 include하지 않으며, endpoint guard도 404만 반환한다.

응답 `data`:

```jsonc
{
  "environment": "development",
  "enabled": false,
  "mode": "dry_run_only",
  "confirm_phrase": "RESET",
  "target_schemas": ["app"],
}
```

### 17.4 `POST /admin/reset`

```jsonc
{
  "confirm": "RESET",
  "access_reason": "reset 절차 리허설",
  "dry_run": true,
  "include_seed": false,
}
```

- 권한: `admin`
- dev/staging에서만 router 등록. 운영은 404.
- `dry_run=true`만 지원한다. `false`는 `422 DRY_RUN_ONLY`.
- `confirm`은 `RESET`과 정확히 일치해야 한다.
- 성공 시 `admin_audit_log`에 `dev_reset.dry_run`을 기록한다.
- 실제 DB reset(`alembic downgrade base` → `upgrade head`)과 seed 적용은 이번 T-214 범위가 아니다.
  실행 모드 도입 시 별도 환경 kill-switch, admin 재인증, backup snapshot 확인, audit을 먼저 고정한다.

## 18. AI agent 구현 체크리스트

- [ ] `apps/api/app/api/v1/admin/__init__.py` 라우터 분기
- [ ] `apps/api/app/api/v1/admin/{users,trips,features,pois,datasets,entities,audit,etl,dedup,integrity,debug,backup,seed,reset,rustfs}.py`
- [ ] `apps/api/app/services/admin/{entity_browser,entity_crud,audit_chain,seed_scenarios,reset}.py`
- [ ] `apps/api/app/middleware/admin_audit.py` (chain prev_hash + content_hash)
- [ ] `apps/api/app/core/rbac.py` (`roles` 검사 + 404 변환)
- [ ] 통합 테스트 + RBAC 거부 e2e + chain 검증
- [ ] 운영 환경 `ENABLE_SEED=false` 시 seed/reset 라우트 404 확인
