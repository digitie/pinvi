# tasks.md — 열린 백로그

열린 진행/예정/보류 task만 둔다. 완료·머지·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 작성·유지 규칙과 반복 체크리스트는
[`docs/tasks-rule.md`](tasks-rule.md), 현재 진척과 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

## 현재 선점 / 충돌 회피

- **TDR(Trip Detail Rewrite) = Claude 단독 진행**(2026-07-20 결정, 레인 A/B 분리 폐지).
  마스터 계획 `docs/execplan/trip-detail-rewrite.md`. Codex는 이 에픽 미사용. Claude가
  T-301→T-305(backend/ETL) 후 T-306~T-309c(web UI)를 DAG 순서로 직접 구현한다.
  브랜치는 `agent/claude-tdr-<task>`. 완료: T-306a(#396), T-301(#397), T-302(#398), T-303(#399),
  T-304(#400), T-309c(#402). 진행: T-305(PR #401 대기). **backend(T-301~305) 완료 임박, 남은 것=web UI.**

## kor-travel-map compatible pair

- [ ] **T-VN-41-P — cache-target generation·outbox paired consumer** — Map ADR-081 /
      `T-VN-41A/B/C`와 맞물려 POI canonical source generation, transaction-coupled command
      outbox, strict pull inbox/ACK/NACK/DLQ/replay, restore epoch barrier, fixed snapshot Merkle,
      durable cache invalidation과 default-off fail-closed gate를 구현한다. admin 인증은 사용하지 않고
      command/consumer/restore-fence/recovery principal을 분리한다. 실행 정본:
      `docs/execplan/t-vn-41-cache-target-consumer.md`. production enable 전 snapshot replay lower-bound
      inbox dedupe, DB advisory cross-process single-flight, snapshot 전용 timeout, 429/503 `Retry-After`,
      exact 100,000개 latency/RSS와 100,001개 413 non-retry를 n150에서 증명한다. generation 7에서는
      command=`cache-target:command`, consumer 역할=`cache-target:read/claim/ack/nack/snapshot` exact
      5개 배열로 clean-cut하고 legacy `cache-target:consumer` scope와 generation 6 조합, token swap을
      fail-close한다(ADR-059). migration 0048의 durable run 정본과 ordinary command/consumer token만 쓰는
      `pinvi-cache-target-causal-canary`로 PUT→event apply→ACK→cache generation→DELETE와 성공 transaction의
      fresh command/event/ACK provenance, remote stream-before/snapshot/stream-after control, local/remote
      cursor 3종·count·Merkle 및 pending/leased/dead 0을 production에서 증명한다. final commit은
      `csv5 → Map H35 gc → final all-writer fence → Map typed evidence → Pin finalize` 순서이며 finalize는
      HTTP 없이 stopped-Map evidence와 fresh Pin DB evidence를 대조한다. canonical request/Map/fence/evidence는
      append-only audit 한 행과 fresh Manager 재조회로 결박한다.
      - [x] Map generation 7 artifact owner `1285ff4974a2fa8d4b71f810dc9fca249397e8fc`, functional owner
        `9b945ce832ecc3ed037d66c9d4e7bda9a1a69ae0`, service OpenAPI SHA-256
        `622ea54c98e9b0c09592cf84aced36227992c6bdf256742a3532b892f0efccf2`를 vendored bytes/runtime
        generation `7`과 함께 exact pin하고 generation 6, 17-route scope drift, command/consumer token swap
        음성 gate를 고정했다.
      - [ ] n150에서 generation 7 token-swap 음성과 causal canary receipt를 포함한 paired live proof를 남긴다.

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
- [~] T-305 — 전용 `app.trip_day_rise_sets` table + ETL asset + day-level rise/set read + batched
  re-seed + 완료 시그널. **구현 완료·검증·단일 리뷰(ETL 경합 P2 반영) 통과, PR #401 대기.**
  `agent/claude-tdr-day-rise-set`. (ADR-055)

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

- [ ] TDR-mobile — TDR day-color/공휴일/일출·일몰을 `apps/mobile`에 mirror(별도 release train,
      T-284 scope gate). TDR 완료 후 착수.
