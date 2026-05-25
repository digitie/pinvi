# ETL Runbook (`apps/etl` Dagster)

Dagster code location은 `apps/etl`에 분리 (ADR-006). ETL의 실제 변환·적재 코드는
`python-krtour-map`에 있고, 본 저장소는 **execution shell** 만 (resource 주입 +
schedule + sensor + retry).

## 1. 책임 분담

| 영역 | 본 저장소 (`apps/etl`) | `python-krtour-map` |
|------|----------------------|---------------------|
| Dagster code location | ✓ | ✗ |
| Asset definitions (얇은 어댑터) | ✓ | ✗ |
| Resource (`AsyncKrtourMapClient`, provider clients) | ✓ DI | provider lib |
| Schedule / Sensor | ✓ | ✗ |
| Retry policy | ✓ | ✗ |
| 변환 (provider raw → DTO) | ✗ | ✓ |
| 적재 (`feature.*` schema) | ✗ | ✓ |
| Record Linkage | ✗ | ✓ |

## 2. 구조

```
apps/etl/
├── pyproject.toml                       # dagster + dagit + python-krtour-map git URL pin
├── tripmate/
│   └── etl/
│       ├── __init__.py
│       ├── definitions.py               # Dagster code location entry
│       ├── resources.py                 # KrtourMapResource, VisitKoreaResource, ...
│       ├── schedules.py                 # cron 정의 + KST 고정
│       ├── sensors.py                   # run_failure_sensor (Sentry)
│       └── assets/
│           ├── feature_event_festivals.py
│           ├── feature_price_fuel.py
│           ├── feature_weather_kma_short_term.py
│           ├── feature_place_heritage.py
│           ├── feature_event_heritage.py
│           ├── feature_vworld_import.py
│           ├── tripmate_telegram_weekly.py  # TripMate 자체 job
│           ├── tripmate_email_outbox.py
│           └── ...
└── tests/
    ├── test_definitions.py
    └── test_asset_<name>.py
```

## 3. Asset 구조 (얇은 어댑터)

```python
# apps/etl/tripmate/etl/assets/feature_event_festivals.py
from dagster import asset, AssetExecutionContext, Backoff, RetryPolicy

from krtour.map import AsyncKrtourMapClient


@asset(
    group_name="feature_event",
    retry_policy=RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL),
    description="VisitKorea 축제를 event feature로 적재",
)
async def feature_event_festivals(
    ctx: AssetExecutionContext,
    krtour_map: KrtourMapResource,
    visitkorea: VisitKoreaResource,
) -> dict:
    async with krtour_map.client() as client:
        items = await visitkorea.client.search_festival_async(
            modified_time_from=(ctx.partition_time_window.start if ctx.has_partition_key else None),
        )
        bundles = client.providers.visitkorea.festival_to_bundles(items)
        result = await client.load_festivals(bundles)
        ctx.log.info("loaded", extra=result.as_metadata())
        ctx.add_output_metadata(result.as_metadata())
        return result.as_metadata()
```

**핵심**: TripMate `apps/etl` asset은 얇음 — provider 호출 + `client.providers.<provider>.<convert>` +
`client.load_*` + 로깅. 비즈니스 로직은 모두 라이브러리에.

## 4. Resource

```python
# apps/etl/tripmate/etl/resources.py
from dagster import ConfigurableResource, ResourceParam
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from krtour.map import AsyncKrtourMapClient
from python_visitkorea_api import VisitKoreaClient
from python_kma_api import KmaClient


class TripmateEngineResource(ConfigurableResource):
    dsn: str
    pool_size: int = 10

    def create_engine(self) -> AsyncEngine:
        return create_async_engine(self.dsn, pool_size=self.pool_size, pool_pre_ping=True)


class KrtourMapResource(ConfigurableResource):
    engine: ResourceParam[AsyncEngine]
    rustfs_endpoint: str
    rustfs_bucket: str

    async def client(self) -> AsyncKrtourMapClient:
        return AsyncKrtourMapClient(
            engine=self.engine,
            file_store=...,
            providers=await self._provider_clients(),
        )


class VisitKoreaResource(ConfigurableResource):
    service_key: str
    timeout: float = 10.0

    @property
    def client(self) -> VisitKoreaClient:
        return VisitKoreaClient(service_key=self.service_key, timeout=self.timeout)
```

## 5. Schedule

