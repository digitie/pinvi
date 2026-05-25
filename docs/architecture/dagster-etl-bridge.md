# Dagster ETL Bridge (TripMate ↔ `python-krtour-map`)

`apps/etl`이 `python-krtour-map`의 collect/load 함수를 호출하는 표준 패턴.
ADR-006 (Dagster code location 분리) + ADR-002 (함수 직접 호출).

## 1. 핵심 원칙

- `apps/etl`은 **얇은 execution shell** — provider 호출 + 라이브러리 함수 호출 +
  로깅만
- 비즈니스 로직(변환 + 적재 + dedup)은 **모두 `python-krtour-map`**
- wrapper / adapter class 금지 (ADR-005)
- TripMate `apps/api`는 `apps/etl`에 의존 X (다른 venv)
- Dagster definitions / asset / resource / schedule / sensor만 본 저장소
- 라이브러리 schema (`feature.*`, `provider_sync.*`)는 라이브러리 alembic으로

자세한 운영은 [`docs/runbooks/etl.md`](../runbooks/etl.md).

## 2. 구조 (Sprint 5)

```
apps/etl/
├── pyproject.toml                          # uv venv, dagster + python-krtour-map git URL pin
├── tripmate/
│   └── etl/
│       ├── __init__.py
│       ├── definitions.py                  # Dagster code location entry
│       ├── resources.py                    # 모든 resource (engine / file_store / provider clients / krtour_map)
│       ├── schedules.py                    # cron + KST 강제
│       ├── sensors.py                      # run_failure_sensor (Sentry + admin alert)
│       ├── partitions.py                   # 시간 / region 파티션
│       └── assets/
│           ├── feature_event_festivals.py
│           ├── feature_price_fuel.py
│           ├── feature_weather_kma_short_term.py
│           ├── feature_weather_kma_ultra_short.py
│           ├── feature_weather_kma_mid.py
│           ├── feature_place_heritage.py
│           ├── feature_event_heritage.py
│           ├── feature_place_rest_area.py
│           ├── feature_place_beach.py
│           ├── feature_route_forest.py
│           ├── feature_area_park.py
│           ├── feature_air_quality.py
│           ├── feature_vworld_import.py
│           ├── feature_juso_address.py
│           ├── # TripMate 자체 jobs
│           ├── tripmate_telegram_weekly.py
│           ├── tripmate_email_outbox.py
│           ├── tripmate_pii_retention.py
│           └── tripmate_location_log_archive.py
└── tests/
```

## 3. Resource

```python
# apps/etl/tripmate/etl/resources.py
from dagster import ConfigurableResource, ResourceParam, EnvVar
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from krtour.map import AsyncKrtourMapClient
from python_visitkorea_api import VisitKoreaClient
from python_kma_api import KmaClient
from python_opinet_api import OpinetClient
from python_khoa_api import KhoaClient
from python_krex_api import KrexClient
from python_krheritage_api import KrheritageClient
from python_krforest_api import KrforestClient
from python_krmois_api import KrmoisClient
from python_airkorea_api import AirkoreaClient
from python_kraddr_geo import AsyncAddressClient


class TripmateDatabaseResource(ConfigurableResource):
    dsn: str = EnvVar("TRIPMATE_DATABASE_URL")
    pool_size: int = 10

    def create_engine(self) -> AsyncEngine:
        return create_async_engine(self.dsn, pool_size=self.pool_size, pool_pre_ping=True)


class RustFSResource(ConfigurableResource):
    endpoint: str = EnvVar("TRIPMATE_RUSTFS_ENDPOINT_URL")
    bucket_feature: str = EnvVar("TRIPMATE_RUSTFS_BUCKET_FEATURE")
    access_key: str = EnvVar("TRIPMATE_RUSTFS_ACCESS_KEY_ID")
    secret_key: str = EnvVar("TRIPMATE_RUSTFS_SECRET_ACCESS_KEY")

    def create_store(self):
        # python-krtour-map.FileStore 인스턴스 생성
        from krtour.map import FileStore
        return FileStore(endpoint=self.endpoint, bucket=self.bucket_feature,
                         access_key=self.access_key, secret_key=self.secret_key)


class KraddrGeoResource(ConfigurableResource):
    juso_api_key: str = EnvVar("TRIPMATE_JUSO_API_KEY")

    def create_client(self) -> AsyncAddressClient:
        return AsyncAddressClient(juso_api_key=self.juso_api_key)


class KrtourMapResource(ConfigurableResource):
    db: ResourceParam[TripmateDatabaseResource]
    rustfs: ResourceParam[RustFSResource]
    kraddr_geo: ResourceParam[KraddrGeoResource]
    visitkorea: ResourceParam["VisitKoreaResource"]
    kma: ResourceParam["KmaResource"]
    # ...

    async def client(self) -> AsyncKrtourMapClient:
        return AsyncKrtourMapClient(
            engine=self.db.create_engine(),
            file_store=self.rustfs.create_store(),
            kraddr_geo_client=self.kraddr_geo.create_client(),
            providers={
                "visitkorea": self.visitkorea.create_client(),
                "kma": self.kma.create_client(),
                # ...
            },
        )


class VisitKoreaResource(ConfigurableResource):
    service_key: str = EnvVar("VISITKOREA_SERVICE_KEY")
    timeout: float = 10.0
    max_retries: int = 2

    def create_client(self) -> VisitKoreaClient:
        return VisitKoreaClient(
            service_key=self.service_key,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )


# 동일 패턴: KmaResource, OpinetResource, KhoaResource, KrexResource,
#           KrheritageResource, KrforestResource, KrmoisResource, AirkoreaResource
```

