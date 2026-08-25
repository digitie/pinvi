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
SELECT run_id, mode, scope, status, result, error_message, created_at, completed_at
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
WHERE action IN ('retention.dry_run', 'retention.execute', 'retention.execute_failed')
ORDER BY log_id DESC
LIMIT 5;
```

성공 기준:

- 최신 `retention_runs.status = 'completed'`.
- `result.pii`에 익명화/삭제 count가 남는다.
- `result.location.archived_rows`와 `deleted_active_rows`가 기대 범위다.
- `location_access_log_archive`에 archive row가 있고, active table의 6개월 초과 row가 줄었다.
- `admin_audit_log`에 `retention.execute`가 같은 실행 사유로 남는다.

### 5.1 `status`가 뜻하는 것

| 값 | 뜻 |
| --- | --- |
| `dry_run` | dry-run 실행. 파괴적 작업을 하지 않는다. |
| `completed` | 전부 커밋됐다. **요청한 `scope`의** 삭제·익명화·아카이브가 실제로 일어났다(`scope='pii'`는 아카이브를 하지 않고 `scope='location'`은 익명화를 하지 않는다). |
| `failed` | **아무것도 지워지지 않았다.** 시도했고 실패했으며 전부 폐기됐다. |
| `executing` | **아직 커밋되지 않았다 = 아무것도 지워지지 않았다.** 진행 중이거나, 프로세스가 죽었거나, 실패했는데 복구 기록 자체가 실패했다. |
| `rolled_back` | 운영자가 §5.2 절차로 수동 종결한 stale run. 시스템이 스스로 쓰지 않는다. |
| `approved` | CHECK 제약에는 있으나 **현재 코드가 쓰지 않는다.** |

근거: 파괴 SQL·`completed` UPDATE·admin audit 적재가 라우트의 **단일 커밋**에 묶여 있다. 영수증
행만 그 앞에서 따로 커밋되므로(T-338), 영수증이 남아 있다고 해서 작업이 수행된 것은 아니다.

**상태만으로는 "진행 중"과 "죽음"을 구분할 수 없다.** 그 판정은 §5.2다.

**API가 503을 반환했다고 해서 미삭제인 것은 아니다.** 최종 커밋이 서버에서는 성공했는데 응답
ack가 유실되면 클라이언트는 503을 받지만 DB의 영수증은 `completed`이고 작업은 실제로 수행됐다.
그 경우 서버 로그에 `실패를 기록하려 했으나 이미 종결 상태다`가 ERROR로 남는다. **응답이 아니라
영수증을 믿어라.**

**실패한 execute도 `admin_audit_log`에 `retention.execute_failed`로 남는다**(T-342). 파괴 작업
자체의 감사(`retention.execute`)는 성공 트랜잭션 안에 있어 실패 시 함께 폐기되지만, 라우트가 그
실패를 잡아 별도 트랜잭션으로 "시도했고 실패했다"를 추가로 남긴다. kill-switch/confirm-phrase처럼
run조차 만들어지지 않은 채 막힌 경우도 남으며, 그때는 `resource_id`가 없다 — "누가 언제
시도했는가"는 run 생성 여부와 무관하게 감사 가치가 있다. 상세 원인은 이 행이 아니라
`retention_runs.error_message`에 있다 — 실패를 조사할 때는 두 테이블을 함께 본다.

### 5.2 `executing`이 오래 남아 있을 때

```sql
SELECT run_id, started_at, now() - started_at AS age
FROM app.retention_runs
WHERE status = 'executing' AND started_at < now() - interval '15 minutes';
```

**세션이 살아 있는지 실제로 확인할 수 있다**(T-344) — `execute_retention()`이 트랜잭션 진입 직후
`application_name`에 run_id를 싣는다(`'pinvi-retention-execute:' || run_id`, `is_local=true`라 이
트랜잭션이 끝나면 사라진다). `run_id`를 위 쿼리에서 얻은 값으로 바꿔 실행한다:

```sql
SELECT pid, state, wait_event_type, wait_event, query_start, now() - query_start AS duration
FROM pg_stat_activity
WHERE application_name = 'pinvi-retention-execute:<run_id>';
```

- **행이 없으면** 프로세스가 죽은 것이고, 위 표에 따라 **파괴적 작업은 롤백됐다.** 그대로 다시
  실행해도 안전하다. 필요하면 아래로 수동 종결한다.
- **`state = 'active'`면 기다린다.** 큰 배치는 오래 걸릴 수 있다.
- **`state = 'idle in transaction'`이면 기다려도 저절로 안 풀릴 수 있다** — 애플리케이션 코드가
  다음 문장을 실행하지 않고 멈춘 상태다. 다만 T-341의 `idle_in_transaction_session_timeout=60s`가
  있으므로, 이 상태가 60초를 넘겨도 지속된다면 그 자체가 이상 신호다(정상이라면 자동으로 끊긴다).
  `pg_terminate_backend(pid)`로 강제 종료한 뒤 재확인한다.

```sql
UPDATE app.retention_runs
SET status = 'rolled_back',
    error_message = 'stale executing reaped',
    completed_at = now()
WHERE run_id = '<run_id>' AND status = 'executing';
```

자동 정리 작업(reaper)은 **두지 않는다.** heartbeat가 없어 "살아 있는 장기 run"과 "죽은 run"을
구분할 수 없고, 순진한 reaper는 진행 중인 실행을 실패로 오기록해 감사 기록을 오염시킨다.

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
