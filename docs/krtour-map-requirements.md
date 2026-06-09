# krtour-map 요구사항 명세 — TripMate가 필요로 하는 것

> **이 문서의 독자**: `python-krtour-map` 개발 에이전트.
> **작성 목적**: TripMate가 feature 도메인을 위해 `python-krtour-map`에 **구체적으로
> 무엇을, 왜, 언제** 필요로 하는지를 한 곳에 모아, krtour-map 쪽에서 우선순위와
> 계약을 결정할 수 있게 한다.
> **검증 기준선**: TripMate `main`(이 저장소) + `python-krtour-map` `main`
> `HEAD=b775c74`(`merge #111`) 양쪽을 2026-06-06에 대조했다.
>
> **읽는 순서**: §0(가장 중요한 모순) → §1(통합 모델 결정) → §2(능력별 요구사항) →
> §3(데이터 계약) → §4(현재 격차 요약표).

---

## 0. 가장 중요한 발견 — 두 저장소의 통합 모델이 정반대다

TripMate와 krtour-map은 **서로를 어떻게 연결할지에 대해 정반대의 문서/구현을
갖고 있다.** 이걸 먼저 합의하지 않으면 아래 모든 요구사항이 무의미하다.

| 항목 | TripMate가 믿는 것 | krtour-map이 만든 것 |
|------|---------------------|------------------------|
| 통합 방식 | **OpenAPI HTTP** 호출 (ADR-026, 2026-06-04) | **in-process 함수 호출** (`from krtour.map import AsyncKrtourMapClient`), "HTTP 없음"(ADR-003) |
| 진입 문서 | `docs/krtour-map-integration.md` | `docs/tripmate-integration.md` |
| 포트 | API `9011` / Admin `9012` | 라이브러리는 포트 없음. 디버그 UI만 `8087` |
| 계약 파일 | `packages/krtour-map-admin/openapi.user.json`, `openapi.json`, `docs/tripmate-rest-api.md`, `docs/openapi-admin-contract.md` | **존재하지 않음.** 실제로는 `packages/krtour-map-debug-ui/openapi.json` 하나뿐 |
| 인증 | TripMate가 HTTP 계약에 인증 가정 | 디버그 UI는 **인증 없음**, `127.0.0.1` 전용, "운영자만" |
| HTTP 엔드포인트 | `/features/in-bounds`, `/features/search`, `/features/nearby/by-target`, `/features/{id}`, `POST /tripmate/features/batch`, `/admin/feature-update-requests` | `GET /features`(bbox), `GET /features/{id}`, `/debug/*`(health/version/etl/geocoding) — **그 외 전부 없음** |

**즉, TripMate `docs/krtour-map-integration.md`가 참조하는 krtour-map 산출물(패키지명,
openapi.user.json, 포트 9011, `/tripmate/features/batch` 등)은 krtour-map 저장소에
실재하지 않는다.** 이건 "최신 OpenAPI 계약을 따른다"는 문서의 전제가 깨졌다는 뜻이다.

→ **결정 필요(DEC-01, 이 저장소 `docs/decisions-needed-2026-06-06.md`)**: 통합 모델을
**(A) in-process 라이브러리** 로 되돌릴지, **(B) krtour-map이 운영급 HTTP 서비스를
신설**할지. 이 결정에 따라 §2의 "전달 형태"가 갈린다. 아래 §2는 두 모델 모두에서
**필요한 능력 자체는 동일**하므로, krtour-map은 결정과 무관하게 §2의 누락 능력부터
채우면 된다.

---

## 1. 통합 모델 두 안의 함의 (krtour-map 작업량 관점)

### 1-A. in-process 라이브러리(현 krtour-map 설계 유지)
- krtour-map 추가 작업: **HTTP 서버 불필요.** §2의 누락 client 메서드만 구현.
- TripMate 추가 작업: ADR-026 철회, `python-krtour-map` 의존성 추가, DI(`AsyncKrtourMapClient`) 구성, `feature` schema에 접근할 engine/DSN 주입.
- 장점: 단일 노드(Odroid/N150)에서 네트워크 hop 0, 직렬화 비용 0, krtour-map 9개월 설계와 일치.
- 단점: TripMate가 krtour-map의 Postgres(`feature`/`provider_sync` schema)에 직접 연결해야 함 → 배포/스키마 결합도 ↑.

