# tasks.md — 열린 백로그

열린 진행/예정/보류 task만 둔다. 완료·머지·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 작성·유지 규칙과 반복 체크리스트는
[`docs/tasks-rule.md`](tasks-rule.md), 현재 진척과 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

## 현재 선점 / 충돌 회피

- **T-VN-20 / issue #394 = Codex**(`fix/ktm-public-api-key-header`):
  `apps/api/app/clients/kor_travel_map.py`의 public API 인증과 해당 unit/contract snapshot·통합 문서만
  수정한다. service token 우선순위는 유지하고 `key` query를 제거하며
  `X-Kor-Travel-Map-Api-Key` header-only 계약으로 전환한다.
- **T-ADM-C6c = Codex**(`fix/c6c-ops-contract`): `apps/api`의 kor-travel-map admin
  client·provider-sync/ETL projection, 공용 schema·provider-sync UI/E2E·문서를 수정한다. TDR
  레인과 파일이 겹치면 C6c가 선행하며, provider-sync 밖의 Web 화면 구조는 바꾸지 않는다.
- **TDR(Trip Detail Rewrite) = Claude 단독 진행**(2026-07-20 결정, 레인 A/B 분리 폐지).
  마스터 계획 `docs/execplan/trip-detail-rewrite.md`. Codex는 이 에픽 미사용. Claude가
  T-301→T-305(backend/ETL) 후 T-306~T-309c(web UI)를 DAG 순서로 직접 구현한다.
  브랜치는 `agent/claude-tdr-<task>`. 완료: T-306a(#396), T-301(#397), T-302(#398), T-303(#399).
  진행: T-304(PR 대기).

## kor-travel-map 공개 API 인증 계약 정합

- [ ] **T-VN-20 / issue #394** — kor-travel-map PR #794의 clean-cut에 맞춰 public API key를
  `X-Kor-Travel-Map-Api-Key` header로만 전송한다. URL `key` query를 제거하고 service token 우선순위,
  batch의 ServiceToken-only allowlist, exact vendored OpenAPI hash/equality, 운영 Compose env 배선과
  opt-in live HTTP smoke를 unit/contract gate로 고정한다. 단일 적대적 리뷰 승인과 로컬 gate는
  완료했으며 draft PR·CI·N150 live smoke·머지가 남았다.

## kor-travel-map admin ops 계약 복구

- [ ] **T-VN-03-P / issue #392** — 잔여 관측 read
  (`consistency/{issues,reports}`, `system-logs`, `api-call-logs`)를 PR #387의
  `ops:read` principal로 결선한다. `/ops/metrics`·`health-deep` direct caller는 부재를 고정하고
  새 caller를 만들지 않는다. PinVi [PR #393](https://github.com/digitie/pinvi/pull/393) head와
  Map [PR #782](https://github.com/digitie/kor-travel-map/pull/782) head는 C6c manifest v4 exact
  pair source에 포함해 동일 배포 단위로 전환한다. 설계는
  [`docs/execplan/t-vn-03-ops-observability-principal.md`](execplan/t-vn-03-ops-observability-principal.md).

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
> Claude 단독 진행(레인 분리 폐지). 완료: T-300(#383), T-306a 모달 기반(#396).

### 백엔드 / 데이터 (T-301~T-305)

- [x] T-301 — Day presentation backend. **PR #397 머지 완료**(main c703bb6). **ADR-055**.
- [x] T-302 — Kakao/Naver Local + 통합 `GET /search` source-tagged. **PR #398 머지 완료**(main 4ae8c8a). **ADR-054**.
- [x] T-303 — feature-request 파이프라인(source/external_ref + auto-fire + reconciliation).
      **PR #399 머지 완료**(main d0a438b). (ADR-054)
- [~] T-304 — detail-card: `GET /features/{id}/detail-card` kind별 + generic fallback + opt-in 외부
      enrichment(display-only) + in-bounds `price` kind.
      **구현 완료·검증(ruff/mypy/pytest + web) 통과, 단일 리뷰 후 PR 대기.**
      `agent/claude-tdr-detail-card`. **ADR-056**.
- [ ] T-305 — 전용 `app.trip_day_rise_sets` table + ETL asset + day-level rise/set read + batched
      re-seed(파생-date only) + 완료 시그널 + e2e seed/provider mock. (ADR-055)

### 웹 UI (T-306~T-309c) — T-306a 모달 기반은 #396 머지 완료

- [ ] T-306 — day-delete confirm(F2, `ConfirmDialog` 소비) + out-of-range actionable
      배너/아이콘(F1). (dep T-301, T-306a) (ADR-056/055)
- [ ] T-307 — per-day color picker(`TripDayControls`) + `display_marker_color` 렌더(지도+리스트 뱃지
      parity) + PoiEditor F7 polish + fit-bounds 확인(F6/F7). (dep T-301) (ADR-055)
- [ ] T-308 — 신규 `TripDayHeader.tsx`(effective date + 공휴일 뱃지 + 일출/일몰 pending) +
      SharedTripView 렌더(F8-UI, F1 empty-date). (dep T-301, T-305) (ADR-055)
- [ ] T-309a — autocomplete 재작성: `MapSearchBox` `onSelect` union + address + source 아이콘 + 정렬 +
      debounce + attribution(F3-UI). (dep T-302) (ADR-054)
- [ ] T-309b — 외부 pick add-POI + best-effort auto-request UX + snapshot POI 렌더(F4-UI).
      (dep T-303) (ADR-054)
- [ ] T-309c — `FeatureDetailModal` **본문**(T-306a shell 소비, kind별 detail-card, opt-in enrichment
      링크+attribution, 마커 팝업→detail→modal 양 지도, price kind, weather 제외)(F5-UI).
      (dep T-304, T-306a) (ADR-056)

## Sprint 6 / v1.0.0 후속 Task 초안

- [ ] T-273 — v1.0.0 E2E / Live Gate. 남은 hard blocker는 geofence 운영 설정이다.
      mutating suite는 local dev에서 통과했으며, 전용 staging Web/API는 release evidence 재실행 조건이다.
- [ ] T-274 — v1.0.0 릴리즈.

## 보류 / 미래 작업

- [ ] TDR-mobile — TDR day-color/공휴일/일출·일몰을 `apps/mobile`에 mirror(별도 release train,
      T-284 scope gate). TDR 완료 후 착수.
