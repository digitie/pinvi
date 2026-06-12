# ETL Runbook (`apps/etl` Dagster)

Dagster code location은 `apps/etl`에 분리 (ADR-006). ADR-026 이후 krtour-map
feature provider 적재는 `python-krtour-map` 독립 프로그램이 소유한다. 본 저장소의
Dagster는 TripMate `app` schema 소유 job(KASI 특일/출몰시각, 알림, 보존정책 등)을
실행한다.

## 1. 책임 분담

| 영역 | 본 저장소 (`apps/etl`) | `python-krtour-map` |
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
> 구분한다. TripMate `apps/etl`에는 feature/provider 적재 Dagster 코드가 없으며
> (그 책임은 `python-krtour-map` 소유), 따라서 이관할 "레거시 feature provider
> 스켈레톤"은 존재하지 않는다. 신규 asset은 `app` schema 소유 job일 때만 여기 둔다.

현재 구현(2026-06-06):

```
apps/etl/
├── pyproject.toml                       # dagster + TripMate app-owned ETL deps
├── tripmate/
│   ├── __init__.py
│   └── etl/
│       ├── __init__.py
│       ├── definitions.py               # Dagster code location entry (sensors=[])
│       ├── resources.py                 # TripmateDatabaseResource, KasiResource
│       ├── schedules.py                 # kasi_special_days_job cron (KST 03:30)
│       ├── jobs.py                      # kasi_poi_rise_set_job (POI 출몰시각 one-shot)
│       └── assets/
│           ├── __init__.py
│           └── tripmate_kasi_special_days.py
└── tests/
    ├── test_definitions.py
    └── test_kasi_special_days.py
```

계획(미구현 — `app` schema 소유 job 후보):

```
tripmate/etl/
├── sensors.py                           # (계획) run_failure_sensor (Sentry/outbox)
└── assets/
    ├── tripmate_telegram_weekly.py      # (계획) 주간 브리프 — D-11
    ├── tripmate_email_outbox.py         # (계획) 이메일 outbox worker
    ├── tripmate_pii_retention.py        # (계획) PII 보존정책
    └── tripmate_location_log_archive.py # (계획) 위치로그 archive — DEC-10
```

## 3. KASI asset 구조

```python
# apps/etl/tripmate/etl/assets/tripmate_kasi_special_days.py
from dagster import asset, AssetExecutionContext, Backoff, RetryPolicy


@asset(
    group_name="tripmate_kasi",
    retry_policy=RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL),
    description="KASI 특일 정보를 과거 6개월 ~ 미래 18개월 범위로 upsert",
)
async def tripmate_kasi_special_days(
    ctx: AssetExecutionContext,
    db: TripmateEngineResource,
    kasi: KasiResource,
) -> dict:
    # month bucket: today - 6 months through today + 18 months, inclusive
    # call python-kasi-api special day namespaces and upsert app.kasi_special_days
    ...
```

POI 출몰시각은 정기 asset이 아니라 POI 생성 시 enqueue되는 job이다.
`python-kasi-api`의 `rise_set.location`으로 "위치별 해달 출몰시각 정보조회"를
호출하고 `app.trip_poi_rise_sets`에 1회 저장한다.

구현 상태(2026-06-05): `tripmate_kasi_special_days` asset,
`kasi_special_days_job` schedule, `kasi_poi_rise_set_job` one-shot job이 등록되어
있다. 날짜와 좌표가 있는 POI는 API 생성 시 `status='pending_fetch'` row를 만들고,
Dagster job은 해당 row를 `success` 또는 `failed`로 전이한다.

## 4. Resource

```python
# apps/etl/tripmate/etl/resources.py
from dagster import ConfigurableResource, ResourceParam
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from kasi import AsyncKasiClient


class TripmateEngineResource(ConfigurableResource):
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
# apps/etl/tripmate/etl/schedules.py
from dagster import ScheduleDefinition, define_asset_job

kasi_special_days_job = define_asset_job("kasi_special_days_job", selection=["tripmate_kasi_special_days"])

schedules = [
    ScheduleDefinition(job=kasi_special_days_job, cron_schedule="30 3 * * *", execution_timezone="Asia/Seoul"),
]
```

KST 강제. import 시점 DB / 네트워크 접근 X.

## 6. 환경변수 (Dagster 컨테이너)