### 1-B. 운영급 HTTP 서비스(현 TripMate ADR-026 유지)
- krtour-map 추가 작업(**큰 신규**): `krtour-map-debug-ui`와 별개로 **인증 있는 운영 API**를 신설하거나 debug-ui를 운영급으로 승격. 포트 9011/9012 정렬, §2의 모든 엔드포인트 신설, `openapi.user.json`(사용자 표면)·`openapi.json`(전체) 생성 + drift gate, 인증/인가(토큰), rate-limit.
- TripMate 추가 작업: `apps/api/app/clients/krtour_map.py` httpx client 구현(현재 stub만 있음).
- 장점: 프로세스/배포 격리, TripMate가 feature DB를 몰라도 됨.
- 단점: krtour-map에 상당한 신규 표면 + 운영 부담, 네트워크 hop.

> 어느 쪽이든 **§2의 누락 능력(near/radius, batch-by-ids, text search, weather card,
> feature-update-request, dedup/merge admin)은 공통으로 필요**하다. krtour-map은 이
> 능력들을 client 메서드로 먼저 구현하면, HTTP로 가더라도 라우터에서 얇게 노출만
> 하면 된다.

---

## 2. 능력별 요구사항 (왜/언제 필요한지 + 현재 상태 + 격차)

각 항목 형식:
- **용도(왜/언제)**: TripMate의 어떤 사용자 흐름이 이걸 호출하는지.
- **TripMate 호출 형태**: 기대하는 입력/출력.
- **krtour-map 현재 상태**: 라이브러리 client / 디버그 UI HTTP 각각에 있는지.
- **격차 / 요청**: krtour-map이 해줘야 할 것.

### 2.1 viewport feature 조회 (bbox) — `features_in_bounds`
- **용도**: 지도 화면을 드래그/줌할 때마다 보이는 영역의 마커를 채운다. TripMate
  `GET /features/in-bounds`(features.md §2.1)의 데이터 소스. 가장 호출 빈도 높은 read.
- **TripMate 호출 형태**: 입력 `min_lon,min_lat,max_lon,max_lat`, `kinds[]`,
  (선택)`zoom`/`cluster_unit`. 출력은 개별 마커 또는 **클러스터** 목록.
- **krtour-map 현재 상태**:
  - client: `features_in_bounds(*, min_lon, min_lat, max_lon, max_lat, kinds=None, limit=1000) -> list[dict]` **존재**. GIST `&&` envelope 사용. 반환 행:
    `feature_id, kind, name, category, lon, lat, marker_icon, marker_color, status`.
  - HTTP: `GET /features?min_lon&min_lat&max_lon&max_lat&kind(repeatable)&limit` **존재**(debug-ui, 인증 없음).
- **격차 / 요청**:
  1. **클러스터링 책임 합의**: TripMate features.md §2.1은 zoom별 시도/시군구/읍면동
     클러스터를 기대한다. 현재 client는 클러스터링을 **하지 않는다**(개별 행만).
     krtour-map `docs/tripmate-integration.md` §4.1 예시는 `cluster_unit` 파라미터를
     쓰지만 **실제 client 시그니처에는 없다.** → 클러스터링을 krtour-map이 제공할지
     (서버 집계, `cluster_unit: sido|sigungu|eupmyeondong|None`), TripMate가
     로컬에서 할지 결정 필요(DEC-04). 단일 노드 성능상 **DB 집계(krtour-map)** 권장.
  2. 반환 필드명 합의: §3 참조(`name` vs `title`, `lon/lat` vs `coord{}`).

### 2.2 feature 상세 — `get_feature`
- **용도**: 마커 클릭 → 상세 패널. POI 추가 시 feature 검증. TripMate
  `GET /features/{id}`.
- **krtour-map 현재 상태**: client `get_feature(feature_id: str) -> dict | None`
  **존재**(JSONB `address/detail/urls/raw_refs` 역직렬화 포함). HTTP `GET
  /features/{feature_id}` **존재**.
- **격차 / 요청**: 거의 충족. `detail`이 kind별 모델(`PlaceDetail` 등)로 직렬화되는지,
  `urls` 셰입이 TripMate features.md §2.2와 일치하는지 필드 단위 확인만 필요.

