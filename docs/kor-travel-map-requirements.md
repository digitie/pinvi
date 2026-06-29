# kor-travel-map 요구사항 명세 — Pinvi가 필요로 하는 것

> **이 문서의 독자**: `kor-travel-map` 개발 에이전트.
> **작성 목적**: Pinvi가 feature 도메인을 위해 `kor-travel-map`에 **구체적으로
> 무엇을, 왜, 언제** 필요로 하는지를 한 곳에 모아, kor-travel-map 쪽에서 우선순위와
> 계약을 결정할 수 있게 한다.
> **검증 기준선**: Pinvi `main`(이 저장소) + `kor-travel-map` `main`
> `HEAD=b775c74`(`merge #111`) 양쪽을 2026-06-06에 대조했다.
>
> **읽는 순서**: §0(가장 중요한 모순) → §1(통합 모델 결정) → §2(능력별 요구사항) →
> §3(데이터 계약) → §4(현재 격차 요약표) → §6(public 도메인 필드) →
> §7(`curated_features` 소비 계약).
>
> **2026-06-12 추가 요구**: `kor-travel-map`에 `curated_features` 기능이 추가됐다.
> Pinvi는 이를 자체 큐레이션을 대체하는 것이 아니라 **추가 소스**로 소비한다.
> kor_travel_map curated feature 1건은 Pinvi `curated_trip_plans` 1건으로 1:1 복사되어야 하며,
> 상세 REST 계약은 §7 요구사항으로 정리한다.

---

## 0. 가장 중요한 발견 — 두 저장소의 통합 모델이 정반대다

Pinvi와 kor-travel-map은 **서로를 어떻게 연결할지에 대해 정반대의 문서/구현을
갖고 있다.** 이걸 먼저 합의하지 않으면 아래 모든 요구사항이 무의미하다.

| 항목 | Pinvi가 믿는 것 | kor-travel-map이 만든 것 |
|------|---------------------|------------------------|
| 통합 방식 | **OpenAPI HTTP** 호출 (ADR-026, 2026-06-04) | **in-process 함수 호출** (`from kor_travel_map.map import AsyncKorTravelMapClient`), "HTTP 없음"(ADR-003) |
| 진입 문서 | `docs/kor-travel-map-integration.md` | `docs/pinvi-integration.md` |
| 포트 | API/Admin API `12701` | 라이브러리는 포트 없음. 디버그 UI만 `8087` |
| 계약 파일 | `packages/kor-travel-map-admin/openapi.user.json`, `openapi.json`, `docs/pinvi-rest-api.md`, `docs/openapi-admin-contract.md` | **존재하지 않음.** 실제로는 `packages/kor-travel-map-debug-ui/openapi.json` 하나뿐 |
| 인증 | Pinvi가 HTTP 계약에 인증 가정 | 디버그 UI는 **인증 없음**, `127.0.0.1` 전용, "운영자만" |
| HTTP 엔드포인트 | `/features/in-bounds`, `/features/search`, `/features/nearby/by-target`, `/features/{id}`, `POST /pinvi/features/batch`, `/admin/feature-update-requests` | `GET /features`(bbox), `GET /features/{id}`, `/debug/*`(health/version/etl/geocoding) — **그 외 전부 없음** |

**즉, Pinvi `docs/kor-travel-map-integration.md`가 참조하는 kor-travel-map 산출물(패키지명,
openapi.user.json, 포트 12701, `/pinvi/features/batch` 등)은 kor-travel-map 저장소에
실재하지 않는다.** 이건 "최신 OpenAPI 계약을 따른다"는 문서의 전제가 깨졌다는 뜻이다.

→ **결정 필요(DEC-01, 이 저장소 `docs/decisions-needed-2026-06-06.md`)**: 통합 모델을
**(A) in-process 라이브러리** 로 되돌릴지, **(B) kor-travel-map이 운영급 HTTP 서비스를
신설**할지. 이 결정에 따라 §2의 "전달 형태"가 갈린다. 아래 §2는 두 모델 모두에서
**필요한 능력 자체는 동일**하므로, kor-travel-map은 결정과 무관하게 §2의 누락 능력부터
채우면 된다.

---

## 1. 통합 모델 두 안의 함의 (kor-travel-map 작업량 관점)

