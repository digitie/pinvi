# Dagster ETL Bridge

`apps/etl`은 Pinvi가 소유한 `app` schema 운영 job을 실행하는 Dagster code
location이다. kor-travel-map feature provider 적재는 최신 ADR-026 이후
`kor-travel-map` 독립 프로그램/API/Admin/Dagster가 소유한다.

## 1. 핵심 원칙

- Pinvi Dagster는 `app` schema 소유 데이터만 쓴다.
- `feature` / `provider_sync` schema 적재, provider raw → DTO 변환, dedup은
  kor-travel-map 저장소 책임이다.
- Pinvi Dagster에서 `kor-travel-map` 내부 모듈이나 `AsyncKorTravelMapClient`를
  import하지 않는다.
- 외부 public API 클라이언트는 해당 Pinvi job이 `app` schema에 저장할 때만 쓴다.
  예: `python-kasi-api` 특일/출몰시각.
- app-owned job은 ADR-050의 retry/backoff, idempotency, bounded metadata,
  failure notification, destructive dry-run gate를 따른다.

자세한 운영은 [`docs/runbooks/etl.md`](../runbooks/etl.md).

## 2. 구조

> ADR-045 Phase 6(T-210c): Pinvi `apps/etl`에는 feature/provider 적재 Dagster가
> 없으므로 kor-travel-map으로 이관할 레거시 스켈레톤도 없다. 아래는 현재 구현과
> 계획(미구현)을 구분한 것이며, 상세 트리는 [`docs/runbooks/etl.md`](../runbooks/etl.md) §2.

현재 구현(2026-06-28):

```
apps/etl/
├── pyproject.toml
├── pinvi/etl/
│   ├── definitions.py     # code location (KASI + email + retention assets, jobs, schedules, sensors=[])
│   ├── resources.py       # PinviDatabaseResource, KasiResource
│   ├── schedules.py       # kasi_special_days_job + pinvi_email_outbox_job + pinvi_pii_retention_job
│   ├── jobs.py            # kasi_poi_rise_set_job (one-shot)
│   └── assets/
│       ├── pinvi_kasi_special_days.py
│       ├── pinvi_email_outbox.py
│       └── pinvi_pii_retention.py
└── tests/
```

계획(미구현, `app` schema 소유 job 후보): `sensors.py`(run_failure_sensor),
`pinvi_telegram_weekly`(D-11) / `pinvi_location_log_archive`(DEC-10).
POI 출몰시각은 별도 asset 파일이 아니라
`jobs.py`의 one-shot job(`kasi_poi_rise_set_job`)으로 구현돼 있다.

## 3. KASI assets

### 3.1 `pinvi_kasi_special_days`

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

### 3.3 `pinvi_email_outbox`

- 15분마다 KST 실행.
- `app.email_queue`의 pending due/backoff/stuck, failed, bounced, complained, retry exhausted를
  집계한다.
- template별 실패율은 최근 24시간 상위 10개 template만 metadata로 남긴다.
- 이메일 주소, payload, provider raw 응답은 metadata/API 응답에 넣지 않는다.
- 실제 발송은 FastAPI lifespan worker가 계속 담당한다.

### 3.4 `pinvi_pii_retention`

- 매일 KST 04:15 실행.
- `app.users`, OAuth identity, email verification token, user session, OAuth transient table,
  location/admin audit log의 보존 기간 만료 후보를 집계한다.
- 삭제 계정 PII grace는 30일, session grace는 30일, location retention은 6개월이다.
- `admin` / `operator` / `cpo` 역할이 있는 삭제 계정은 후보에서 제외하고
  `excluded_privileged_deleted_users`로만 보고한다.
- Sprint 5 범위는 dry-run metadata와 Admin summary 노출까지다. 실제 delete/anonymize/archive는
  T-276 kill-switch/dashboard/evidence log 범위에서 연다.

## 4. Schedule

```python
from dagster import ScheduleDefinition, define_asset_job

kasi_special_days_job = define_asset_job(
    "kasi_special_days_job",
    selection=["pinvi_kasi_special_days"],
)

pinvi_email_outbox_job = define_asset_job(
    "pinvi_email_outbox_job",
    selection=["pinvi_email_outbox"],
)

pinvi_pii_retention_job = define_asset_job(
    "pinvi_pii_retention_job",
    selection=["pinvi_pii_retention"],
)

kasi_special_days_schedule = ScheduleDefinition(
    job=kasi_special_days_job,
    cron_schedule="30 3 * * *",
    execution_timezone="Asia/Seoul",
)

pinvi_email_outbox_schedule = ScheduleDefinition(
    job=pinvi_email_outbox_job,
    cron_schedule="*/15 * * * *",
    execution_timezone="Asia/Seoul",
)

pinvi_pii_retention_schedule = ScheduleDefinition(
    job=pinvi_pii_retention_job,
    cron_schedule="15 4 * * *",
    execution_timezone="Asia/Seoul",
)
```

POI 출몰시각은 정기 schedule이 아니라 POI 생성 이벤트에서 run을 enqueue한다.

## 5. 실패 알림

Dagster `run_failure_sensor`는 retry가 모두 소진된 실패를 Sentry와
`app.telegram_system_notification_outbox`로 전달한다. 개별 asset/job은 Telegram을
직접 호출하지 않는다. 외부 API 호출 실패 시 서비스키나 요청 URL의 `serviceKey` 값은
마스킹한다.

## 6. AI agent 체크리스트

- [ ] 새 feature provider 적재가 필요하면 Pinvi가 아니라 `kor-travel-map`에 PR.
- [ ] Pinvi `apps/etl` asset은 `app` schema 소유 job인지 먼저 확인.
- [ ] KASI live 검증은 `DATA_GO_KR_SERVICE_KEY`가 있을 때만 수행.
- [ ] schedule timezone은 항상 `Asia/Seoul`.
- [ ] import 시점 DB/network access 금지.
- [ ] mutating job은 idempotency key와 dry-run/실행 gate를 문서화.
