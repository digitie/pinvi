# Kakao Local + Naver Local 통합 — 장소 검색 표시 전용 provider

본 문서는 Pinvi(`apps/api`)가 **Kakao Local(장소 키워드 검색)** + **Naver Local(지역
검색)** 을 **표시 전용(display-only) 외부 장소 provider**로 서버 사이드 호출하는
계약이다. ADR-054 기준(**ADR-015 `docs/integrations/kakao-map.md`를 supersede** — §12).

> **경계 한 줄 요약 (ADR-026/054)**
> - **정본 feature 데이터**(place/event/notice/price) → `kor-travel-map` **OpenAPI HTTP
>   계약**. Kakao/Naver는 정본 소스가 **아니다**. → `docs/kor-travel-map-integration.md`.
> - **주소/좌표/행정구역 geocoding** → `kor-travel-geo` **v2 REST**(ADR-025).
>   → `docs/integrations/kor-travel-geo.md`.
> - **Kakao Local + Naver Local** → 본 문서. **주소 자동완성 보강 + 장소 딥링크
>   enrichment 전용**. 내부(feature + my_poi + address) 결과가 부족할 때만 호출하는
>   보조 소스이며, 응답의 **provider 파생 콘텐츠는 절대 저장·재전달하지 않는다**(§7).

권위 출처는 Kakao Developers `Local` REST 문서와 Naver `검색 API - 지역` 문서다.
본 문서는 Pinvi 입장의 사용 계약이며, 표시/보관/약관 제약이 정본이다.

## 1. 목적과 범위 (WHY-NOW, ADR-054)

Kakao/Naver를 표시 전용으로 들이는 이유는 **kor-travel-geo + kor-travel-map만으로는
못 메우는 구체 gap** 때문이다 — ADR-015가 Kakao Local 직접 호출을 드롭했던 전제와
달라진 부분만 도입한다.

- **주소 자동완성 보강**: `MapSearchBox` 자동완성이 feature명(kor-travel-map) + 내
  POI + kor-travel-geo 주소를 우선 노출하되, 사용자가 실제로 찾는 상호/브랜드
  장소명(예: "스타벅스 강남", 신규 카페)이 내부에 없을 때 **주소가 붙은 후보**를
  Kakao/Naver로 채운다. `PlaceSearchResult`에 병합한다(source 아이콘, internal-first).
- **장소 딥링크 enrichment**: feature/POI 상세에서 카카오맵/네이버 지도 **back-link**를
  제공(라이브 재조회, 표시 전용).

범위 밖(명시):

- **정본 feature 생성은 여전히 kor-travel-map만** 한다. Kakao/Naver 픽으로 POI를
  추가하면 feature-request 파이프라인이 **user-authored 이름+좌표+노트 + opaque
  `external_ref`만** 전달하고, provider 콘텐츠는 절대 전달하지 않는다(§7, ADR-054 M2/M3,
  `docs/integrations/kor-travel-map-rest-api.md`).
- 길찾기/경로/카테고리 통계 등 provider 부가 API는 사용하지 않는다.

## 2. 개관

```
┌────────────────────────────────────────────────────────────────┐
│ Pinvi apps/api (FastAPI)                                       │
│   GET /search  (unified, source-tagged: feature|my_poi|address │
│                 |kakao|naver)  ── internal-first, K-threshold  │
│   clients/kakao_local.py · clients/naver_local.py (httpx)      │
└────────────────────────────────────────────────────────────────┘
        │ 내부 결과 < K 일 때만 ▼ (서버 사이드, secret 서버 보관)
        ├──────────────────────────┬───────────────────────────────┐
        ▼                          ▼                               │
┌───────────────────────┐  ┌───────────────────────┐              │
│ Kakao Local           │  │ Naver Local           │              │
│ dapi.kakao.com        │  │ openapi.naver.com     │              │
│ Authorization:KakaoAK │  │ X-Naver-Client-Id/Sec │              │
└───────────────────────┘  └───────────────────────┘              │
   결과는 표시 전용 · provider 콘텐츠 미저장 · 카카오/네이버 검색 attribution 필수 ─┘
```

