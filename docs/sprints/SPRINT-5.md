# SPRINT-5 — 실시간 + ETL + 운영 가시화 + Backup/Restore 1차

- **상태**: in progress / 상세 Task 계획 수립 및 PR 리뷰 gap 반영. 일부 선반영: T-067 KASI,
  T-109 geofencing,
  T-110 Grafana, T-115 backup foundation. post-v0.1.0 main에는 Admin 운영 화면,
  ETL/provider sync read view, Grafana prod URL, dashboard/system 운영 지표, dedup/integrity
  action 일부, Trip WebSocket frontend client 1차 연결이 추가됐다(T-207~T-232).
  남은 세부 Task와 live e2e 카탈로그는 `docs/execplan/sprint5-v020-release-plan.md`
  (T-233, PR 리뷰 반영 T-256~T-258 포함)에서 관리한다.
- **선행**: Sprint 4 DoD 완료 (v0.1.0 릴리즈됨). 단 DEC-06에 따라 live feature
  read(T-066)가 v0.1.0 게이트다.
- **목표**: WebSocket 동시 편집 + Dagster 첫 적재 활성화 + Prometheus/Grafana +
  Loki + Admin
  운영 화면 (Record Linkage, provider sync, integrity, debug logs) +
  **Grafana iframe embed** + **Backup/Restore 1차 (script + endpoint + 수동
  snapshot UI, 핫스왑 restore UI는 Sprint 6)**
- **릴리즈**: `v0.2.0` (Sprint 5 종료 시 tag). 운영 가시화 + 데이터 적재 활성화.
- **남은 release gate**: WebSocket 후속(conflict UX, token refresh, TanStack invalidation),
  app-owned ETL 추가 job, Loki/request timeline stream, 지도 마커/색상 parity,
  backup/restore 1차 스테이징 훈련, legal/ops preflight crosswalk, `v0.2.0` Release notes.
- **DoD**:
  - `WS /ws/trips/{trip_id}` 동작 — POI CRUD/reorder broadcast + presence
  - LWW + optimistic lock 충돌 다이얼로그
  - PR 리뷰 gap crosswalk — PIPA incident, DSR, retention execution, email suppression,
    moderation, RBAC, user lifecycle, rate-limit/abuse, provider tracking, mobile/AI scope가
    Sprint 6 Task로 연결됨
  - `apps/etl` Dagster code location 활성화 + Pinvi `app` schema 소유 job:
    - `pinvi_kasi_special_days` (특일 5개 dataset, 일 1회) + POI
      `kasi_poi_rise_set_job` one-shot (T-067 선행 완료)
    - (계획) `pinvi_email_outbox`, `pinvi_pii_retention`,
      `pinvi_location_log_archive`, `pinvi_telegram_weekly`
    - feature/provider 적재 asset(VisitKorea/OpiNet/KMA/KrHeritage 등)은
      `kor-travel-map` 소유이며 본 저장소 ETL에 추가하지 않는다(ADR-026/T-210c).
  - vworld 법정동코드 임포트 trigger UI (`kor-travel-geo`에 위임)
  - `/admin/etl` Dagit 임베드 + 자체 요약
  - `/admin/dedup-review` (라이브러리 `dedup_review_queue` callback)
  - `/admin/features/{id}/sources` / `/overrides` / `/weather-values` (M-15)
  - `/admin/provider-sync` 재시도/일시정지/재개
  - `/admin/integrity` `app.data_integrity_violations` 1차 소스
  - `/admin/debug/logs` Loki LogQL WebSocket stream
  - `/admin/debug/request/{id}` X-Request-Id 타임라인
  - Prometheus + cAdvisor + Grafana 컨테이너 활성
  - Loki + Promtail 로그 수집은 후속 또는 운영 선택 계층
  - **`/admin/grafana` Grafana iframe embed** (ADR-022 보조,
    `docs/runbooks/grafana-admin-embed.md`)
  - **`scripts/backup-db.sh` + `scripts/restore-db.sh`** — pg_dump --custom +
    pg_restore. 핫스왑 워크플로 design은 Sprint 6에서 finalize (ADR-022).
  - **`POST /admin/backup/snapshot`** — manual trigger (admin role) → backup
    file 생성 + sha256 + admin_audit_log 기록. RustFS 또는 외부 위치 미러는 후속
    운영 보강.

## 산출물

### 2026-06-27 범위 정리

이미 main에 반영된 항목:

- `/admin/etl`, `/admin/provider-sync` read view와 Pinvi ETL registry / upstream ops proxy.
- `/admin/dedup-review`, `/admin/integrity`, `/admin/debug/logs` read view와 dedup/integrity action 일부.
- `/admin/grafana` prod public URL 주입 경로.
- `/admin` dashboard 운영 그래프/부하/용량 요약.
- `/admin/system` 의존 API + Docker collector 상태 화면.
- Admin 여행/POI 생성, 상세 drill-down, 파일/아바타/RustFS quota, 복사·이동·삭제 운영 기능.
- Trip 상세 화면 WebSocket wrapper + presence summary + domain event debounce reload.