```python
# apps/etl/tripmate/etl/schedules.py
from dagster import ScheduleDefinition, define_asset_job

festival_job = define_asset_job("festival_job", selection=["feature_event_festivals"])
fuel_job = define_asset_job("fuel_job", selection=["feature_price_fuel"])
weather_short_term_job = define_asset_job("weather_short_term_job", selection=["feature_weather_kma_short_term"])

schedules = [
    ScheduleDefinition(job=festival_job, cron_schedule="0 3 * * 1", execution_timezone="Asia/Seoul"),  # 매주 월 03:00
    ScheduleDefinition(job=fuel_job, cron_schedule="0 6,14,22 * * *", execution_timezone="Asia/Seoul"),  # 하루 3회
    ScheduleDefinition(job=weather_short_term_job, cron_schedule="*/30 * * * *", execution_timezone="Asia/Seoul"),
    # 부하 분산: 월간 job 들은 서로 다른 일자에
    # ...
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
| `TRIPMATE_RUSTFS_ENDPOINT_URL` | `http://rustfs:9000` |
| `TRIPMATE_RUSTFS_BUCKET_FEATURE` | `tripmate-feature-media` |
| Provider API 키 | `KMA_SERVICE_KEY`, `VISITKOREA_SERVICE_KEY`, `OPINET_API_KEY`, `KHOA_API_KEY`, `EXPRESSWAY_API_KEY`, `KRHERITAGE_API_KEY`, ... |
| `TRIPMATE_SENTRY_DSN` | (선택) |

키 없는 provider는 schedule 생성 안 함 (자동 skip).

## 7. 실행

### 7.1 로컬 dev

```bash
cd ~/tripmate-workspaces/tripmate/apps/etl
uv venv .venv --python 3.12
uv pip install -e .
uv run dagster dev   # UI + daemon http://localhost:23000
```

### 7.2 Docker

```yaml
# infra/docker-compose.yml — dagster service
services:
  dagster:
    build: ./apps/etl
    depends_on: [postgres]
    ports:
      - "23000:3000"
    environment:
      TRIPMATE_DATABASE_URL: postgresql+asyncpg://tripmate:changeme@postgres:5432/tripmate
      TRIPMATE_RUSTFS_ENDPOINT_URL: http://rustfs:9000
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

- raw provider 응답 long-term 저장 X — `python-krtour-map`의 `source_records`에만
- 위치 좌표는 PostGIS `geom` + EPSG:4326 → `coord_5179` (meter) 컬럼 라이브러리가
  관리
- KST 시간축 (`Asia/Seoul`). UTC 저장 + 응용 변환
- key 마스킹: `serviceKey`, `certkey`, `apiKey`, `token`

## 11. AI agent 작업 체크리스트

새 asset 추가:

- [ ] **`python-krtour-map`에 먼저 PR** — provider 변환 + load 함수 + 단위 테스트
- [ ] 본 저장소 `apps/etl/tripmate/etl/assets/<name>.py` 추가 (얇은 어댑터)
- [ ] `apps/etl/tripmate/etl/resources.py`에 provider client resource 추가
- [ ] `apps/etl/tripmate/etl/schedules.py` cron 추가
- [ ] `apps/etl/tests/test_asset_<name>.py` — `materialize_to_memory` + fixture
- [ ] retry_policy 명시 (기본 3 × exponential backoff)
- [ ] 본 runbook + `docs/sprints/SPRINT-5.md` 갱신
- [ ] Sentry tags + admin/telegram 알림 흐름 검증

## 12. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `dagster dev` 시작 안 됨 | python-krtour-map 의존 누락 | `uv pip install -e ../python-krtour-map` |
| Schedule이 cron에 안 맞춰 실행 | timezone 미설정 | `execution_timezone="Asia/Seoul"` 명시 |
| Asset 실패 무한 재시도 | `RetryPolicy` 미설정 | 명시 + Sentry 알림 |
| `import time DB/network access` 경고 | `definitions.py`에서 직접 호출 | resource로 분리 |
| Soak `started-at` marker 없음 | `etl-soak-reset` 안 함 | `scripts/etl-soak-reset-and-start.sh --yes` |

## 13. 관련 문서

- `docs/krtour-map-integration.md` — 라이브러리 호출 패턴
- `docs/api/admin.md` §9 — Admin ETL 화면
- `docs/integrations/sentry.md` — Dagster sensor 통합
- `docs/integrations/telegram.md` — Admin 알림
- ADR-006 — Dagster code location 분리
