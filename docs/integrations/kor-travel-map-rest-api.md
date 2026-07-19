# kor-travel-map REST API 계약 — Pinvi 소비 기준 (붙이는 작업 청사진)

> **목적**: Pinvi `apps/api`/`apps/web`가 `kor-travel-map`의 **운영 HTTP API**를
> 실제로 연결(integrate)하기 위한 권위 계약 + Pinvi 측 작업 목록.
> **상태(중대 변화)**: 2026-06-08 기준 **kor-travel-map이 운영급 HTTP API를 이미 구축했다.**
> 더 이상 "목표/aspirational"이 아니라 **실재하는 계약**이다 — ADR-026/027(DEC-01=B)
> 의 전제가 충족됨.
> **검증 기준선**: `kor-travel-map` `origin/main` `HEAD=f442bd0`
> (`packages/kor-travel-map-admin/openapi.user.json`, title `kor-travel-map-user` v0.2.0-dev) +
> Pinvi `origin/main` `HEAD=0485974`(#87 feature_id opaque string 반영)을 2026-06-08 대조.
> **2026-06-10 재대조 (kor_travel_map `origin/main` `0e45bd7`)**: kor_travel_map **ADR-048/T-216a~g 전부
> 머지 완료** — RFC7807 problem+json, envelope payload/meta 분리(`meta.page.next_cursor`),
> batch `data.found`(§7 잔여 1 우리 제안 **수용됨**), in-bounds `max_items`,
> `meta.cluster.cluster_unit`(§7 잔여 2 수용됨). → **T-181 잔여 lockstep 대기 해제,
> 실행 가능**. 본문 중 "미머지/대기" 표기는 이 노트가 우선한다.
> 추가 정정: **kor_travel_map admin API는 :12701 `/v1/admin/*`**이다. 본문/`config.py`는
> admin API base도 `12701`을 기본값으로 둔다.
> 결정 반영: 재적재 vs 사용자 제안 분리 흐름(§2.8/2.9)은 kor_travel_map **ADR-051(2026-06-10)**로
> 공식 승인됐고, 잔여 합의 5건(§7)은 kor_travel_map T-217c가 확정해 회신 예정.
> **2026-06-12 추가**: kor-travel-map `curated_features`는 Pinvi
> `curated_trip_plans`의 추가 import 소스다. Pinvi-native 큐레이션을 대체하지 않는다.
> 상세 REST 계약은 아직 미확정이므로 §2.11은 후속 소비 설계로만 기록한다.
> **2026-06-24 재대조 (kor_travel_map `feat/admin-auth-api-keys` `ae86783`)**:
> REST backend 패키지 정본 경로가 `packages/kor-travel-map-api/openapi.user.json`으로
> 이동했고, public REST surface는 설정에 따라 `key` query를 요구할 수 있다
> (service token 요청은 우회). `curated_features`의 item 포함 snapshot 경로는 이후 kor_travel_map
> PR #533으로 admin `/v1/admin/curated-features/{id}/detail-snapshot`으로 이관됐다(ADR-049, §2.11).
> **정본 소스**: kor-travel-map `packages/kor-travel-map-api/openapi.user.json`(사용자 표면) +
> `docs/architecture/rest-api.md`(prose 계약). 본 문서와 충돌 시 **openapi.user.json 우선**.
> **관계**: 능력 격차 분석은 `docs/kor-travel-map-requirements.md`(이제 대부분 해소),
> 통합 패턴 개요는 `docs/kor-travel-map-integration.md`(본 문서가 구체 계약으로 대체/보강).
>
> **2026-07-18 T-ADM-C6c clean cut**: admin ops 소비는
> `/v1/ops/datasets`·`/v1/ops/pipeline/{overview,executions}`·pipeline cancellation이 정본이다.
> 삭제된 `/v1/ops/dagster/summary`·`/v1/ops/providers*`·`/v1/ops/import-jobs*`를 호출하거나
> alias로 복구하지 않는다. Pinvi server는 ops 호출에 frontend BFF secret을 쓰지 않고,
> map 전용 service/operator token과 method별 scope만 보낸다.
> import-job 목록의 `load_batch_id`/`parent_job_id`는 Pinvi 경계에서 UUID 정규형으로 고정한다.
> cancellation POST가 dispatch된 뒤 invalid JSON·envelope drift·비계약 5xx 또는 projection drift가
> 발생하면 실패로 단정하지 않고 503 `PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN`과 canonical detail GET
> reconciliation으로 수렴한다. Map의 typed 502는 `DAGSTER_TERMINATE_FAILED`, typed 503은
> `DAGSTER_UNAVAILABLE|DAGSTER_TERMINATION_TIMEOUT` status/code 쌍만 그대로 보존한다.
> Admin UI는 409·5xx·전송 오류처럼 결과가 불확실할 때만 job별 reconciliation을 잠근다.
> 400/401/403/422/429와 exact `404 PIPELINE_EXECUTION_NOT_FOUND`의 확정 거절은 polling 없이 form과
> 입력을 보존해 수정·재시도한다. code 누락·불일치·route drift 404는 미확정 reconciliation을 유지하며,
> 두 사유는 Pinvi body 계약과 같은 최대 500자다.
> update request 원 scope는 optional이지만 있으면 canonical이며 effective scope와 같아야 한다.
> selector-none은 원 scope null/effective `dataset_wide`이고 직접 pair member는 effective scope를 쓴다.
> non-exact root의 provider/dataset 배열은 요청 filter이며 대표 pair가 없을 수 있다. root는 child
> provider/dataset pair를 함께 가질 수 있고 상세 요청 job은 anchor/대표가 아닌 same-root child일 수 있다.
> 모든 ops 성공의 `meta.duration_ms/request_id`와 전달 `X-Request-Id` 상관관계를 검증한다. typed
> cancellation problem은 전체 detail과 member/run 불변식을 통과해야 하며, 404는 정확한
> `PIPELINE_EXECUTION_NOT_FOUND`만 보존한다. grid는 canonical detail URL, preview/scope-refresh,
> canonical/orphan 조합과 pair 기준 active/latest를 정본으로 검증한다.
> effective provider/dataset vector는 request filter와 representative pair의 exact 합집합이다. standalone
> child lookup은 recursive lineage이므로 직계 parent만으로 제한하지 않는다. 409 `IN_PROGRESS`는 full
> `in_progress` detail/root-only, `UNSAFE`는 full `failed` detail/root-only/detail 없음 shape만 보존한다.
> attempt `failed`의 member `cancel_failed`는 frozen base mismatch가 근거이므로 모든 canonical run
> 결과와 조합될 수 있다. `retryable`은 run-backed failed member와 matching run이 모두
> `cancel_failed`이고 세 error가 retry-capable code인 exact 조합만 허용한다. resolved member 불가능
> 전이와 noncanonical run enum은 허용하지 않는다. attempt `failed`의 attempt error는 failed canonical
> code여야 하지만 exact-base retryable member/run evidence와 definitive failed evidence는 섞일 수 있다.
> `cancel_failed` run error는 retryable/failed canonical code만 허용한다. 최초 attempt만 full root
> topology를 요구하고 retry lineage는 unresolved subset에서 resolved root/requested member 누락을
> 허용한다. attempt/run timestamp와 termination flag, resolved member/Dagster terminal mapping은 Map DB
> lifecycle을 따른다. typed 502/503은 detail `status=retryable`과 outer/detail attempt error code exact
> 일치까지 검증한다. 409 in-progress와 typed 502/503의 `Retry-After`는 digit-only 1..300이 필수이며
> 409 unsafe에는 header가 없어야 한다. Python/TS relay도 같은 범위만 파싱한다. attempt finish 전
> `in_progress/error=null`에서 member `cancel_failed`와 terminal run이 잠시 공존하는 CAS snapshot은
> 허용하지만 pending run·unknown error policy는 거부한다. error code/message와 member operation kind는
> 각각 Map invariant와 DB의 trim/non-empty 제약을 따른다.

---

## 0. 한눈에 — 무엇이 바뀌었나

`docs/kor-travel-map-requirements.md`(2026-06-06)가 "kor-travel-map에 없다"고 한 능력 대부분이
**구현 완료**됐다. kor-travel-map은 `packages/kor-travel-map-api`(FastAPI, 포트 **12701**)에
Pinvi-facing `openapi.user.json`을 export하고, 다음 사용자 표면 엔드포인트를 제공한다:

| 능력 | 엔드포인트 | 직전 상태 → 현재 |
|------|-----------|------------------|
| bbox + 클러스터 | `GET /features/in-bounds` | 클러스터 미지원 → **서버 클러스터(`cluster_unit`) 지원** |
| 단건 상세 | `GET /features/{feature_id}` | ✅ |
| **배치** | `POST /v1/features/batch` (구 `/pinvi/features/batch`) | ❌ → **✅(cap ≤200, 응답 `data.found`)** |
| 반경 | `GET /features/nearby` / `/nearby/by-target` | ❌ → **✅(cursor)** |
| 텍스트 검색 | `GET /features/search` | ❌ → **✅(cursor)** |
| 날씨 카드 | `GET /features/{feature_id}/weather` | 미구현 → **✅(metric 목록)** |
| 카테고리 | `GET /categories` | export만 → **✅ HTTP** |
| 공개 해수욕장 | `GET /v1/public/beaches*` | kor_travel_map T-222b → **✅(목록·상세·marker)** |
| 공개 축제 | `GET /v1/public/festivals*` | kor_travel_map T-222b → **✅(월별 목록·상세·marker)** |
| feature 갱신요청 | `POST /v1/admin/feature-update-requests` + `GET .../{id}` (kor_travel_map 운영자 전용, §2.8) | ❌ → **✅** |
| provider 신선도 | `GET /providers/{provider}/last-sync` | — → ✅ |
| health/version | `GET /health`, `GET /version` | — → ✅ |

Pinvi는 feature read cutover와 drift gate를 완료했고, 2026-06-12에는 public
beach/festival 표면도 소비 측에서 연결했다(T-130). 남은 큰 cross-repo 소비 작업은 kor_travel_map
`curated_features` REST 계약 확정 후 Pinvi `curated_trip_plans` 1:1 import(T-211)다.

---

## 1. 연결 규약 (전 엔드포인트 공통)

- **Base URL**: 로컬 `http://127.0.0.1:12701` — **admin/ops API 포함 전 표면이 :12701**
  (`/v1/admin/*`·`/v1/ops/*` path로 구분, Pinvi Admin 프록시 전용·사용자 경로 미노출).
  Pinvi 설정은 `PINVI_KOR_TRAVEL_MAP_API_BASE_URL`과
  `PINVI_KOR_TRAVEL_MAP_ADMIN_BASE_URL` 모두 기본값을 `12701`로 둔다.
- **버전 prefix**: **외부 전 표면 `/v1` (라이브, 2026-06-09)** — kor_travel_map PR #318/#319/#321이 `/v1`
  clean cut + batch `/pinvi/features/batch`→`/v1/features/batch` + 파라미터 개명을 머지
  (`openapi.user.json` `kor-travel-map-user 0.2.0-dev`). `/health`·`/version`만 비버전. **Pinvi T-170
  client는 `/v1`로 hard cutover 완료**(T-181) — 전 feature/category 경로 `/v1`, batch 경로/검색
  파라미터(`min_lon/min_lat/max_lon/max_lat`+`page_size`) 갱신. 구 unprefixed alias 미유지(ADR-046).
  ※ ~~problem+json 에러 + envelope payload/meta 분리는 kor_travel_map 미머지~~ → **2026-06-10
  kor_travel_map `0e45bd7`에서 머지 완료** — client의 `{error:{code}}`·`data.next_cursor` 파싱은
  이제 실계약과 불일치, **T-181 잔여 즉시 실행 대상**(problem+json `code`,
  `meta.page.next_cursor`, batch `found`, in-bounds `max_items`).
- **인증**: kor_travel_map ADR-060 이후 public REST surface(`/v1/features*`,
  `/v1/public*`, `/v1/categories`, `/v1/providers*`)는 운영 설정
  `KOR_TRAVEL_MAP_API_PUBLIC_API_KEY_REQUIRED=true`에서 VWorld 호환 `key` query를
  요구할 수 있다. trusted admin proxy 또는 `X-Kor-Travel-Map-Service-Token` 요청은
  이 검증을 우회한다. Pinvi client는 `PINVI_KOR_TRAVEL_MAP_SERVICE_TOKEN`이 있으면
  service token 헤더를 보내고, 없으면 `PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY`(미설정 시
  `PINVI_VWORLD_API_KEY`)를 `key` query로 붙인다. **사용자 토큰을 kor_travel_map로
  전달하지 않는다.** `/v1/admin/*`는 운영에서
  `X-Kor-Travel-Map-Admin-Proxy-Secret` + `X-Kor-Travel-Map-Actor`가 필요할 수 있으며,
  Pinvi admin client는 `PINVI_KOR_TRAVEL_MAP_ADMIN_PROXY_SECRET`/`..._ACTOR`로 전송한다.
  단, canonical `/v1/ops/datasets*`·`/v1/ops/pipeline*`와 관측 read
  (`/v1/ops/consistency/*`, `/v1/ops/system-logs`, `/v1/ops/api-call-logs`)의
  server-to-server 호출은 이 frontend 자격을 전송하지 않는다. GET은
  `PINVI_KOR_TRAVEL_MAP_OPS_READ_TOKEN`,
  canonical cancellation은 별도 `PINVI_KOR_TRAVEL_MAP_OPS_CANCEL_TOKEN`을
  `X-Kor-Travel-Map-Ops-Token`으로 보내고, 각각
  `X-Kor-Travel-Map-Ops-Scope: ops:read`와 `ops:cancel`을 보낸다. cancel token은 pipeline
  cancellation POST 이외의 mutation에는 사용할 수 없다. 두 token은 서로 달라야
  하며 한 token과 caller가 주장한 scope를 조합하는 방식으로 대체할 수 없다. actor는
  kor_travel_map 서버 설정의 `service:pinvi`로 고정해 요청 header로 위조할 수 없게 한다.
  비운영에서는 두 token이 모두 비어 있을 때만 local-dev opt-out을 허용한다. 하나라도 설정하면
  두 token을 모두 설정해야 하고, 각각 32자 이상, 모든 Unicode whitespace 금지, 서로 다름을
  동일하게 강제한다. production은 opt-out을 허용하지 않는다. 운영 admin base URL은 HTTP(S),
  host `127.0.0.1|host.docker.internal`, port `12701`, root path만 허용한다. cross-repo smoke는
  반드시 두 service principal 경로를 각각 사용한다. `/v1/ops/metrics`와
  `/v1/ops/health-deep`는 현재 PinVi runtime direct caller가 없으며 새 caller도 같은
  `ops:read` 계약 없이는 추가하지 않는다.
  Pinvi cancellation relay는 POST 전에 운영자·`access_reason`·`request_id` intent를 감사 원장에
  commit하고 결과를 같은 `request_id`로 추가 기록한다. 응답 성공/typed 실패/network loss 모두
  canonical detail과 import-job/provider grid 목록 GET으로 재조정하며 blind POST retry는 하지 않는다.
  detail의 요청 job id, execution/import job, standalone 또는 update-request root, frozen cancellation
  member identity가 서로 맞지 않으면 502로 fail-close한다. 취소 typed 409는
  `PIPELINE_CANCELLATION_IN_PROGRESS|PIPELINE_CANCELLATION_UNSAFE`만 보존하고, 404
  `PIPELINE_EXECUTION_NOT_FOUND`의 code/details도 그대로 보존한다.
- **응답 envelope (확정 — kor_travel_map 0e45bd7 라이브)**: 성공 = `{ "data": <payload>, "meta": <Meta> }`.
  `data`는 **payload만** — 단건 `<object>`, 목록 `{items:[]}`, in-bounds `{clusters:[],items:[]}`,
  batch `{found:{<id>:Feature}, missing:[]}`. pagination·추적은 `meta`로 일원화:
  `meta = { duration_ms, request_id, page?:{page_size, next_cursor, total}, cluster?:{cluster_unit} }`
  (`page`는 pageable 목록에만, `total`은 `?include_total=true` opt-in 기본 `null`,
  `cluster`는 in-bounds 클러스터 응답에만 — optional 취급). `meta`/`request_id`는 전 응답
  항상 present, `next_cursor` 소진 시 `null` (불변식 §1.4/E). `data.next_cursor`/
  `data.total_count`/`count`는 **폐기됨** — **T-170 client list 메서드의
  `meta.page.next_cursor` threading 교체 = T-181 잔여**(현재 `data`만 반환·`meta` 폐기).
  canonical ops client는 `meta`를 선택값으로 완화하지 않는다. `duration_ms` 누락/음수, non-string
  `request_id`, 전달한 `X-Request-Id`와 다른 응답 ID는 upstream 성공으로 인정하지 않는다.
  dataset `sync_scope`는 `dataset_wide|target_grids|external_system:<name>`만 허용하고,
  `poi_cache_targets.allowed_sync_scopes`에는 `dataset_wide`를 섞지 않는다.
- **에러 envelope (확정 — RFC7807 라이브)**: `Content-Type: application/problem+json`,
  body = `{ type, title, status, detail, code, request_id }` — 머신 코드는 **top-level 확장
  멤버 `code`**. 표준 코드: `FEATURE_NOT_FOUND`(404), `INVALID_BBOX`(422),
  `TOO_MANY_IDS`(422, 배치>200), `VALIDATION_ERROR`(422), `RATE_LIMITED`(429),
  `LOCK_BUSY`(409 + `Retry-After`), `UPSTREAM_UNAVAILABLE`(503). Pinvi client
  `_error_code`는 현재 `payload["error"]["code"]`를 읽으므로 **problem+json top-level
  `code` 파싱으로 교체 = T-181 잔여**.
- **좌표**: WGS84, 순서 **lon, lat**. bbox = `min_lon, min_lat, max_lon, max_lat`.
  목록/요약 응답의 좌표는 **평면 `lon`/`lat` 숫자**(중첩 `coord{}` 객체 아님).
- **datetime**: ISO 8601(KST-aware). **Pinvi는 자기 외부 응답에서 `+09:00`로
  재투영**(ADR-030) — kor_travel_map 원본 그대로 사용자에게 흘리지 않는다.
- **Pinvi 응답 셰입은 Pinvi 소유**. kor_travel_map 응답을 받아 Pinvi `{data,meta}`로
  다시 감싸고 필요한 필드만 투영한다. 원천 필드명 의미는 바꾸지 않는다.

---

## 2. 엔드포인트 계약

각 항목: 호출 형태 → 응답 핵심 셰입 → Pinvi 소비처 → 매핑/주의.

### 2.1 `GET /v1/features/in-bounds` — 지도 viewport
- **params**: `min_lon* min_lat* max_lon* max_lat*`(number), `kind`(repeat), `category`,
  `zoom`, `cluster_unit`, `max_items`(≤2000, 기본 1000 — 구 `limit` 폐기).
- **200 `FeaturesInBoundsResponse`**: `data:{ clusters:[ClusterSummary], items:[FeatureSummary] }, meta:{duration_ms, request_id, cluster?:{cluster_unit}}`
  (`count`/`data.cluster_unit` 폐기 — granularity는 `meta.cluster`).
  - `ClusterSummary` = `{ cluster_key, feature_count, lon, lat }`.
  - `FeatureSummary` = `{ feature_id, kind, name, category, lon|null, lat|null, marker_color|null, marker_icon|null, status }`.
- **소비처**: Pinvi `GET /features/in-bounds`(features.py). 지도 마커/클러스터.
- **주의**: **클러스터링은 kor_travel_map 서버가 한다**(`cluster_unit`/`zoom`). Pinvi
  `services/cluster_query.py`(직접 `feature` schema SQL 조인)는 **경계 위반 + 중복** —
  제거하고 서버 cluster로 대체(§6-E). 응답 클러스터 셰입(`cluster_key/feature_count/lon/lat`)이
  Pinvi 현재 schema(`cluster_id/center/feature_count/sample_kinds/bbox`)와 다름 → 정렬 필요.

### 2.2 `GET /v1/features/{feature_id}` — 단건 상세
- **params**: `feature_id*`(**string** path).
- **200 `FeatureDetailEnvelopeResponse`**: `data:FeatureDetailResponse` =
  `{ feature_id, kind, name, category, lon|null, lat|null, address(object), legal_dong_code|null,
  sido_code|null, sigungu_code|null, marker_color|null, marker_icon|null, urls(object),
  detail(object), status, updated_at }`.
- **소비처**: 마커 클릭 상세, POI 추가 시 검증. 404 = `FEATURE_NOT_FOUND`.
- **주의**: `name`(Pinvi 코드의 `title` 아님), `address`는 **구조화 객체**(평면
  `address_road/address_jibun` 아님) → schema 정렬(§6-D).

### 2.3 `POST /v1/features/batch` — 배치 조회 (성능 핵심)
- **body `FeatureBatchRequest`**: `{ feature_ids: [string] }` (**cap ≤200**, 초과 시 `TOO_MANY_IDS`).
- **200 `FeatureBatchResponse`**: `data:{ found: { <feature_id>: <FeatureDetail> }, missing:[string] }, meta:{...}`.
  (2026-06-10: id-keyed map 키가 `items`→**`found`**로 확정 — list `items[]`(배열)와
  타입 분리, 우리 §7 제안 수용. **client `_data().get("items")` 파싱은 T-181에서 `found`로
  교체 필수** — 현재는 전 결과가 조용히 missing 처리됨.)
- **소비처**: `GET /trips/{id}`의 `trip_view_builder` — trip POI들의 `feature_id[]`로 최신
  feature 일괄 조회(N+1 방지). `missing`은 삭제/없음 → POI `feature_snapshot` fallback + `is_broken`.
- **주의**: 200개 초과 trip은 **client에서 청크 분할** 호출. Pinvi
  `trip_view_builder`가 기대하는 `features_by_ids(list[uuid]) -> list` (UUID·list)를
  `{items,missing}` map·string으로 교체(§6-F).

### 2.4 `GET /v1/features/nearby` — 반경 + `…/nearby/by-target`
- **nearby params**: `lon* lat* radius_m*`, `kind` `category` `status` `provider`,
  `page_size`, `cursor`, `sort`(기본 distance).
- **200 `FeaturesNearbyResponse`**: `data:{ origin:NearbyOriginSummary, items:[NearbyFeatureSummary] }, meta:{..., page:{page_size, next_cursor, total}}`.
  `NearbyFeatureSummary` = FeatureSummary + `distance_m`. (`data.next_cursor` 폐기 →
  `meta.page.next_cursor`.)
- **by-target**: `external_system* target_key*`(등록된 POI cache target) + `radius_km`.
  Pinvi POI를 cache target으로 등록하면(kor_travel_map `PUT /v1/admin/poi-cache-targets/...`,
  admin 표면) "이 POI 주변" 질의 가능 — Sprint 후순위.
- **소비처**: "내 위치/POI 주변 N km". cursor 페이지네이션.

### 2.5 `GET /v1/features/search` — 텍스트 검색
- **params**: `q`, `kind`, `category`, 분리 4-float bbox(`min_lon/min_lat/max_lon/max_lat`),
  `page_size`, `cursor`, `include_total`(opt-in) — q 또는 bbox 필요. (구 `limit`/CSV bbox 폐기.)
- **200 `FeatureSearchResponse`**: `data:{ items:[FeatureSummary] }, meta:{..., page:{page_size, next_cursor, total|null}}`.
- **소비처**: 통합 검색(`GET /search`)의 **feature 파트만**. 주소 후보는 Pinvi가
  **kor-travel-geo v2 직접**(ADR-025), 내 POI는 Pinvi 로컬 — 합쳐서 응답.

### 2.6 `GET /v1/features/{feature_id}/weather` — 날씨 카드
- **params**: `feature_id*`, `asof`(선택).
- **200 `FeatureWeatherResponse`**: `data:WeatherCardData` =
  `{ feature_id, asof|null, latest_at|null, is_stale, source_styles:[string], metrics:[WeatherMetricOut] }`.
  `WeatherMetricOut` = `{ metric_key, metric_name|null, forecast_style, timeline_bucket|null,
  valid_at|null, issued_at|null, observed_at|null, value_number|null, value_text|null, unit|null, severity|null }`.
- **소비처**: feature 상세 날씨, 텔레그램 brief.
- **주의(셰입 대수술)**: kor_travel_map는 **평탄한 metric 목록 + forecast_style 태그**를 준다.
  Pinvi 현재 schema는 `{short_term[], daily[], sources[]}`, features.md는
  `{nowcast, ultra_short, short, mid, advisories}`. → Pinvi가 `forecast_style`
  (nowcast/ultra_short/short/mid/observed/index/advisory)별로 metric을 **그룹핑해 카드 구성**
  (변환은 Pinvi 표현 계층, KMA provider 변환 직접 작성 아님 — 금지룰 준수)(§6-D).

### 2.7 `GET /v1/categories` — 카테고리 카탈로그
- **params**: `include_counts`, `active_only`.
- **200 `CategoriesResponse`**: `data:{ items:[CategorySummary] }` (+`include_counts` 관련
  필드는 최신 `openapi.user.json` 확인 — `count`류는 envelope 표준화로 폐기 계열).
  `CategorySummary` = `{ code(8자리), label, parent_code|null, depth, path:[str], maki_icon,
  tier1..4_code/name, is_active, sort_order, db_active|null, db_feature_count|null }`.
- **소비처**: 마커 범례, 필터 칩, Admin 카테고리 매핑. 저빈도 → 클라이언트 캐시(긴 TTL).

### 2.8 재적재 vs 사용자 제안 — 완전히 별개 (DEC-05 확정, 2026-06-08)

**둘은 다른 작업이고 서로 연결되지 않는다.**

**(A) 재적재(feature-update-request) = kor-travel-map Admin — Pinvi 제품 무관**
- **경로 변경(kor_travel_map PR #317)**: `/pinvi/feature-update-requests*` alias **제거** →
  **`/v1/admin/feature-update-requests*`** 로 고정(admin spec — **API는 :12701**).
  `POST`(create/dry-run) / `GET /{id}` / `POST /{id}/cancel` / `POST /{id}/run-now`.
- "특정 scope를 다시 적재(Dagster job)"하는 **kor-travel-map 운영자 기능**. kor-travel-map admin
  콘솔에서 운영. **Pinvi 일반 사용자 비노출, 사용자 제안 흐름과 무관.**
  Pinvi 제품은 surface하지 않는다.

**(B) 사용자 feature 제안 = Pinvi 소유 → 승인 시 kor_travel_map feature change API로 반영**
- ① **사용자 제안 큐** (user 도메인, T-177 완료): `app.feature_suggestions` +
  `POST /features/requests`(즉시 201) + `GET /features/requests/{id}`.
  rate-limit/dedup. **kor_travel_map 직접 호출 X.**
- ② **Pinvi Admin 검사/승인/거절** (admin 도메인): `/admin/feature-requests` +
  approve/reject(RBAC admin/operator + audit). **승인 시 §2.9 kor_travel_map feature change API 호출.**

### 2.9 feature change API — `POST/PATCH/DELETE /admin/features` (kor_travel_map PR #317, K-15 해소)

**Pinvi Admin 도메인 전용**(`require_admin_destructive_enabled` + 서비스 토큰 —
**API base는 :12701 `/v1/admin/*`**). 사용자 제안 승인 시 호출.
`place`/`event`만 대상. **kor_travel_map ADR-051(2026-06-10)이 이 흐름을 전송 구간 정본으로
공식 승인** — 별도 suggestions API는 만들지 않는다.

| 동작 | 호출 | body 핵심 | 응답 |
|------|------|-----------|------|
| 추가 | `POST /admin/features` | `AdminFeatureCreateRequest`: `kind*(place\|event)`, `name*`, `category*`, `marker_color*`, `marker_icon*`, `reason*`, `coord{lat,lon}`, address/코드, `detail`, `urls`, `status(draft\|active\|inactive\|hidden)`, `feature_id?`, `idempotency_key?`, `operator?` | `AdminFeatureChangeResponse` |
| 수정 | `PATCH /admin/features/{feature_id}` | `AdminFeaturePatchRequest`: 전 필드 optional + `reason*` | 〃 |
| 삭제(soft) | `DELETE /admin/features/{feature_id}` | `AdminFeatureDeleteRequest`: `reason*`, `operator?` | 〃 |
| 비활성 | `POST /admin/features/{feature_id}/deactivate` | `AdminFeatureDeactivateRequest` | — |
| 검수 큐 | `GET /admin/features/change-requests`, `POST .../{id}/approve\|reject` | `AdminFeatureReviewActionRequest`(operator/reason) | 〃 |

- **낙관적 동시성(T-VN-13)**: 수정·삭제 전에
  `GET /admin/features/{feature_id}/revision`을 호출해 raw strong `ETag`를 읽고, 그 값을
  변형하지 않은 채 PATCH/DELETE의 단일 `If-Match` 헤더로 전달한다. 누락은 `428`, malformed는
  `422`, 제출 뒤 provider/user write가 끼어든 stale revision은 `412 PRECONDITION_FAILED`다.
  `412`를 자동 재시도하거나 마지막 write wins로 바꾸지 않고, 최신 feature를 다시 읽은 뒤 운영자가
  변경을 재검토·재제출하게 한다. change-request approve는 제출 당시 kor_travel_map이 저장한
  `base_row_revision`을 사용하므로 Pinvi가 별도 `If-Match`를 보내지 않는다.
- **응답 `data.request`(AdminFeatureChangeRequestRecord)**: `feature_id, request_id, action,
  state, review_mode, payload, base_row_revision, applied_at, reviewed_at/by, created_at`. → Pinvi는
  `feature_id`+`request_id`를 `feature_suggestions` row에 저장하고 state로 확정 추적.
- **review_mode(kor_travel_map 설정 `KOR_TRAVEL_MAP_ADMIN_FEATURE_CHANGE_REVIEW_MODE`, 기본 `require_review`)**:
  `require_review`=`ops.feature_change_requests`에 pending → kor_travel_map 운영자 approve 후 적용.
  `immediate`=요청 transaction에서 즉시 version 1 적용. **Pinvi는 자기 Admin에서 이미 검수**
  하므로 이중 검수가 되지 않도록 **review_mode 합의 필요(DEC-05 하위결정, §7)**.
- **version 0(provider)/1(user) 분리 내구성**: provider 재적재가 user version-1 row를 덮거나
  사용자 삭제 row를 되살리지 않는다(PR #317). → Pinvi가 추가한 장소·폐업 신고가 재적재로
  사라지지 않음(closure/correction 신뢰).
- **closure**: "영구 폐업" = `DELETE`(soft) 또는 `/{id}/deactivate` — kor_travel_map 권장 확정 필요(§7).

### 2.10 `GET /v1/providers/{provider}/last-sync`, `GET /health`, `GET /version`
- provider 신선도(brief/Admin 상태판), liveness, 버전. Pinvi Admin 상태판·헬스 체크용.
  `/health`·`/version`만 비버전 경로 (구 `/debug/health|version`은 kor_travel_map T-214h로 제거).

### 2.11 `curated_features` — Pinvi curated trip plan import (Admin 전용 detail snapshot)

**상태**: Pinvi가 kor-travel-map `GET /v1/admin/curated-features/{curated_feature_id}/detail-snapshot`을
소비해 `curated_trip_plans` / `curated_plan_pois`로 1:1 import한다. 구 public 경로
`GET /v1/curated-features/{id}/pinvi-copy`는 kor_travel_map PR #533로 제거됐고, item을
담은 snapshot은 이제 admin 표면(`/v1/admin/*`, 헤더 `X-Kor-Travel-Map-Service-Token` 필요)에만
존재한다(ADR-049).

제품 의미:

- Pinvi-native 큐레이션: Admin/운영자가 Pinvi 안에서 직접 만든다.
- kor_travel_map `curated_features` import: kor_travel_map curated feature 1건을 Pinvi
  `curated_trip_plans` 1건으로 1:1 복사한다.
- 두 흐름은 모두 같은 `/notice-plans` 사용자 copy 흐름을 사용한다.

사용하는 kor_travel_map REST 표면 (admin base :12701, 헤더 `X-Kor-Travel-Map-Service-Token` 필요):

```http
GET /v1/admin/curated-features/{curated_feature_id}/detail-snapshot
```

snapshot plan-level 객체 키는 `plan` → `content`로 개명됐다(ADR-049). version/etag/
updated_at/theme/source/items[]는 그대로다.

Pinvi import 매핑:

| kor_travel_map | Pinvi |
|--------|----------|
| curated feature 1건 | `app.curated_trip_plans` 1건 |
| curated feature item/POI | `app.curated_plan_pois` |
| item `feature_id` | `curated_plan_pois.feature_id` nullable 저장 |
| item 표시 snapshot | `feature_snapshot` |
| item day/order | `day_index` / `sort_order` |
| snapshot `version` / `etag` | `source_curated_feature_version` / `source_etag` |
| item id | `source_curated_feature_item_id` |

Pinvi는 kor-travel-map을 OpenAPI HTTP로만 호출한다. kor-travel-map Python 패키지 import나 DB
직접 접근은 금지한다. `kor-travel-concierge`는 Pinvi curated trip plan 생성 흐름에 관여하지
않는다.

---

## 3. 데이터 계약 (반드시 맞출 것)

| 항목 | kor_travel_map 실제(정본) | Pinvi 현재 | 조치 |
|------|-------------------|----------------|------|
| **feature_id** | `f_{bjd\|global}_{kind[0]}_{sha1[:16]}` **문자열**(예 `f_1168010100_p_3c0c2820e96d28d3`) — UUID 아님 | #87로 opaque string 1차 반영 | 잔여 `uuid.UUID(...)` 캐스트 전수 제거 확인(§6-C) |
| 표시명 | `name` | 일부 `title` | `name`으로 통일 |
| 좌표(목록) | 평면 `lon`/`lat` | ✅ T-182 완료(2026-06-09) — Pinvi 정본도 `lon`/`lat` 채택 | 잔여: 구모델 매핑(`coord.longitude`) 제거는 T-173 라우터 cutover에서 |
| 주소 | 구조화 `address` 객체 + `legal_dong_code/sido_code/sigungu_code` | 평면 `address_road/jibun` | schema 정렬 |
| category | 8자리 코드(`"01070100"`) + 카탈로그 label | 한글명 가정 흔적 | 코드 저장 + `/categories` label 조회 |
| marker | `marker_icon`(maki), `marker_color`(`P-01`~`P-16`) | 동일 | OK |
| 클러스터 | `{cluster_key, feature_count, lon, lat}` | `{cluster_id, center, feature_count, sample_kinds, bbox}` | 서버 셰입으로 정렬 |
| 날씨 | metric 목록 + `forecast_style` 태그 | `{short_term,daily}` / `{nowcast,…}` | 그룹핑 변환 |
| envelope | `{data, meta}` — `data`=payload만(목록 `{items}`, batch `{found,missing}`), pagination은 `meta.page.next_cursor` | 자체 `{data}` + client가 `data`만 반환 | client에서 `meta.page` threading 후 재투영(T-181) |

---

## 4. Pinvi 현재 연결 상태 (진행)

- ✅ **T-170/T-171 완료(PR #102)**: `apps/api/app/clients/kor_travel_map.py` httpx client(계약
  메서드 + 도메인 예외 + 재시도 + 서비스 토큰 + lifespan/dependency) + `Settings`
  `pinvi_kor_travel_map_*` 배선. user API(12701) 소비 준비됨.
- 레거시 `apps/api/app/etl_bridge/kor_travel_map.py`(in-process Protocol stub) + `features.py`
  라우터는 아직 stub을 사용 → `/features/*` 503. **라우터 cutover/셰입 정렬은 T-173/T-124**.
- `trip_view_builder`/`cluster_query`는 완성됐으나 미연결(T-175/T-174).
- admin 도메인 feature change client는 미구현(T-180, PR #317로 대상 API 생김).
  **base는 API 12701 `/v1/admin/*`** 이며, `pinvi_kor_travel_map_admin_base_url`도
  같은 기본값을 사용해야 한다.

---

## 5. 인증·경계 확인 필요 (kor_travel_map와 합의)

1. **서비스 토큰 메커니즘**: `X-Kor-Travel-Map-Service-Token` 헤더 값/발급 주체/검증 위치(프록시).
   운영 배포에서 Pinvi→kor_travel_map 호출이 인증되는 구체 방식.
2. ~~**`/v1` prefix 시점**~~ → **해소(2026-06-10)**: `/v1` 라이브, unprefixed alias 없음.
3. **cache-target write 위치**: `/v1/admin/poi-cache-targets/*`(admin 표면)로 확정 —
   `/pinvi/*` namespace는 kor_travel_map에서 **제거됨**(kor_travel_map는 Pinvi 전용이 아님).
   by-target nearby 쓸 때 등록 흐름은 admin flow로 협의.
4. **DEC-05 — K-15 해소(kor_travel_map PR #317)**: feature change API(`POST/PATCH/DELETE
   /v1/admin/features*`) 신설됨 → T-179 완료. **§7 합의 5건 ✅ 확정(kor_travel_map T-217c, 2026-06-11,
   kor_travel_map `decisions.md` ADR-051)** + Pinvi 반영 완료:
   1. **review_mode**: 기본 `require_review` 2단 검토(Pinvi 1차 + kor_travel_map 운영자 최종). →
      Pinvi는 record status `applied`→`added`, 그 외→`approved`.
   2. **idempotency_key** = `suggestion_id`(request_id) → kor_travel_map `make_feature_id(user_request,
      idempotency_key)`로 결정적 feature_id, 재시도 동일.
   3. **출처 태깅**: operator 고정 `"pinvi-admin"`(admin id 미노출, 익명 D-11) + reason
      `[suggestion:<request_id>]` prefix(change-requests 큐가 출처 표시).
   4. **admin 인증**: 12701 `/v1/admin/*`, 코드 인증은 kor_travel_map `admin_destructive_enabled`
      kill-switch뿐 — 호출자 인증은 인프라 계층(SSO/IP allowlist). service token은 선택 pass-through.
   5. **closure**: 영구 폐업 = soft `DELETE`(`user_deleted_*`, provider 재적재 부활 차단) /
      일시 비활성 = `deactivate`(미사용).
5. **rate limit**: `RATE_LIMITED` 정책값(분당 한도) 확인 → Pinvi 디바운스/캐시 정합.

---

## 6. Pinvi 측 작업 목록 (붙이는 작업)

> 권장 순서: A→B→C 먼저(연결 토대), 이후 D~H 병행. 각 항목 제안 Task.

- **[A] ✅ T-170 — httpx client 신설** (완료 PR #102): `apps/api/app/clients/kor_travel_map.py`
  + lifespan/dependency + MockTransport 계약 테스트.
- **[B] ✅ T-171 — config 배선** (완료 PR #102): `Settings` `pinvi_kor_travel_map_*` + `.env.example`.
- **[C] T-172 — feature_id 문자열 정합 마감**: #87 후속, `features.py`/`schemas/feature.py`/
  `trip_view_builder`의 잔여 `uuid.UUID` 캐스트·`split("@")` 가정 제거(감사 C-09).
- **[D] T-173 — 응답 셰입 정렬**: `schemas/feature.py` + `docs/api/features.md`를 kor_travel_map
  실제 계약(`name`/평면 lon,lat/구조화 address/weather metric 그룹핑/cluster 셰입)에 맞춤.
- **[E] T-174 — 클러스터링 서버 위임**: `/features/in-bounds`가 kor_travel_map `cluster_unit` 결과를
  쓰도록 변경. `services/cluster_query.py`(직접 `feature` schema SQL — 경계 위반) **제거**.
- **[F] T-175 — trip view 배치 연결**: `GET /trips/{id}`에 `trip_view_builder` 연결(감사 C-05) +
  `POST /v1/features/batch`(string ids, cap 200 청크) 호출 + `{found,missing}` → snapshot
  fallback 매핑 (inactive feature는 `found`+status로 옴 — "철회/폐업" 표시 분기, kor_travel_map D-12).
- **[G] T-176 — 검색/날씨/카테고리/근접 라우터 실연결**: `/features/{id}/weather`(metric 그룹핑),
  `/search`(feature=kor_travel_map + 주소=kor-travel-geo + 내 POI), `/features/nearby`, `/categories` 캐시.
- **[H1 완료] T-177 — 사용자 feature 제안 큐(DEC-05, user 도메인)**:
  `app.feature_suggestions`
  테이블 + `POST /features/requests`(즉시 201) + `GET /features/requests/{id}` 실구현
  (감사 C-12 미존재 테이블 실체화), per-user rate-limit + dedup. **kor_travel_map 직접 호출 X.**
- **[H2] ✅ T-179 백엔드 — Admin 검사/승인 → kor_travel_map feature change(DEC-05, admin 도메인)** (완료
  2026-06-11): `apps/api/app/api/v1/admin/feature_requests.py` — `GET /admin/feature-requests`
  목록(RBAC admin/operator, 이메일 마스킹) + `approve`/`reject`(admin + audit). 승인 시 §2.9
  **`POST/PATCH/DELETE /v1/admin/features*`** 호출(suggestion_type별), 결과 `feature_id`/
  `request_id`/state를 `feature_suggestions.kor_travel_map_ref`에 저장(status `added`/`approved`). kor_travel_map
  호출 먼저 → 성공 시에만 commit(실패 시 pending 유지). idempotency_key=request_id, 출처 태깅
  operator 고정 `"pinvi-admin"` + reason `[suggestion:<id>]` prefix(§7 #3 확정·익명 D-11).
  ⚠️ 재적재(feature-update-request)와 **무관**. **web 검토 UI 완료**
  (`apps/web/app/(admin)/admin/feature-requests/page.tsx` — 검토 큐 + 승인/거절 패널).
  **§7 합의 5건 ✅ 확정(kor_travel_map T-217c, 2026-06-11) + Pinvi 반영 완료** — §7 참조.
- **[admin client] ✅ T-180 — kor_travel_map admin HTTP client(API 12701 `/v1/admin/*`)** (완료 2026-06-11):
  `apps/api/app/clients/kor_travel_map_admin.py` — `KorTravelMapAdminClient` (create/patch/delete_feature
  → `data.request` + change-requests list/approve/reject, 재시도·도메인 예외는 user client 재사용).
  base = :12701 `/v1/admin/*` (`pinvi_kor_travel_map_admin_base_url` 기본값도 12701),
  `X-Kor-Travel-Map-Service-Token`(`pinvi_kor_travel_map_admin_service_token`, 미설정 시 공용 토큰 fallback).
  lifespan/`get_kor_travel_map_admin_client` 의존성 + MockTransport 계약 테스트. **승인 시 호출 배선은 T-179.**
- **[공통] T-178 — 에러/저하 정책**: kor_travel_map 5xx/timeout → Pinvi `503 FEATURE_SERVICE_UNAVAILABLE`
  + POI snapshot fallback(read), `LOCK_BUSY`/`RATE_LIMITED`는 Retry-After 존중.
- **[표준 추종] T-181 — ADR-048(kor_travel_map PR #316) 표준 추종 (hard cutover lockstep)**: kor_travel_map
  외부 표면 `/v1` + RFC7807 + 파라미터/좌표명 정렬이 안정되는 **cut commit에 맞춰 T-170 client를
  lockstep 일괄 교체** — (1) base path `/v1`(config-driven, **이중지원 의존 안 함**), (2)
  `_error_code`를 problem+json **top-level 확장 `code`** 파싱으로, (3) 쿼리 빌더 개명 대응
  (`search` bbox CSV→4 float, in-bounds `limit`→`max_items`, `total_count` opt-in
  `?include_total=true`), (4) 좌표 필드명 정렬 결과 반영(§7-B, DEC-07 하위결정), (5) **envelope
  payload/meta 분리 대응** — client list 메서드가 `data.next_cursor` 대신 `meta.page.next_cursor`를
  threading(현재 `data`만 반환·`meta` 폐기 → page 메서드는 작은 page 객체 반환으로 변경), `meta`/
  `request_id` 항상 present·`next_cursor` null 계약 테스트. frontend는 T-210e codegen이 신 spec pin.
  **선행**: §7 ADR-048 A~F 수렴 완료(df69057) + 잔여 1(batch `items`→`found`) — **kor_travel_map
  `0e45bd7`(2026-06-10)에서 전부 머지·해소됨 → 대기 해제, 즉시 실행 가능.**
  ※ 2026-06-09 재리뷰로 "무중단 이중지원" 전제 **철회**.
  ✅ **2026-06-10 완료(client 계층)**: `apps/api/app/clients/kor_travel_map.py` — (2) `_error_code`
  problem+json top-level `code`(구 `error.code` fallback), (3) in-bounds `limit`→`max_items` +
  `search` `include_total` opt-in, (5) `_payload`로 `(data, meta)` 분리 + nearby/search
  `meta.page.next_cursor`/`total` threading + in-bounds `meta.cluster.cluster_unit` re-projection,
  batch `data.found` 파싱. 계약 테스트 `tests/unit/test_kor_travel_map_client.py`(15). **이 client는 아직
  feature 라우터에 미배선(라우터는 레거시 Protocol stub 사용) — 라우터 cutover는 T-173.** (1)
  base path `/v1`는 기존 반영, (4) 좌표 평면 lon/lat은 기존 반영.

---

## 7. 미해결 / 사용자 결정 후보

- DEC-05 — **확정(2026-06-08)**: 재적재(kor_travel_map admin, 비노출)와 사용자 제안 완전 분리.
  K-15 feature change API는 **kor_travel_map PR #317로 구현 완료**.
- **PR #317 연동 합의 대기(kor_travel_map PR #317 코멘트로 질의)**:
  1. **review_mode**: Pinvi가 자기 Admin에서 이미 검수하므로 이중 검수 방지 —
     kor_travel_map `immediate` 운영 / Pinvi `create→approve` 2-step / 요청 단위 override 중 합의.
  2. **idempotency_key 멱등**: 같은 제안 재시도 시 동일 feature_id 반환 여부.
  3. **출처 태깅**: Pinvi + suggestion_id 추적(operator/reason vs 전용 source 필드).
  4. **admin 인증**: `/v1/admin/features*`(`require_admin_destructive_enabled`, **API 12701**) 호출 토큰 방식.
  5. **closure**: 영구 폐업 = `DELETE`(soft) vs `/{id}/deactivate` 권장.
- **ADR-048 재리뷰 A–F — 수렴 완료(kor_travel_map df69057에서 6건 전부 수용, 2026-06-09)**:
  소유자 지시(호환성 무시, 일관성/확장성/안정성 우선)로 1차 "무중단/동결"을 철회한 재리뷰를
  kor_travel_map가 **전부 반영**. 합의 결과(이제 kor_travel_map `docs/rest-api.md` + ADR-048 #2~#13에 박힘):
  - **A. hard cutover ✅**: 외부 `/v1` clean cut, 구 unprefixed/alias 미유지(ADR-046 무-shim 정합).
    `Deprecation`/`Sunset`은 GA 후 `/v2` 거버넌스에만 귀속.
  - **B. 좌표명 = `lon`/`lat` ✅(ADR-048 #10)**: kor_travel_map 정본 유지, **Pinvi DEC-07을 `lon`/`lat`로
    하향 정렬**(경계 매핑 0). → 우리측 T-182.
  - **C. `cluster_key` 유지 ✅**: 코드 확인 결과 행정구역 코드(sido/sigungu/eupmyeondong) =
    **자연키**라 §3.1 규칙상 `cluster_key`가 맞음(kor_travel_map 2차의 `cluster_id` 개명 철회).
  - **D. `feature_id` 값 불변식 ✅(§3.2/#11)**: 재적재·편집·버전승급·soft delete에 값 불변,
    정체성 변경 = 새 feature+link. FK·snapshot 영속 보장.
  - **E. envelope 불변식 ✅(§3.3/#12)**: `meta`/`request_id` 전 응답 present, `meta.page.next_cursor`
    항상 키 존재·소진 시 `null`.
  - **F. `/vN` 거버넌스 ✅(#13)**: pre-1.0 in-place break → v1.0.0 GA에 `/v1` 동결 → `/v2`+N-1.
  - **추가 수용**: kor_travel_map 2차의 **envelope payload/meta 완전 분리(#2)** — `data`=payload만
    (목록 `{items:[]}`), pagination/추적은 `meta{duration_ms,request_id,page{page_size,next_cursor,
    total}}`로 일원화. **소비자 관점 endorse**(확장성·일관성↑). + action sub-resource 규약(#8) +
    단일 정본 수렴(#9, `rest-api.md`=전 표면 정본 / `pinvi-rest-api.md`=소비 매핑 view).
- **ADR-048 3차 검토 — 잔여 정합성 2건 → ✅ 전부 수용·머지됨(kor_travel_map 0e45bd7, 2026-06-10)**:
  1. **batch `found` 채택**: `POST /v1/features/batch` 응답이 `data={found{}, missing[]}`로
     확정 (우리 제안 그대로). → T-181에서 client 파싱 교체.
  2. **`cluster_unit` → `meta.cluster.cluster_unit`** 채택 (cluster 응답 경로에서만 존재,
     optional 취급).
- **DEC-07 좌표명 하위결정(신규, B 선결)**: Pinvi 정본 좌표 필드를 `lon`/`lat`(kor_travel_map 정렬,
  terse) vs `longitude`/`latitude`(현 DEC-07 유지, kor_travel_map가 맞춤) 중 택1. 권고: **`lon`/`lat`로
  정렬**(kor_travel_map가 대용량 feature read 소유 + 바이트·파싱 유리). 결정 시 DEC-07 + `schemas/feature`
  + web Zod 정렬.
- frontend codegen(T-210e): kor_travel_map `openapi.user.json` → `openapi-typescript` + Zod mirror +
  CI drift gate. (백엔드 client는 수기 httpx로 충분, kor_travel_map 권고.)
- `docs/kor-travel-map-integration.md`의 "목표(미존재)" 표현을 "구현됨"으로 갱신(후속 문서 PR) —
  본 문서가 구체 계약을 가지므로 거기로 포인터.

---

## 8. 드리프트 게이트 (T-210e, 2026-06-11)

수기 httpx client(kor_travel_map 권고)가 kor_travel_map `openapi.user.json`과 silent drift하는 것을 막는다.

- **vendor 스냅샷**: `apps/api/tests/contract/kor-travel-map-openapi-user.json` — Pinvi가 구현 기준으로
  삼은 kor_travel_map user 스펙 pin.
- **계약 테스트**: `apps/api/tests/unit/test_kor_travel_map_contract.py` (CI `pytest tests/unit`에서 실행) —
  (1) user client 경로(`/v1/features/*`·`/v1/categories`·`/v1/public/*`) ⊆ 스냅샷 paths,
  (2) 매핑(`features.py`/`public.py`가 읽는 FeatureSummary/ClusterSummary/
  FeatureDetailResponse/WeatherCardData/WeatherMetricOut/CategorySummary/FeatureBatchData/
  BeachPublicView/FestivalPublicView/PublicMapMarkerLayerData 등) ⊆ 스냅샷 component schemas,
  (3) public beach query parameter exact shape,
  (4) 로컬 전용: sibling `kor-travel-map` 스펙과 public beach query shape 일치
  (핀 신선도, CI에서는 skip — `PINVI_KOR_TRAVEL_MAP_OPENAPI_USER_PATH`로 override 가능).
- **갱신 절차** (kor_travel_map 스펙 변경 시):
  1. `cp ../kor-travel-map/packages/kor-travel-map-api/openapi.user.json
     apps/api/tests/contract/kor-travel-map-openapi-user.json`
  2. `pytest apps/api/tests/unit/test_kor_travel_map_contract.py` 실행.
  3. 실패하면 사라진/바뀐 경로·필드·query를 `clients/kor_travel_map.py` +
     `features.py`/`public.py` 매핑 + `_CLIENT_PATHS`/`_CLIENT_QUERY_PARAMETERS`/
     `_SCHEMA_FIELDS`에 맞춰 갱신(= kor_travel_map drift 대응 PR).
- **codegen(선택)**: frontend `openapi-typescript` + Zod mirror는 미도입(후속). 백엔드는 본
  스냅샷 게이트로 충분(kor_travel_map 권고: 수기 httpx 유지).