남은 `v0.2.0` 후보 gate:

- `WS /ws/trips/{trip_id}` 후속: TanStack Query invalidation, 공유 presence store,
  401 close token refresh, conflict UX. Day rename/delete optimistic lock API gap은 T-287로 분리한다.
- 사용자/Admin 지도뷰 marker palette, POI custom color/icon, feature snapshot/upstream category
  fallback, selected/broken/cluster 상태 parity.
- Pinvi `app` schema 소유 ETL 추가 job(`email_outbox`, PII retention, location archive,
  telegram weekly/daily summary).
- Loki/Promtail 또는 대체 로그 stream과 request timeline.
- Backup/restore 1차 스크립트/endpoint의 스테이징 복구 훈련.
- 리뷰 반영 legal/ops preflight: incident/DSR/retention execution/email suppression/RBAC/user lifecycle/
  abuse 운영 표면을 Sprint 6 Task로 고정.
- `v0.2.0` tag/GitHub Release notes.

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
- `apps/etl/pinvi/etl/__init__.py`
- `apps/etl/pinvi/etl/definitions.py` (Dagster code location)
- `apps/etl/pinvi/etl/resources.py` (`PinviDatabaseResource`, `KasiResource`)
- `apps/etl/pinvi/etl/assets/pinvi_kasi_special_days.py`
- `apps/etl/pinvi/etl/jobs.py` (`kasi_poi_rise_set_job`)
- `apps/etl/pinvi/etl/schedules.py`
- `apps/etl/pinvi/etl/assets/{pinvi_email_outbox,pinvi_pii_retention,pinvi_location_log_archive,pinvi_telegram_weekly}.py`
  (계획, `app` schema 소유 job일 때만)
- `apps/etl/tests/test_definitions.py`
- `apps/etl/tests/test_kasi_special_days.py`
- `apps/etl/tests/test_email_outbox.py` / `test_pii_retention.py` (계획)

### 프론트엔드

- `packages/api-client/src/websocket.ts` (재연결 + heartbeat)
- `apps/web/components/trips/TripDetail.tsx` (presence summary + domain event debounce reload)
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

- `infra/docker-compose.yml` Prometheus/cAdvisor/Grafana 추가
- `infra/prometheus/prometheus.yml`
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

- **ADR-035**: WebSocket broker 모델 (단일 프로세스 in-memory, v2 Redis Streams 또는
  PostgreSQL LISTEN/NOTIFY)
- 후속 ADR 후보(번호 미배정): optimistic lock + `If-Match` 정책
- 후속 ADR 후보(번호 미배정): Pinvi Dagster `app` schema job 표준 (KASI/알림/보존정책)
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

1. `pinvi_kasi_special_days` materialize → `app.kasi_special_days` upsert 확인
2. `kasi_poi_rise_set_job` 단일 POI 실행 → `app.trip_poi_rise_sets` success/failed 확인
3. `pinvi_email_outbox` / retention 계열 job은 `app` schema만 변경하는지 확인
   - retention 계열은 Sprint 5에서 dry-run까지, 실제 delete/anonymize/archive는 T-276으로 닫는다.
4. feature/provider materialize 검증(VisitKorea/OpiNet/KMA/KrHeritage 등)은
   `kor-travel-map` 저장소의 Sprint/런북에서 수행
5. `/admin/dedup-review` 의심 쌍 발생 → 좌우 비교 → 판정 → 라이브러리 callback
6. `/admin/provider-sync` 일시정지 후 재개 → cursor 유지 확인

## 종료 체크리스트

- [ ] DoD 모두 통과
- [ ] WebSocket 동시 편집 5명 시뮬레이션 통과
- [ ] Dagster app-owned asset/job 첫 적재 통과
- [ ] Prometheus scrape target UP + API p95/request dashboard 확인
- [ ] Loki LogQL stream Admin에서 확인(후속/선택)
- [ ] **Grafana iframe `/admin/grafana`에서 표시 + dashboard 4개 동작**
- [ ] **`scripts/backup-db.sh` 수동 실행 → restore까지 통과 (스테이징)**
- [ ] **`POST /admin/backup/snapshot` 1회 트리거 후 admin_audit_log 기록 확인**
- [ ] **PR 리뷰 legal/ops gap crosswalk 완료 — T-256~T-258 기준**
- [ ] **`v0.2.0` git tag + GitHub Release notes**
- [ ] `docs/journal.md` Sprint 5 종료 엔트리
- [ ] `docs/resume.md` "다음 한 작업" → Sprint 6
