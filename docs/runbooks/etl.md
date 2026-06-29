# ETL Runbook (`apps/etl` Dagster)

Dagster code location은 `apps/etl`에 분리 (ADR-006). ADR-026 이후 kor-travel-map
feature provider 적재는 `kor-travel-map` 독립 프로그램이 소유한다. 본 저장소의
Dagster는 Pinvi `app` schema 소유 job(KASI 특일/출몰시각, 알림, 보존정책 등)을
실행한다.

## 1. 책임 분담

| 영역 | 본 저장소 (`apps/etl`) | `kor-travel-map` |
|------|----------------------|---------------------|
| Dagster code location | `app` schema job | feature provider job |
| KASI 특일/출몰시각 | ✓ | ✗ |
| 알림/outbox/PII retention | ✓ | ✗ |
| Schedule / Sensor | ✓ | 자체 운영 |
| 변환 (provider raw → DTO) | ✗ | ✓ |
| 적재 (`feature.*` schema) | ✗ | ✓ |
| Record Linkage | ✗ | ✓ |

## 2. 구조

> ADR-045 Phase 6(T-210c) 정합: 아래는 **현재 구현된 파일**과 **계획(미구현)**을
> 구분한다. Pinvi `apps/etl`에는 feature/provider 적재 Dagster 코드가 없으며
> (그 책임은 `kor-travel-map` 소유), 따라서 이관할 "레거시 feature provider
> 스켈레톤"은 존재하지 않는다. 신규 asset은 `app` schema 소유 job일 때만 여기 둔다.

현재 구현(2026-06-28):

```
apps/etl/
├── pyproject.toml                       # dagster + Pinvi app-owned ETL deps
├── pinvi/
│   ├── __init__.py
│   └── etl/
│       ├── __init__.py
│       ├── definitions.py               # Dagster code location entry (sensors=[pinvi_run_failure_sensor])
│       ├── resources.py                 # PinviDatabaseResource, KasiResource
│       ├── schedules.py                 # KASI cron + email/telegram/retention/location cron
│       ├── jobs.py                      # kasi_poi_rise_set_job (POI 출몰시각 one-shot)
│       ├── sensors.py                   # pinvi_run_failure_sensor (ADR-050 실패 통지, T-291)
│       └── assets/
│           ├── __init__.py
│           ├── pinvi_email_outbox.py
│           ├── pinvi_kasi_special_days.py
│           ├── pinvi_location_log_archive.py
│           ├── pinvi_pii_retention.py
│           └── pinvi_telegram_system_outbox.py
└── tests/
    ├── test_definitions.py
    ├── test_run_failure_sensor.py
    ├── test_email_outbox.py
    ├── test_kasi_special_days.py
    ├── test_location_log_archive.py
    ├── test_pii_retention.py
    └── test_telegram_system_outbox.py
```

계획(미구현 — `app` schema 소유 job 후보):

```
pinvi/etl/
└── assets/
    └── pinvi_telegram_weekly.py         # (계획) 주간/일간 사용자 브리프 — D-11/D-1
```

## 2.1 App-Owned Job 표준 (ADR-050)

신규 `apps/etl` job은 ADR-050을 기본 게이트로 삼는다.

- Pinvi `app` schema 소유 job만 추가한다. `feature` / `provider_sync` schema,
  provider raw → DTO 변환, dedup, coverage 갱신은 `kor-travel-map`에 먼저 PR.
- import 시점 DB/network/file write side effect 금지. DB engine과 외부 client는 resource에서
  lazy 생성한다.
- schedule은 항상 `execution_timezone="Asia/Seoul"`을 명시한다.
- transient failure가 가능한 job은 기본 `RetryPolicy(max_retries=3, delay=60,
  backoff=Backoff.EXPONENTIAL)`를 쓴다. queue worker/provider client가 이미 retry를 하면
  이중 retry를 피한다.
- mutating job은 idempotency key를 갖는다. 예: daily/month bucket, provider business key,
  `(category, idempotency_key)` unique key, 또는 `FOR UPDATE SKIP LOCKED` queue claim.