### 1-A. in-process 라이브러리(현 kor-travel-map 설계 유지)
- kor-travel-map 추가 작업: **HTTP 서버 불필요.** §2의 누락 client 메서드만 구현.
- Pinvi 추가 작업: ADR-026 철회, `kor-travel-map` 의존성 추가, DI(`AsyncKorTravelMapClient`) 구성, `feature` schema에 접근할 engine/DSN 주입.
- 장점: 단일 노드(Odroid/N150)에서 네트워크 hop 0, 직렬화 비용 0, kor-travel-map 9개월 설계와 일치.
- 단점: Pinvi가 kor-travel-map의 Postgres(`feature`/`provider_sync` schema)에 직접 연결해야 함 → 배포/스키마 결합도 ↑.

### 1-B. 운영급 HTTP 서비스(현 Pinvi ADR-026 유지)
- kor-travel-map 추가 작업(**큰 신규**): `kor-travel-map-debug-ui`와 별개로 **인증 있는 운영 API**를 신설하거나 debug-ui를 운영급으로 승격. 포트 12701 정렬, §2의 모든 엔드포인트 신설, `openapi.user.json`(사용자 표면)·`openapi.json`(전체) 생성 + drift gate, 인증/인가(토큰), rate-limit.
- Pinvi 추가 작업: `apps/api/app/clients/kor_travel_map.py` httpx client 구현(현재 stub만 있음).
- 장점: 프로세스/배포 격리, Pinvi가 feature DB를 몰라도 됨.
- 단점: kor-travel-map에 상당한 신규 표면 + 운영 부담, 네트워크 hop.

> 어느 쪽이든 **§2의 누락 능력(near/radius, batch-by-ids, text search, weather card,
> feature-update-request, dedup/merge admin)은 공통으로 필요**하다. kor-travel-map은 이
> 능력들을 client 메서드로 먼저 구현하면, HTTP로 가더라도 라우터에서 얇게 노출만
> 하면 된다.

---

## 2. 능력별 요구사항 (왜/언제 필요한지 + 현재 상태 + 격차)

각 항목 형식:
- **용도(왜/언제)**: Pinvi의 어떤 사용자 흐름이 이걸 호출하는지.
- **Pinvi 호출 형태**: 기대하는 입력/출력.
- **kor-travel-map 현재 상태**: 라이브러리 client / 디버그 UI HTTP 각각에 있는지.
- **격차 / 요청**: kor-travel-map이 해줘야 할 것.

### 2.1 viewport feature 조회 (bbox) — `features_in_bounds`
- **용도**: 지도 화면을 드래그/줌할 때마다 보이는 영역의 마커를 채운다. Pinvi
  `GET /features/in-bounds`(features.md §2.1)의 데이터 소스. 가장 호출 빈도 높은 read.
- **Pinvi 호출 형태**: 입력 `min_lon,min_lat,max_lon,max_lat`, `kinds[]`,
  (선택)`zoom`/`cluster_unit`. 출력은 개별 마커 또는 **클러스터** 목록.
- **kor-travel-map 현재 상태**:
  - client: `features_in_bounds(*, min_lon, min_lat, max_lon, max_lat, kinds=None, limit=1000) -> list[dict]` **존재**. GIST `&&` envelope 사용. 반환 행:
    `feature_id, kind, name, category, lon, lat, marker_icon, marker_color, status`.
  - HTTP: `GET /features?min_lon&min_lat&max_lon&max_lat&kind(repeatable)&limit` **존재**(debug-ui, 인증 없음).
- **격차 / 요청**:
  1. **클러스터링 책임 합의**: Pinvi features.md §2.1은 zoom별 시도/시군구/읍면동
     클러스터를 기대한다. 현재 client는 클러스터링을 **하지 않는다**(개별 행만).
     kor-travel-map `docs/pinvi-integration.md` §4.1 예시는 `cluster_unit` 파라미터를
     쓰지만 **실제 client 시그니처에는 없다.** → 클러스터링을 kor-travel-map이 제공할지
     (서버 집계, `cluster_unit: sido|sigungu|eupmyeondong|None`), Pinvi가
     로컬에서 할지 결정 필요(DEC-04). 단일 노드 성능상 **DB 집계(kor-travel-map)** 권장.
  2. 반환 필드명 합의: §3 참조(`name` vs `title`, `lon/lat` vs `coord{}`).

### 2.2 feature 상세 — `get_feature`
- **용도**: 마커 클릭 → 상세 패널. POI 추가 시 feature 검증. Pinvi
  `GET /features/{id}`.
