# tasks.md — 열린 백로그

열린 진행/예정/보류 task만 둔다. 완료·머지·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 작성·유지 규칙과 반복 체크리스트는
[`docs/tasks-rule.md`](tasks-rule.md), 현재 진척과 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

## 현재 선점 / 충돌 회피

- **TDR(Trip Detail Rewrite) = Claude 단독 진행**(2026-07-20 결정, 레인 A/B 분리 폐지).
  마스터 계획 `docs/execplan/trip-detail-rewrite.md`. Codex는 이 에픽 미사용. Claude가
  T-301→T-305(backend/ETL) 후 T-306~T-309c(web UI)를 DAG 순서로 직접 구현한다.
  브랜치는 `agent/claude-tdr-<task>`. **TDR 본편(backend+web UI) 전부 머지 완료**: T-306a(#396),
  T-301(#397), T-302(#398), T-303(#399), T-304(#400), T-305(#401), T-309c(#402), T-306(#404),
  T-307(#405+#411), T-308(#406), T-309a/b(1 PR). 잔여는 mobile mirror(TDR-mobile, 별도 train)뿐.
- **T-VN-41-F1D-C1a = Codex** — `feat/tvn41-pinvi-candidate-head`는 PinVi 후보 이미지의
  DB·credential 비접근 static Alembic head 검사와 해당 CLI 계약만 변경한다. Manager/Map 파일과
  ordinary API 동작은 이 PR 범위 밖이다.

## T-VN-41 runtime rebootstrap

- [/] **T-VN-41-F1D-C1a — PinVi 후보 migration head 검사** — `pinvi-admin-bootstrap head`가
  후보 이미지의 `__file__` 고정 루트에서 revision module을 실행하지 않는 AST literal graph로 exact
  단일 head를 JSON으로 반환하고, 동적·0개·복수·설정 오류는 typed fail-closed error로 종료한다.
- [/] **T-VN-41-F1D-C1b — PinVi seven-image provenance** — API뿐 아니라 Web·Dagster image도
  동일한 exact `PINVI_SOURCE_REVISION`과 `PINVI_BUILD_ENVIRONMENT` OCI label을 image 자체에
  기록한다. Manager candidate는 세 label이 모두 release pin과 일치할 때만 DB reset 단계로 진행한다.
  PinVi deploy wrapper도 build/pull/up 전에 선택한 runtime image label을 같은 입력과 대조한다.
  DB·DSN·credential file·현재 작업 디렉터리는 읽지 않는다.

## kor-travel-map compatible pair

- [/] **T-VN-42 — Map user OpenAPI 재vendor(`95d2c128`) 소비 정렬** —
      브랜치 `chore/revendor-map-user-spec`. 스냅샷 SHA-256 `6a2ee0f9…`(Map `95d2c128`·`origin/main`
      284fd10c와 바이트 동일). consumer drift 2건을 흡수한다: ① 3축 feature state cutover(`1f2bdc3a`)로
      user 표면에서 사라진 `status` 소비 절단, ② bitemporal cutover(`6650aa71`)로 옮겨간 시점 조회
      (`…/weather/snapshot`, `target_at`/`known_at`)와 `WeatherCardData.asof` → `selected_at` 개명.
      곁들여 transport 시간대 정책을 하나로 통일했다(aware만 수용 + 라우터에서 KST 보정).
  - [x] user 표면 `status` 소비 절단 + **누출 방지 회귀 테스트**(단위/통합, 되돌리면 red).
  - [x] 시점 조회 snapshot 경로 복구 + query 계약 exact 핀(`/weather`는 빈 집합).
  - [x] 공개 문서 정정(`docs/api/features.md` §1.1·§2.3, `docs/integrations/kor-travel-map-rest-api.md`).
  - [/] **admin 표면 3축 정렬(같은 PR, 병렬 레인)** — Map admin `AdminFeatureRecord`/
        `AdminFeatureDetailFeatureRecord`에도 `status`가 없다. `schemas/admin.py`가 이를 required로
        두고 있어 PinVi admin의 feature 목록/상세가 502 `FEATURE_SERVICE_BAD_GATEWAY`였고,
        `lifecycle_state`/`publication_state`/`quality_state` 3축 + admin client query 이름
        (`status`/`provider`/`dataset_key` → 3축/`provider_dataset_id`)으로 재배선 중이다.
  - [x] **user client query 폐쇄 게이트** — `_CLIENT_QUERY_PARAMETERS`가 `_CLIENT_PATHS` 전체를
        덮도록 폐쇄 단언을 걸고(면제 없음), "client가 스냅샷에 없는 query를 보내는지"를 MockTransport로
        보는 반대 방향 게이트를 신설했다. 그 구멍으로 살아 있던 `/v1/categories?active_only=` 전송을
        제거하고, Pinvi 표면의 `active_only`는 응답 `is_active`로 **로컬 필터**로 구현했다
        (공개/admin 두 라우터 + 문서 + 테스트). `_CLIENT_PATHS` 목록 자체도 client 소스의 `/v1/...`
        리터럴과 양방향 정확 일치를 강제해(정적 스캔) "목록에 안 적어서 검사도 안 되는" 구멍을 닫았다.
  - [ ] **admin weather-values 경로 전환** — `api/v1/admin/features.py`가 user 경로를 써서 비공개
        feature의 admin 조회가 404다. Map admin 전용 `GET /v1/admin/features/{id}/weather`로 옮긴다.
        (같은 핸들러의 `asof` 보정은 라운드 2에서 `normalize_asof_query()` 통과로 해결됨.)
  - [ ] **admin 상세 `state_transitions`/`curations` 투영** — Map admin 상세가 주는 list는
        sources/issues/overrides/files/**state_transitions**/**curations**이고 Pinvi가 남겨 둔
        `versions`/`change_requests`는 늘 빈 배열이다. Web 상세의 거짓 0 카운트 칩은 제거했고, 두 list를
        실제로 투영하는 것은 아래 admin 스냅샷 vendoring과 함께 한다.
  - [ ] **admin OpenAPI 스냅샷 vendoring** — 지금 계약 게이트는 user 스냅샷만 본다. 위 admin 드리프트가
        CI에 전혀 잡히지 않은 근본 원인이므로 admin 스냅샷도 핀하고 소비 필드/query 계약을 건다.
  - [ ] **공개 `status` 필드 제거(별도 breaking cutover)** — `FeatureSummary`/`FeatureDetail`/
        `DetailCardBase`(`app/schemas/feature.py`)는 지금 항상 None인 `status`를 web/mobile 계약 때문에
        남겨 두고 있다. web/mobile 소비처와 함께 정리한다.

- [/] **T-VN-40 PinVi canonical curation consumer** — Map legacy curated-feature snapshot 대신
  collection/item UUID service snapshot을 소비한다. bigint revision/strong ETag/item-set receipt,
  actor-scoped import idempotency, plan/POI mutation+audit 단일 transaction을 먼저 완료하고 legacy
  admin snapshot/client/source ID 열을 제거한 뒤 paired service receipt와 n150 live import를 닫는다.
  - Docker Manager PR #174의 raw PinVi token→Map digest 경계는 draft 상태다. 병합 후 n150 canonical
    import/backfill live acceptance와 exact paired receipt를 확인하기 전에는 receipt complete와 legacy
    source column·route의 물리 삭제를 금지한다.
- [/] **T-VN-41-ABC — cache target relay producer/consumer 결박** — Map queued refresh의 source event/outbox
  원자화, restore exact replay `200` OpenAPI 선언, PinVi service artifact exact re-vendor와 restore-fence
  one-shot command를 하나의 compatible pair로 고정한다. command는 sync disabled 상태에서 immutable
  pre-CAS receipt로 응답 유실 exact replay까지 검증할 뿐 writer를 열지 않는다. Map/PinVi 두 draft PR의 exact SHA·artifact SHA와
  적대적 재리뷰 뒤 n150 isolated rehearsal을 별도 완료 조건으로 둔다.
  - [ ] **docker-manager pair 재핀(F1J-D 전제)** — Manager tracked v5 pinset은 아직 옛 pair를 고정한다.
        `MAP_PINNED_RUNTIME_SOURCE`=`4672aa96…`, `PINVI_PINNED_RUNTIME_SOURCE`=PinVi 재핀 머지 SHA,
        `pinset_sha256` 재계산 후 trusted Manager release를 배포해야 n150 격리 rehearsal이 fail-close를 통과한다.
  - Map #975 **머지 SHA** `4672aa966cd473f17fd4f69ee8066276f7be900d`(2026-08-18 재핀 — 이전 dangling 후보
    `e093e555…` 대체, service OpenAPI 바이트 동일)와 service OpenAPI
    `c6f9aba6ab4b815c394e5e1cb5fb4a2c3488d147d5bb1a7e21b92c1796f4aebd`를 PinVi
    provenance에 재핀했다. paired CI·재리뷰·n150 isolated Live UI E2E가 모두 성공할 때까지
    완료 receipt와 병합은 금지한다. production `SYNC_ENABLED=true`는 final C7 root enable
    boundary 전까지 Settings validation이 거부하며, 격리 n150 live proof는 `smoke` stack에서만
    실행한다.
- [/] **T-VN-41-F — C6c 격리 compatible-pair 증명** — 서비스 전 단계이므로 production consumer enable,
  운영 데이터 보존·복원, 중간 DB 백업은 이 task의 범위가 아니다. 데이터가 필요하면 fixture 또는
  ETL 재실행으로 새로 만든다. 설계 정본은
  [`t-vn-41-f1j-contract-provenance.md`](execplan/t-vn-41-f1j-contract-provenance.md)다.
  - [x] **F1J-A Map fixture lifecycle** — Map PR #960에서 동적 cancel-probe fixture의 arm/consume/finalize
        lifecycle와 DB 불변식을 병합했다.
  - [x] **F1J-B Manager orchestration** — docker-manager PR #159에서 정적 job ID를 제거하고 dynamic
        fixture의 exact unsafe `409` 회수와 response-loss 복구를 병합했다.
  - [x] **F1J-C service provenance 재결박** — PinVi PR #435와 docker-manager PR #160이 Map `1df45b57`의
        service OpenAPI exact bytes/SHA-256와 `cache_target=7`, `c6c_cancel_probe=2` capability를 하나의 일반
        service provenance로 재vendor·preflight 결박했다. PinVi ordinary runtime에는 fixture scope/token/route를
        주입하지 않는다.
  - [/] **F1J-D n150 final isolated rehearsal/UI E2E** — F1J-C의 exact pinset만으로 별도 Compose
    project·DB·volume을 생성해 destructive rehearsal과 live UI E2E를 실행하고 즉시 폐기한다. 운영
    stack·DB·backup/restore는 금지한다. 첫 격리 build에서 wheel `force-include` source path가 Docker
    filesystem에 없음을 확인했다. canonical contract를 editable install 전에 같은 source-relative 위치에
    복사하는 PinVi Docker fix PR을 merge한 뒤 동일 pinset rehearsal을 재개한다.
- (역사·참조) **T-VN-41-F production final boundary 초안(2026-08-05, PR #429)** —
  [`t-vn-41-production-final-boundary.md`](execplan/t-vn-41-production-final-boundary.md). 당시 F1 re-pin은
  Manager PR #130으로 됐으나 그 pin(`c0afaa4e…`)은 F1F-A에서 old release로 판정돼 재핀됐고, F1A(default-off
  bootstrap)는 착수되지 않은 채 F1D-C one-shot·F1F-B canonical env replace로 대체됐으며, F2 cutover는 미착수다.
  문서 헤더에 역사 기록으로 표기했다. 현행 실행 정본은 위 F1J 항목이며 두 문서가 어긋나면 F1J(신규)를 따른다.

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

- [x] **T-VN-SEC-03** — `npm audit` **high 7→0**(critical 0 유지). in-range 표적 update 4종
      (brace-expansion/form-data/js-yaml/shell-quote) + next-전파분(postcss@8.4.31 dedupe→8.5.23,
      미사용 optional sharp/@img 제거)은 lockfile 수술로 처리(overrides는 stale lock 재해석에만
      미반영, 재생성 시 정상 적용 — 가드로 유지). 잔여 13 moderate는 Expo/maplibre major graph →
      Sprint M-1 이관.
      (완료: 2026-08-04, PR #426, claude → tasks-done.md)

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

## 웹 디자인 시스템 — Hallmark 감사·재설계 (2026-08-18)

> 감사 정본: `docs/journal.md` 2026-08-18 항목(13 critical · 26 major · 19 minor, 7표면). 잠금 시스템:
> `DESIGN.md` "Hallmark 잠금 시스템". 재설계는 시스템 → 공개 표면 → 앱 셸 → 여행 상세 → 나머지 순서의 PR 단위.

- [x] **T-312** — Hallmark PR-1+PR-2: 시스템 잠금(`DESIGN.md` 섹션 추가, `cta`/`focus`/`shadow-overlay`/`zIndex`
      토큰 + spring 삭제, Pretendard self-host, `.focus-ring` outline, `html/body overflow-x: clip`, keep-all) +
      프리미티브(`components/ui/Button.tsx` Button/ButtonLink 8상태·44px, `FormField/Select/TextArea` 44px·16px) + 공개 표면(랜딩 Narrative Workflow 재구성, `PublicMasthead/PublicColophon/Wordmark`, auth 레이아웃·
      로그인·회원가입·verify-pending 재발송·verify-email, 공유 뷰 chrome+오류 상태, 404/FullPageMessage,
      favicon·앱 아이콘·themeColor Rausch/canvas, 내부 문구 제거). (완료: 2026-08-18, PR #447, claude → tasks-done.md)
- [x] **T-313** — Hallmark PR-1b(코드모드, 89파일): `bg-white→bg-canvas`, `text-white`→채움 위 `text-on-primary`/
      ink 위 `text-canvas`(마커 인라인 색 위는 유지), 채운 primary CTA→`bg-cta … hover:bg-cta-hover`,
      `bg-black/NN→bg-scrim/50`, `shadow-*→shadow-card|overlay`, 미정의 `bg-surface`→`bg-surface-soft`,
      `'...'→'…'`, `vh→dvh`(풀스크린 지도 표면의 `100svh`는 의도적으로 유지 — 모바일 chrome 토글 리사이즈 방지),
      `text-[NNpx]`→스케일, 본문 `text-muted-soft→text-muted`. eslint-plugin-tailwindcss 도입은 후속(T-317).
      (완료: 2026-08-18, PR #448, claude → tasks-done.md)
- [x] **T-314** — Hallmark PR-3(앱 셸·대시보드·탐색 지도): `AppShell` ground `bg-canvas` + 모바일 하단 탭바
      (주요 4 + 더보기 시트, 가로 스크롤 nav 폐기)·데스크톱 ink 밑줄 탭, `useMobileWebLayout` UA 정규식 제거
      (뷰포트·pointer 미디어쿼리만), eyebrow(uppercase accent 라벨) 4곳 삭제, 탐색/지도 shell 장식 칩 6개 삭제,
      TripDashboard 필터를 `role=tab`→`aria-pressed` 토글 그룹(44px)·목록 skeleton·오류 패널(회복 행동)과
      빈 상태(다음 행동 CTA) 분리. (완료: 2026-08-18, PR #450, claude → tasks-done.md)
- [/] **T-315** — Hallmark PR-4(여행 상세·모달): `components/ui/Dialog.tsx` 프리미티브 신설
  (scrim/overlay/z-modal 토큰 + `useModalDialog` 내장 + 헤더/본문/푸터 슬롯 + busy 잠금),
  `LocationConsentDialog`(focus trap 없던 것)·`NoticePlanCopyDialog` 이관, 임의 z-index
  (`z-[50]/[60]/[70]`) 전면 토큰화, 마커 팔레트 UI 오용(TripDayHeader 일출/일몰)·`bg-primary/10`
  accent tint 제거. **잔여**: TripEditDialog/TripManualPoiDialog/FeatureRequestDialog/TripDayControls/
  RestoreHotswapDialog 이관, TripDetail 3중 컨테인먼트·컨트롤 중복 정리.
- [ ] **T-316** — Hallmark PR-5(지도·설정·파일·법무): 파괴적 액션 확인 정책(토큰 회수·동의 철회·연결 해제 =
      Dialog, 가역 = 즉시+Undo, `window.confirm` 제거), 탐색 지도 장식 칩·상시 오류 dl 삭제, 설정 Admin chrome
      분리(`SettingsHeader`), DSR/신고 raw JSON textarea → 일반 필드, 법무 measure 65ch·초안 배너 중립화.

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