- log/run metadata는 bounded summary만 남긴다. PII, secret, raw token, full URL query,
  긴 raw payload 금지.
- retry 소진 실패는 `run_failure_sensor`가 Sentry와
  `app.telegram_system_notification_outbox`로 전달한다. asset/job에서 Telegram을 직접 호출하지 않는다.
- PII delete/anonymize, location archive/delete, backup/restore 같은 파괴적 작업은 Sprint 5에서
  dry-run만 허용한다. 실제 실행은 kill-switch, `access_reason`, admin audit, staging mutating e2e,
  rollback 절차가 있는 별도 task에서 연다.

## 3. KASI asset 구조

```python
# apps/etl/pinvi/etl/assets/pinvi_kasi_special_days.py
from dagster import asset, AssetExecutionContext, Backoff, RetryPolicy


@asset(
    group_name="pinvi_kasi",
    retry_policy=RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL),
    description="KASI 특일 정보를 과거 6개월 ~ 미래 18개월 범위로 upsert",
)
async def pinvi_kasi_special_days(
    ctx: AssetExecutionContext,
    db: PinviEngineResource,
    kasi: KasiResource,
) -> dict:
    # month bucket: today - 6 months through today + 18 months, inclusive
    # call python-kasi-api special day namespaces and upsert app.kasi_special_days
    ...
```

POI 출몰시각은 정기 asset이 아니라 POI 생성 시 enqueue되는 job이다.
`python-kasi-api`의 `rise_set.location`으로 "위치별 해달 출몰시각 정보조회"를
호출하고 `app.trip_poi_rise_sets`에 1회 저장한다.

구현 상태(2026-06-05): `pinvi_kasi_special_days` asset,
`kasi_special_days_job` schedule, `kasi_poi_rise_set_job` one-shot job이 등록되어
있다. 날짜와 좌표가 있는 POI는 API 생성 시 `status='pending_fetch'` row를 만들고,
Dagster job은 해당 row를 `success` 또는 `failed`로 전이한다.

### 3.1 Email outbox asset

구현 상태(2026-06-28): `pinvi_email_outbox` asset과 `pinvi_email_outbox_job` schedule이
등록되어 있다. 15분마다 `app.email_queue`를 읽어 pending due/backoff/stuck, failed,
bounced, complained, retry exhausted, template별 실패율을 PII 없이 bounded metadata로 남긴다.
실제 발송 source of truth는 FastAPI lifespan `email_outbox_worker_lifespan`이며, Dagster asset은
운영 점검과 Admin summary 노출만 담당한다. hard-bounce/complaint suppression 집행은 T-277 범위다.

### 3.2 PII retention asset

구현 상태(2026-06-29): `pinvi_pii_retention` asset과 `pinvi_pii_retention_job` schedule이
등록되어 있다. 매일 KST 04:15 `app` schema의 삭제 계정 PII, OAuth identity, 만료 verification/reset
token, 오래된 session, 만료 OAuth transient row를 집계한다. 6개월 초과 `location_access_log`는
`pinvi_location_log_archive`가 단독으로 집계하고, `admin_audit_log` PII 후보는 `/admin/etl`과
`/admin/retention`의 별도 `audit_retention` summary로만 집계한다. metadata와 API 응답에는 카운트와
cutoff만 남기고 user id, email, token hash, 원본 위치 좌표는 남기지 않는다.

이 asset은 destructive 작업을 하지 않는 dry-run 전용이다. 실제 delete/anonymize/archive 실행,
kill-switch, evidence log, Admin retention dashboard는 T-276 범위다. `admin` / `operator` /
`cpo` 역할이 있는 삭제 계정은 후보에서 제외하고 `excluded_privileged_deleted_users`로만 보고한다.

### 3.3 Location log archive asset