## 4. Asset 패턴 (얇은 어댑터)

```python
# apps/etl/tripmate/etl/assets/feature_event_festivals.py
from dagster import asset, AssetExecutionContext, Backoff, RetryPolicy
from datetime import datetime, timedelta

from tripmate.etl.resources import KrtourMapResource, VisitKoreaResource


@asset(
    group_name="feature_event",
    retry_policy=RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL),
    description="VisitKorea 축제를 event feature로 적재 (rolling 1m ~ +12m)",
)
async def feature_event_festivals(
    context: AssetExecutionContext,
    krtour_map: KrtourMapResource,
    visitkorea: VisitKoreaResource,
) -> dict:
    async with await krtour_map.client() as client:
        # 1) provider 호출 (asyncio)
        items = await visitkorea.create_client().search_festival_async(
            modified_time_from=datetime.now() - timedelta(days=1),
            event_start_from=datetime.now() - timedelta(days=30),
            event_start_to=datetime.now() + timedelta(days=365),
        )

        # 2) 라이브러리 변환 함수 (순수)
        bundles = client.providers.visitkorea.festival_to_bundles(items)

        # 3) 라이브러리 적재 함수 (DB write)
        result = await client.load_festivals(bundles)

        # 4) 로깅 + Dagster metadata
        context.log.info("loaded festivals", **result.as_metadata())
        context.add_output_metadata(result.as_metadata())

        return result.as_metadata()
```

핵심:

- TripMate에는 `festival_to_bundles` / `load_festivals` 구현 없음 — 라이브러리에
- asset 함수는 변환 / 적재를 호출만 — 비즈니스 로직 추가 X
- import 시점 (`from ... import asset`)에 DB / 네트워크 접근 X

## 5. Schedule (KST 강제)

```python
# apps/etl/tripmate/etl/schedules.py
from dagster import ScheduleDefinition, define_asset_job

festival_job = define_asset_job("festival_job", selection=["feature_event_festivals"])

festival_schedule = ScheduleDefinition(
    job=festival_job,
    cron_schedule="0 3 * * 1",                # 매주 월 03:00
    execution_timezone="Asia/Seoul",
    default_status=DefaultScheduleStatus.RUNNING,
)
```

KST 강제. 부하 분산: 월간 job들은 서로 다른 일자에 (KMA 1일 / OpiNet 4일 등).

## 6. Sensor (실패 알림)

```python
# apps/etl/tripmate/etl/sensors.py
from dagster import RunFailureSensorContext, run_failure_sensor
import sentry_sdk
import httpx


@run_failure_sensor
def on_run_failure(context: RunFailureSensorContext):
    # 1) Sentry
    sentry_sdk.capture_message(
        f"Dagster run failed: {context.failure_event.message}",
        level="error",
        contexts={
            "dagster": {
                "run_id": context.dagster_run.run_id,
                "job_name": context.dagster_run.job_name,
            }
        },
        tags={"component": "etl", "asset": context.dagster_run.job_name},
    )

    # 2) Admin Telegram (outbox 패턴)
    # apps/api에 직접 호출하지 않고 DB outbox 사용
    asyncio.run(_insert_outbox(context))


async def _insert_outbox(context):
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(os.environ["TRIPMATE_DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO app.telegram_system_notification_outbox
              (id, category, payload, status, scheduled_at)
            VALUES (gen_random_uuid(), 'etl_failure',
              :payload, 'pending', now())
        """), {"payload": json.dumps({
            "run_id": context.dagster_run.run_id,
            "job_name": context.dagster_run.job_name,
            "error": context.failure_event.message,
            "stale_serving_used": False,
        })})
```

## 7. Partitions

시간 기반 또는 region 기반:

```python
from dagster import DailyPartitionsDefinition

daily_partitions = DailyPartitionsDefinition(start_date="2026-01-01", timezone="Asia/Seoul")

@asset(partitions_def=daily_partitions, ...)
async def feature_weather_kma_short_term(context, krtour_map):
    asof = context.partition_time_window.start
    # ...
```

## 8. TripMate 자체 job (라이브러리 호출 없음)

```python
# apps/etl/tripmate/etl/assets/tripmate_telegram_weekly.py
@asset(group_name="tripmate_notifications", ...)
async def tripmate_telegram_weekly_summary(context, db, telegram):
    # TripMate trip + telegram targets 조회 → 메시지 생성 → 발송
    ...
```

`apps/api`의 `app.trips` / `app.telegram_targets` / `email_queue` 등을 사용.
라이브러리 호출 없음.

## 9. AI agent 작업 체크리스트

새 asset 추가:

- [ ] **`python-krtour-map`에 먼저 PR** — provider 변환 + load 함수
- [ ] 본 저장소 `apps/etl/tripmate/etl/assets/<name>.py` (얇은 어댑터)
- [ ] resource 추가 시 `resources.py` 업데이트
- [ ] schedule cron + KST 강제 + 부하 분산
- [ ] `retry_policy=RetryPolicy(max_retries=3, ...)` 명시
- [ ] `apps/etl/tests/test_asset_<name>.py` `materialize_to_memory` + fixture
- [ ] import 시점 DB / 네트워크 접근 X 검증
- [ ] sensor 통합 (Sentry + admin outbox)
- [ ] [etl.md](../runbooks/etl.md) 본문 갱신
- [ ] 비밀값 마스킹 (Sentry / Loki)
