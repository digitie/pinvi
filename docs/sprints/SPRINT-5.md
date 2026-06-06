# SPRINT-5 — 실시간 + ETL + 운영 가시화 + Backup/Restore 1차

- **상태**: proposed (일부 선반영: T-067 KASI, T-109 geofencing, T-110 Grafana,
  T-115 backup foundation)
- **선행**: Sprint 4 DoD 완료 (v0.1.0 릴리즈됨). 단 DEC-06에 따라 live feature
  read(T-066)가 v0.1.0 게이트다.
- **목표**: WebSocket 동시 편집 + Dagster 첫 적재 활성화 + Loki/Grafana + Admin
  운영 화면 (Record Linkage, provider sync, integrity, debug logs) +
  **Grafana iframe embed** + **Backup/Restore 1차 (script + endpoint + 수동
  snapshot UI, 핫스왑 restore UI는 Sprint 6)**
- **릴리즈**: `v0.2.0` (Sprint 5 종료 시 tag). 운영 가시화 + 데이터 적재 활성화.
- **DoD**:
  - `WS /ws/trips/{trip_id}` 동작 — POI CRUD/reorder broadcast + presence
  - LWW + optimistic lock 충돌 다이얼로그
  - `apps/etl` Dagster code location 활성화 + TripMate `app` schema 소유 job:
    - `tripmate_kasi_special_days` (특일 5개 dataset, 일 1회) + POI
      `kasi_poi_rise_set_job` one-shot (T-067 선행 완료)
    - (계획) `tripmate_email_outbox`, `tripmate_pii_retention`,
      `tripmate_location_log_archive`, `tripmate_telegram_weekly`
    - feature/provider 적재 asset(VisitKorea/OpiNet/KMA/KrHeritage 등)은
      `python-krtour-map` 소유이며 본 저장소 ETL에 추가하지 않는다(ADR-026/T-210c).
  - vworld 법정동코드 임포트 trigger UI (`python-kraddr-geo`에 위임)
  - `/admin/etl` Dagit 임베드 + 자체 요약
  - `/admin/dedup-review` (라이브러리 `dedup_review_queue` callback)
  - `/admin/features/{id}/sources` / `/overrides` / `/weather-values` (M-15)
  - `/admin/provider-sync` 재시도/일시정지/재개
  - `/admin/integrity` `app.data_integrity_violations` 1차 소스
  - `/admin/debug/logs` Loki LogQL WebSocket stream
  - `/admin/debug/request/{id}` X-Request-Id 타임라인
  - Loki + Promtail + Grafana 컨테이너 활성
  - **`/admin/grafana` Grafana iframe embed** (ADR-022 보조,
    `docs/runbooks/grafana-admin-embed.md`)
  - **`scripts/backup-db.sh` + `scripts/restore-db.sh`** — pg_dump --custom +
    pg_restore. 핫스왑 워크플로 design은 Sprint 6에서 finalize (ADR-022).
  - **`POST /admin/backup/snapshot`** — manual trigger (admin role) → backup
    file 생성 + sha256 + admin_audit_log 기록. RustFS 또는 외부 위치 미러는 후속
    운영 보강.

## 산출물

### 백엔드 (`apps/api`)

- `apps/api/app/api/v1/ws.py` (FastAPI WebSocket)
- `apps/api/app/services/realtime_broker.py` (단일 프로세스 in-memory broker)
- `apps/api/app/services/optimistic_lock.py`
- `apps/api/app/api/v1/admin/{etl,dedup_review,provider_sync,integrity,debug,grafana,backup}.py`
- `apps/api/app/services/admin/loki_stream.py` (LogQL WebSocket)
- `apps/api/app/services/admin/request_trace.py` (X-Request-Id 조합)
- `apps/api/app/services/backup_service.py` — pg_dump trigger + audit.
  `scripts/backup-db.sh` 호출 wrapper. RustFS/external mirror는 후속 운영 보강.

### ETL (`apps/etl`)

- `apps/etl/pyproject.toml` (dagster + dagster-webserver + provider client git URL pin)
- `apps/etl/tripmate/etl/__init__.py`
- `apps/etl/tripmate/etl/definitions.py` (Dagster code location)
- `apps/etl/tripmate/etl/resources.py` (`TripmateDatabaseResource`, `KasiResource`)
- `apps/etl/tripmate/etl/assets/tripmate_kasi_special_days.py`
- `apps/etl/tripmate/etl/jobs.py` (`kasi_poi_rise_set_job`)
- `apps/etl/tripmate/etl/schedules.py`
- `apps/etl/tripmate/etl/assets/{tripmate_email_outbox,tripmate_pii_retention,tripmate_location_log_archive,tripmate_telegram_weekly}.py`
  (계획, `app` schema 소유 job일 때만)
- `apps/etl/tests/test_definitions.py`
- `apps/etl/tests/test_kasi_special_days.py`
- `apps/etl/tests/test_email_outbox.py` / `test_pii_retention.py` (계획)

