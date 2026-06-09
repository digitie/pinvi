# krtour-map REST API 계약 — TripMate 소비 기준 (붙이는 작업 청사진)

> **목적**: TripMate `apps/api`/`apps/web`가 `python-krtour-map`의 **운영 HTTP API**를
> 실제로 연결(integrate)하기 위한 권위 계약 + TripMate 측 작업 목록.
> **상태(중대 변화)**: 2026-06-08 기준 **krtour-map이 운영급 HTTP API를 이미 구축했다.**
> 더 이상 "목표/aspirational"이 아니라 **실재하는 계약**이다 — ADR-026/027(DEC-01=B)
> 의 전제가 충족됨.
> **검증 기준선**: `python-krtour-map` `origin/main` `HEAD=f442bd0`
> (`packages/krtour-map-admin/openapi.user.json`, title `krtour-map-user` v0.2.0-dev) +
> TripMate `origin/main` `HEAD=0485974`(#87 feature_id opaque string 반영)을 2026-06-08 대조.
> **정본 소스**: krtour-map `packages/krtour-map-admin/openapi.user.json`(사용자 표면) +
> `docs/tripmate-rest-api.md`(prose 계약). 본 문서와 충돌 시 **openapi.user.json 우선**.
> **관계**: 능력 격차 분석은 `docs/krtour-map-requirements.md`(이제 대부분 해소),
> 통합 패턴 개요는 `docs/krtour-map-integration.md`(본 문서가 구체 계약으로 대체/보강).

---

## 0. 한눈에 — 무엇이 바뀌었나

`docs/krtour-map-requirements.md`(2026-06-06)가 "krtour-map에 없다"고 한 능력 대부분이
**구현 완료**됐다. krtour-map은 `packages/krtour-map-admin`(FastAPI, 포트 **9011**)에
TripMate-facing `openapi.user.json`을 export하고, 다음 13개 엔드포인트를 제공한다:

| 능력 | 엔드포인트 | 직전 상태 → 현재 |
|------|-----------|------------------|
| bbox + 클러스터 | `GET /features/in-bounds` | 클러스터 미지원 → **서버 클러스터(`cluster_unit`) 지원** |
| 단건 상세 | `GET /features/{feature_id}` | ✅ |
| **배치** | `POST /tripmate/features/batch` | ❌ → **✅(cap ≤200)** |
| 반경 | `GET /features/nearby` / `/nearby/by-target` | ❌ → **✅(cursor)** |
| 텍스트 검색 | `GET /features/search` | ❌ → **✅(cursor)** |
| 날씨 카드 | `GET /features/{feature_id}/weather` | 미구현 → **✅(metric 목록)** |
| 카테고리 | `GET /categories` | export만 → **✅ HTTP** |
| feature 갱신요청 | `POST /tripmate/feature-update-requests` + `GET .../{id}` | ❌ → **✅** |
| provider 신선도 | `GET /providers/{provider}/last-sync` | — → ✅ |
| health/version | `GET /health`, `GET /version` | — → ✅ |

→ **이제 공은 TripMate에 있다.** TripMate는 (1) httpx client를 만들고 (2) feature_id를
문자열로 다루고(이미 #87로 1차 반영) (3) 응답 셰입을 krtour 실제 계약에 맞추고
(4) 클러스터링·배치를 서버 위임으로 재배선해야 한다. §6의 작업 목록.

---

## 1. 연결 규약 (전 엔드포인트 공통)

- **Base URL**: 로컬 `http://127.0.0.1:9011`. TripMate 설정 `TRIPMATE_KRTOUR_MAP_API_BASE_URL`.
  (Admin/ops `9012`는 TripMate Admin 프록시 전용 — 사용자 경로 미노출.)
- **버전 prefix**: 현재 **prefix 없음**(`/features/...`). **krtour ADR-048(PR #316, OPEN)** 가
  외부 사용자 표면 전체를 `/v1`로 옮기고 admin/ops/debug까지 `/v1` 통일 예정. → TripMate
  client는 base path를 **설정값**으로 두어 `/v1` 전환에 대비한다(§6-G). **전환 방식 = hard
  cutover**(2026-06-09 재리뷰, 소유자 지시): TripMate가 v0.1.0 미출시 + `/features/*` 503 +
  유일 소비자라 보호할 설치 기반이 0 → 구 unprefixed alias 동시지원(shim)은 ADR-046(무-shim)과
  모순이라 두지 않고, krtour `/v1` cut commit에 **lockstep**으로 base만 교체(§7-A, T-181).
- **인증**: 코드에는 인증 없음(krtour ADR-005). 운영 인증은 **네트워크/인프라 계층**에서
  강제 — reverse proxy SSO / IP allowlist / `X-Krtour-Service-Token` pass-through(krtour
  D-1). → TripMate client는 설정된 서비스 토큰 헤더를 **그대로 전달**할 수 있어야 한다
  (`TRIPMATE_KRTOUR_MAP_SERVICE_TOKEN`, 선택). **사용자 토큰을 krtour로 전달하지 않는다.**
- **응답 envelope**: 성공 = `{ "data": <payload>, "meta": <Meta> }`. **현재**: 목록 =
  `data.items[]` (+ `data.next_cursor` 또는 `data.clusters[]`).
  **⚠️ ADR-048(PR #316) 예고 변경 — payload/meta 완전 분리**: `data`는 payload만(목록
  `{items:[]}`, in-bounds `{clusters,items,cluster_unit}`), pagination·추적은 `meta`로 일원화
  (`meta={duration_ms, request_id, page?:{page_size, next_cursor, total}}`). 즉 `data.next_cursor`/
  `data.total_count`/`count` 폐기 → `meta.page.next_cursor`. **T-170 client list 메서드는
  `meta.page.next_cursor`를 threading하도록 변경 필요**(현재 `data`만 반환·`meta` 폐기)(T-181).
- **에러 envelope**: 현재 `{ "error": { "code", "message", "request_id", "retry_after_seconds"? } }`.
  표준 코드: `FEATURE_NOT_FOUND`(404), `INVALID_BBOX`(422), `TOO_MANY_IDS`(422, 배치>200),
  `RATE_LIMITED`(429), `LOCK_BUSY`(409 + `Retry-After: 15`, update-request `run_mode=now`),
  `UPSTREAM_UNAVAILABLE`(503). FastAPI 검증 실패는 `HTTPValidationError`(422).
  **⚠️ ADR-048(PR #316, OPEN) 예고 변경**: 에러를 RFC7807 `application/problem+json`으로 전환
  예정 — 위 코드 enum이 problem+json **확장 멤버 `code`**로 유지되는지(어디서 읽을지) 합의 필요(§7).
  TripMate client(`_error_code`)는 현재 `payload["error"]["code"]`를 읽으므로 전환 시 갱신 대상(T-181).
- **좌표**: WGS84, 순서 **lon, lat**. bbox = `min_lon, min_lat, max_lon, max_lat`.
  목록/요약 응답의 좌표는 **평면 `lon`/`lat` 숫자**(중첩 `coord{}` 객체 아님).
- **datetime**: ISO 8601(KST-aware). **TripMate는 자기 외부 응답에서 `+09:00`로
  재투영**(ADR-030) — krtour 원본 그대로 사용자에게 흘리지 않는다.
- **TripMate 응답 셰입은 TripMate 소유**. krtour 응답을 받아 TripMate `{data,meta}`로
  다시 감싸고 필요한 필드만 투영한다. 원천 필드명 의미는 바꾸지 않는다.

---

## 2. 엔드포인트 계약

각 항목: 호출 형태 → 응답 핵심 셰입 → TripMate 소비처 → 매핑/주의.

### 2.1 `GET /features/in-bounds` — 지도 viewport
- **params**: `min_lon* min_lat* max_lon* max_lat*`(number), `kind`(repeat), `category`,
  `zoom`, `cluster_unit`, `limit`.
- **200 `FeaturesInBoundsResponse`**: `data:{ count, cluster_unit, clusters:[ClusterSummary], items:[FeatureSummary] }, meta:{duration_ms}`.
  - `ClusterSummary` = `{ cluster_key, feature_count, lon, lat }`.
  - `FeatureSummary` = `{ feature_id, kind, name, category, lon|null, lat|null, marker_color|null, marker_icon|null, status }`.
- **소비처**: TripMate `GET /features/in-bounds`(features.py). 지도 마커/클러스터.
- **주의**: **클러스터링은 krtour 서버가 한다**(`cluster_unit`/`zoom`). TripMate
  `services/cluster_query.py`(직접 `feature` schema SQL 조인)는 **경계 위반 + 중복** —
  제거하고 서버 cluster로 대체(§6-E). 응답 클러스터 셰입(`cluster_key/feature_count/lon/lat`)이
  TripMate 현재 schema(`cluster_id/center/feature_count/sample_kinds/bbox`)와 다름 → 정렬 필요.

### 2.2 `GET /features/{feature_id}` — 단건 상세
- **params**: `feature_id*`(**string** path).
- **200 `FeatureDetailEnvelopeResponse`**: `data:FeatureDetailResponse` =
  `{ feature_id, kind, name, category, lon|null, lat|null, address(object), legal_dong_code|null,
  sido_code|null, sigungu_code|null, marker_color|null, marker_icon|null, urls(object),
  detail(object), status, updated_at }`.
- **소비처**: 마커 클릭 상세, POI 추가 시 검증. 404 = `FEATURE_NOT_FOUND`.
- **주의**: `name`(TripMate 코드의 `title` 아님), `address`는 **구조화 객체**(평면
  `address_road/address_jibun` 아님) → schema 정렬(§6-D).

### 2.3 `POST /tripmate/features/batch` — 배치 조회 (성능 핵심)
- **body `FeatureBatchRequest`**: `{ feature_ids: [string] }` (**cap ≤200**, 초과 시 `TOO_MANY_IDS`).
- **200 `FeatureBatchResponse`**: `data:{ items: { <feature_id>: <FeatureDetail> }, missing:[string] }, meta:{duration_ms}`.
- **소비처**: `GET /trips/{id}`의 `trip_view_builder` — trip POI들의 `feature_id[]`로 최신
  feature 일괄 조회(N+1 방지). `missing`은 삭제/없음 → POI `feature_snapshot` fallback + `is_broken`.
- **주의**: 200개 초과 trip은 **client에서 청크 분할** 호출. TripMate
  `trip_view_builder`가 기대하는 `features_by_ids(list[uuid]) -> list` (UUID·list)를
  `{items,missing}` map·string으로 교체(§6-F).

### 2.4 `GET /features/nearby` — 반경 + `…/nearby/by-target`
- **nearby params**: `lon* lat* radius_m*`, `kind` `category` `status` `provider`,
  `page_size`, `cursor`, `sort`(기본 distance).
- **200 `FeaturesNearbyResponse`**: `data:{ origin:NearbyOriginSummary, items:[NearbyFeatureSummary], next_cursor|null }`.
  `NearbyFeatureSummary` = FeatureSummary + `distance_m`.
- **by-target**: `external_system* target_key*`(등록된 POI cache target) + `radius_km`.
  TripMate POI를 cache target으로 등록하면(krtour `PUT …/poi-cache-targets/...`, 현재
  `/admin/*`) "이 POI 주변" 질의 가능 — Sprint 후순위.
- **소비처**: "내 위치/POI 주변 N km". cursor 페이지네이션.

### 2.5 `GET /features/search` — 텍스트 검색
- **params**: `q`, `kind`, `category`, `bbox`, `limit`, `cursor` (q 또는 bbox 필요).
- **200 `FeatureSearchResponse`**: `data:{ items:[FeatureSummary], next_cursor|null, total_count|null }`.
- **소비처**: 통합 검색(`GET /search`)의 **feature 파트만**. 주소 후보는 TripMate가
  **kraddr-geo v2 직접**(ADR-025), 내 POI는 TripMate 로컬 — 합쳐서 응답.

### 2.6 `GET /features/{feature_id}/weather` — 날씨 카드
- **params**: `feature_id*`, `asof`(선택).
- **200 `FeatureWeatherResponse`**: `data:WeatherCardData` =
  `{ feature_id, asof|null, latest_at|null, is_stale, source_styles:[string], metrics:[WeatherMetricOut] }`.
  `WeatherMetricOut` = `{ metric_key, metric_name|null, forecast_style, timeline_bucket|null,
  valid_at|null, issued_at|null, observed_at|null, value_number|null, value_text|null, unit|null, severity|null }`.
- **소비처**: feature 상세 날씨, 텔레그램 brief.
- **주의(셰입 대수술)**: krtour는 **평탄한 metric 목록 + forecast_style 태그**를 준다.
  TripMate 현재 schema는 `{short_term[], daily[], sources[]}`, features.md는
  `{nowcast, ultra_short, short, mid, advisories}`. → TripMate가 `forecast_style`
  (nowcast/ultra_short/short/mid/observed/index/advisory)별로 metric을 **그룹핑해 카드 구성**
  (변환은 TripMate 표현 계층, KMA provider 변환 직접 작성 아님 — 금지룰 준수)(§6-D).

### 2.7 `GET /categories` — 카테고리 카탈로그
- **params**: `include_counts`, `active_only`.
- **200 `CategoriesResponse`**: `data:{ count, include_counts, items:[CategorySummary] }`.
  `CategorySummary` = `{ code(8자리), label, parent_code|null, depth, path:[str], maki_icon,
  tier1..4_code/name, is_active, sort_order, db_active|null, db_feature_count|null }`.
- **소비처**: 마커 범례, 필터 칩, Admin 카테고리 매핑. 저빈도 → 클라이언트 캐시(긴 TTL).

### 2.8 재적재 vs 사용자 제안 — 완전히 별개 (DEC-05 확정, 2026-06-08)

**둘은 다른 작업이고 서로 연결되지 않는다.**

**(A) 재적재(feature-update-request) = krtour-map Admin — TripMate 제품 무관**
- **경로 변경(krtour PR #317)**: `/tripmate/feature-update-requests*` alias **제거** →
  **`/admin/feature-update-requests*`** 로 고정(admin spec, 포트 9012).
  `POST`(create/dry-run) / `GET /{id}` / `POST /{id}/cancel` / `POST /{id}/run-now`.
- "특정 scope를 다시 적재(Dagster job)"하는 **krtour-map 운영자 기능**. krtour-map admin
  (9012)에서 운영. **TripMate 일반 사용자 비노출, 사용자 제안 흐름과 무관.** TripMate 제품은
  surface하지 않는다.

**(B) 사용자 feature 제안 = TripMate 소유 → 승인 시 krtour feature change API로 반영**
- ① **사용자 제안 큐** (user 도메인): `app.feature_suggestions` + `POST /features/requests`
  (즉시 201) + `GET /features/requests/{id}`. rate-limit/dedup. **krtour 직접 호출 X.**
- ② **TripMate Admin 검사/승인/거절** (admin 도메인): `/admin/feature-requests` +
  approve/reject(RBAC admin/operator + audit). **승인 시 §2.9 krtour feature change API 호출.**

### 2.9 feature change API — `POST/PATCH/DELETE /admin/features` (krtour PR #317, K-15 해소)

**TripMate Admin 도메인 전용**(admin base 9012, `require_admin_destructive_enabled` + 서비스 토큰).
사용자 제안 승인 시 호출. `place`/`event`만 대상.

| 동작 | 호출 | body 핵심 | 응답 |
|------|------|-----------|------|
| 추가 | `POST /admin/features` | `AdminFeatureCreateRequest`: `kind*(place\|event)`, `name*`, `category*`, `marker_color*`, `marker_icon*`, `reason*`, `coord{lat,lon}`, address/코드, `detail`, `urls`, `status(draft\|active\|inactive\|hidden)`, `feature_id?`, `idempotency_key?`, `operator?` | `AdminFeatureChangeResponse` |
| 수정 | `PATCH /admin/features/{feature_id}` | `AdminFeaturePatchRequest`: 전 필드 optional + `reason*` | 〃 |
| 삭제(soft) | `DELETE /admin/features/{feature_id}` | `AdminFeatureDeleteRequest`: `reason*`, `operator?` | 〃 |
| 비활성 | `POST /admin/features/{feature_id}/deactivate` | `AdminFeatureDeactivateRequest` | — |
| 검수 큐 | `GET /admin/features/change-requests`, `POST .../{id}/approve\|reject` | `AdminFeatureReviewActionRequest`(operator/reason) | 〃 |

- **응답 `data.request`(AdminFeatureChangeRequestRecord)**: `feature_id, request_id, action,
  state, review_mode, payload, applied_at, reviewed_at/by, created_at`. → TripMate는
  `feature_id`+`request_id`를 `feature_suggestions` row에 저장하고 state로 확정 추적.
- **review_mode(krtour 설정 `KRTOUR_MAP_ADMIN_FEATURE_CHANGE_REVIEW_MODE`, 기본 `require_review`)**:
  `require_review`=`ops.feature_change_requests`에 pending → krtour 운영자 approve 후 적용.
  `immediate`=요청 transaction에서 즉시 version 1 적용. **TripMate는 자기 Admin에서 이미 검수**
  하므로 이중 검수가 되지 않도록 **review_mode 합의 필요(DEC-05 하위결정, §7)**.
- **version 0(provider)/1(user) 분리 내구성**: provider 재적재가 user version-1 row를 덮거나
  사용자 삭제 row를 되살리지 않는다(PR #317). → TripMate가 추가한 장소·폐업 신고가 재적재로
  사라지지 않음(closure/correction 신뢰).
- **closure**: "영구 폐업" = `DELETE`(soft) 또는 `/{id}/deactivate` — krtour 권장 확정 필요(§7).

### 2.10 `GET /providers/{provider}/last-sync`, `GET /health`, `GET /version`
- provider 신선도(brief/Admin 상태판), liveness, 버전. TripMate Admin 상태판·헬스 체크용.

---

## 3. 데이터 계약 (반드시 맞출 것)

| 항목 | krtour 실제(정본) | TripMate 현재 | 조치 |
|------|-------------------|----------------|------|
| **feature_id** | `f_{bjd\|global}_{kind[0]}_{sha1[:16]}` **문자열**(예 `f_1168010100_p_3c0c2820e96d28d3`) — UUID 아님 | #87로 opaque string 1차 반영 | 잔여 `uuid.UUID(...)` 캐스트 전수 제거 확인(§6-C) |
| 표시명 | `name` | 일부 `title` | `name`으로 통일 |
| 좌표(목록) | 평면 `lon`/`lat` | `coord:{longitude,latitude}` | 투영 계층에서 변환 |
| 주소 | 구조화 `address` 객체 + `legal_dong_code/sido_code/sigungu_code` | 평면 `address_road/jibun` | schema 정렬 |
| category | 8자리 코드(`"01070100"`) + 카탈로그 label | 한글명 가정 흔적 | 코드 저장 + `/categories` label 조회 |
| marker | `marker_icon`(maki), `marker_color`(`P-01`~`P-16`) | 동일 | OK |
| 클러스터 | `{cluster_key, feature_count, lon, lat}` | `{cluster_id, center, feature_count, sample_kinds, bbox}` | 서버 셰입으로 정렬 |
| 날씨 | metric 목록 + `forecast_style` 태그 | `{short_term,daily}` / `{nowcast,…}` | 그룹핑 변환 |
| envelope | `{data, meta}` / `{data:{items,next_cursor}}` | 자체 `{data}` | client에서 언랩 후 재투영 |

---

## 4. TripMate 현재 연결 상태 (진행)

- ✅ **T-170/T-171 완료(PR #102)**: `apps/api/app/clients/krtour_map.py` httpx client(계약
  메서드 + 도메인 예외 + 재시도 + 서비스 토큰 + lifespan/dependency) + `Settings`
  `tripmate_krtour_map_*` 배선. user API(9011) 소비 준비됨.
- 레거시 `apps/api/app/etl_bridge/krtour_map.py`(in-process Protocol stub) + `features.py`
  라우터는 아직 stub을 사용 → `/features/*` 503. **라우터 cutover/셰입 정렬은 T-173/T-124**.
- `trip_view_builder`/`cluster_query`는 완성됐으나 미연결(T-175/T-174).
- admin 도메인(9012) feature change client는 미구현(T-180, PR #317로 대상 API 생김).

---

## 5. 인증·경계 확인 필요 (krtour와 합의)

1. **서비스 토큰 메커니즘**: `X-Krtour-Service-Token` 헤더 값/발급 주체/검증 위치(프록시).
   운영 배포에서 TripMate→krtour 호출이 인증되는 구체 방식.
2. **`/v1` prefix 시점**: 도입 전까지 unprefixed 고정, 도입 시 base path만 교체.
3. **cache-target write 위치**: 현재 `/admin/poi-cache-targets/*`(admin 표면). TripMate가
   POI를 cache target으로 등록하려면 `/tripmate/*`로 이동 필요(krtour 예고됨) — by-target nearby 쓸 때.
4. **DEC-05 — K-15 해소(krtour PR #317)**: feature change API(`POST/PATCH/DELETE /admin/features`)
   신설됨 → T-179 actionable. **잔여 합의(§7)**: review_mode(require_review vs immediate),
   idempotency_key 멱등성, 출처 태깅, closure(DELETE vs deactivate), admin 인증.
5. **rate limit**: `RATE_LIMITED` 정책값(분당 한도) 확인 → TripMate 디바운스/캐시 정합.

---

## 6. TripMate 측 작업 목록 (붙이는 작업)

> 권장 순서: A→B→C 먼저(연결 토대), 이후 D~H 병행. 각 항목 제안 Task.

- **[A] ✅ T-170 — httpx client 신설** (완료 PR #102): `apps/api/app/clients/krtour_map.py`
  + lifespan/dependency + MockTransport 계약 테스트.
- **[B] ✅ T-171 — config 배선** (완료 PR #102): `Settings` `tripmate_krtour_map_*` + `.env.example`.
- **[C] T-172 — feature_id 문자열 정합 마감**: #87 후속, `features.py`/`schemas/feature.py`/
  `trip_view_builder`의 잔여 `uuid.UUID` 캐스트·`split("@")` 가정 제거(감사 C-09).
- **[D] T-173 — 응답 셰입 정렬**: `schemas/feature.py` + `docs/api/features.md`를 krtour
  실제 계약(`name`/평면 lon,lat/구조화 address/weather metric 그룹핑/cluster 셰입)에 맞춤.
- **[E] T-174 — 클러스터링 서버 위임**: `/features/in-bounds`가 krtour `cluster_unit` 결과를
  쓰도록 변경. `services/cluster_query.py`(직접 `feature` schema SQL — 경계 위반) **제거**.
- **[F] T-175 — trip view 배치 연결**: `GET /trips/{id}`에 `trip_view_builder` 연결(감사 C-05) +
  `POST /tripmate/features/batch`(string ids, cap 200 청크) 호출 + `{items,missing}` → snapshot
  fallback 매핑.
- **[G] T-176 — 검색/날씨/카테고리/근접 라우터 실연결**: `/features/{id}/weather`(metric 그룹핑),
  `/search`(feature=krtour + 주소=kraddr-geo + 내 POI), `/features/nearby`, `/categories` 캐시.
- **[H1] T-177 — 사용자 feature 제안 큐(DEC-05, user 도메인)**: `app.feature_suggestions`
  테이블 + `POST /features/requests`(즉시 201) + `GET /features/requests/{id}` 실구현
  (감사 C-12 미존재 테이블 실체화), per-user rate-limit + dedup. **krtour 직접 호출 X.**
- **[H2] T-179 — Admin 검사/승인 → krtour feature change(DEC-05, admin 도메인) — actionable**:
  `/admin/feature-requests` 목록/검사 + `approve`/`reject`(RBAC admin/operator + audit).
  승인 시 §2.9 **`POST/PATCH/DELETE /admin/features`** 호출(K-15 = krtour PR #317로 구현됨).
  결과 `feature_id`/`request_id`/state를 `feature_suggestions`에 저장. review_mode 합의(§7) 선행.
  ⚠️ 재적재(feature-update-request)와 **무관**.
- **[admin client] T-180 — krtour admin HTTP client(9012)**: §2.9 feature change +
  (운영자) feature-update-request 재적재 proxy를 호출하는 admin-base client. T-170의 user
  client(9011)와 분리. `tripmate_krtour_map_admin_base_url` + 서비스 토큰.
- **[공통] T-178 — 에러/저하 정책**: krtour 5xx/timeout → TripMate `503 FEATURE_SERVICE_UNAVAILABLE`
  + POI snapshot fallback(read), `LOCK_BUSY`/`RATE_LIMITED`는 Retry-After 존중.
- **[표준 추종] T-181 — ADR-048(krtour PR #316) 표준 추종 (hard cutover lockstep)**: krtour
  외부 표면 `/v1` + RFC7807 + 파라미터/좌표명 정렬이 안정되는 **cut commit에 맞춰 T-170 client를
  lockstep 일괄 교체** — (1) base path `/v1`(config-driven, **이중지원 의존 안 함**), (2)
  `_error_code`를 problem+json **top-level 확장 `code`** 파싱으로, (3) 쿼리 빌더 개명 대응
  (`search` bbox CSV→4 float, in-bounds `limit`→`max_items`, `total_count` opt-in
  `?include_total=true`), (4) 좌표 필드명 정렬 결과 반영(§7-B, DEC-07 하위결정), (5) **envelope
  payload/meta 분리 대응** — client list 메서드가 `data.next_cursor` 대신 `meta.page.next_cursor`를
  threading(현재 `data`만 반환·`meta` 폐기 → page 메서드는 작은 page 객체 반환으로 변경), `meta`/
  `request_id` 항상 present·`next_cursor` null 계약 테스트. frontend는 T-210e codegen이 신 spec pin.
  **선행**: §7 ADR-048 A~F 수렴 완료(df69057) + 잔여 1(batch `items` 키 충돌) 정리. krtour spec이
  아직 unprefixed라 **현재 대기**(차단 아님). ※ 2026-06-09 재리뷰로 "무중단 이중지원" 전제 **철회**.

---

## 7. 미해결 / 사용자 결정 후보

- DEC-05 — **확정(2026-06-08)**: 재적재(krtour admin, 비노출)와 사용자 제안 완전 분리.
  K-15 feature change API는 **krtour PR #317로 구현 완료**.
- **PR #317 연동 합의 대기(krtour PR #317 코멘트로 질의)**:
  1. **review_mode**: TripMate가 자기 Admin에서 이미 검수하므로 이중 검수 방지 —
     krtour `immediate` 운영 / TripMate `create→approve` 2-step / 요청 단위 override 중 합의.
  2. **idempotency_key 멱등**: 같은 제안 재시도 시 동일 feature_id 반환 여부.
  3. **출처 태깅**: TripMate + suggestion_id 추적(operator/reason vs 전용 source 필드).
  4. **admin 인증**: `/admin/features*`(`require_admin_destructive_enabled`, 9012) 호출 토큰 방식.
  5. **closure**: 영구 폐업 = `DELETE`(soft) vs `/{id}/deactivate` 권장.
- **ADR-048 재리뷰 A–F — 수렴 완료(krtour df69057에서 6건 전부 수용, 2026-06-09)**:
  소유자 지시(호환성 무시, 일관성/확장성/안정성 우선)로 1차 "무중단/동결"을 철회한 재리뷰를
  krtour가 **전부 반영**. 합의 결과(이제 krtour `docs/rest-api.md` + ADR-048 #2~#13에 박힘):
  - **A. hard cutover ✅**: 외부 `/v1` clean cut, 구 unprefixed/alias 미유지(ADR-046 무-shim 정합).
    `Deprecation`/`Sunset`은 GA 후 `/v2` 거버넌스에만 귀속.
  - **B. 좌표명 = `lon`/`lat` ✅(ADR-048 #10)**: krtour 정본 유지, **TripMate DEC-07을 `lon`/`lat`로
    하향 정렬**(경계 매핑 0). → 우리측 T-182.
  - **C. `cluster_key` 유지 ✅**: 코드 확인 결과 행정구역 코드(sido/sigungu/eupmyeondong) =
    **자연키**라 §3.1 규칙상 `cluster_key`가 맞음(krtour 2차의 `cluster_id` 개명 철회).
  - **D. `feature_id` 값 불변식 ✅(§3.2/#11)**: 재적재·편집·버전승급·soft delete에 값 불변,
    정체성 변경 = 새 feature+link. FK·snapshot 영속 보장.
  - **E. envelope 불변식 ✅(§3.3/#12)**: `meta`/`request_id` 전 응답 present, `meta.page.next_cursor`
    항상 키 존재·소진 시 `null`.
  - **F. `/vN` 거버넌스 ✅(#13)**: pre-1.0 in-place break → v1.0.0 GA에 `/v1` 동결 → `/v2`+N-1.
  - **추가 수용**: krtour 2차의 **envelope payload/meta 완전 분리(#2)** — `data`=payload만
    (목록 `{items:[]}`), pagination/추적은 `meta{duration_ms,request_id,page{page_size,next_cursor,
    total}}`로 일원화. **소비자 관점 endorse**(확장성·일관성↑). + action sub-resource 규약(#8) +
    단일 정본 수렴(#9, `rest-api.md`=전 표면 정본 / `tripmate-rest-api.md`=소비 매핑 view).
- **ADR-048 3차 검토 — 잔여 정합성 2건(krtour PR #316 3차 코멘트, 2026-06-09)**:
  1. **batch `items`(map) ↔ list `items`(array) 키 충돌**: `POST /tripmate/features/batch`는
     `data={items{}, missing[]}`(id-keyed map)인데 list는 `data={items:[]}`(배열) → 같은 `items`
     키가 2종 타입이라 공유 모델·`openapi-typescript` codegen 충돌. **batch는 별도 키 권장**
     (예: `data={found:{<id>:feature}, missing:[]}`). map 자체는 유지, 이름만 분리.
  2. **`cluster_unit` 위치(minor)**: in-bounds `data.cluster_unit`은 적용 granularity = 메타 성격 →
     `meta`(또는 `meta.cluster`) 후보. 강제 아님, krtour 판단.
- **DEC-07 좌표명 하위결정(신규, B 선결)**: TripMate 정본 좌표 필드를 `lon`/`lat`(krtour 정렬,
  terse) vs `longitude`/`latitude`(현 DEC-07 유지, krtour가 맞춤) 중 택1. 권고: **`lon`/`lat`로
  정렬**(krtour가 대용량 feature read 소유 + 바이트·파싱 유리). 결정 시 DEC-07 + `schemas/feature`
  + web Zod 정렬.
- frontend codegen(T-210e): krtour `openapi.user.json` → `openapi-typescript` + Zod mirror +
  CI drift gate. (백엔드 client는 수기 httpx로 충분, krtour 권고.)
- `docs/krtour-map-integration.md`의 "목표(미존재)" 표현을 "구현됨"으로 갱신(후속 문서 PR) —
  본 문서가 구체 계약을 가지므로 거기로 포인터.