- 호출은 **전부 서버 사이드**(httpx). provider host는 웹 `connect-src`에 넣지 않는다.
  브라우저가 직접 여는 것은 **딥링크 nav host**(`map.kakao.com`, `map.naver.com`,
  `place.map.kakao.com`)뿐이며 이는 `connect-src`가 필요 없다(§8, ADR-054 M18).
- attribution 로고("카카오"/"네이버 검색")는 **로컬 번들 asset**으로 둔다(원격 img-src
  금지). maki glyph도 unpkg 대신 self-host로 확정한다(모달 PR 전, ADR-054 M18).

## 3. Provider endpoint 계약 (Pinvi가 호출하는 것)

### 3.1 Kakao Local — 키워드로 장소 검색

`GET https://dapi.kakao.com/v2/local/search/keyword.json`
헤더 `Authorization: KakaoAK {REST_API_KEY}` (§6, 기존 OAuth 앱 키 재사용).

요청 query 파라미터:

| 파라미터 | 타입 | 비고 |
|----------|------|------|
| `query` | string | 필수. 검색 키워드 |
| `x` / `y` | float | 중심 경도/위도. "내 주변 검색"일 때만(§9) |
| `radius` | int | `x`/`y`와 함께. m 단위(≤20000) |
| `size` | int | 페이지당(≤15). Pinvi는 K 보강분만 |
| `sort` | string | `accuracy`(기본) / `distance` |

응답: `meta{total_count, pageable_count, is_end}` + `documents[]`. 각 document 필드와
Pinvi 매핑:

| Kakao 필드 | 의미 | Pinvi 매핑(`PlaceSearchResult`) |
|-----------|------|------------------------------|
| `id` | 장소 ID(문자열) | `external_id` (opaque, 저장 대상은 §7의 external_ref만) |
| `place_name` | 상호명 | `name` |
| `address_name` | 지번 주소 | `address` |
| `road_address_name` | 도로명 주소 | `road_address` |
| `x` / `y` | 경도 / 위도(WGS84) | `coord{lon:x, lat:y}` |
| `category_name` / `category_group_name` | 카테고리 | `category` (표시 전용) |
| `phone` | 전화 | `phone` (**표시 전용, 미저장**) |
| `place_url` | 카카오맵 상세 URL | `provider_url` (back-link), `external_ref.deep_link_url` |

### 3.2 Naver Local — 지역 검색

`GET https://openapi.naver.com/v1/search/local.json`
헤더 `X-Naver-Client-Id: {ID}` + `X-Naver-Client-Secret: {SECRET}` (§6, 신규 Search 앱).

요청 query 파라미터:

| 파라미터 | 타입 | 비고 |
|----------|------|------|
| `query` | string | 필수. 검색어 |
| `display` | int | 결과 수(**최대 5**). Naver Local 상한이 낮음 |
| `start` | int | 시작(최대 1) |
| `sort` | string | `random`(기본) / `comment` |

> Naver Local은 좌표 중심(radius) 파라미터가 **없다** — "내 주변" 반경 필터는 지원
> 안 함. 좌표는 Kakao에만 전달하고, Naver는 키워드로만 조회한다.

응답: `total, start, display` + `items[]`. 각 item 필드와 Pinvi 매핑:

| Naver 필드 | 의미 | Pinvi 매핑(`PlaceSearchResult`) |
|-----------|------|------------------------------|
| `title` | 상호명(**`<b>` 태그 포함 HTML**) | `name` — **태그 strip + 언이스케이프 후** |
| `address` | 지번 주소 | `address` |
| `roadAddress` | 도로명 주소 | `road_address` |
| `mapx` / `mapy` | 경도 / 위도, **WGS84 × 10⁷ 정수** | `coord{lon:mapx/1e7, lat:mapy/1e7}` |
| `category` | 카테고리 | `category` (표시 전용) |
| `telephone` | 전화(보통 빈 문자열) | `phone` (**표시 전용, 미저장**) |
| `link` | 업체 링크 URL | `provider_url` (back-link), `external_ref.deep_link_url` |

- **좌표 스케일 주의**: Naver `mapx`/`mapy`는 정수 `WGS84 × 10⁷`이다. `/1e7` 후
  `(lon, lat)`로 쓴다(구 KATEC 가정 금지). 파싱 실패 항목은 좌표 없는 후보로 버린다.
