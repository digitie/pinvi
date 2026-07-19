# tasks.md — 열린 백로그

열린 진행/예정/보류 task만 둔다. 완료·머지·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 작성·유지 규칙과 반복 체크리스트는
[`docs/tasks-rule.md`](tasks-rule.md), 현재 진척과 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

## 현재 선점 / 충돌 회피

- **T-ADM-C6c = Codex**(`fix/c6c-ops-contract`): `apps/api`의 kor-travel-map admin
  client·provider-sync/ETL projection, 공용 schema·provider-sync UI/E2E·문서를 수정한다. TDR
  레인과 파일이 겹치면 C6c가 선행하며, provider-sync 밖의 Web 화면 구조는 바꾸지 않는다.
- **TDR(Trip Detail Rewrite) 레인 분리** — 마스터 계획 `docs/execplan/trip-detail-rewrite.md`.
  파일 소유로 A/B 충돌을 막는다.
  - **레인 B = Codex**(`agent/codex-tdr-*`): `apps/api`, `apps/etl`, `packages/schemas`,
    `packages/api-client`, `docs/`(ADR/api), migrations, CHANGELOG, seed. → T-301~T-305.
  - **레인 A = Claude**(`agent/claude-tdr-*`): `apps/web/components`, `apps/web/lib`,
    `packages/domain`(small). → T-306~T-309c.
  - 공유 계약 필드는 **B가 먼저 정의**, A가 소비. `packages/domain/src/marker.ts`는 A가 소유하되
    web+mobile 공유이므로 pure 유지(`dayColor` optional). 자세한 파일 소유·DAG는 execplan §3.2/§3.1.

## kor-travel-map admin ops 계약 복구

- [ ] **T-ADM-C6c** — PR #724 이후 삭제된
  `/v1/ops/dagster/summary`·`/v1/ops/providers*`·`/v1/ops/import-jobs*` 호출을 제거하고,
  `/v1/ops/datasets`·`/v1/ops/pipeline/{overview,executions}`·canonical cancellation으로
  전환한다. kor-travel-map 전용 service/operator principal은 read/cancel capability를 분리하며,
  Pinvi server가 frontend BFF secret을 전송하거나 trusted CIDR 확대에 의존하지 않는다.
  양 저장소 contract test, 배포 순서(map → Pinvi), 직전 image rollback smoke가 완료 조건이다.
  - 구현 완료, 검증 대기: exact 운영 URL allowlist, canonical `PINVI_ENVIRONMENT`, 비운영 token pair
    fail-close, 취소 detail/list reconciliation과 blind retry 잠금, provider schedule 출처 degraded 배너.
    결정적 400/401/403/422/429와 exact `404 PIPELINE_EXECUTION_NOT_FOUND` 거절은 reconciliation에서
    제외하고 사유 수정·재시도를 허용하며, 그 밖의 404는 미확정 잠금을 유지한다.
  - 남은 완료 gate: WSL 정적/단위/통합/Web gate, map·Pinvi 동일 image 조합, N150 prod live UI E2E.

## TDR — Trip Detail Rewrite (T-300~T-309c)

> 계약·설계 정본: ADR-054/055/056(`docs/decisions.md`) + `docs/execplan/trip-detail-rewrite.md`.
> T-300(공휴일 read-path)은 **PR #383로 main 머지 완료** → 아래 open task만 남는다.

### 레인 B (Codex, backend/data/external)

- [ ] T-301 — Day presentation backend. `trip_days.marker_color`(nullable+inherit),
      effective_date 파생(ensure_trip_day materialize 폐지), out_of_range, POI별
      `display_marker_color`, DELETE-day 409 `DAY_HAS_POIS` guard, day schema 양 언어,
      shared-view emit. **ADR-055**. (선점 시 `agent/codex-tdr-day-presentation`)
- [ ] T-302 — Kakao/Naver Local client + config + `GET /search` typed source-tagged(address 포함,
      `/features/search` 삭제) + location_audit + quota/cache + api-client + `docs/api/search.md` +
      `docs/integrations/kakao-naver-local.md` 연결. **ADR-054**.
- [ ] T-303 — feature-request 파이프라인: `source`/`external_ref` first-class(POI+suggestion),
      best-effort decoupled auto-fire, GLOBAL dedup, post-approval reconciliation. (ADR-054)
- [ ] T-304 — detail-card: `GET /features/{id}/detail-card` kind별 + generic fallback + opt-in 외부
      enrichment(display-only) + in-bounds `price` kind. **ADR-056**.
- [ ] T-305 — 전용 `app.trip_day_rise_sets` table + ETL asset + day-level rise/set read + batched
      re-seed(파생-date only) + 완료 시그널 + e2e seed/provider mock. (ADR-055)

### 레인 A (Claude, web/domain UI)

- [ ] T-306 — 공용 `useModalDialog` 훅 + `ConfirmDialog` + day-delete confirm(F2) + out-of-range
      actionable 배너/아이콘(F1). (dep T-301) (ADR-056/055)
- [ ] T-307 — per-day color picker(`TripDayControls`) + `display_marker_color` 렌더(지도+리스트 뱃지
      parity) + PoiEditor F7 polish + fit-bounds 확인(F6/F7). (dep T-301) (ADR-055)
- [ ] T-308 — 신규 `TripDayHeader.tsx`(effective date + 공휴일 뱃지 + 일출/일몰 pending) +
      SharedTripView 렌더(F8-UI, F1 empty-date). (dep T-301, T-305) (ADR-055)
- [ ] T-309a — autocomplete 재작성: `MapSearchBox` `onSelect` union + address + source 아이콘 + 정렬 +
      debounce + attribution(F3-UI). (dep T-302) (ADR-054)
- [ ] T-309b — 외부 pick add-POI + best-effort auto-request UX + snapshot POI 렌더(F4-UI).
      (dep T-303) (ADR-054)
- [ ] T-309c — `FeatureDetailModal`(bottom sheet, kind별, opt-in enrichment 링크+attribution, 마커
      팝업→detail→modal 양 지도, price kind, weather 제외)(F5-UI). (dep T-304) (ADR-056)

## Sprint 6 / v1.0.0 후속 Task 초안

- [ ] T-273 — v1.0.0 E2E / Live Gate. 남은 hard blocker는 geofence 운영 설정이다.
      mutating suite는 local dev에서 통과했으며, 전용 staging Web/API는 release evidence 재실행 조건이다.
- [ ] T-274 — v1.0.0 릴리즈.

## 보류 / 미래 작업

- [ ] TDR-mobile — TDR day-color/공휴일/일출·일몰을 `apps/mobile`에 mirror(별도 release train,
      T-284 scope gate). TDR 완료 후 착수.
