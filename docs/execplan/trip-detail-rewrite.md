# Trip Detail Rewrite (TDR) — 마스터 실행 계획

> TDR 산출물. Trip **detail** 페이지 + 지원 REST를 8개 feature로 재작성한다. 단위 task backlog는
> `docs/tasks.md`, 완료 이력은 `docs/tasks-done.md`, 규칙은 `docs/tasks-rule.md`. 신규 결정은
> ADR-054/055/056으로 박는다. 외부 provider 계약은 `docs/integrations/kakao-naver-local.md`,
> 검색 계약은 `docs/api/search.md`(각 PR에서 작성).

## 1. 목표와 범위

사용자 지시: **깨끗한 코드/구조 · 기능적으로 완전하고 직관적인 REST · 일관·완결·쉬운 UI.** Pinvi 자체
REST 표면은 자유롭게 재설계하되, `kor-travel-map` 소유권은 유지한다(feature/provider_sync schema는
Pinvi가 DDL/import/`feature_id` 발급/provider→DTO 작성 금지). 검증됨: 본 설계에는 소유권 위반이
없다 — F4/F5는 **Pinvi 소유 POI snapshot + read projection**에서만 동작한다.

### 8개 feature (상태)

| # | feature | 상태 |
| - | ------- | ---- |
| F1 | 여행 기간 축소 시 범위 밖(out-of-range) 일자 경고 | net-new (서버 필드 + UI) |
| F2 | POI가 있는 day 삭제 확인 | net-new (client confirm + 서버 409 guard) |
| F3 | autocomplete가 ADDRESS 표시 + Kakao/Naver 병합(source 아이콘, internal-first) | net-new (검색 통합 + provider) |
| F4 | non-feature Kakao/Naver pick 추가 시 place feature-request 자동 발화 | partial (요청 파이프라인 존재, source/external_ref/auto-fire 확장) |
| F5 | 지도 viewport feature(place/event/notice/price) white-maki 마커 → 팝업 → 전체화면 kind별 detail modal | partial (`FeatureMapView` viewport+마커+팝업 존재, price kind·detail-card·modal net-new) |
| F6 | trip 지도가 모든 POI에 fit + DAY별 16색 마커(생성 시 기본, override 가능) | partial (fit-bounds 존재, day-color net-new) |
| F7 | POI별 마커 색/아이콘 override | **done** (`trip_day_pois.custom_marker_color/icon` + `PoiEditor` + `resolveMarkerStyle` custom tier) |
| F8 | day row에 공휴일 + 일출/일몰 표시 | partial (공휴일 read-path는 **PR #383로 main 머지 완료** — day 일출/일몰 + effective_date 재키잉 net-new) |

## 2. 최종 설계 결정 (FINAL — 재개봉 금지)

6차원 adversarial review를 통과한 확정 결정이다. ADR 3건으로 분할하여 박는다.

### 2.1 데이터 모델 & 서버 계산 → **ADR-055**

- **effective_date**: `services/poi.py#ensure_trip_day`(≈58-60행)에서 `trip_days.date = trip.start_date +
  (day_index-1)` **materialize 중단**(`date=None` 저장). `trip_days.date` = 명시적 per-day OVERRIDE
  전용. 서버가 **항상** `effective_date = date ?? (start_date + (day_index-1))` 파생, start_date null이면
  null. start_date 편집은 파생 day 전체를 reflow. `day_index >= 1` CHECK 추가; day_index는 영구적으로
  sparse/gappy(reorder op 없음). 모든 민간 날짜는 Asia/Seoul plain DATE, `now()` 파생 금지.
  - **버그 수정 근거**: 기존엔 auto-created day는 date를 frozen materialize, `services/trip.py#update_trip`은
    start_date 편집 시 day.date를 건드리지 않음 → `trip_days.date`가 frozen+null 혼재 → 모든
    `date ?? derived` 로직이 틀림. 본 결정이 이를 제거한다.
- **out_of_range**: `TripViewDay` 서버 필드. start_date 설정됨 AND `effective_date > end_date`일 때 true.
  클라이언트는 서버 `effective_date`/`out_of_range`를 **소비만** 함 — `apps/web/lib/tripDateLabels.ts`는
  재계산 **중단**.
- **marker_color**: `trip_days.marker_color` NULLABLE `String(16)`. NULL = 팔레트 기본
  `P-{((day_index-1)%16)+1:02d}`를 **공유 domain resolver**에서 해석(view-builder에 mirror). backfill
  없음, 3-insert-site materialize 없음. `PATCH /days/{i}`는 `exclude_unset` — 생략된 color가 저장된
  override를 clobber하지 않음. 우선순위 체인(ADR-055에 박음):
  **custom(POI) > dayColor > resolved > upstream > snapshot > category > kind > fallback**. dayColor는
  항상 존재하는 서버 resolved tier **위**에 위치(안 그러면 trip 지도에서 per-day가 이길 수 없음). 이는
  의도적으로 trip 지도에서 per-feature 색을 recolor함; per-POI custom(F7)은 여전히 최상위.
- **display_marker_color (단일 resolved 색이 지도 + 리스트 뱃지 공통)**: 서버가 `TripView`에서 POI별
  `display_marker_color`(custom > day > resolved > upstream) 계산; web은 지도 pin과 `TripPoiList` 번호
  뱃지 **양쪽**에 렌더 — client-side 우선순위 없음, parity 보장, mobile-safe.
- **day 일출/일몰**: NEW `app.trip_day_rise_sets` — key `(trip_id, day_index)`, 전용 ETL asset,
  pending/success/error 상태, **결정적 기준 좌표**(day POI centroid → 없으면 first-ADDED POI by
  `created_at` → 없으면 `primary_region_code` centroid fallback). "earliest-by-sort_order" 거부(LexoRank는
  user-draggable → 불안정). `TripViewDay`에 `rise_set` + `rise_set_reference`("XX 장소 기준") 노출.
- **async pending/stale**: effective-date 변경 시 day rise/set을 **파생-date day에만 scope된 SINGLE
  BATCHED UPDATE**로 re-seed; last-good 값은 `stale`/`needs_refetch` 플래그로 **유지**(null 금지); "계산
  중" UI; ETL 완료 시그널(WS 이벤트 또는 bounded client poll)로 값 도착 시 헤더 refresh.
- **DELETE-day**: PRIMARY = 이미 로드된 `poi_count`로 client-side confirm(round-trip 0). 서버 self-defense:
  `?cascade=true` 없는 DELETE는 POI 존재 시에만 `409 DAY_HAS_POIS`(고유 body `code`, body에 poi_count);
  version-conflict 409는 자체 code 유지. 204-always 아님.
- **copy_trip (out-of-scope 주석)**: 기존 target으로 merge 시 target day color 유지(source color 폐기) —
  버그 아님, 문서화.

### 2.2 외부 provider + 검색 + feature-request → **ADR-054**

- **ToS = display-only**: Kakao Local + Naver Local 결과는 DISPLAY-ONLY. provider 파생 콘텐츠
  (phone/address/category/road_address/rating)는 **절대 persist/forward 금지**. USER-AUTHORED 필드(사용자가
  입력/유지한 name, 사용자가 놓은 coordinate, user note) + OPAQUE `{provider, external_id, deep_link_url}`
  참조만 persist. view 시 live provider detail re-fetch. 기본 autocomplete = kor-travel-geo +
  kor-travel-map; Kakao/Naver는 display-only 보강. ADR-054는 **왜 지금 ADR-015를 supersede하는지**
  명시(kor-travel-geo/kor-travel-map 단독으로는 특정 주소-autocomplete + place-link gap을 못 채움).
- **secrets/CSP**: Kakao Local은 `Authorization: KakaoAK {REST_API_KEY}` — 기존 OAuth 앱과 **동일 키**
  (`pinvi_kakao_oauth_rest_api_key`, 로컬 product enable), redundant Kakao 키 발급 금지. Naver Search는
  **별도** Search-API 앱 credential(`X-Naver-Client-Id/Secret`, 신규 `pinvi_naver_search_client_id/secret`).
  신규 키는 `SecretStr`. 호출은 **SERVER-SIDE**(httpx) → provider 호스트는 web `connect-src`에 넣지 않음.
  deep-link nav 호스트(`map.kakao.com`, `map.naver.com`)만 browser-facing(connect-src 불필요). attribution
  로고는 LOCAL asset 번들(remote img-src 아님). maki-glyph unpkg 문제(self-host)는 modal PR 전에 결정.
- **attribution**: 모든 Kakao/Naver-sourced row·detail view에 "카카오"/"네이버 검색" attribution + back-link
  가시 노출은 HARD UI 요구.
- **quota/cost**: 내부(feature+my_poi+address) 결과 < K일 때만 Kakao/Naver 호출; 서버 short-TTL 캐시 key
  `(q, rounded-coord-cell)`; debounce 유지; min query length; cancel-in-flight. Naver open quota ≈25k/day.
- **location_audit**: `/search`의 near-coordinate 제3자 전달 = 위치정보 제3자 제공. 별도 `lat`/`lon` 파라미터
  사용, `/search`(또는 `/v1/search`)를 `middleware/location_audit.py`의 `PURPOSE_BY_PATH`에 purpose
  `third_party_place_search`로 추가, 핸들러에서 `request.state.location_audit_coord` 설정, 좌표는 기존
  location-consent flow로 gate, 사용자가 "내 주변 검색" 선택 시에만 전송.
- **feature-request 확장**: `source`(feature|kakao|naver|manual) + opaque `external_ref`를 `FeatureSuggestion`
  AND `trip_day_pois`의 **first-class 컬럼**(snapshot에 묻지 않음) 양쪽에 추가. auto-fire는 **best-effort +
  POI create와 decouple**(POI create는 항상 성공; rate-limit/dup 시 enqueue 조용히 skip). 자체 idempotency
  key `(user, provider, external_id)` 24h 생존; manual 20/day와 **분리·non-blocking** budget. 전 요청자에
  걸쳐 `(provider, external_id)`로 **GLOBAL dedup**(하나의 suggestion으로 collapse, interested-user count
  기록). post-approval **reconciliation**: admin approve 시 minted feature_id를 `(provider, external_id)`
  일치하는 모든 `trip_day_pois`에 attach, snapshot-only 상태 clear. create_feature에는 user-authored
  name+coord+note + external_ref만 forward — provider 콘텐츠 절대 금지.
- **검색 통합 (ONE endpoint)**: path `GET /search` 유지. typed `{results: PlaceSearchResult[],
  degraded_sources: []}` 반환, `source ∈ {feature, my_poi, kakao, naver, address}`. `PlaceSearchResult` =
  `{source, feature_id?, external_id?, name, address, road_address?, coord{lon,lat}, category?,
  marker_color?, marker_icon?, provider_url?, phone?(display-only, 미persist)}`. 정렬: feature+my_poi+address
  (internal) 먼저, 그다음 kakao, 그다음 naver; 부분 degradation에도 stable. `GET /features/search`
  DELETE(source=feature와 동일). `/search/places` 신설 금지. 기존 `unified_search`/`UnifiedSearchResult`는
  untyped `list[dict]` leak을 이 typed 계약으로 대체.

### 2.3 feature detail-card + modal → **ADR-056**

- **detail-card**: `GET /features/{id}/detail-card`가 THE 사용자 detail read — typed,
  kind-discriminated `FeatureDetailCard`, kind별(place/event/notice/price) general-user 필드만 노출 +
  GENERIC FALLBACK arm(name/category/address/kind, weather/route/area용). `GET /features/{id}`는 raw/debug
  passthrough로 demote. 외부 보강은 OPT-IN `?providers=kakao,naver`, DISPLAY-ONLY(live fetch, attribution,
  미persist), 보강 실패 시 `/search` mirror `degraded` 마커. feature-less trip POI(feature_id=null)는 저장된
  POI snapshot으로 modal 렌더(feature_id 불필요). in-bounds 기본 kinds에 `price` 추가. name+coord fuzzy
  match confidence guard → low-confidence면 잘못된 phone/URL 대신 "일치하는 외부 정보 없음" 표시.
- **modal**: 공유 `useModalDialog` 훅(focus trap + focus restoration + Escape + backdrop + aria-modal +
  history/popstate back-button close). `ConfirmDialog`, `FeatureDetailModal`, refactor된 `ConflictDialog`를
  이 훅으로 route(현 ConflictDialog는 trap/restoration 없음 — WCAG 2.4.3 / 2.1.2). FeatureDetailModal =
  mobile에서 bottom sheet(drag-handle + thumb-zone X, `overflow-y-auto overscroll-contain`, `padding:
  max(1rem, env(safe-area-inset-*))`); mobile에선 마커 탭이 sheet 직접 open(nested 아이콘 없음).
- **onSelect union**: `MapSearchBox` `onSelect: (result: PlaceSearchResult) => void`(source-tagged union)를
  autocomplete 재작성 **전에** 정의. FeatureMapView는 모든 source에서 `result.coord`로 flyTo; TripDetail은
  `result.source` 분기(feature/my_poi → feature_id POI-create; kakao/naver → external_ref POI-create). 명시적
  sub-task.
- **out-of-range UX**: actionable 배너("종료일을 XX로 연장" one-click `PATCH trip.end_date`; "이 일자 삭제");
  탭 경고 `aria-label` "여행 기간을 벗어난 일자"; empty-date affordance "여행 시작일을 설정하면 날짜가
  표시됩니다"(start_date=null).
- **shared view**: `apps/web/.../SharedTripView.tsx`(public read-only)는 day-color + 공휴일 + 일출 렌더;
  out-of-range nag / F4 auto-request / F3 검색 **제외**. shared endpoint view-builder는 동일 day 필드 emit.
  per-feature visibility matrix를 ADR-055에 codify.

## 3. Task 계획

레인: **A = Claude Code**(web/domain UI), **B = Codex**(backend/data/external, HEAVIER). ADR 1건/PR:
ADR-055 in T-301, ADR-054 in T-302, ADR-056 in T-304. 테스트 + doc/OpenAPI slice는 각 backend PR과 함께
탑승(tasks-rule §7).

| task | 레인 | 소유자 | 한 줄 범위 | 의존 | 주요 파일 | ADR |
| ---- | ---- | ------ | ---------- | ---- | -------- | --- |
| ~~T-300~~ | B | Codex | **DONE (PR #383)** — holiday read-path(`TripViewDay.holidays[]` + KASI join + `tripDateLabels.ts`)가 main에 머지됨. Lane A gate 충족. T-301이 holiday join을 `effective_date` 기준으로 재키잉 | — | `TripDayHoliday`, `services/trip_view_builder.py`, `lib/tripDateLabels.ts` | — |
| T-301 | B | Codex | day presentation backend: marker_color nullable+inherit, effective_date/out_of_range, POI별 display_marker_color, DELETE 409 guard, day schema 양 언어, shared-view emit | T-300 | `services/poi.py#ensure_trip_day`, `services/trip.py#update_trip`, `services/trip_view_builder.py`, `packages/schemas`, migrations | **055** |
| T-302 | B | Codex | Kakao/Naver client + config + `GET /search` typed source-tagged(address 포함) + location_audit + quota/cache + api-client | T-300 | `clients/kakao_local.py`·`clients/naver_local.py`(신규), `core/config.py`, `middleware/location_audit.py`, `packages/api-client`, `docs/integrations/kakao-naver-local.md`, `docs/api/search.md` | **054** |
| T-303 | B | Codex | feature-request 파이프라인: source/external_ref first-class, best-effort decoupled auto-fire, global dedup, reconciliation | T-300 | `models/feature_suggestion.py`, `services/poi.py`, `api/v1/admin/feature_requests.py`, `clients/kor_travel_map`, migrations | 054 |
| T-304 | B | Codex | detail-card kind별 + generic fallback + opt-in 외부 보강 + price kind | T-300 | `api/v1/features.py`(`GET /features/{id}/detail-card`), `packages/schemas`(`FeatureDetailCard`), `GET /features/in-bounds` | **056** |
| T-305 | B | Codex | 전용 `trip_day_rise_sets` table + ETL asset + day rise/set read + batched re-seed + 완료 시그널 + e2e seed/provider mock | T-301 | `app.trip_day_rise_sets`(migration), `apps/etl` asset, `services/kasi.py`, `services/trip_view_builder.py` | 055 |
| T-306 | A | Claude | useModalDialog + ConfirmDialog + day-delete confirm + out-of-range actionable 배너/아이콘 | T-300, T-301 | `components/ui/useModalDialog.ts`·`ConfirmDialog.tsx`(신규), `TripDetail.tsx`(경고 전용 edit) | 056 |
| T-307 | A | Claude | per-day color picker + display_marker_color 렌더(지도+리스트 뱃지 parity) + PoiEditor F7 polish + fit-bounds 확인 | T-301 | `TripDayControls.tsx`(day-color picker), `TripPoiList`, `TripMapView`, `PoiEditor`, `packages/domain/src/marker.ts` | 055 |
| T-308 | A | Claude | 신규 `TripDayHeader.tsx`(effective date + 공휴일 뱃지 + 일출/일몰 pending) + SharedTripView 렌더 | T-301 | `components/.../TripDayHeader.tsx`(신규), `SharedTripView.tsx`, `packages/domain` | 055 |
| T-309a | A | Claude | autocomplete 재작성: onSelect union, address+source 아이콘+정렬+debounce, attribution | T-302 | `MapSearchBox`, `FeatureMapView`, `TripDetail.tsx` 분기 | 054 |
| T-309b | A | Claude | 외부 pick add-POI + best-effort auto-request UX + snapshot POI 렌더 | T-303 | `TripDetail.tsx`, POI-create 경로, snapshot 렌더 | 054 |
| T-309c | A | Claude | FeatureDetailModal(bottom sheet, kind별, opt-in 보강 링크+attribution, 마커 팝업→detail→modal 양 지도, price kind, weather 제외) | T-304 | `FeatureDetailModal.tsx`(신규), `FeatureMapView`, `TripMapView` | 056 |

### 3.1 의존성 DAG

```
T-300 (holiday 머지)
  ├─ T-301 (day presentation) ─┬─ T-305 (rise/set table+ETL)
  │                            ├─ T-307 (day color/badge render)
  │                            └─ T-308 (TripDayHeader + shared)
  ├─ T-306 (modal 훅 + confirm + out-of-range)   [T-301도 소비]
  ├─ (T-301) …
  ├─ T-302 (Kakao/Naver + /search) ── T-309a (autocomplete 재작성)
  ├─ T-303 (feature-request 확장) ─── T-309b (외부 add-POI + auto-request)
  └─ T-304 (detail-card) ─────────── T-309c (FeatureDetailModal)
```

- T-300은 **PR #383로 완료**(공휴일 스키마·view-builder가 이미 main에 있음) → T-301/T-306/T-307/T-308의
  holiday gate는 이미 충족. Lane A는 최신 main에서 즉시 착수 가능(단 day 서버 필드는 T-301 선행).
- T-301 → {T-306, T-307, T-308} (day 서버 필드 계약 선행).
- T-302 → T-309a, T-303 → T-309b, T-304 → T-309c (각 backend 계약이 UI를 gate).
- **A 스타터(shared 파일 0개)**: `ConfirmDialog` + `FeatureDetailModal` shell + `useModalDialog`를
  T-300/계약 window 동안 선행 구축.

### 3.2 파일 소유 규칙 (충돌 회피)

- **B 소유**: `apps/api`, `apps/etl`, `packages/schemas`, `packages/api-client`, `docs/`(ADR),
  migrations, CHANGELOG, seed. 공유 계약 필드는 B가 먼저 정의, A가 소비.
- **A 소유**: `apps/web/components` + `apps/web/lib` + `packages/domain`(small).
- **intra-A 충돌 방지**: 신규 `TripDayHeader.tsx` 추출(**T-308 소유**); day-color picker는
  `TripDayControls`(**T-307**)에 유지; `TripDetail.tsx`의 유일한 편집은 경고용 **T-306**. 세 A task가
  `TripDetail.tsx`/day 헤더를 동시에 건드리지 않도록 분리.
- `packages/domain/src/marker.ts#resolveMarkerStyle`는 web+mobile 공유 — **pure 유지**. `dayColor`는
  OPTIONAL threaded input으로만 추가(mobile 지도에서 thread하지 않음 — mobile silent recolor 방지).

## 4. 테스트 / 롤아웃 게이트

1. **per-PR**: backend PR = `pytest -q` + `ruff check` + `mypy --strict`(apps/api); web PR = `npm run
   typecheck` + `npm run lint`(apps/web) + `packages/domain` vitest. (Linux 기준, CLAUDE.md §6.)
2. **adversarial review 2인**: 각 PR은 테스트 전 **2명의 adversarial reviewer**를 거친다.
3. **live UI e2e (destructive-allowed)**: WSL → SSH → N150 경로로 실 UI e2e. dev DB 대상 mutating 허용.
   Playwright는 N150 우선, Windows fallback(ADR-051).
4. **final N150 prod**: 최종 검증은 N150 운영 노드.

## 5. 교차 에이전트 PR 리뷰 규율

각 task 완료 후, **닫힘 상태 무관** 2일 window 안의 다른 에이전트 PR을 리뷰한다: adversarial review →
comment → issue 등록 → fix → merge. **review-reflection PR**(리뷰 반영만 하는 PR)은 리뷰 대상에서 제외.
author 필드는 codex/claude를 구분 못 하므로 브랜치 prefix(`agent/codex-*` vs `agent/claude-*`)로 판별.
(codex PR 리뷰 워크플로우 = MEMORY `codex-pr-review-workflow`.)

## 6. Out of scope (문서에 명시)

- **Mobile(apps/mobile) parity** — 별도 release train(T-284 scope gate). resolver는 `dayColor`를 OPTIONAL
  threaded input으로 pure 유지; 이번 sprint에 mobile 지도에서 thread하지 않음(mobile silent recolor 방지).
  후속 task로 mirror. Mobile shared 화면 보강도 OOS.
- **multi-day cluster 색** — neutral/mixed 규칙 정의 OR 명시적 defer.
- **weather/route/area rich detail arm** — generic fallback로 커버; weather는 inline temp 팝업 유지.
- **`prefers-reduced-motion`** (flyTo/fitBounds/day-color churn) — known gap으로 기록.

## 7. 수용된 잔여 리스크 (accepted)

- **의도적 recolor**: dayColor가 resolved tier 위에 있어 trip 지도에서 per-feature 색을 recolor함. per-POI
  custom(F7)은 여전히 최상위 — 수용.
- **rise/set snapshot-only**: 날짜 변경 시 recompute하지 않고 last-good + `stale` 플래그 유지, ETL 완료
  시그널로 refresh — 일시적 stale 값 노출 수용.
- **provider quota degradation**: Kakao/Naver quota 소진 시 `degraded_sources`로 degrade, internal 결과만
  반환 — 수용.
- **match-confidence guard**: low-confidence 외부 매칭은 "일치하는 외부 정보 없음"으로 fallback — 일부 실제
  일치를 놓칠 수 있음, 잘못된 phone/URL 노출보다 안전 선택.
- **day_index 영구 sparse**: reorder op 없이 gappy 유지 — 수용.

## 8. ADR / 참조

- **신규**: ADR-054(외부 provider + 검색 통합 + feature-request), ADR-055(day 데이터 모델 + 서버 계산 +
  visibility matrix), ADR-056(feature detail-card + modal). 배치 후 `docs/decisions.md` 말미 "다음 신규
  ADR = **ADR-057**".
- **supersede**: ADR-054가 ADR-015(직접 Kakao Local search DROP)를 supersede(why-now 명시).
- **참조 문서**: `docs/integrations/kakao-naver-local.md`(provider 계약, T-302 작성),
  `docs/api/search.md`(검색 계약, T-302 작성), ADR-018(geofencing), ADR-052(category/marker override),
  ADR-053(route optimize).