- **`title` HTML strip 필수**: `<b>`/`</b>` 및 HTML 엔티티(`&amp;` 등)를 제거해 표시명으로.
- **stable id 부재**: Naver Local은 안정적 장소 ID를 주지 않는다. `external_id`는
  `link`를 정규화한 값으로 파생한다(§7 글로벌 dedup `(provider, external_id)`의 키).

## 4. `PlaceSearchResult` 병합 (계약은 search doc이 정본)

통합 `GET /search`가 `{results: PlaceSearchResult[], degraded_sources[]}`를 반환한다
(계약 정본 = `docs/api/search.md`, ADR-054 M14). `source ∈ {feature, my_poi, address,
kakao, naver}`. 정렬은 **internal(feature+my_poi+address) 우선 → kakao → naver**,
부분 degrade에도 안정적. Kakao/Naver row는 §5 항상 표시.

`PlaceSearchResult` = `{source, feature_id?, external_id?, name, address, road_address?,
coord{lon,lat}, category?, marker_color?, marker_icon?, provider_url?, phone?}`. `phone`은
**표시 전용이며 절대 저장하지 않는다**(§7).

## 5. 약관 제약 (표시 전용 · attribution · 쿼터)

### 5.1 표시 전용 · 콘텐츠 미저장 (ADR-054 M1/D4)

- Kakao/Naver 응답은 **DISPLAY-ONLY**. `phone`/`address`/`road_address`/`category`/`title`
  등 **provider 파생 콘텐츠를 DB에 persist하거나 다른 서비스로 forward하지 않는다**.
- POI/feature-request로 넘어가 **저장하는 것은**: 사용자가 타이핑/유지한 **name**,
  사용자가 찍은 **coord**, 사용자 **note**, 그리고 opaque **`{provider, external_id,
  deep_link_url}` = external_ref**뿐이다.
- 상세를 볼 때 provider 정보는 **매번 라이브 재조회**한다(캐시된 콘텐츠 재표시 금지,
  §10 캐시는 단기 검색 응답 완화용일 뿐 콘텐츠 영속화가 아님).

### 5.2 attribution + back-link (ADR-054 M19, HARD requirement)

- Kakao/Naver 소스 **모든 검색 row와 상세 view**에 "카카오" / "네이버 검색"
  **가시적 attribution + back-link**(`provider_url`)를 표시한다. 누락 시 약관 위반.
- 로고/워드마크는 **로컬 asset**(원격 img-src 금지).

### 5.3 쿼터/비용 (ADR-054 M20)

- Naver 오픈 API 쿼터 ≈ **25,000 호출/일**. Kakao Local도 앱 쿼터 한도가 있다.
- **internal-first short-circuit**: 내부 결과(feature+my_poi+address) 수 ≥ **K**면
  Kakao/Naver를 **호출하지 않는다**(§10). 최소 query 길이 게이트, 클라이언트 디바운스
  유지, in-flight 취소.

## 6. Secret 관리 (ADR-054 M18)

| 값 | 설정 키 | 타입 | 비고 |
|----|---------|------|------|
| Kakao REST 키 | `pinvi_kakao_oauth_rest_api_key` | `str` (기존) | **기존 OAuth 앱 키 재사용** — Kakao 콘솔에서 `로컬` 제품만 추가 활성. 중복 Kakao 키 발급 금지 |
| Naver Search Client ID | `pinvi_naver_search_client_id` | `SecretStr` (신규) | OAuth용 `pinvi_naver_oauth_client_id`와 **별개 앱**(검색 API 전용) |
| Naver Search Client Secret | `pinvi_naver_search_client_secret` | `SecretStr` (신규) | 위와 세트 |

- Kakao 인증은 `Authorization: KakaoAK {키}` **헤더**, Naver는 `X-Naver-Client-Id` /
  `X-Naver-Client-Secret` **헤더**로 실린다. secret이 query가 아니라 헤더에 있으므로
  `api_call_logging.sanitize_api_call_endpoint`(query 마스킹)로는 URL에 남지 않는다 —
  그래도 **요청 헤더 전체를 로그/Sentry에 남기지 않는다**.
- 신규 값은 `SecretStr`. 사용 시 `.get_secret_value()`로만 꺼내고 로그 금지.

