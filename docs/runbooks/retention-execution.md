# Retention 실행 Runbook

## 1. 목적

`/admin/retention`으로 PII 보존기간 정리와 위치 접근 로그 archive/delete를 운영자가 실행할 때의
사전 점검, 실행, 검증 절차다. T-240/T-241 Dagster job은 후보를 dry-run으로 집계하고, 실제
파괴 작업은 이 runbook과 Admin API의 kill-switch를 통과할 때만 수행한다.

## 2. 사전 조건

- 대상 환경은 명시가 없으면 dev/staging이다. prod 작업은 `docs/deploy-runbook.local.md`를 먼저
  읽고, 실제 도메인·호스트·접속 정보는 tracked 문서에 남기지 않는다.
- 최신 Alembic head가 적용되어 `app.retention_runs`와
  `app.location_access_log_archive`가 있어야 한다.
- `/admin/etl` 또는 `/admin/retention`에서 `location_audit_outbox` cutoff 이전 pending row와
  hash-chain bridge mismatch가 없는지 확인한다.
- 실행자는 `admin` 또는 `cpo` role이어야 하며, 실행 사유를 남긴다.

## 3. Dry-run 확인

Admin UI:

1. `/admin/retention`으로 이동한다.
2. `PII`, `위치 로그 archive`, `실행 이력`을 확인한다.
3. `Dry-run` scope와 사유를 입력하고 dry-run을 기록한다.

API:

```bash
curl -sS -X POST "$PINVI_API_ORIGIN/admin/retention/dry-run" \
  -H "Content-Type: application/json" \
  -H "Cookie: pinvi_access=<admin-cookie>" \
  --data '{"scope":"all","access_reason":"보존기간 후보 점검"}'
```

## 4. Execute

기본값은 비활성이다.

```bash
PINVI_RETENTION_EXECUTE_ENABLED=false
PINVI_RETENTION_EXECUTE_CONFIRM_PHRASE="EXECUTE RETENTION"
```

실행을 열 때는 배포 환경 변수에서 `PINVI_RETENTION_EXECUTE_ENABLED=true`를 설정한 뒤 API를
재기동한다. 실행 후에는 즉시 다시 `false`로 내린다.

```bash
curl -sS -X POST "$PINVI_API_ORIGIN/admin/retention/execute" \
  -H "Content-Type: application/json" \
  -H "Cookie: pinvi_access=<admin-cookie>" \
  --data '{
    "scope":"all",
    "access_reason":"보존기간 만료 데이터 정리",
    "confirm_phrase":"EXECUTE RETENTION"
  }'
```

## 5. 검증

```sql
SELECT run_id, mode, scope, status, result, created_at, completed_at
FROM app.retention_runs
ORDER BY created_at DESC
LIMIT 5;
```

```sql
SELECT count(*) AS archived_rows
FROM app.location_access_log_archive;
```

```sql
SELECT count(*) AS old_active_location_rows
FROM app.location_access_log
WHERE occurred_at <= now() - interval '6 months';
```

```sql
SELECT action, resource_type, resource_id, occurred_at
FROM app.admin_audit_log
WHERE action IN ('retention.dry_run', 'retention.execute')
ORDER BY log_id DESC
LIMIT 5;
```

성공 기준:

- 최신 `retention_runs.status = 'completed'`.
- `result.pii`에 익명화/삭제 count가 남는다.
- `result.location.archived_rows`와 `deleted_active_rows`가 기대 범위다.
- `location_access_log_archive`에 archive row가 있고, active table의 6개월 초과 row가 줄었다.
- `admin_audit_log`에 `retention.execute`가 같은 실행 사유로 남는다.

## 6. 중지 기준

- `RETENTION_PRECHECK_FAILED`: cutoff 이전 pending outbox 또는 chain bridge mismatch를 먼저 해결한다.
- `RETENTION_KILL_SWITCH_DISABLED`: 환경변수와 재기동 상태를 확인한다.
- `RETENTION_CONFIRM_PHRASE_INVALID`: 요청 body의 confirm phrase를 확인한다.
- execute 중 DB 오류가 발생하면 추가 실행을 멈추고 `retention_runs`, API 로그, DB 트랜잭션 상태를
  확인한다. 운영 incident 가능성이 있으면 `docs/runbooks/security-incidents.md`로 전환한다.

## 7. 참고

- `docs/api/admin.md` §2.2
- `docs/compliance/lbs-act.md` §3.4
- `docs/architecture/user-location.md` §7
- `docs/execplan/retention-execution-dashboard.md`