구현 상태(2026-06-28): `pinvi_location_log_archive` asset과
`pinvi_location_log_archive_job` schedule이 등록되어 있다. 매일 KST 04:30
`app.location_access_log`의 6개월 초과 archive 후보, archive tail `content_hash`와 active head
`prev_hash`의 bridge 상태, 미처리 `app.location_audit_outbox` blocker, purpose별 후보 수를
집계한다.

이 asset은 destructive 작업을 하지 않는 dry-run 전용이다. metadata와 `/admin/etl/summary`
응답에는 row count, log id, hash bridge 상태, cutoff만 남기고 user id, raw coordinate, IP 원문은
남기지 않는다. 실제 archive/delete/anonymize 실행과 archive table/chain tail join 정책은
T-276 kill-switch/dashboard/evidence log 범위다.

### 3.4 Telegram system outbox asset

구현 상태(2026-06-28): `pinvi_telegram_system_outbox` asset과
`pinvi_telegram_system_outbox_job` schedule이 등록되어 있다. 15분마다
`app.telegram_system_notification_outbox`의 pending due/backoff/stuck, sent, skipped,
failed, retry exhausted, category별 retry exhausted 비율을 집계한다.

이 asset은 발송을 수행하지 않는 운영 점검 전용이다. 실제 발송 source of truth는 FastAPI
lifespan `telegram_outbox_worker_lifespan`이며, Dagster asset은 retry/backoff 상태와
Admin summary 노출만 담당한다. metadata와 `/admin/etl/summary` 응답에는 category와 count만
남기고 payload, message text, user id, chat id, token, last_error 원문은 넣지 않는다.

## 4. Resource

```python
# apps/etl/pinvi/etl/resources.py
from dagster import ConfigurableResource, ResourceParam
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from kasi import AsyncKasiClient


class PinviEngineResource(ConfigurableResource):
    dsn: str
    pool_size: int = 10

    def create_engine(self) -> AsyncEngine:
        return create_async_engine(self.dsn, pool_size=self.pool_size, pool_pre_ping=True)


class KasiResource(ConfigurableResource):
    service_key: str
    timeout: float = 10.0

    def create_client(self) -> AsyncKasiClient:
        return AsyncKasiClient(service_key=self.service_key, timeout=self.timeout)
```

## 5. Schedule

```python
# apps/etl/pinvi/etl/schedules.py
from dagster import ScheduleDefinition, define_asset_job

kasi_special_days_job = define_asset_job("kasi_special_days_job", selection=["pinvi_kasi_special_days"])
pinvi_email_outbox_job = define_asset_job("pinvi_email_outbox_job", selection=["pinvi_email_outbox"])
pinvi_pii_retention_job = define_asset_job("pinvi_pii_retention_job", selection=["pinvi_pii_retention"])
pinvi_location_log_archive_job = define_asset_job(
    "pinvi_location_log_archive_job",
    selection=["pinvi_location_log_archive"],
)
pinvi_telegram_system_outbox_job = define_asset_job(
    "pinvi_telegram_system_outbox_job",
    selection=["pinvi_telegram_system_outbox"],
)

schedules = [
    ScheduleDefinition(job=kasi_special_days_job, cron_schedule="30 3 * * *", execution_timezone="Asia/Seoul"),
    ScheduleDefinition(
        name="pinvi_email_outbox_schedule",
        job=pinvi_email_outbox_job,
        cron_schedule="*/15 * * * *",
        execution_timezone="Asia/Seoul",
    ),
    ScheduleDefinition(
        name="pinvi_pii_retention_schedule",
        job=pinvi_pii_retention_job,
        cron_schedule="15 4 * * *",
        execution_timezone="Asia/Seoul",
    ),
    ScheduleDefinition(
        name="pinvi_location_log_archive_schedule",
        job=pinvi_location_log_archive_job,
        cron_schedule="30 4 * * *",
        execution_timezone="Asia/Seoul",
    ),
    ScheduleDefinition(
        name="pinvi_telegram_system_outbox_schedule",
        job=pinvi_telegram_system_outbox_job,
        cron_schedule="*/15 * * * *",
        execution_timezone="Asia/Seoul",
    ),
]
```