```python
# apps/api/app/core/config.py (Settings 발췌, ADR-054)
# Kakao Local — 기존 OAuth REST 키 재사용(pinvi_kakao_oauth_rest_api_key), 신규 키 없음
pinvi_kakao_local_enabled: bool = True
pinvi_kakao_local_base_url: str = "https://dapi.kakao.com"
# Naver Local — 검색 API 전용 신규 앱 credential
pinvi_naver_local_enabled: bool = True
pinvi_naver_local_base_url: str = "https://openapi.naver.com"
pinvi_naver_search_client_id: SecretStr = SecretStr("")
pinvi_naver_search_client_secret: SecretStr = SecretStr("")
# 공통 전송/보강 정책
pinvi_place_provider_timeout_seconds: float = 2.5
pinvi_place_provider_max_attempts: int = 2
pinvi_place_search_internal_threshold: int = 5   # K: 내부 결과가 이 수 미만일 때만 provider 호출
pinvi_place_search_cache_ttl_seconds: int = 60   # (q, coord-cell) 단기 캐시 TTL
```

## 7. 서버 사이드 client 구조 (`clients/kor_travel_geo.py` 미러)

`kor-travel-geo` client와 동일 패턴: **factory + `api_call_event_hooks` + 수동 지수
백오프 + lifespan + `app.state` + `Depends`**. provider tag는 각각
`"kakao_local"` / `"naver_local"`.

```python
# apps/api/app/clients/kakao_local.py (구조 발췌 — kor_travel_geo.py 미러)
class KakaoLocalUnavailable(Exception): ...

class KakaoLocalClient:
    """Kakao Local 전송 전용(httpx.AsyncClient 1개). 표시 전용 — 콘텐츠 미저장."""
    def __init__(self, http: httpx.AsyncClient, *, rest_api_key: str,
                 max_attempts: int = 2, backoff_base_seconds: float = 0.2) -> None:
        self._http = http
        self._key = (rest_api_key or "").strip()
        self._max_attempts = max(1, max_attempts)
        self._backoff = backoff_base_seconds

    async def search_keyword(self, *, query: str, size: int,
                             x: float | None = None, y: float | None = None,
                             radius: int | None = None) -> dict[str, Any]:
        params = {"query": query, "size": size}
        if x is not None and y is not None:      # "내 주변 검색"일 때만 좌표 전달(§9)
            params |= {"x": x, "y": y, "radius": radius or 20000, "sort": "distance"}
        # transient(타임아웃/연결/5xx)만 수동 지수 백오프 재시도, 4xx는 즉시 실패
        return await self._get("/v2/local/search/keyword.json", params)

    def _auth_headers(self) -> dict[str, str]:
        if not self._key:
            raise KakaoLocalUnavailable("Kakao REST 키 미설정")
        return {"Authorization": f"KakaoAK {self._key}"}

def create_kakao_local_client(app_settings: Settings) -> KakaoLocalClient:
    http = httpx.AsyncClient(
        base_url=app_settings.pinvi_kakao_local_base_url,
        timeout=app_settings.pinvi_place_provider_timeout_seconds,
        event_hooks=api_call_event_hooks(
            db_session.async_session_factory, provider="kakao_local"),
    )
    return KakaoLocalClient(http, rest_api_key=app_settings.pinvi_kakao_oauth_rest_api_key,
                            max_attempts=app_settings.pinvi_place_provider_max_attempts)
```

`clients/naver_local.py`도 동형이되 provider `"naver_local"`, base_url
`pinvi_naver_local_base_url`, `_auth_headers`는
`{"X-Naver-Client-Id": id.get_secret_value(), "X-Naver-Client-Secret":
secret.get_secret_value()}`, endpoint `/v1/search/local.json`, `display` 파라미터(≤5).

lifespan / Depends도 `kor_travel_geo_client_lifespan` / `get_kor_travel_geo_client` 미러:

- `kakao_local_client_lifespan` / `naver_local_client_lifespan` → `app.state.kakao_local_client`
  / `app.state.naver_local_client` 세팅·close. `*_enabled=false`면 client를 만들지 않는다.
- `get_kakao_local_client` / `get_naver_local_client` (Depends) — client 없으면 **hard
  fail이 아니라 degrade**: `/search` 핸들러가 해당 provider를 `degraded_sources`에
  넣고 나머지 소스로 응답(§11). geo와 달리 provider 부재가 검색 전체를 막지 않는다.

