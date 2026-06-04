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

```
apps/etl/
├── pyproject.toml                       # dagster + dagit + TripMate app-owned ETL deps
├── tripmate/
│   └── etl/
│       ├── __init__.py
│       ├── definitions.py               # Dagster code location entry
│       ├── resources.py                 # DB, KASI, 알림 resource
│       ├── schedules.py                 # cron 정의 + KST 고정
│       ├── sensors.py                   # run_failure_sensor (Sentry)
│       └── assets/
│           ├── tripmate_kasi_special_days.py
│           ├── tripmate_kasi_poi_rise_set.py
│           ├── tripmate_telegram_weekly.py  # TripMate 자체 job
│           ├── tripmate_email_outbox.py
│           └── ...
└── tests/
    ├── test_definitions.py
    └── test_asset_<name>.py
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
| `TRIPMATE_RUSTFS_ENDPOINT_URL` | `http://rustfs:9003` |
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
      TRIPMATE_RUSTFS_ENDPOINT_URL: http://rustfs:9003
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
- [ ] 본 저장소 `apps/etl/tripmate/etl/assets/<name>.py` 추가
- [ ] `apps/etl/tripmate/etl/resources.py`에 필요한 client resource 추가
- [ ] `apps/etl/tripmate/etl/schedules.py` cron 추가
- [ ] `apps/etl/tests/test_asset_<name>.py` — `materialize_to_memory` + fixture
- [ ] retry_policy 명시 (기본 3 × exponential backoff)
- [ ] 본 runbook + `docs/sprints/SPRINT-5.md` 갱신
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