KST 강제. import 시점 DB / 네트워크 접근 X.

## 6. 환경변수 (Dagster 컨테이너)

| 환경변수 | 예시 |
|----------|------|
| `PINVI_DATABASE_URL` | `postgresql+asyncpg://pinvi:changeme@postgres:5432/pinvi` |
| `PINVI_DAGSTER_DOWNLOAD_DIR` | `/opt/pinvi/.tmp/dagster-downloads` |
| `PINVI_DAGSTER_LOG_DIR` | `/opt/pinvi/.tmp/dagster-logs` |
| `PINVI_DAGSTER_HOME` | `/opt/pinvi/.tmp/dagster` |
| `PINVI_ETL_CONFIG_PATH` | `/opt/pinvi/config/etl-datasets.json` |
| `PINVI_RUSTFS_ENDPOINT_URL` | `http://rustfs:9000` |
| `PINVI_RUSTFS_BUCKET_FEATURE` | `pinvi-feature-media` |
| `DATA_GO_KR_SERVICE_KEY` | KASI 등 data.go.kr 공통 서비스키 |
| `PINVI_KASI_SPECIAL_DAYS_LOOKBACK_MONTHS` | `6` |
| `PINVI_KASI_SPECIAL_DAYS_LOOKAHEAD_MONTHS` | `18` |
| `PINVI_SENTRY_DSN` | (선택) |

`DATA_GO_KR_SERVICE_KEY`가 없으면 KASI live job은 skip/fail-fast 정책 중 하나를
명시한다. OpenAI API key는 사용하지 않는다.

## 7. 실행

### 7.1 로컬 dev

```bash
cd ~/pinvi-workspaces/pinvi-codex/apps/etl
uv venv .venv --python 3.12
uv pip install -e .
uv run dagster dev --host 0.0.0.0 --port 12802   # UI + daemon http://localhost:12802
```

### 7.2 Docker

```yaml
# infra/docker-compose.yml — dagster service
services:
  dagster:
    build: ./apps/etl
    depends_on: [postgres]
    ports:
      - "12802:3000"
    environment:
      PINVI_DATABASE_URL: postgresql+asyncpg://pinvi:changeme@postgres:5432/pinvi
      PINVI_RUSTFS_ENDPOINT_URL: http://rustfs:9000
      # ...
    volumes:
      - ./apps/etl:/opt/pinvi/apps/etl
      - ./.tmp/dagster:/opt/pinvi/.tmp/dagster
```

## 8. Soak (장시간 검증)

`scripts/etl-soak-*.sh` (v1 자산 일부 재사용 + 라이브러리 분리 반영).

```bash
# 초기화 + 시작
scripts/etl-soak-reset-and-start.sh --yes

# 상태 확인
scripts/etl-soak-status.sh

# 모니터링 (실패 시 alert)
scripts/etl-soak-monitor.sh --strict

# 모든 asset trigger
scripts/etl-soak-trigger-all.sh

# 백그라운드
scripts/etl-soak-background-start.sh
```

soak config: `config/etl-datasets.soak.json` (12시간 이내 schedule로 압축).

마커 파일: `.tmp/etl-soak/started-at`.

## 8.1 Admin live gate

구현 상태(2026-06-28, T-243): `/admin/etl/summary`는 Pinvi Dagster
`/server_info`와 `/graphql`을 읽어 code location repository/job/asset/schedule, 최근 run
상태를 live snapshot으로 반환한다. `server_info` 실패는 `pinvi.status=down`, GraphQL 실패는
`pinvi.status=degraded`로 강등하고, static app-owned registry와 outbox/retention summary는 계속
반환한다.

검증 기준:

- `/server_info`가 `dagster_version`, `dagster_webserver_version`, `dagster_graphql_version`을
  반환한다.
- GraphQL `repositoriesOrError`에서 `pinvi.etl.definitions` code location, app-owned jobs,
  assets, schedules가 보인다.