| 환경변수 | 예시 |
|----------|------|
| `TRIPMATE_DATABASE_URL` | `postgresql+asyncpg://tripmate:changeme@postgres:5432/tripmate` |
| `TRIPMATE_DAGSTER_DOWNLOAD_DIR` | `/opt/tripmate/.tmp/dagster-downloads` |
| `TRIPMATE_DAGSTER_LOG_DIR` | `/opt/tripmate/.tmp/dagster-logs` |
| `TRIPMATE_DAGSTER_HOME` | `/opt/tripmate/.tmp/dagster` |
| `TRIPMATE_ETL_CONFIG_PATH` | `/opt/tripmate/config/etl-datasets.json` |
| `TRIPMATE_RUSTFS_ENDPOINT_URL` | `http://rustfs:12101` |
| `TRIPMATE_RUSTFS_BUCKET_FEATURE` | `tripmate-feature-media` |
| `DATA_GO_KR_SERVICE_KEY` | KASI 등 data.go.kr 공통 서비스키 |
| `TRIPMATE_KASI_SPECIAL_DAYS_LOOKBACK_MONTHS` | `6` |
| `TRIPMATE_KASI_SPECIAL_DAYS_LOOKAHEAD_MONTHS` | `18` |
| `TRIPMATE_SENTRY_DSN` | (선택) |

`DATA_GO_KR_SERVICE_KEY`가 없으면 KASI live job은 skip/fail-fast 정책 중 하나를
명시한다. OpenAI API key는 사용하지 않는다.

## 7. 실행

### 7.1 로컬 dev

```bash
cd ~/tripmate-workspaces/tripmate-codex/apps/etl
uv venv .venv --python 3.12
uv pip install -e .
uv run dagster dev --host 0.0.0.0 --port 9023   # UI + daemon http://localhost:9023
```

### 7.2 Docker

```yaml
# infra/docker-compose.yml — dagster service
services:
  dagster:
    build: ./apps/etl
    depends_on: [postgres]
    ports:
      - "9023:3000"
    environment:
      TRIPMATE_DATABASE_URL: postgresql+asyncpg://tripmate:changeme@postgres:5432/tripmate
      TRIPMATE_RUSTFS_ENDPOINT_URL: http://rustfs:12101
      # ...
    volumes:
      - ./apps/etl:/opt/tripmate/apps/etl
      - ./.tmp/dagster:/opt/tripmate/.tmp/dagster
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

## 9. 알림 정책 (Sentry + Telegram)

### 9.1 Dagster `run_failure_sensor`

```python
# apps/etl/tripmate/etl/sensors.py
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

- raw provider 응답 long-term 저장은 소유 서비스에서만 한다. krtour-map feature
  provider raw는 krtour-map `source_records` 책임이고, KASI 특일/출몰시각 raw는
  TripMate `app` schema의 `raw_payload`에 보존한다.
- 위치 좌표는 외부 표면에서 `(lon, lat)`를 유지한다. krtour-map feature 공간 컬럼은
  krtour-map이 관리한다.
- KST 시간축 (`Asia/Seoul`). UTC 저장 + 응용 변환
- key 마스킹: `serviceKey`, `certkey`, `apiKey`, `token`

## 11. AI agent 작업 체크리스트

새 asset 추가:

- [ ] TripMate `app` schema 소유 job인지 확인. feature provider job이면
      `python-krtour-map`에 먼저 PR
- [x] 본 저장소 `apps/etl/tripmate/etl/assets/<name>.py` 추가
- [x] `apps/etl/tripmate/etl/resources.py`에 필요한 client resource 추가
- [x] `apps/etl/tripmate/etl/schedules.py` cron 추가
- [x] `apps/etl/tests/test_asset_<name>.py`에 해당하는 helper 테스트 추가
- [x] retry_policy 명시 (기본 3 × exponential backoff)
- [x] 본 runbook + 추적 문서 갱신
- [ ] Sentry tags + admin/telegram 알림 흐름 검증

## 12. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `dagster dev` 시작 안 됨 | 의존성 누락 | `uv pip install -e .` 후 pyproject 확인 |
| Schedule이 cron에 안 맞춰 실행 | timezone 미설정 | `execution_timezone="Asia/Seoul"` 명시 |
| Asset 실패 무한 재시도 | `RetryPolicy` 미설정 | 명시 + Sentry 알림 |
| `import time DB/network access` 경고 | `definitions.py`에서 직접 호출 | resource로 분리 |
| Soak `started-at` marker 없음 | `etl-soak-reset` 안 함 | `scripts/etl-soak-reset-and-start.sh --yes` |

## 13. 관련 문서

- `docs/krtour-map-integration.md` — krtour-map OpenAPI HTTP 호출 패턴
- `docs/integrations/kasi.md` — KASI 특일/출몰시각 계약
- `docs/api/admin.md` §9 — Admin ETL 화면
- `docs/integrations/sentry.md` — Dagster sensor 통합
- `docs/integrations/telegram.md` — Admin 알림
- ADR-006 — Dagster code location 분리