### 프론트엔드

- `apps/web/lib/websocket.ts` (재연결 + heartbeat)
- `apps/web/components/poi/ConflictDialog.tsx`
- `apps/web/app/admin/etl/page.tsx`
- `apps/web/app/admin/dedup-review/page.tsx`
- `apps/web/app/admin/features/[id]/{sources,overrides,weather-values}/page.tsx`
- `apps/web/app/admin/provider-sync/page.tsx`
- `apps/web/app/admin/integrity/page.tsx`
- `apps/web/app/admin/debug/{logs,request/[id]}/page.tsx`
- `apps/web/app/admin/grafana/page.tsx` — Grafana iframe (anonymous viewer URL
  + `frame-ancestors` CSP 허용, `docs/runbooks/grafana-admin-embed.md`)
- `apps/web/app/admin/backup/page.tsx` — manual snapshot trigger 버튼 (UI 본격은
  Sprint 6, 본 Sprint는 trigger + 결과 표시만)

### 인프라

- `infra/docker-compose.yml` Loki/Promtail/Grafana 추가
- `infra/promtail/config.yml`
- `infra/loki/local-config.yaml`
- `infra/grafana/{provisioning,dashboards}/` — anonymous viewer + 기본 dashboard
  (API p95 latency / DB pool / WS 연결 / ETL 자산 상태)
- `apps/api/app/core/logging.py` structlog JSON 활성화
- `scripts/backup-db.sh` — pg_dump --custom → 결과를 RustFS + 옵션 외부 NAS로
- `scripts/restore-db.sh` — pg_restore. 본 Sprint는 manual / SSH only. 핫스왑
  자동화는 Sprint 6 (ADR-022 finalize)

### 테스트

- `tests/integration/test_ws_trip_channel.py` (broadcast + close 4403)
- `tests/integration/test_optimistic_lock.py` (409 + ConflictDialog)
- `apps/etl/tests/test_email_outbox.py`
- `apps/etl/tests/test_pii_retention.py`
- `tests/integration/test_admin_dedup_review.py` (라이브러리 callback)

### ADR

- 후속 ADR 후보(번호 미배정): WebSocket broker 모델 (단일 프로세스 in-memory, v2 Redis
  Streams)
- 후속 ADR 후보(번호 미배정): optimistic lock + `If-Match` 정책
- 후속 ADR 후보(번호 미배정): TripMate Dagster `app` schema job 표준 (KASI/알림/보존정책)
- 후속 ADR 후보(번호 미배정): Loki retention 정책 (7일, Odroid 용량)
- ADR-022 (참조): Backup/Restore 핫스왑 정책 — 본 Sprint는 script + endpoint만,
  Sprint 6에서 UI + 핫스왑 finalize
- 후속 ADR 후보(번호 미배정): Grafana anonymous viewer + frame-ancestors CSP (admin embed)

## SPEC V8 매핑

- 03-frontend.md §9 (J장 실시간 동기화)
- 04-admin.md §7 ~ §10 (M-10, M-11, M-12, M-15)
- 01-data.md §3 (라이브러리 위임 항목 — provider sync, dedup queue)
- 00-infrastructure.md §2.7 (Loki/Sentry/Grafana)

## ETL 첫 적재 검증 시나리오

본 Sprint 종료 직전:

1. `tripmate_kasi_special_days` materialize → `app.kasi_special_days` upsert 확인
2. `kasi_poi_rise_set_job` 단일 POI 실행 → `app.trip_poi_rise_sets` success/failed 확인
3. `tripmate_email_outbox` / retention 계열 job은 `app` schema만 변경하는지 확인
4. feature/provider materialize 검증(VisitKorea/OpiNet/KMA/KrHeritage 등)은
   `python-krtour-map` 저장소의 Sprint/런북에서 수행
5. `/admin/dedup-review` 의심 쌍 발생 → 좌우 비교 → 판정 → 라이브러리 callback
6. `/admin/provider-sync` 일시정지 후 재개 → cursor 유지 확인

## 종료 체크리스트

- [ ] DoD 모두 통과
- [ ] WebSocket 동시 편집 5명 시뮬레이션 통과
- [ ] Dagster app-owned asset/job 첫 적재 통과
- [ ] Loki LogQL stream Admin에서 확인
- [ ] **Grafana iframe `/admin/grafana`에서 표시 + dashboard 4개 동작**
- [ ] **`scripts/backup-db.sh` 수동 실행 → restore까지 통과 (스테이징)**
- [ ] **`POST /admin/backup/snapshot` 1회 트리거 후 admin_audit_log 기록 확인**
- [ ] **`v0.2.0` git tag + GitHub Release notes**
- [ ] `docs/journal.md` Sprint 5 종료 엔트리
- [ ] `docs/resume.md` "다음 한 작업" → Sprint 6