### 2.3 반경 검색 (near a point) — `features_nearby` **[누락]**
- **용도**: "내 위치/POI 주변 N km 안의 장소" 흐름. TripMate `GET /features/nearby`
  (features.md §2.4), user-location 흐름, 추천. 반경은 최대 50km.
- **TripMate 호출 형태**: 입력 `lon, lat, radius_m, kinds[], limit`. 출력은 in-bounds의
  개별 셰입 배열(클러스터 없음).
- **krtour-map 현재 상태**: **없음.** client/repo에 `features_nearby`/`ST_DWithin`
  함수가 없다(survey 확인). HTTP에도 near 엔드포인트 없음. 단, `coord_5179`(미터,
  EPSG:5179) STORED 컬럼은 이미 있어 구현 토대는 마련됨.
- **격차 / 요청**: `features_nearby(*, lon, lat, radius_m, kinds=None, limit=100)`
  신설. `coord_5179` + `ST_DWithin`(CTE 1회 변환, krtour-map ADR-012)로 구현.
  krtour-map `docs/tripmate-integration.md` §4.3은 이미 이 시그니처를 문서화했으나
  **구현은 아직 없다** — 문서-구현 drift.

### 2.4 feature_id 배치 조회 — `features_batch` / `get_features` **[누락, 중요]**
- **용도(매우 중요)**: TripMate가 여행계획을 열 때(`GET /trips/{id}`),
  trip의 모든 POI에 박힌 `feature_id[]`로 **최신 feature 정보를 한 번에** 가져와
  화면을 조립한다(`trip_view_builder`). 이게 없으면 POI마다 `get_feature`를 N번
  호출(N+1) → 단일 노드에서 치명적.
- **TripMate 호출 형태**: 입력 `feature_ids: list[str]`(수십~수백 개). 출력은
  `feature_id -> feature(또는 null)` 매핑. 일부 id가 삭제/없음이어도 부분 성공.
- **krtour-map 현재 상태**: **없음.** client에 `get_features([...])`/batch가 없고
  단건 `get_feature`만 있다. TripMate 문서가 기대하는 `POST /tripmate/features/batch`
  HTTP 엔드포인트도 **없다.**
- **격차 / 요청**: `get_features(feature_ids: list[str]) -> dict[str, dict | None]`
  (또는 list) 신설. 단일 쿼리(`WHERE feature_id = ANY(:ids)`)로 처리. **우선순위
  높음** — trip 상세 화면 성능의 핵심.

### 2.5 텍스트 검색 — `search_features` **[누락]**
- **용도**: 통합 검색(`GET /search`, features.md §2.7)의 feature 부분. 사용자가
  "광안리" 입력 → 이름/카테고리 매칭 feature. 여행 계획의 기본 기능.
- **krtour-map 현재 상태**: **없음.** `pg_trgm` GIN 인덱스
  `idx_features_name_trgm`(features.name)는 **이미 존재**하지만 이를 쓰는 쿼리
  함수가 노출돼 있지 않다. HTTP에도 없음.
- **격차 / 요청**: `search_features(*, q: str, viewport: BBox | None = None,
  kinds=None, limit=20) -> list[dict]` 신설. trigram 유사도 + (선택)viewport bias.
  주소 후보는 TripMate가 kraddr-geo로 별도 조회하므로 krtour-map은 **feature만**
  돌려주면 된다.

### 2.6 날씨 카드 — `build_weather_card` **[누락]**
- **용도**: feature 상세의 날씨(`GET /features/{id}/weather`, features.md §2.3).
  관측+예보+특보를 KMA 시간축 기준 한 카드로. trip brief(텔레그램)도 사용.
- **TripMate 호출 형태**: 입력 `feature_id`(좌표), `asof`(선택). 출력
  `{nowcast, ultra_short[], short[], mid, advisories[], sources[]}`.
- **krtour-map 현재 상태**: **미구현(future).** client docstring에
  `build_weather_card`가 "예정"으로만 있음. weather/price value 테이블도 아직
  생성 전(현재 detail은 JSONB).
