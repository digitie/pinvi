# tasks.md — 열린 백로그

열린 진행/예정/보류 task만 둔다. 완료·머지·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 작성·유지 규칙과 반복 체크리스트는
[`docs/tasks-rule.md`](tasks-rule.md), 현재 진척과 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

## 현재 선점 / 충돌 회피

- **T-VN-08 = Codex**(`fix/t-vn-08-false-broken`):
  batch client/builder와 공용 Trip schema/domain, Web·Mobile Trip 표시, 관련 unit/integration/
  mocked/live E2E 및 계약 문서를 수정한다. TDR 검색 기능과 C6c admin client는 건드리지 않는다.
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
  브랜치는 `agent/claude-tdr-<task>`. **TDR 본편(backend+web UI) 전부 머지 완료**: T-306a(#396),
  T-301(#397), T-302(#398), T-303(#399), T-304(#400), T-305(#401), T-309c(#402), T-306(#404),
  T-307(#405+#411), T-308(#406), T-309a/b(1 PR). 잔여는 mobile mirror(TDR-mobile, 별도 train)뿐.

## kor-travel-map batch 상태 계약

- [ ] **T-VN-08** — trip view의 batch transport/contract 실패를 feature 부재로 오인하지 않고
      저장 snapshot을 유지한다. POI별 `feature_resolution_state`를
      `not_linked|found|missing|unverified`로 노출하고, `missing`만 broken count에 반영한다.
      `feature_id`는 `@`를 포함해 어떤 포맷도 해석하지 않는 불투명 문자열로 전달한다. 현재 2-state
      decoder는 exact `found|missing` key와 완전·배타 partition, detail 내부 exact ID/표시 필드,
      중복 JSON member를 fail-closed로 검증한다.

- [ ] **T-VN-11-P** — kor-travel-map `T-VN-11`의
      `found|retired|suppressed|missing|unchanged + revision` batch 응답을 typed PinVi consumer 계약으로
      같은 cutover에서 전환한다. transport 실패는 upstream 상태값으로 축약하지 않고 소비자
      `unverified` 경계를 유지하며, 현재 2-state exact partition 테스트를 5-state partition 테스트로 교체한다.

## 보안·의존성

- [x] **T-VN-SEC-01** — `npm audit` critical(`vitest<=3.2.5`)을 workspace 3곳(apps/web·packages/domain·
      packages/schemas) 일괄 vitest v4 전환으로 제거했다. rolldown-vite/oxc 충돌하는 `@vitejs/plugin-react`를
      제거하고 `oxc.jsx` automatic 런타임으로 대체했다. audit 25→20(critical 0). 잔여 20(high 7/moderate 13)은
      후속으로 T-VN-SEC-02(next 15.x 보안 패치)·T-VN-SEC-03(next-전파 transitive + Expo SDK-56)로 분리했다.
      (완료: 2026-07-28, PR #412, claude → 상세는 tasks-done.md)

- [x] **T-VN-SEC-02** — `next`를 15.5.18→**15.5.22**로 올려 request-path web CVE 8건(App Router
      Server Actions DoS·SSRF·cache confusion·Server Function endpoint 노출 등, 전부 `<15.5.21` fixed)을
      제거했다. **정정**: SEC-01의 "Next 16 major 필요" 전제는 npm audit union range(…-16.3.0-preview.7)
      오독이었고, 실제 fix는 in-range 15.x 패치다. next build/typecheck/lint/vitest 통과.
      npm audit는 여전히 `next high`로 표시하는데, 이는 next가 exact-pin한 build-time postcss@8.4.31 +
      미사용 optional sharp@0.34.5(앱은 `next/image` 미사용, 자체 postcss는 이미 8.5.23)을 전파하기
      때문이며 앱에서 exploit 불가다. override는 next의 exact pin을 만족 못 해 `npm ci`가 거부→불가.
      해당 전파분은 T-VN-SEC-03로 이관. (완료: 2026-07-28, PR #414, claude → tasks-done.md)

- [ ] **T-VN-SEC-03** — next-전파 transitive(exact-pin build-time postcss@8.4.31 + 미사용 optional
      sharp@0.34.5)와 Expo SDK-56 build-tooling transitive(brace-expansion/form-data/js-yaml/shell-quote)를
      정리한다. 전자는 next 상위 릴리스가 pin을 올릴 때 자연 해소되거나, **scoped nested override**
      (`overrides.next.{postcss,sharp}`)로 audit-green 시도 가능(단 next build 회귀 검증 + `npm ci` 수용 확인
      필수 — global override는 이미 미적용 확인). 후자는 `@pinvi/mobile` Expo peer graph ERESOLVE 때문에
      Expo SDK 상향과 함께 Sprint M-1 모바일 하드닝에서 처리한다. 모두 앱 request-path 미노출/미사용.

- [x] **T-VN-STYLE-01** — `npm run format:check` baseline을 Prettier로 일괄 포맷했다(포맷 207개, 기능
      변경 0). vendored byte-pinned 파일 12개(`apps/api/tests/contract/` SHA-256 핀 + `.agents/skills/`·
      `.claude/skills/` pg-aiguide 세트)는 원본 유지 + `.prettierignore`로 영구 제외했다.
      (완료: 2026-07-28, PR #413, claude → tasks-done.md)

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
- [x] T-304 — detail-card kind별 + generic fallback + opt-in enrichment + in-bounds price.
      **PR #400 머지 완료**(main 77aedbd). **ADR-056**.
- [x] T-305 — 전용 `app.trip_day_rise_sets` table + ETL asset + day-level rise/set read + batched
      re-seed + 완료 시그널. **PR #401 머지 완료**(2026-07-21). (ADR-055)

### 웹 UI (T-306~T-309c) — T-306a 모달 기반은 #396 머지 완료

- [x] T-306 — day-delete confirm(F2, `ConfirmDialog` 소비) + out-of-range actionable
      배너/아이콘(F1). **PR #404 머지 완료**. (dep T-301, T-306a) (ADR-056/055)
- [x] T-307 — per-day color picker(`TripDayControls`) + `display_marker_color` 렌더(지도+리스트 뱃지
      parity) + PoiEditor F7 polish + fit-bounds 확인(F6/F7). **PR #405 머지 완료**. (dep T-301) (ADR-055)
      후속: 색/이름만 바꾸는 일자 업데이트에 날짜를 강제하지 않는 friction 수정 **PR #411 머지 완료**.
- [x] T-308 — 신규 `TripDayHeader.tsx`(effective date + 공휴일 뱃지 + 일출/일몰 pending) +
      SharedTripView 렌더(F8-UI, F1 empty-date). **PR #406 머지 완료**. (dep T-301, T-305) (ADR-055)
- [x] T-309a — autocomplete 재작성: `MapSearchBox` `onSelect` union + address + source 아이콘 + 정렬 +
      debounce + attribution + back-link(F3-UI). **T-309b와 1 PR로 진행**. (dep T-302) (ADR-054)
- [x] T-309b — 외부 pick add-POI + best-effort auto-request UX + snapshot POI 렌더(F4-UI) +
      provider 파생 콘텐츠 미저장(§5.1). **T-309a와 1 PR로 진행**. (dep T-303) (ADR-054)
- [x] T-309c — `FeatureDetailModal` 본문 + 마커→상세 모달(양 지도, opt-in enrichment, weather 제외).
      **PR #402 머지 완료**. feature-less POI 모달은 T-309b 통합. (ADR-056)

## 실시간 WebSocket

- [x] T-WS-C7 — trip WebSocket reject(`accept→close`)에 env-tunable settle(기본 0.25s)을 넣어 101
      handshake를 flush → close code(4401/4403/4408 등)가 리버스 프록시 edge를 건너 살아남게 한다.
      미적용 시 브라우저가 1006으로 관측 → 클라이언트가 auth-refresh/stop을 오분류(kor-travel-map C7
      #809/#820 동일 계층, 포팅). 미인증 reject flood가 settle로 FD 증폭하지 못하게 동시 settle cap.
      **적대적 리뷰 2명(P2 DoS cap·P3 test-order 반영) 통과. PR #410 머지 완료.** edge-특정 검증은 prod(#868 해제 후).

## Sprint 6 / v1.0.0 후속 Task 초안

- [ ] T-273 — v1.0.0 E2E / Live Gate. 남은 hard blocker는 geofence 운영 설정이다.
      mutating suite는 local dev에서 통과했으며, 전용 staging Web/API는 release evidence 재실행 조건이다.
- [ ] T-274 — v1.0.0 릴리즈.

## 보류 / 미래 작업

(현재 없음 — TDR-mobile은 완료, `docs/tasks-done.md` 참조.)