- **kor-travel-map 현재 상태**: client `get_feature(feature_id: str) -> dict | None`
  **존재**(JSONB `address/detail/urls/raw_refs` 역직렬화 포함). HTTP `GET
  /features/{feature_id}` **존재**.
- **격차 / 요청**: 거의 충족. `detail`이 kind별 모델(`PlaceDetail` 등)로 직렬화되는지,
  `urls` 셰입이 Pinvi features.md §2.2와 일치하는지 필드 단위 확인만 필요.

### 2.3 반경 검색 (near a point) — `features_nearby` **[누락]**
- **용도**: "내 위치/POI 주변 N km 안의 장소" 흐름. Pinvi `GET /features/nearby`
  (features.md §2.4), user-location 흐름, 추천. 반경은 최대 50km.
- **Pinvi 호출 형태**: 입력 `lon, lat, radius_m, kinds[], limit`. 출력은 in-bounds의
  개별 셰입 배열(클러스터 없음).
- **kor-travel-map 현재 상태**: **없음.** client/repo에 `features_nearby`/`ST_DWithin`
  함수가 없다(survey 확인). HTTP에도 near 엔드포인트 없음. 단, `coord_5179`(미터,
  EPSG:5179) STORED 컬럼은 이미 있어 구현 토대는 마련됨.
- **격차 / 요청**: `features_nearby(*, lon, lat, radius_m, kinds=None, limit=100)`
  신설. `coord_5179` + `ST_DWithin`(CTE 1회 변환, kor-travel-map ADR-012)로 구현.
  kor-travel-map `docs/pinvi-integration.md` §4.3은 이미 이 시그니처를 문서화했으나
  **구현은 아직 없다** — 문서-구현 drift.

### 2.4 feature_id 배치 조회 — `features_batch` / `get_features` **[누락, 중요]**
- **용도(매우 중요)**: Pinvi가 여행계획을 열 때(`GET /trips/{id}`),
  trip의 모든 POI에 박힌 `feature_id[]`로 **최신 feature 정보를 한 번에** 가져와
  화면을 조립한다(`trip_view_builder`). 이게 없으면 POI마다 `get_feature`를 N번
  호출(N+1) → 단일 노드에서 치명적.
- **Pinvi 호출 형태**: 입력 `feature_ids: list[str]`(수십~수백 개). 출력은
  `feature_id -> feature(또는 null)` 매핑. 일부 id가 삭제/없음이어도 부분 성공.
- **kor-travel-map 현재 상태**: **없음.** client에 `get_features([...])`/batch가 없고
  단건 `get_feature`만 있다. Pinvi 문서가 기대하는 `POST /pinvi/features/batch`
  HTTP 엔드포인트도 **없다.**
- **격차 / 요청**: `get_features(feature_ids: list[str]) -> dict[str, dict | None]`
  (또는 list) 신설. 단일 쿼리(`WHERE feature_id = ANY(:ids)`)로 처리. **우선순위
  높음** — trip 상세 화면 성능의 핵심.

### 2.5 텍스트 검색 — `search_features` **[누락]**
- **용도**: 통합 검색(`GET /search`, features.md §2.7)의 feature 부분. 사용자가
  "광안리" 입력 → 이름/카테고리 매칭 feature. 여행 계획의 기본 기능.
- **kor-travel-map 현재 상태**: **없음.** `pg_trgm` GIN 인덱스
  `idx_features_name_trgm`(features.name)는 **이미 존재**하지만 이를 쓰는 쿼리
  함수가 노출돼 있지 않다. HTTP에도 없음.
- **격차 / 요청**: `search_features(*, q: str, viewport: BBox | None = None,
  kinds=None, limit=20) -> list[dict]` 신설. trigram 유사도 + (선택)viewport bias.
  주소 후보는 Pinvi가 kor-travel-geo로 별도 조회하므로 kor-travel-map은 **feature만**
  돌려주면 된다.

### 2.6 날씨 카드 — `build_weather_card` **[누락]**
- **용도**: feature 상세의 날씨(`GET /features/{id}/weather`, features.md §2.3).
  관측+예보+특보를 KMA 시간축 기준 한 카드로. trip brief(텔레그램)도 사용.
- **Pinvi 호출 형태**: 입력 `feature_id`(좌표), `asof`(선택). 출력
  `{nowcast, ultra_short[], short[], mid, advisories[], sources[]}`.
- **kor-travel-map 현재 상태**: **미구현(future).** client docstring에
  `build_weather_card`가 "예정"으로만 있음. weather/price value 테이블도 아직
  생성 전(현재 detail은 JSONB).