## 8. CSP / 딥링크 host

- provider API host(`dapi.kakao.com`, `openapi.naver.com`)는 서버만 호출 →
  **웹 `connect-src`에 추가 금지**.
- 브라우저가 여는 것은 back-link nav host뿐: `place.map.kakao.com` / `map.kakao.com`,
  `map.naver.com`(또는 `naver.me`) — `target="_blank" rel="noopener noreferrer"`,
  connect-src 불필요.
- attribution 로고 + maki glyph = **로컬 번들**(원격 img-src/script 금지).

## 9. 위치 감사 — 위치정보 제3자 제공 (ADR-054 M12)

"내 주변 검색"으로 사용자 좌표를 **Kakao에 전달**하는 것은 단순 수집이 아니라
**위치정보 제3자 제공**이다(`docs/compliance/lbs-act.md`). 좌표 없는 키워드 검색은
감사 대상이 아니다.

- `/search`(또는 `/v1/search`)를 `middleware/location_audit.py`의 `PURPOSE_BY_PATH`에
  **`third_party_place_search`** 로 등록한다.
- 좌표는 `lat`/`lon` **별도 query 파라미터**로 받고, 핸들러에서
  `request.state.location_audit_coord = (lat, lon)`을 세팅한다(`_extract_coord`가
  `location_audit_coord`를 우선 읽음).
- 좌표 전달은 **기존 위치 동의 flow 뒤에 게이트**한다. 사용자가 "내 주변 검색"을
  **명시적으로 선택**했을 때만 Kakao에 좌표를 보낸다. 기본 검색은 좌표 미전송(Naver는
  애초에 좌표 파라미터 없음, §3.2).
- 좌표 정밀도/평문 로깅 제약은 kor-travel-geo와 동일(user-location §7, 소수 4자리).

## 10. 캐시 / rate-limit / internal-first (ADR-054 M20)

- **internal-first short-circuit**: `/search` 핸들러가 먼저 feature+my_poi+address를
  모은다. 결과 수 ≥ `pinvi_place_search_internal_threshold`(K)면 provider **미호출**.
- **단기 캐시**: 키 `(q, rounded-coord-cell)`, TTL ≈ `pinvi_place_search_cache_ttl_seconds`
  (in-process TTL, Redis는 후속). 좌표는 cell로 quantize해 키 폭증 방지(kor-travel-geo
  `_coord_str` 사고 동일). **캐시는 검색 응답 완화용일 뿐 provider 콘텐츠 영속화가
  아니며**, 상세 view는 항상 라이브 재조회(§5.1).
- **디바운스/최소 길이/취소**: 클라이언트 디바운스 유지, 최소 query 길이 게이트,
  in-flight 취소(ADR-054 M20). rate-limit은 Pinvi `slowapi` 경계에서 자기 쿼터 방어.

## 11. degraded-source 동작

- provider 호출이 5xx/타임아웃/키 미설정/쿼터 초과이면 **해당 provider만**
  `degraded_sources`에 추가하고 나머지 소스로 `200`을 반환한다. **검색 전체를 실패시키지
  않는다**(internal 결과는 provider와 무관하게 항상 반환).
- 상세 enrichment(`GET /features/{id}/detail-card?providers=kakao,naver`, ADR-056)도
  동일 — enrichment 실패 시 `degraded` 마커를 달고 base detail-card는 그대로 준다.
- name+coord 퍼지 매칭 confidence가 낮으면 잘못된 전화/URL 대신 "일치하는 외부 정보
  없음"을 표시한다(ADR-056 match-confidence guard).

## 12. ADR-015 supersede (본 문서가 kakao-map.md를 대체)

- ADR-015(`docs/integrations/kakao-map.md`)는 (a) 지도 클라이언트를 Kakao→VWorld로
  바꾸고 (b) Local 검색을 kor-travel-map 경유로 라우팅하며 Kakao Local 직접 호출을
  드롭했다. **(a)는 유효**(지도 엔진은 여전히 `vworld-map-web`, ADR-046).
- ADR-054가 뒤집는 것은 **(b)뿐**: 표시 전용 + attribution + external_ref-only
  파이프라인이라는 제약 하에서 Kakao Local + Naver Local **직접 서버 호출**을
  자동완성 주소/딥링크 gap 보강용으로 재도입한다(정본 feature는 여전히
  kor-travel-map). `kakao-map.md`의 "Local 검색" 항목은 본 문서로 대체된다.

