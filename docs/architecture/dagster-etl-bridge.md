# Dagster ETL Bridge

`apps/etl`은 TripMate가 소유한 `app` schema 운영 job을 실행하는 Dagster code
location이다. krtour-map feature provider 적재는 최신 ADR-026 이후
`python-krtour-map` 독립 프로그램/API/Admin/Dagster가 소유한다.

## 1. 핵심 원칙

- TripMate Dagster는 `app` schema 소유 데이터만 쓴다.
- `feature` / `provider_sync` schema 적재, provider raw → DTO 변환, dedup은
  krtour-map 저장소 책임이다.
- TripMate Dagster에서 `python-krtour-map` 내부 모듈이나 `AsyncKrtourMapClient`를
  import하지 않는다.
- 외부 public API 클라이언트는 해당 TripMate job이 `app` schema에 저장할 때만 쓴다.
  예: `python-kasi-api` 특일/출몰시각.

자세한 운영은 [`docs/runbooks/etl.md`](../runbooks/etl.md).

## 2. 구조

```
apps/etl/
├── pyproject.toml
├── tripmate/
│   └── etl/
│       ├── definitions.py
│       ├── resources.py
│       ├── schedules.py
│       ├── sensors.py
│       └── assets/
│           ├── tripmate_kasi_special_days.py
│           ├── tripmate_kasi_poi_rise_set.py
│           ├── tripmate_telegram_weekly.py
│           ├── tripmate_email_outbox.py
│           ├── tripmate_pii_retention.py
│           └── tripmate_location_log_archive.py
└── tests/
```

## 3. KASI assets

### 3.1 `kasi_special_days_daily`

- 하루 1회 KST 실행.
- 실행일 기준 과거 6개월부터 미래 18개월까지 월 단위로 조회.
- `python-kasi-api`의 특일 계열 5개 dataset을 모두 호출.
- `app.kasi_special_days`에 upsert.
- 별도 삭제 없음.

### 3.2 `kasi_poi_rise_set_job`

- POI 생성 시 enqueue/run.
- API 생성 경로가 `app.trip_day_pois`의 좌표 snapshot과 `app.trip_days.date`를
  기준으로 `app.trip_poi_rise_sets` row를 먼저 만든다.
- `python-kasi-api` `rise_set.location`으로 "위치별 해달 출몰시각 정보조회" 호출.
- 날짜/좌표가 있으면 `pending_fetch` → `success` / `failed`로 전이한다.
- 날짜/좌표가 없으면 `pending_date` / `pending_coord` 상태로 남긴다.

## 4. Schedule

```python
from dagster import ScheduleDefinition, define_asset_job

kasi_special_days_job = define_asset_job(
    "kasi_special_days_job",
    selection=["tripmate_kasi_special_days"],
)

kasi_special_days_schedule = ScheduleDefinition(
    job=kasi_special_days_job,
    cron_schedule="30 3 * * *",
    execution_timezone="Asia/Seoul",
)
```

POI 출몰시각은 정기 schedule이 아니라 POI 생성 이벤트에서 run을 enqueue한다.

## 5. 실패 알림

Dagster `run_failure_sensor`는 기존 outbox 패턴을 따른다. 외부 API 호출 실패 시
서비스키나 요청 URL의 `serviceKey` 값은 마스킹한다.

## 6. AI agent 체크리스트

- [ ] 새 feature provider 적재가 필요하면 TripMate가 아니라 `python-krtour-map`에 PR.
- [ ] TripMate `apps/etl` asset은 `app` schema 소유 job인지 먼저 확인.
- [ ] KASI live 검증은 `DATA_GO_KR_SERVICE_KEY`가 있을 때만 수행.
- [ ] schedule timezone은 항상 `Asia/Seoul`.
- [ ] import 시점 DB/network access 금지.