- 모든 schedule의 `execution_timezone`은 `Asia/Seoul`이다.
- `runsOrError(limit=5)`의 최신 run status를 `/admin/etl` Pinvi job row에 표시한다.
- run tag 값은 Admin 응답에 싣지 않는다. 최신 run은 `run_id`, `status`, `job_name`,
  timestamp만 노출한다.

## 9. 알림 정책 (Sentry + Telegram)

### 9.1 Dagster `run_failure_sensor`

```python
# apps/etl/pinvi/etl/sensors.py
from dagster import RunFailureSensorContext, run_failure_sensor
import sentry_sdk

@run_failure_sensor
def on_run_failure(context: RunFailureSensorContext):
    sentry_sdk.capture_message(...)
    # admin_notifications row insert
    # telegram_system_notification_outbox row insert
```

retry 소진된 마지막 시도에서만 발송 (`RetryPolicy(max_retries=3)` 모두 실패 후).

### 9.2 Outbox 발송

별도 schedule이 `app.telegram_system_notification_outbox` `status='pending'`
처리 — exponential backoff.

## 10. 데이터 정책

- raw provider 응답 long-term 저장은 소유 서비스에서만 한다. kor-travel-map feature
  provider raw는 kor-travel-map `source_records` 책임이고, KASI 특일/출몰시각 raw는
  Pinvi `app` schema의 `raw_payload`에 보존한다.
- 위치 좌표는 외부 표면에서 `(lon, lat)`를 유지한다. kor-travel-map feature 공간 컬럼은
  kor-travel-map이 관리한다.
- KST 시간축 (`Asia/Seoul`). UTC 저장 + 응용 변환
- key 마스킹: `serviceKey`, `certkey`, `apiKey`, `token`

## 11. AI agent 작업 체크리스트

새 asset 추가:

- [ ] Pinvi `app` schema 소유 job인지 확인. feature provider job이면
      `kor-travel-map`에 먼저 PR
- [ ] import 시점 DB/network/file write side effect가 없는지 확인
- [ ] schedule timezone `Asia/Seoul` 명시
- [ ] retry policy 또는 retry를 끄는 이유 명시
- [ ] idempotency key / unique constraint / queue claim 기준 명시
- [ ] PII, secret, raw token, full URL query가 log/run metadata에 남지 않는지 확인
- [ ] 본 저장소 `apps/etl/pinvi/etl/assets/<name>.py` 또는 `jobs.py` 추가
- [ ] `apps/etl/pinvi/etl/resources.py`에 필요한 client resource 추가
- [ ] `apps/etl/pinvi/etl/schedules.py` cron 추가
- [ ] `apps/etl/tests/test_asset_<name>.py`에 해당하는 helper 테스트 추가
- [ ] `run_failure_sensor` → Sentry/outbox 알림 흐름 검증
- [ ] 파괴적 작업은 dry-run 기본값과 실제 실행 gate 문서화
- [ ] 본 runbook + 추적 문서 갱신

## 12. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `dagster dev` 시작 안 됨 | 의존성 누락 | `uv pip install -e .` 후 pyproject 확인 |
| Schedule이 cron에 안 맞춰 실행 | timezone 미설정 | `execution_timezone="Asia/Seoul"` 명시 |
| Asset 실패 무한 재시도 | `RetryPolicy` 미설정 | 명시 + Sentry 알림 |
| `import time DB/network access` 경고 | `definitions.py`에서 직접 호출 | resource로 분리 |
| Soak `started-at` marker 없음 | `etl-soak-reset` 안 함 | `scripts/etl-soak-reset-and-start.sh --yes` |

## 13. 관련 문서

- `docs/kor-travel-map-integration.md` — kor-travel-map OpenAPI HTTP 호출 패턴
- `docs/integrations/kasi.md` — KASI 특일/출몰시각 계약
- `docs/api/admin.md` §9 — Admin ETL 화면
- `docs/integrations/sentry.md` — Dagster sensor 통합
- `docs/integrations/telegram.md` — Admin 알림
- ADR-006 — Dagster code location 분리
- ADR-050 — Pinvi app-owned Dagster job 표준