- **격차 / 요청**: weather value 적재 + `build_weather_card(feature_id, *, asof=None)`
  구현. **Pinvi는 KMA provider 변환을 직접 작성하지 않는다**(절대 금지 #3) —
  반드시 kor-travel-map이 제공. 우선순위: 중(상세 화면/brief에 필요, MVP 후순위 가능).

### 2.7 카테고리 카탈로그 — `list_categories`
- **용도**: 마커 범례, 필터 칩, Admin 카테고리 매핑 화면. 8자리 category code →
  표시명/마커 색/아이콘.
- **kor-travel-map 현재 상태**: `kor_travel_map.map.category`에 **정적 카탈로그(144개 코드)**
  존재. 단 런타임 "현재 DB에 있는 카테고리 + 개수" 질의 함수는 없음.
- **격차 / 요청**: 정적 카탈로그를 consumer가 쓸 수 있게 **export**(예
  `from kor_travel_map.map.category import PlaceCategory, CATEGORY_CATALOG`) + 마커 매핑이
  `@kor_travel_map/map-marker-react`(npm)와 같은 소스인지 보장(drift gate). HTTP면
  `GET /categories` 정적 노출.

### 2.8 사용자 제안과 kor_travel_map feature change — DEC-05 반영
- **사용자 제안 큐**: Pinvi가 `app.feature_suggestions`와 `POST /features/requests`,
  `GET /features/requests/{id}`를 소유한다. 이 단계는 kor-travel-map을 직접 호출하지 않는다.
- **kor-travel-map 반영 지점**: Pinvi Admin 승인 후 kor-travel-map admin API
  `POST/PATCH/DELETE /admin/features`로 반영한다(T-179/T-180). 재적재용
  `/admin/feature-update-requests`와 사용자 제안은 서로 다른 작업이다.
- **현재 상태**: kor-travel-map PR #317로 admin feature change API가 생겨 T-179가
  actionable 상태가 됐다.
- **격차 / 요청**: 사용자 제안을 받는 큐(테이블 + client 메서드
  `enqueue_feature_update_request(...)`, `get_feature_update_request(id)`,
  목록/처리 helper) 신설. **결정 필요(DEC-05)**: 이 큐를 kor-travel-map이 소유할지,
  Pinvi `app` schema가 소유하고 승인 시에만 kor-travel-map 적재를 호출할지.

### 2.9 Admin: dedup 검토 / merge / 정합성 위반
- **용도**: Pinvi Admin 콘솔의 feature 운영 화면(`/admin/features`,
  dedup review, 정합성). kor-travel-map-integration.md §4와 kor_travel_map `docs/pinvi-
  integration.md` §6.
- **kor-travel-map 현재 상태**: client `pending_dedup_reviews(limit)` **존재**,
  `sync_dedup_candidates(...)` **존재**. merge 실행(`merge_features`)·정합성
  위반 목록(`list_data_integrity_violations`)은 kor_travel_map 문서엔 있으나 client
  export 확인 필요(survey상 dedup repo는 있음, merge helper는 불명확).
- **격차 / 요청**: `merge_features(master_id, loser_id, reason)`,
  `update_dedup_review(key, status)`, `list_data_integrity_violations(...)`를
  public client API로 확정. (`ops.feature_consistency_reports` 테이블은 이미 있음.)

### 2.10 적재(write) — `load_feature_bundles` + provider 변환 + sync state
- **용도**: Pinvi `apps/etl`(Dagster)이 공공 API → feature 적재. **Pinvi는
  provider raw→DTO 변환을 직접 쓰지 않는다**(절대 금지 #3) — kor-travel-map의
  `providers.*` 순수 함수에 위임.
- **kor-travel-map 현재 상태**: `load_feature_bundles(bundles) -> FeatureLoadResult`
  **존재**. providers export: `kma, opinet, krex, standard_data, visitkorea`
  **존재**. `knps`, `krheritage`는 소스엔 있으나 **package-level re-export 안 됨**
  (full path로만 import 가능). `upsert_sync_state`는 **미구현(future)**.
- **격차 / 요청**:
  1. `knps`, `krheritage`를 `providers/__init__`에서 export(Pinvi Dagster asset이
     쓰기 쉽게).
  2. `ProviderSyncState` 적재 helper(`upsert_sync_state`) 구현 — Dagster asset이
     cursor/마지막 성공시각을 기록해야 증분 적재가 됨.
  3. `FreshnessPolicy`/스케줄은 Pinvi `apps/etl` 책임(kor_travel_map는 asset 정의 안 함) —
     현 경계 유지.

### 2.11 healthz / 버전
- **용도**: Pinvi 배포 체크, Admin 상태판.
- **kor-travel-map 현재 상태**: HTTP `GET /debug/health`, `GET /debug/version` 존재.
  client `healthz()`는 kor_travel_map 문서 체크리스트(§18)에 언급되나 export 확인 필요.
- **격차 / 요청**: `client.healthz() -> dict`(engine/extension/provider 키 매핑)를
  public으로 보장. (HTTP 모델이면 인증 없는 `/healthz` 별도.)

### 2.12 POI 좌표 출몰시각(rise/set) — **Pinvi가 직접 처리 중(참고)**
- Pinvi는 KASI 특일/일출몰을 `app.kasi_special_days` / `app.trip_poi_rise_sets`로
  자체 구현(T-067 완료). kor-travel-map은 이 부분 **불요**. 단, 만약 kor-travel-map이
  weather/astro를 feature detail로 제공하기로 하면 중복이 되므로 경계만 확인.

---

## 3. 데이터 계약 — 합의 필요한 필드/포맷

이 불일치들은 통합 모델과 무관하게 **반드시** 한 값으로 합의해야 한다.

### 3.1 `feature_id` 포맷 — **세 곳이 다 다르다 (DEC-02)**
| 출처 | 포맷 |
|------|------|
| Pinvi `docs/api/features.md:239` | `f_{bjd_code}_{kind[0]}_{sha1[:16]}` 예: `f_2611000000_p_abc123` |
| kor-travel-map 실제(`core.make_feature_id`, survey) | `"{kind}:{hash}"` 예: `place:abc123` (확인 요망) |
| Pinvi **코드**(`features.py`) | `uuid.UUID` (잘못됨 — 위 둘 다와 불일치) |
- **요청**: kor-travel-map이 `make_feature_id`의 **확정 포맷과 규칙**을 명문화(문서 +
  OpenAPI 스키마 description). 이게 정본이고 Pinvi가 문자열로 그대로 저장·전달한다.
  Pinvi 코드의 UUID 가정은 버그(Pinvi가 고침).

### 3.2 좌표 표현
- kor-travel-map client 반환: 평면 `lon, lat`(in-bounds) / `coord` 객체(get_feature).
- Pinvi API 응답: `coord: {longitude, latitude}` 객체(features.md).
- **요청**: kor-travel-map은 일관되게 **하나**로(권장: `coord: {lon, lat}` 객체, WGS84,
  6자리). bbox 인자 순서는 `min_lon, min_lat, max_lon, max_lat`로 통일(현재 일치).
  Pinvi가 자기 응답 셰입(`longitude/latitude`)으로 투영하는 건 Pinvi 책임.

### 3.3 표시 이름 필드
- kor-travel-map: `name`. Pinvi in-bounds 응답: `name`. Pinvi 코드 일부: `title`.
- **요청**: 원천은 `name` 고정. Pinvi가 `title`로 바꾸지 않음(코드 버그, Pinvi 수정).

### 3.4 feature 셰입(상세) 필드 정합
Pinvi `features.md` §2.2가 기대하는 필드: `feature_id, kind, name, coord,
address_road, address_jibun, category, marker_color, marker_icon, urls{...},
detail{...}, raw_refs[], parent_feature_id, sibling_group_id, status, deleted_at,
created_at, updated_at`.
- kor-travel-map `Feature` DTO 실제: `feature_id, kind, name, category, coord, geom,
  address(Address 객체: road/legal/admin + bjd_code 등), urls, marker_icon,
  marker_color, parent_feature_id, sibling_group_id, detail, raw_refs, status,
  created_at, updated_at, deleted_at`.
- **차이**: Pinvi는 `address_road`/`address_jibun` **평면 문자열**을 기대하는데
  kor-travel-map은 `address`가 **구조화 객체**(road/legal/admin + 코드들). →
  **요청**: kor-travel-map `Address` 객체의 표준 직렬화(키 이름)를 명문화. Pinvi가
  필요한 평면 필드로 투영. category는 kor-travel-map이 8자리 코드, Pinvi features.md
  예시는 한글명("해수욕장") — **코드+표시명 둘 다** 제공 권장.

### 3.5 응답 envelope
- Pinvi는 자기 API에서 `{data, meta}`로 감싼다. kor-travel-map(HTTP 모델이면)도
  `{data, meta}`를 따른다고 Pinvi 문서가 가정. in-process 모델이면 kor-travel-map은
  **DTO/list만 반환**(래핑 키 없음, kor_travel_map ADR-003) → Pinvi가 감쌈. 어느 모델이냐에
  따라 다르므로 DEC-01 후 확정.

---

## 4. 격차 요약표 (kor-travel-map 작업 백로그 후보)

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
| K-14 | 운영급 HTTP 서비스 | (신규) | ✅ 구축됨(`kor-travel-map-admin` 12701) | — | 2026-06-08 완료 |
| **K-15** | **단건 feature 추가/수정/삭제 API** | (신규) | **✅ 구축됨 — kor_travel_map PR #317** | — | 2026-06-09 완료 |

> **2026-06-09 갱신**: K-1~K-15 모두 구현 완료. K-15는 kor_travel_map **PR #317**(`POST/PATCH/DELETE
> /admin/features` + 검수 워크플로 + version 0/1 분리)로 해소.

### K-15 — 단건 feature 추가/수정/삭제 API ✅ (kor_travel_map PR #317 구현)

- **왜/언제**: Pinvi 사용자 제안 → **Pinvi Admin 검사/승인** → 승인된 단건을 kor_travel_map
  feature로 반영(DEC-05).
- **kor_travel_map 구현(PR #317)**: `POST /admin/features`(create) / `PATCH /admin/features/{id}`(수정) /
  `DELETE /admin/features/{id}`(soft delete), `place`/`event` 대상. `review_mode`
  (require_review|immediate), version 0(provider)/1(user) 분리 + 재적재 보존. 응답에
  `feature_id`/`request_id`/state. (계약 상세 `docs/integrations/kor-travel-map-rest-api.md` §2.9.)
- **Pinvi 후속**: T-179(Admin 승인→호출) + T-180(admin API client). 연동 합의 5건
  (review_mode 등)은 kor_travel_map PR #317 코멘트로 질의(§7).

> **권장 진행**: K-15(단건 add)와 K-13(feature_id 포맷 명문화)을 우선. 운영 HTTP 서비스
> (K-14)는 이미 구축됨.

---

## 5. kor-travel-map 쪽에서 확인/회신해 주면 좋은 것
1. DEC-01(통합 모델)에 대한 kor-travel-map 측 선호 — 9개월 설계가 in-process인데 HTTP로
   갈 의사가 있는지, 있다면 운영 HTTP 서비스 신설 일정.
2. `make_feature_id` 확정 포맷(K-13).
3. K-3/K-4/K-5 구현 가능 시점.
4. **단건 feature 추가 API(K-15) 신설 시점** — Pinvi 사용자 제안 승인 흐름이 의존. 현재
   add 경로는 offline-upload(파일)뿐이라 단건 추가 불가.
5. 클러스터링을 서버(kor-travel-map DB 집계)가 할지(DEC-04) 선호. (in-bounds `cluster_unit`로 구현됨)

---

## 6. Public 표면 요구사항 (T-130 — Pinvi `/public/*` 차단 해소)

> **상태 (2026-06-12)**: kor-travel-map T-222b가 `openapi.user.json`에
> `/v1/public/beaches*`, `/v1/public/festivals*`를 추가해 본 §6 요구는 1차 충족됐다.
> Pinvi T-130도 해당 표면을 소비하도록 연결했다. 아래 요구 표는 왜 public 표면이 필요했는지
> 보존하는 이력이며, 현재 구현 정본은 `docs/api/public.md`와
> `docs/integrations/kor-travel-map-rest-api.md`다.

### 6.0 배경 / 현재 격차

Pinvi는 비로그인 공개 read API `/public/*`(IP rate limit, kor_travel_map 데이터만)를 설계해 뒀다
(`docs/api/public.md`): 로그인 화면 축제 광고 + 비로그인 지도 마커 layer + 해수욕장/축제 상세.
기존에는 kor_travel_map user API(`openapi.user.json`)가 일반 `/v1/features/*` + `/v1/categories`만
노출해 해수욕장/축제의 **풍부한 도메인 필드**(수질·KHOA 예보·축제 상세 등)를 계약에 담지
않았다. 현재는 public view 전용 표면이 생겨 Pinvi가 해당 응답을 서버 측에서 프록시한다.

### 6.1 필요한 것 — beach(해수욕장)

Pinvi `/public/beaches`(+`/{id}`, `/beaches/map-markers`)가 노출하려는 필드(public.md §2.1~2.3):

| Pinvi 노출 필드 | kor_travel_map에서 필요한 것 |
|---|---|
| display_name / lon,lat / 행정코드 / 도로명주소 | 일반 `FeatureSummary`/`FeatureDetailResponse`로 충족 |
| beach_width_m / beach_length_m / beach_material | place(해수욕장 category) feature **`detail` payload**에 포함 필요 |
| latest_water_quality (수질 등급 + 측정일) | KHOA/수질 provider 값 — feature 단위 조회 표면 필요 |
| upcoming_index_forecasts (KHOA 예보) | KHOA index forecast — feature weather/index 표면으로 |
| latest_observation / latest_weather | 기존 `GET /v1/features/{id}/weather`(metric) 재사용 가능 여부 확인 |
| emergency_contact / homepage_url / image_url | feature `detail` / `urls` |
| source_providers | feature `detail` 또는 sources |

→ **충족 방식(2026-06-12)**: `GET /v1/public/beaches`, `/map-markers`, `/{feature_id}`가
해수욕장 public view를 제공한다. 수질/KHOA index/weather는 nullable 필드로 먼저 열었다.

### 6.2 필요한 것 — festival(축제/이벤트)

Pinvi `/public/festivals/monthly`(+`/{id}`, `/festivals/map-markers`)가 노출하려는 필드
(public.md §2.4~2.6):

| Pinvi 노출 필드 | kor_travel_map에서 필요한 것 |
|---|---|
| festival_name / venue_name / lon,lat / 주소 | event `FeatureSummary`/`FeatureDetailResponse` |
| event_start_date / end_date / event_status | event feature **`detail`**에 기간·상태 필요 |
| 월별 count (`months[]`) | "이번 달 진행 축제" 집계 — 서버 집계 또는 Pinvi가 기간 범위 search로 집계 |
| festival_content / mnnst·auspc·suprt_instt_name / phone / homepage / reference_date | event feature `detail` / `urls` |

→ **충족 방식(2026-06-12)**: `GET /v1/public/festivals/monthly`, `/map-markers`,
`/{feature_id}`가 기간 overlap 월별 축제 public view를 제공한다.

### 6.3 공개(no-auth) 표면 / 인증

- `/v1/features/*` GET은 이미 공용 read(인프라 SSO 비강제, rest-api.md §1.3)이므로 Pinvi가
  **서버측에서** 프록시하면 인증 문제는 없다(Pinvi `/public/*`만 비로그인 노출, kor_travel_map 호출은 서버).
- 별도 no-auth public 표면은 필수 아님 — **핵심 격차는 위 6.1/6.2의 도메인 필드(`detail`) 계약**이다.

### 6.4 우선순위 / 비차단

- **v0.1.0 비차단**(공개 광고/마커는 nice-to-have).
- **최소안**: 일반 viewport 마커는 Pinvi가 `GET /v1/features/in-bounds`(category 필터)로 이미
  가능 → lightweight `map-markers`만이라도 우선 가능. 풍부한 상세(수질·예보·축제 내용)는 후속.
- 도메인 필드가 계약에 들어와 Pinvi `/public/*` 구현을 완료했다(T-130). 앱 내부 공통
  rate-limit는 T-195 후속이다.

### 6.5 kor_travel_map 회신 요청 — 완료

1. 해수욕장/축제 public view 표면 추가 — 완료.
2. 수질·KHOA index는 nullable projection으로 1차 노출 — 후속 데이터 보강은 kor_travel_map 쪽 provider
   freshness/field 보강에서 추적.
3. "월별 active 축제" 집계는 kor_travel_map `/v1/public/festivals/monthly`가 제공 — 완료.

---

## 7. `curated_features` → Pinvi curated trip plans import 요구사항

> **상태 (2026-06-12)**: kor-travel-map의
> `GET /v1/admin/curated-features/{curated_feature_id}/detail-snapshot` 계약을 Pinvi가
> 소비한다(admin base :12701, 헤더 `X-Kor-Travel-Map-Service-Token`). 구 public 경로
> `GET /v1/curated-features/{id}/pinvi-copy`는 kor_travel_map PR #533로 제거됐다(ADR-049).
> 본 절은 해당 detail snapshot 계약과 Pinvi 저장 매핑을 기록한다.

### 7.1 제품 의미

Pinvi의 curated trip plan은 두 소스를 모두 지원한다.

| 소스 | 의미 |
|------|------|
| Pinvi-native 큐레이션 | Admin/운영자가 Pinvi 안에서 직접 기획·작성 |
| kor_travel_map `curated_features` import | kor-travel-map이 제공하는 curated feature 묶음을 Pinvi가 REST로 조회해 1:1 복사 |

kor_travel_map import는 Pinvi-native 큐레이션을 대체하지 않는다. 두 흐름은 모두
`app.curated_trip_plans` / `app.curated_plan_pois`에 저장되고, 사용자는 같은
`/notice-plans/{id}/copy` 흐름으로 자기 trip에 가져온다.

### 7.2 필요한 REST 표면

Pinvi가 사용하는 최소 능력:

| 능력 | 요청 |
|------|------|
| 상세 조회 | curated feature 1건의 메타 + 하위 item/POI 전체 |
| 증분 확인 | `updated_at` 또는 version/etag 기반으로 Pinvi import stale 여부 판단 |
| 안정 id | 같은 kor_travel_map curated feature와 item을 재조회해도 동일 id 유지 |

admin base :12701, 헤더 `X-Kor-Travel-Map-Service-Token` 필요. snapshot plan-level 객체
키는 `plan` → `content`로 개명됐다(ADR-049). version/etag/updated_at/theme/source/items[]는
그대로다.

```http
GET /v1/admin/curated-features/{curated_feature_id}/detail-snapshot
```

### 7.3 데이터 매핑

| kor_travel_map `curated_features` | Pinvi 저장 |
|---------------------------|---------------|
| curated feature id | `curated_trip_plans.source_curated_feature_id` |
| title/summary/category/region/source | `curated_trip_plans.title/summary/category/destination/source_name` |
| publish/visibility | Pinvi `is_published`는 기본 false로 import 후 Admin이 확정 |
| item/POI 목록 | `curated_plan_pois` |
| item day/order | `day_index` / `sort_order` |
| item `feature_id` | `curated_plan_pois.feature_id` nullable 저장 |
| item 표시명/좌표/카테고리 | `feature_snapshot` |
| snapshot `version` / `etag` | `source_curated_feature_version` / `source_etag` |
| item id | `source_curated_feature_item_id` |

### 7.4 `feature_id` 정책

- kor_travel_map item이 `feature_id`를 제공하면 Pinvi는 같은 plan 안에서 해당
  feature-backed POI를 먼저 찾고, 없으면 생성한다.
- kor_travel_map item이 `feature_id`를 제공하지 않으면 `feature_id = null`인 curated POI로 저장한다.
- Pinvi-native 큐레이션 역시 feature 없는 자유 POI를 만들 수 있다.
- Pinvi는 `curated:<id>` 같은 가짜 feature id를 만들지 않는다.
- kor_travel_map feature schema와 cross-schema FK는 두지 않는다.

### 7.5 provenance 컬럼

| 컬럼 | 대상 | 용도 |
|-----------|------|------|
| `source_system` | `app.curated_trip_plans` | `pinvi` / `kor-travel-map` 구분 |
| `source_curated_feature_id` | `app.curated_trip_plans` | kor_travel_map curated feature 원본 id |
| `source_curated_feature_version` | `app.curated_trip_plans` | refresh/idempotency 판단 |
| `source_etag` | `app.curated_trip_plans` | kor_travel_map copy snapshot etag |
| `source_imported_at` | `app.curated_trip_plans` | 마지막 import 시각 |
| `source_curated_feature_id` | `app.curated_plan_pois` | kor_travel_map curated feature 원본 id |
| `source_curated_feature_item_id` | `app.curated_plan_pois` | kor_travel_map 하위 item 원본 id |

Pinvi는 kor-travel-map을 HTTP로만 호출하고 Python 패키지 import나 DB 직접 접근을 하지 않는다.
`kor-travel-concierge`는 Pinvi curated trip plan 생성 흐름에 관여하지 않는다.

### 7.6 kor_travel_map 회신 요청

1. copy snapshot item이 이미지/첨부/media 참조를 포함할 때의 셰입.
2. Pinvi가 1:1 import 후 refresh할 때 기존 Pinvi plan을 갱신해야 하는지,
   새 버전 plan을 만들어야 하는지에 대한 장기 권장 정책.
