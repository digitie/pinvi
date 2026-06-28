# Retention Execution / Dashboard 실행 계획

## 목적

T-240/T-241의 dry-run retention 집계를 운영자가 승인·실행·감사할 수 있는
`/admin/retention` 표면으로 확장한다. 실행은 기본 비활성 kill-switch 뒤에 두고,
모든 batch는 candidate snapshot, before/after count, evidence summary, audit log를 남긴다.

## 이번 구현 범위

- `app.retention_runs`: dry-run/execute batch, 상태, scope, candidate snapshot, result,
  access_reason, actor, error, 시작/완료 시각을 저장한다.
- `app.location_access_log_archive`: 6개월 초과 위치 접근 로그를 active table에서 삭제하기 전
  동일 payload와 retention run id로 복사한다.
- `app.audit_log_append_only()`는 `location_access_log`에 한해
  `set_config('app.retention_location_delete_allowed', 'on', true)`가 설정된 transaction에서만
  delete를 허용한다. `admin_audit_log` update/delete 차단은 그대로 유지한다.
- API:
  - `GET /admin/retention/summary`
  - `POST /admin/retention/dry-run`
  - `POST /admin/retention/execute`
  - `GET /admin/retention/runs`
- Web Admin `/admin/retention`: kill-switch 상태, dry-run 후보, 최신 run/evidence,
  confirm phrase 기반 execute form을 표시한다.

## 실행 정책

- 기본 kill-switch는 `PINVI_RETENTION_EXECUTE_ENABLED=false`다.
- execute는 `admin` 또는 `cpo`만 가능하며 `access_reason`과 confirm phrase
  `EXECUTE RETENTION`을 요구한다.
- cleanup 실행:
  - 만료 `user_email_verifications`, 오래된 `user_sessions`, 만료 OAuth transient rows 삭제
  - 삭제 후 grace가 지난 일반 사용자 PII anonymize 및 OAuth identity 삭제
  - 6개월 초과 `location_access_log` row를 archive table에 복사 후 active table에서 삭제
- `location_audit_outbox` 미처리 row가 cutoff 이전에 있거나 chain bridge가 불일치하면
  location archive/delete를 실행하지 않고 batch를 실패 처리한다.
- `admin_audit_log` PII 후보는 append-only 감사 원장의 법정/감사 성격 때문에 이번 PR에서 삭제하지
  않고 result의 `skipped_admin_audit_pii_over_retention`으로 기록한다.

## 검증

- API integration: kill-switch 차단, dry-run run 생성, execute cleanup/anonymize/archive,
  pending outbox blocker, audit log action — `tests/integration/test_admin_retention_api.py` 3 passed.
- Web mock e2e: dashboard render, dry-run, kill-switch disabled execute guard —
  `admin-retention.e2e.ts` Windows fallback Chromium 1 passed (N150 SSH alias 연결 불가).
- DB migration upgrade smoke: integration testcontainer의 Alembic head 적용으로 확인.
- Lint/type: ruff check/format, strict mypy, schemas/api-client/web typecheck, Web lint 통과.
