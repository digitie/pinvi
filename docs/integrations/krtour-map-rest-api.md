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
- **버전 prefix**: 현재 **prefix 없음**(`/features/...`). krtour는 향후 `/v1/...` 도입을
  forward-looking으로 예고(미구현). → TripMate client는 base path를 **설정값**으로 두어
  `/v1` 전환에 대비한다(§6-G).
- **인증**: 코드에는 인증 없음(krtour ADR-005). 운영 인증은 **네트워크/인프라 계층**에서
  강제 — reverse proxy SSO / IP allowlist / `X-Krtour-Service-Token` pass-through(krtour
  D-1). → TripMate client는 설정된 서비스 토큰 헤더를 **그대로 전달**할 수 있어야 한다
  (`TRIPMATE_KRTOUR_MAP_SERVICE_TOKEN`, 선택). **사용자 토큰을 krtour로 전달하지 않는다.**
- **응답 envelope**: 성공 = `{ "data": <payload>, "meta": { "duration_ms": int, ... } }`.
  목록 = `data.items[]` (+ keyset `data.next_cursor` 또는 `data.clusters[]`).
- **에러 envelope**: `{ "error": { "code", "message", "request_id", "retry_after_seconds"? } }`.
  표준 코드: `FEATURE_NOT_FOUND`(404), `INVALID_BBOX`(422), `TOO_MANY_IDS`(422, 배치>200),
  `RATE_LIMITED`(429), `LOCK_BUSY`(409 + `Retry-After: 15`, update-request `run_mode=now`),
  `UPSTREAM_UNAVAILABLE`(503). FastAPI 검증 실패는 `HTTPValidationError`(422).
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

### 2.8 `POST /tripmate/feature-update-requests` (+ `GET .../{request_id}`)
- **body `FeatureUpdateRequestCreateRequest`**: `{ scope*(BboxScope|CenterRadiusScope|
  FeatureIdsScope|…), run_mode('queued'|'now'), dry_run, providers[], dataset_keys[],
  update_policy, priority, operator, reason }`.
- **200 `FeatureUpdateRequestRecord`**: `{ request_id, state, status_url, scope_type, run_mode,
  job_id, dagster_run_id, started_at, finished_at, error_message, … }`.
- **소비처**: feature 데이터가 틀렸을 때 **재적재(re-load) 트리거**(scope 기준).
  `run_mode=now` 잠금 충돌 시 `LOCK_BUSY`(409, Retry-After 15).
- **⚠️ 의미 격차(DEC-05)**: 이건 "특정 scope를 다시 적재"하는 **운영 트리거**지,
  사용자가 "새 카페 추가해주세요"라고 자유 제출하는 큐가 **아니다**. TripMate
  `POST /features/requests {kind,title,coord,note}`(사용자 제안)와 셰입·의미가 다르다.
  → **권고**: 사용자 제안 큐는 TripMate `app` schema가 소유하고(자유 입력 보관), Admin
  승인 시에만 이 krtour 엔드포인트를 scope로 호출(§6-H, DEC-05).

### 2.9 `GET /providers/{provider}/last-sync`, `GET /health`, `GET /version`
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

## 4. TripMate 현재 연결 상태 (출발점)

- `apps/api/app/clients/krtour_map.py` **없음**. 존재하는 건 `apps/api/app/etl_bridge/krtour_map.py`
  — **in-process import용 Protocol stub**(`from krtour.map.client import AsyncKrtourMapClient`),
  싱글톤 항상 `None` → 모든 `/features/*`가 **503 LIBRARY_NOT_READY**. (HTTP 모델 아님.)
- `apps/api/app/core/config.py`에 `TRIPMATE_KRTOUR_MAP_*` **필드 없음** → `.env`의 base URL이
  `extra="ignore"`로 **조용히 무시**됨.
- `services/feature_view.py` 없음(라우터가 client 직접 호출). `trip_view_builder`/`cluster_query`는
  완성됐으나 **어떤 라우터도 호출 안 함**(dead code).
- 즉 TripMate는 **HTTP client·config·배선이 전부 미구현** 상태에서 출발한다.

---

## 5. 인증·경계 확인 필요 (krtour와 합의)

1. **서비스 토큰 메커니즘**: `X-Krtour-Service-Token` 헤더 값/발급 주체/검증 위치(프록시).
   운영 배포에서 TripMate→krtour 호출이 인증되는 구체 방식.
2. **`/v1` prefix 시점**: 도입 전까지 unprefixed 고정, 도입 시 base path만 교체.
3. **cache-target write 위치**: 현재 `/admin/poi-cache-targets/*`(admin 표면). TripMate가
   POI를 cache target으로 등록하려면 `/tripmate/*`로 이동 필요(krtour 예고됨) — by-target nearby 쓸 때.
4. **feature-update-request 소유권(DEC-05)**: 사용자 제안 큐 = TripMate, 재적재 트리거 = krtour.
5. **rate limit**: `RATE_LIMITED` 정책값(분당 한도) 확인 → TripMate 디바운스/캐시 정합.

---

## 6. TripMate 측 작업 목록 (붙이는 작업)

> 권장 순서: A→B→C 먼저(연결 토대), 이후 D~H 병행. 각 항목 제안 Task.

- **[A] T-170 — httpx client 신설**: `apps/api/app/clients/krtour_map.py`
  (`httpx.AsyncClient` lifespan 1개, 타임아웃/재시도(tenacity)/에러 변환, 서비스 토큰 헤더
  pass-through). 기존 `etl_bridge/krtour_map.py`의 in-process Protocol stub 제거/대체.
  계약 테스트는 `httpx.MockTransport` + krtour `openapi.user.json` 픽스처로 먼저 작성.
- **[B] T-171 — config 배선**: `core/config.py`에 `tripmate_krtour_map_api_base_url`(+ 선택
  service token, admin base) 필드 추가. `.env.example`는 이미 존재 — Settings가 읽도록.
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
- **[H] T-177 — feature 갱신요청 분리(DEC-05)**: TripMate `app` 사용자 제안 큐 +
  Admin 승인 시 krtour `POST /tripmate/feature-update-requests`(scope) 호출.
- **[공통] T-178 — 에러/저하 정책**: krtour 5xx/timeout → TripMate `503 FEATURE_SERVICE_UNAVAILABLE`
  + POI snapshot fallback(read), `LOCK_BUSY`/`RATE_LIMITED`는 Retry-After 존중.

---

## 7. 미해결 / 사용자 결정 후보

- DEC-05(feature-update-request 소유권) — §2.8/§6-H 권고안 확정 필요.
- frontend codegen(T-210e): krtour `openapi.user.json` → `openapi-typescript` + Zod mirror +
  CI drift gate. (백엔드 client는 수기 httpx로 충분, krtour 권고.)
- `docs/krtour-map-integration.md`의 "목표(미존재)" 표현을 "구현됨"으로 갱신(후속 문서 PR) —
  본 문서가 구체 계약을 가지므로 거기로 포인터.
