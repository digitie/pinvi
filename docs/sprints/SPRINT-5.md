# SPRINT-5 — 실시간 + ETL + 운영 가시화

- **상태**: proposed
- **선행**: Sprint 4 DoD 완료
- **목표**: WebSocket 동시 편집 + Dagster 첫 적재 활성화 + Loki/Grafana + Admin
  운영 화면 (Record Linkage, provider sync, integrity, debug logs)
- **DoD**:
  - `WS /ws/trips/{trip_id}` 동작 — POI CRUD/reorder broadcast + presence
  - LWW + optimistic lock 충돌 다이얼로그
  - `apps/etl` Dagster code location 활성화 + 4 asset:
    - `python-visitkorea-api_festivals` (event, 주 1회)
    - `python-opinet-api_fuel` (price, 6시간)
    - `python-kma-api_short_term_weather` (weather, 30분)
    - `python-krheritage-api_heritage` (place/area, 주 1회) + `_events` (event, 일 1회)
  - vworld 법정동코드 임포트 trigger UI (`python-kraddr-geo`에 위임)
  - `/admin/etl` Dagit 임베드 + 자체 요약
  - `/admin/dedup-review` (라이브러리 `dedup_review_queue` callback)
  - `/admin/features/{id}/sources` / `/overrides` / `/weather-values` (M-15)
  - `/admin/provider-sync` 재시도/일시정지/재개
  - `/admin/integrity` `app.data_integrity_violations` 1차 소스
  - `/admin/debug/logs` Loki LogQL WebSocket stream
  - `/admin/debug/request/{id}` X-Request-Id 타임라인
  - Loki + Promtail + Grafana 컨테이너 활성

## 산출물

### 백엔드 (`apps/api`)

- `apps/api/app/api/v1/ws.py` (FastAPI WebSocket)
- `apps/api/app/services/realtime_broker.py` (단일 프로세스 in-memory broker)
- `apps/api/app/services/optimistic_lock.py`
- `apps/api/app/api/v1/admin/{etl,dedup_review,provider_sync,integrity,debug}.py`
- `apps/api/app/services/admin/loki_stream.py` (LogQL WebSocket)
- `apps/api/app/services/admin/request_trace.py` (X-Request-Id 조합)

### ETL (`apps/etl`, 신규 디렉토리)

- `apps/etl/pyproject.toml` (dagster + dagit + `python-krtour-map` git URL pin)
- `apps/etl/tripmate/etl/__init__.py`
- `apps/etl/tripmate/etl/definitions.py` (Dagster code location)
- `apps/etl/tripmate/etl/resources.py` (`KrtourMapResource`, `VisitKoreaResource`,
  `OpiNetResource`, `KmaResource`, `KrheritageResource`)
- `apps/etl/tripmate/etl/assets/{feature_event_festivals,feature_price_fuel,feature_weather_kma_short_term,feature_place_heritage,feature_event_heritage,feature_vworld_import}.py`
- `apps/etl/tripmate/etl/schedules.py` (cron 정의)
- `apps/etl/tests/test_definitions.py`
- `apps/etl/tests/test_asset_festivals.py` (materialize_to_memory + fixture)

### 프론트엔드

- `apps/web/lib/websocket.ts` (재연결 + heartbeat)
- `apps/web/components/poi/ConflictDialog.tsx`
- `apps/web/app/admin/etl/page.tsx`
- `apps/web/app/admin/dedup-review/page.tsx`
- `apps/web/app/admin/features/[id]/{sources,overrides,weather-values}/page.tsx`
- `apps/web/app/admin/provider-sync/page.tsx`
- `apps/web/app/admin/integrity/page.tsx`
- `apps/web/app/admin/debug/{logs,request/[id]}/page.tsx`

### 인프라

- `infra/docker-compose.yml` Loki/Promtail/Grafana 추가
- `infra/promtail/config.yml`
- `infra/loki/local-config.yaml`
- `apps/api/app/core/logging.py` structlog JSON 활성화

### 테스트

- `tests/integration/test_ws_trip_channel.py` (broadcast + close 4403)
- `tests/integration/test_optimistic_lock.py` (409 + ConflictDialog)
- `apps/etl/tests/test_asset_festivals.py`
- `apps/etl/tests/test_asset_fuel.py`
- `apps/etl/tests/test_asset_kma.py`
- `tests/integration/test_admin_dedup_review.py` (라이브러리 callback)

### ADR

- ADR-NNN: WebSocket broker 모델 (단일 프로세스 in-memory, v2 Redis Streams)
- ADR-NNN: optimistic lock + `If-Match` 정책
- ADR-NNN: Dagster asset → `AsyncKrtourMapClient` 호출 표준
- ADR-NNN: Loki retention 정책 (7일, Odroid 용량)

## SPEC V8 매핑

- 03-frontend.md §9 (J장 실시간 동기화)
- 04-admin.md §7 ~ §10 (M-10, M-11, M-12, M-15)
- 01-data.md §3 (라이브러리 위임 항목 — provider sync, dedup queue)
- 00-infrastructure.md §2.7 (Loki/Sentry/Grafana)

## ETL 첫 적재 검증 시나리오

본 Sprint 종료 직전:

1. `python-visitkorea-api_festivals` materialize → `/admin/features?kind=event` 결과 확인
2. `python-opinet-api_fuel` materialize → `/admin/features?kind=price&category=fuel`
3. `python-kma-api_short_term_weather` materialize → `/features/{id}/weather` API 응답
4. `python-krheritage-api_heritage` materialize → place/area 분리 적재
5. `/admin/dedup-review` 의심 쌍 발생 → 좌우 비교 → 판정 → 라이브러리 callback
6. `/admin/provider-sync` 일시정지 후 재개 → cursor 유지 확인

## 종료 체크리스트

- [ ] DoD 모두 통과
- [ ] WebSocket 동시 편집 5명 시뮬레이션 통과
- [ ] Dagster 4 asset 첫 적재 통과
- [ ] Loki LogQL stream Admin에서 확인
- [ ] `docs/journal.md` Sprint 5 종료 엔트리
- [ ] `docs/resume.md` "다음 한 작업" → Sprint 6