- **격차 / 요청**: weather value 적재 + `build_weather_card(feature_id, *, asof=None)`
  구현. **TripMate는 KMA provider 변환을 직접 작성하지 않는다**(절대 금지 #3) —
  반드시 krtour-map이 제공. 우선순위: 중(상세 화면/brief에 필요, MVP 후순위 가능).

### 2.7 카테고리 카탈로그 — `list_categories`
- **용도**: 마커 범례, 필터 칩, Admin 카테고리 매핑 화면. 8자리 category code →
  표시명/마커 색/아이콘.
- **krtour-map 현재 상태**: `krtour.map.category`에 **정적 카탈로그(144개 코드)**
  존재. 단 런타임 "현재 DB에 있는 카테고리 + 개수" 질의 함수는 없음.
- **격차 / 요청**: 정적 카탈로그를 consumer가 쓸 수 있게 **export**(예
  `from krtour.map.category import PlaceCategory, CATEGORY_CATALOG`) + 마커 매핑이
  `@krtour/map-marker-react`(npm)와 같은 소스인지 보장(drift gate). HTTP면
  `GET /categories` 정적 노출.

### 2.8 사용자 제안과 krtour feature change — DEC-05 반영
- **사용자 제안 큐**: TripMate가 `app.feature_suggestions`와 `POST /features/requests`,
  `GET /features/requests/{id}`를 소유한다. 이 단계는 krtour-map을 직접 호출하지 않는다.
- **krtour-map 반영 지점**: TripMate Admin 승인 후 krtour-map admin API
  `POST/PATCH/DELETE /admin/features`로 반영한다(T-179/T-180). 재적재용
  `/admin/feature-update-requests`와 사용자 제안은 서로 다른 작업이다.
- **현재 상태**: krtour-map PR #317로 admin feature change API가 생겨 T-179가
  actionable 상태가 됐다.
- **격차 / 요청**: 사용자 제안을 받는 큐(테이블 + client 메서드
  `enqueue_feature_update_request(...)`, `get_feature_update_request(id)`,
  목록/처리 helper) 신설. **결정 필요(DEC-05)**: 이 큐를 krtour-map이 소유할지,
  TripMate `app` schema가 소유하고 승인 시에만 krtour-map 적재를 호출할지.

### 2.9 Admin: dedup 검토 / merge / 정합성 위반
- **용도**: TripMate Admin 콘솔의 feature 운영 화면(`/admin/features`,
  dedup review, 정합성). krtour-map-integration.md §4와 krtour `docs/tripmate-
  integration.md` §6.
- **krtour-map 현재 상태**: client `pending_dedup_reviews(limit)` **존재**,
  `sync_dedup_candidates(...)` **존재**. merge 실행(`merge_features`)·정합성
  위반 목록(`list_data_integrity_violations`)은 krtour 문서엔 있으나 client
  export 확인 필요(survey상 dedup repo는 있음, merge helper는 불명확).
- **격차 / 요청**: `merge_features(master_id, loser_id, reason)`,
  `update_dedup_review(key, status)`, `list_data_integrity_violations(...)`를
  public client API로 확정. (`ops.feature_consistency_reports` 테이블은 이미 있음.)

### 2.10 적재(write) — `load_feature_bundles` + provider 변환 + sync state
- **용도**: TripMate `apps/etl`(Dagster)이 공공 API → feature 적재. **TripMate는
  provider raw→DTO 변환을 직접 쓰지 않는다**(절대 금지 #3) — krtour-map의
  `providers.*` 순수 함수에 위임.
- **krtour-map 현재 상태**: `load_feature_bundles(bundles) -> FeatureLoadResult`
  **존재**. providers export: `kma, opinet, krex, standard_data, visitkorea`
  **존재**. `knps`, `krheritage`는 소스엔 있으나 **package-level re-export 안 됨**
  (full path로만 import 가능). `upsert_sync_state`는 **미구현(future)**.
- **격차 / 요청**:
  1. `knps`, `krheritage`를 `providers/__init__`에서 export(TripMate Dagster asset이
     쓰기 쉽게).
  2. `ProviderSyncState` 적재 helper(`upsert_sync_state`) 구현 — Dagster asset이
     cursor/마지막 성공시각을 기록해야 증분 적재가 됨.
  3. `FreshnessPolicy`/스케줄은 TripMate `apps/etl` 책임(krtour는 asset 정의 안 함) —
     현 경계 유지.

### 2.11 healthz / 버전
- **용도**: TripMate 배포 체크, Admin 상태판.
- **krtour-map 현재 상태**: HTTP `GET /debug/health`, `GET /debug/version` 존재.
  client `healthz()`는 krtour 문서 체크리스트(§18)에 언급되나 export 확인 필요.
- **격차 / 요청**: `client.healthz() -> dict`(engine/extension/provider 키 매핑)를
  public으로 보장. (HTTP 모델이면 인증 없는 `/healthz` 별도.)

### 2.12 POI 좌표 출몰시각(rise/set) — **TripMate가 직접 처리 중(참고)**
- TripMate는 KASI 특일/일출몰을 `app.kasi_special_days` / `app.trip_poi_rise_sets`로
  자체 구현(T-067 완료). krtour-map은 이 부분 **불요**. 단, 만약 krtour-map이
  weather/astro를 feature detail로 제공하기로 하면 중복이 되므로 경계만 확인.

---

## 3. 데이터 계약 — 합의 필요한 필드/포맷

이 불일치들은 통합 모델과 무관하게 **반드시** 한 값으로 합의해야 한다.

### 3.1 `feature_id` 포맷 — **세 곳이 다 다르다 (DEC-02)**
| 출처 | 포맷 |
|------|------|
| TripMate `docs/api/features.md:239` | `f_{bjd_code}_{kind[0]}_{sha1[:16]}` 예: `f_2611000000_p_abc123` |
| krtour-map 실제(`core.make_feature_id`, survey) | `"{kind}:{hash}"` 예: `place:abc123` (확인 요망) |
| TripMate **코드**(`features.py`) | `uuid.UUID` (잘못됨 — 위 둘 다와 불일치) |
- **요청**: krtour-map이 `make_feature_id`의 **확정 포맷과 규칙**을 명문화(문서 +
  OpenAPI 스키마 description). 이게 정본이고 TripMate가 문자열로 그대로 저장·전달한다.
  TripMate 코드의 UUID 가정은 버그(TripMate가 고침).

### 3.2 좌표 표현
- krtour-map client 반환: 평면 `lon, lat`(in-bounds) / `coord` 객체(get_feature).
- TripMate API 응답: `coord: {longitude, latitude}` 객체(features.md).
- **요청**: krtour-map은 일관되게 **하나**로(권장: `coord: {lon, lat}` 객체, WGS84,
  6자리). bbox 인자 순서는 `min_lon, min_lat, max_lon, max_lat`로 통일(현재 일치).
  TripMate가 자기 응답 셰입(`longitude/latitude`)으로 투영하는 건 TripMate 책임.

### 3.3 표시 이름 필드
- krtour-map: `name`. TripMate in-bounds 응답: `name`. TripMate 코드 일부: `title`.
- **요청**: 원천은 `name` 고정. TripMate가 `title`로 바꾸지 않음(코드 버그, TripMate 수정).

### 3.4 feature 셰입(상세) 필드 정합
TripMate `features.md` §2.2가 기대하는 필드: `feature_id, kind, name, coord,
address_road, address_jibun, category, marker_color, marker_icon, urls{...},
detail{...}, raw_refs[], parent_feature_id, sibling_group_id, status, deleted_at,
created_at, updated_at`.
- krtour-map `Feature` DTO 실제: `feature_id, kind, name, category, coord, geom,
  address(Address 객체: road/legal/admin + bjd_code 등), urls, marker_icon,
  marker_color, parent_feature_id, sibling_group_id, detail, raw_refs, status,
  created_at, updated_at, deleted_at`.
- **차이**: TripMate는 `address_road`/`address_jibun` **평면 문자열**을 기대하는데
  krtour-map은 `address`가 **구조화 객체**(road/legal/admin + 코드들). →
  **요청**: krtour-map `Address` 객체의 표준 직렬화(키 이름)를 명문화. TripMate가
  필요한 평면 필드로 투영. category는 krtour-map이 8자리 코드, TripMate features.md
  예시는 한글명("해수욕장") — **코드+표시명 둘 다** 제공 권장.

### 3.5 응답 envelope
- TripMate는 자기 API에서 `{data, meta}`로 감싼다. krtour-map(HTTP 모델이면)도
  `{data, meta}`를 따른다고 TripMate 문서가 가정. in-process 모델이면 krtour-map은
  **DTO/list만 반환**(래핑 키 없음, krtour ADR-003) → TripMate가 감쌈. 어느 모델이냐에
  따라 다르므로 DEC-01 후 확정.

---

## 4. 격차 요약표 (krtour-map 작업 백로그 후보)

| # | 능력 | client 메서드 | 현재 | 우선순위 | 비고 |
|---|------|---------------|------|---------|------|
| K-1 | bbox 조회 | `features_in_bounds` | ✅ 있음 | — | 클러스터링 책임만 결정(DEC-04) |
| K-2 | 단건 상세 | `get_feature` | ✅ 있음 | — | 필드 직렬화 확인 |
| K-3 | 반경 조회 | `features_nearby` | ❌ 없음 | 높음 | `coord_5179`+ST_DWithin |
| K-4 | **배치 조회** | `get_features([...])` | ❌ 없음 | **높음** | trip 상세 N+1 방지 |
| K-5 | 텍스트 검색 | `search_features` | ❌ 없음 | 높음 | trgm 인덱스 이미 있음 |
| K-6 | 날씨 카드 | `build_weather_card` | ❌ 미구현 | 중 | weather value 적재 선행 |
| K-7 | 카테고리 카탈로그 export | `category.*` | △ 정적만 | 중 | export + maki drift gate |
| K-8 | feature 갱신 요청 큐 | `enqueue/get_feature_update_request` | ❌ 없음 | 중 | 소유권 결정(DEC-05) |
| K-9 | dedup merge/정합성 | `merge_features` 등 | △ 부분 | 중 | public export 확정 |
| K-10 | knps/krheritage export | `providers.knps/.krheritage` | △ 미export | 중 | `__init__` 추가 |
| K-11 | sync state 적재 | `upsert_sync_state` | ❌ 미구현 | 중 | 증분 적재 필수 |
| K-12 | healthz public | `healthz()` | △ 확인요망 | 낮음 | |
| K-13 | feature_id 포맷 명문화 | (계약) | △ 불일치 | **높음** | DEC-02, 정본 선언 |
| K-14 | 운영급 HTTP 서비스 | (신규) | ✅ 구축됨(`krtour-map-admin` 9011) | — | 2026-06-08 완료 |
| **K-15** | **단건 feature 추가/수정/삭제 API** | (신규) | **✅ 구축됨 — krtour PR #317** | — | 2026-06-09 완료 |

> **2026-06-09 갱신**: K-1~K-15 모두 구현 완료. K-15는 krtour **PR #317**(`POST/PATCH/DELETE
> /admin/features` + 검수 워크플로 + version 0/1 분리)로 해소.

### K-15 — 단건 feature 추가/수정/삭제 API ✅ (krtour PR #317 구현)

- **왜/언제**: TripMate 사용자 제안 → **TripMate Admin 검사/승인** → 승인된 단건을 krtour
  feature로 반영(DEC-05).
- **krtour 구현(PR #317)**: `POST /admin/features`(create) / `PATCH /admin/features/{id}`(수정) /
  `DELETE /admin/features/{id}`(soft delete), `place`/`event` 대상. `review_mode`
  (require_review|immediate), version 0(provider)/1(user) 분리 + 재적재 보존. 응답에
  `feature_id`/`request_id`/state. (계약 상세 `docs/integrations/krtour-map-rest-api.md` §2.9.)
- **TripMate 후속**: T-179(Admin 승인→호출) + T-180(admin 9012 client). 연동 합의 5건
  (review_mode 등)은 krtour PR #317 코멘트로 질의(§7).

> **권장 진행**: K-15(단건 add)와 K-13(feature_id 포맷 명문화)을 우선. 운영 HTTP 서비스
> (K-14)는 이미 구축됨.

---

## 5. krtour-map 쪽에서 확인/회신해 주면 좋은 것
1. DEC-01(통합 모델)에 대한 krtour-map 측 선호 — 9개월 설계가 in-process인데 HTTP로
   갈 의사가 있는지, 있다면 운영 HTTP 서비스 신설 일정.
2. `make_feature_id` 확정 포맷(K-13).
3. K-3/K-4/K-5 구현 가능 시점.
4. **단건 feature 추가 API(K-15) 신설 시점** — TripMate 사용자 제안 승인 흐름이 의존. 현재
   add 경로는 offline-upload(파일)뿐이라 단건 추가 불가.
5. 클러스터링을 서버(krtour-map DB 집계)가 할지(DEC-04) 선호. (in-bounds `cluster_unit`로 구현됨)