## 13. AI agent 구현 체크리스트

- [ ] `core/config.py` — §6 키 추가. Kakao는 `pinvi_kakao_oauth_rest_api_key` 재사용,
      Naver는 `pinvi_naver_search_client_id/secret`(`SecretStr`) 신규(+ `.env.example`).
- [ ] `clients/kakao_local.py` + `clients/naver_local.py` — factory +
      `api_call_event_hooks(..., provider="kakao_local"/"naver_local")` + 수동 백오프 +
      lifespan + `app.state.*_client` + `get_*_client` Depends(부재 시 degrade).
- [ ] `main.py` lifespan — provider별 `httpx.AsyncClient` 생성/close(`*_enabled` 게이트).
- [ ] `GET /search` 핸들러 — internal-first(K) → provider 병합 →
      `{results: PlaceSearchResult[], degraded_sources[]}`, 정렬 internal→kakao→naver.
      Naver `title` HTML strip, `mapx/mapy /1e7`, Naver `external_id`=`link` 정규화.
- [ ] `middleware/location_audit.py` `PURPOSE_BY_PATH`에 `/search` →
      `third_party_place_search`; 핸들러에서 `request.state.location_audit_coord` 세팅;
      좌표는 "내 주변 검색" 동의 뒤에만 Kakao 전달.
- [ ] provider 콘텐츠 미저장 검증 — POI/feature-request 경로가 user-authored
      name+coord+note + `external_ref{provider,external_id,deep_link_url}`만 저장/forward.
- [ ] attribution 로고 + maki glyph 로컬 asset 번들(원격 img-src 금지); 딥링크 host만
      브라우저 노출.
- [ ] 통합 테스트: `httpx.MockTransport`로 Kakao/Naver 응답 stub → 매핑/좌표 변환/HTML
      strip/degrade/미저장 검증(실 provider 의존 금지).

## 14. 환경변수

```dotenv
# Kakao Local — 기존 OAuth REST 키 재사용(신규 Kakao 키 없음). Kakao 콘솔에서 로컬 제품 활성.
PINVI_KAKAO_OAUTH_REST_API_KEY=
PINVI_KAKAO_LOCAL_ENABLED=true
PINVI_KAKAO_LOCAL_BASE_URL=https://dapi.kakao.com
# Naver Local — 검색 API 전용 신규 앱 credential(SecretStr)
PINVI_NAVER_SEARCH_CLIENT_ID=
PINVI_NAVER_SEARCH_CLIENT_SECRET=
PINVI_NAVER_LOCAL_ENABLED=true
PINVI_NAVER_LOCAL_BASE_URL=https://openapi.naver.com
# 공통 전송/보강 정책
PINVI_PLACE_PROVIDER_TIMEOUT_SECONDS=2.5
PINVI_PLACE_PROVIDER_MAX_ATTEMPTS=2
PINVI_PLACE_SEARCH_INTERNAL_THRESHOLD=5
PINVI_PLACE_SEARCH_CACHE_TTL_SECONDS=60
```

`PINVI_NAVER_SEARCH_*`는 OAuth 로그인용 `PINVI_NAVER_OAUTH_*`와 **다른 앱**이다(검색
API 전용). 전부 서버 전용 secret이며 웹 `NEXT_PUBLIC_*`로 노출하지 않는다.

## 15. 관련 문서

- `docs/api/search.md` — 통합 `GET /search` + `PlaceSearchResult` 계약 정본(ADR-054).
- `docs/kor-travel-map-integration.md` / `docs/integrations/kor-travel-map-rest-api.md`
  — 정본 feature + feature-request(external_ref) 경계.
- `docs/integrations/kor-travel-geo.md` — 주소/좌표 geocoding(내부 우선 소스).
- `docs/integrations/kakao-map.md` — 지도 클라이언트 폐기 문서(ADR-015). 본 문서가 그
  "Local 검색" 항목을 supersede(§12).
- `docs/compliance/lbs-act.md` / `docs/architecture/user-location.md` — 위치정보 제3자
  제공 감사(§9).
- `docs/decisions.md` — ADR-054(외부 provider 표시 전용), ADR-056(detail-card enrichment).
