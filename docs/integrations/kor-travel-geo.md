# kor-travel-geo 통합 — geocoding (v2 REST API 직접 호출)

본 문서는 Pinvi(`apps/api`)가 **사용자 대면 geocoding**(주소↔좌표, 검색,
행정구역)을 위해 `kor-travel-geo`의 **v2 REST API를 직접 HTTP 호출**하는 표준
패턴이다. ADR-025 기준.

> **경계 한 줄 요약**
> - **Feature 데이터**(place/event/weather/...) → `kor-travel-map` **OpenAPI
>   HTTP 계약**(ADR-026). → `docs/kor-travel-map-integration.md`.
> - **Geocoding/주소/행정구역** → `kor-travel-geo` **v2 REST API HTTP 호출**(ADR-025).
>   → 본 문서.
> - kor-travel-map도 자기 ETL 적재 때 kor-travel-geo v2 REST를 쓰지만(그쪽 ADR-006), 그건
>   kor-travel-map 내부 책임이다. Pinvi 사용자 경로는 본 문서 경계만 따른다.

권위 출처는 kor-travel-geo 최신 `main`의 `openapi.json` +
`docs/api-reference/llm-summary.md`다. 본 문서는 Pinvi 입장의 사용 계약이다.

> **v2 공개 API key (ADR-048)**: Pinvi는 `kor-travel-geo` v2 REST 호출마다
> `key=<PINVI_VWORLD_API_KEY>` query를 붙인다. 별도
> `PINVI_KOR_TRAVEL_GEO_API_KEY`는 두지 않는다. `kor-travel-geo`는 같은 raw 값을
> `KTG_VWORLD_API_KEY`로 받아 공개 API key hash 저장/검증(`ops.public_api_keys`)을
> 소유한다. Pinvi 로그에는 key 원본과 query 포함 upstream URL을 남기지 않는다.

## 1. 개관

```
┌───────────────────────────────────────────────────────────┐
│ Pinvi apps/api (FastAPI)                                │
│   GET /geo/search · /geo/reverse · /geo/geocode  (사용자)   │
│   services/geocoding.py — httpx.AsyncClient                │
└───────────────────────────────────────────────────────────┘
                  │ HTTP  POST /v2/geocode|reverse|search
                  ▼
┌───────────────────────────────────────────────────────────┐
│ kor-travel-geo REST 서비스 (별 프로세스/컨테이너)        │
│   FastAPI :12501  (운영 docker network: http://kor-travel-geo:12501)│
│   1차 로컬 PostGIS(도로명주소 전자지도) → 2차 vworld/juso fallback │
└───────────────────────────────────────────────────────────┘
```

- Pinvi는 **v2 candidate 표면**을 우선 의존한다. python 패키지(`kor_travel_geo`)
  in-process import / DB 직접 접근을 사용자 경로에서 쓰지 않는다(ADR-025).
- v1 vworld-호환 표면(`/v1/address/*`)은 legacy/호환 표면이다. 신규 사용자 경로는
  candidate 중심 v2를 쓴다.
- 외부 API(VWorld/juso/epost)는 Pinvi가 직접 호출하지 않는다 — kor-travel-geo REST
  내부 책임(`fallback="api"`).

## 2. 좌표·코드 규약 (전 구간 공통)

- **좌표는 외부 표면에서 항상 `(lon, lat)`**. v2 후보 좌표는
  `point{lon,lat}`이며, v1 호환 표면만 `Point{x,y}`(`x=lon`, `y=lat`)를 쓴다.
  Pinvi 내부도 `(lon, lat)` — `(lat, lng)` 뒤집기 어댑터를 두지 않는다(ADR-015 mirror).
- `crs` 기본 `EPSG:4326`.
- `sig_cd`: 2자리 시도 또는 5자리 시군구. `bjd_cd`: 8자리 prefix 또는 10자리 법정동.
- `confidence`는 **endpoint-local 점수** — geocode/reverse/search/regions 사이에서 직접
  비교하지 않는다(같은 endpoint 안 정렬/표시 보조값으로만).
- 거리 기반 후보는 `distance_m`이 정식 필드(`metadata.distance_m`보다 우선).
- 현재 published `point_precision`은 `centroid` / `grid_cell`이다. `exact` /
  `interpolated` / `approximate` 등은 예약값이라, UI는 모르는 값을 표시하지 않고
  내부 정렬/품질 보조로만 쓴다.

## 3. v2 endpoint 계약 (Pinvi가 호출하는 것)

모두 `POST`, `Content-Type: application/json`, 응답 최상위 `{status, candidates[], ...}`.
Pinvi의 server-to-server client는 모든 v2 요청에 `?key=<PINVI_VWORLD_API_KEY>`를
붙인다(ADR-048). 이 key는 사용자 클라이언트에 노출하지 않는다.

### 3.1 `POST /v2/reverse` — 좌표 → 주소/행정구역

요청:

| 필드 | 타입 | 기본 | 비고 |
|------|------|------|------|
| `lon` | float | 필수 | 경도 |
| `lat` | float | 필수 | 위도 |
| `crs` | string | `EPSG:4326` | |
| `radius_m` | int | `200` | 검색 반경 |
| `include_region` | bool | `true` | region 보강 |
| `include_zipcode` | bool | `true` | 우편번호 보강 |
| `sig_cd`/`bjd_cd` | string | — | hint |

응답 `candidates[]` 항목: `match_kind`(`road`/`parcel`/`keyword`/`region`/`sppn`/`poi`),
`address`, `point{lon,lat}`, `region{sig_cd,bjd_cd,...}`, `source`, `distance_m`,
`confidence`.
- `confidence = 1 - distance_m/radius_m` (반경 내 근접도).
- 국가지점번호 의무지역이면 `match_kind="sppn"` 후보가 함께 올 수 있다(`address`
  없을 수 있음). Pinvi region label 용도로는 `sppn`을 무시한다.

```bash
curl -X POST "$KOR_TRAVEL_GEO/v2/reverse" -H 'Content-Type: application/json' \
  -d '{"lon":129.118,"lat":35.155,"radius_m":200}'
```

### 3.2 `POST /v2/search` — 주소/도로명/행정구역/장소 검색 (자동완성)

요청: `query`(필수), `type`(`address`|`place`|`district`|`road`|`category`,
기본 `address`), `page`(1), `size`(10), `sig_cd`/`bjd_cd`/`bbox` hint.

응답: `status`, `total`, `candidates[]`(`match_kind`, `address`, `place`, `point`,
`region`, `source`, ...). `type="district"`는 행정구역 polygon 대표점
(`ST_PointOnSurface`)을 `point`로 준다(예: `수지구` → `용인시 수지구`).

```bash
curl -X POST "$KOR_TRAVEL_GEO/v2/search" -H 'Content-Type: application/json' \
  -d '{"query":"테헤란로","type":"road","sig_cd":"11680","size":20}'
```

### 3.3 `POST /v2/geocode` — 주소 → 좌표

요청: `query` 또는 `road_address`/`jibun_address`/`keyword` 중 하나(필수),
`sig_cd`/`bjd_cd`/`bbox`/`limit`(10)/`fallback`(`none`|`api`)/`include_geometry`(false).

응답: `{status, query_id, input, candidates[]}`. 각 후보 `confidence`, `match_kind`,
`source`, `point{lon,lat}`, `point_precision`(`centroid`/`grid_cell`, 그 외 예약값),
`address{type,full,road_name_code,postal_code}`, `region`.
`include_geometry=true`면 `point + geometry`(GeoJSON, `kind`=building/region/road)
구조로 함께 반환(point가 도형으로 대체되지 않음).

> `fallback="api"`(외부 vworld/juso 결과를 candidate로 감쌈)는 **기본 사용 안 함**.
> 비용·약관·캐시 정책이 얽혀 있어 `docs/architecture/geocoding-open-decisions.md`
> 결정 전까지 `none` 유지.

### 3.4 `POST /v2/regions/within-radius` — 좌표 반경 내 행정구역

최신 kor-travel-geo `openapi.json`에는 `POST /v2/regions/within-radius`가 있다. 좌표
주변 행정구역 후보를 반경 기준으로 받을 때 사용한다.

Pinvi 사용 원칙:

- 여행 목적지/POI 주변 지역 label처럼 **반경 내 행정구역 후보 목록**이 필요할 때만
  호출한다.
- 단일 좌표의 대표 주소/행정구역 label은 여전히 `/v2/reverse`를 우선한다.
- 후보 정렬/표시는 `distance_m`, `confidence`, region code를 같은 응답 안에서만
  비교한다.

## 3.5 v1 및 admin 표면 확인

최신 `openapi.json`의 public v1 legacy 표면:

| 메서드 | 경로 |
|--------|------|
| `GET` | `/v1/healthz` |
| `GET` | `/v1/address/geocode` |
| `GET` | `/v1/address/reverse` |
| `GET` | `/v1/address/search` |
| `GET` | `/v1/address/zipcode` |
| `GET` | `/v1/address/pobox` |

Admin/ops 표면에는 uploads/jobs/tables/logs/normalize/explain/load-sources,
backup/restore, consistency, audit/snapshot/release/maintenance, cache metrics,
RustFS storage 경로가 포함된다. 특히 RustFS 운영 확인 경로는
`/v1/admin/storage/rustfs/check`, 설정 조회는 `/v1/admin/storage/rustfs/config`다.
Pinvi는 이 admin 표면을 사용자 API에서 호출하지 않는다. kor-travel-geo 운영 콘솔이나
별도 runbook이 소유한다.

## 4. Pinvi 노출 endpoint (신설 제안)

v2 candidate를 Pinvi 표준 응답 `{data, meta}`(`docs/api/common.md`)로 래핑한다.
라우터: `apps/api/app/api/v1/geo.py`.

| Pinvi endpoint | 호출 | 용도 |
|-------------------|------|------|
| `GET /geo/search?q=&type=&size=` | `POST /v2/search` | 주소/장소 자동완성 (Trip 만들 때 목적지 검색, POI 수동 추가) |
| `GET /geo/reverse?lon=&lat=&radius_m=` | `POST /v2/reverse` | 지도 클릭/내 위치 → 주소·행정구역 label |
| `GET /geo/geocode?q=` | `POST /v2/geocode` | 주소 문자열 → 좌표 (공유 링크/딥링크 주소 입력) |

GET 쿼리스트링 → 서비스에서 v2 POST body로 변환한다(클라이언트는 GET이 캐시·
링크 친화적). 좌표를 받는 `/geo/reverse`는 **위치 감사 대상**(§8).

## 5. httpx client 주입 + lifespan

geocoding은 HTTP 의존이므로 kor-travel-map과 별개의 httpx client를 lifespan에서
1개 만들어 재사용한다.

```python
# apps/api/app/core/config.py (Settings 발췌)
pinvi_kor_travel_geo_base_url: str = "http://localhost:12501"   # 운영: http://kor-travel-geo:12501
pinvi_kor_travel_geo_timeout_seconds: float = 3.0
pinvi_kor_travel_geo_enabled: bool = True       # False면 geocoding 기능 비활성(503)
pinvi_vworld_api_key: str = ""                  # ADR-048: kor-travel-geo v2 `key` query
```

```python
# apps/api/app/services/geocoding.py
from __future__ import annotations
import httpx
from app.core.config import settings

class GeocodingUnavailableError(Exception):
    code = "GEOCODING_UNAVAILABLE"

class GeocodingClient:
    """kor-travel-geo v2 REST 얇은 클라이언트. httpx.AsyncClient 주입."""
    def __init__(self, http: httpx.AsyncClient, *, api_key: str) -> None:
        self._http = http
        self._api_key = api_key

    async def reverse(self, *, lon: float, lat: float, radius_m: int = 200,
                      include_region: bool = True, include_zipcode: bool = True) -> dict:
        return await self._post("/v2/reverse", {
            "lon": lon, "lat": lat, "radius_m": radius_m,
            "include_region": include_region, "include_zipcode": include_zipcode,
        })

    async def search(self, *, query: str, type: str = "address", size: int = 10,
                     page: int = 1, sig_cd: str | None = None) -> dict:
        body = {"query": query, "type": type, "size": size, "page": page}
        if sig_cd:
            body["sig_cd"] = sig_cd
        return await self._post("/v2/search", body)

    async def geocode(self, *, query: str, limit: int = 10) -> dict:
        return await self._post("/v2/geocode", {"query": query, "limit": limit})

    async def _post(self, path: str, body: dict) -> dict:
        try:
            resp = await self._http.post(path, params={"key": self._api_key}, json=body)
        except httpx.HTTPError as exc:
            raise GeocodingUnavailableError(str(exc)) from exc
        if resp.status_code >= 500:
            raise GeocodingUnavailableError(f"kor-travel-geo {resp.status_code}")
        resp.raise_for_status()
        return resp.json()
```

```python
# apps/api/app/main.py (lifespan 발췌)
@asynccontextmanager
async def lifespan(app: FastAPI):
    ...
    if settings.pinvi_kor_travel_geo_enabled:
        app.state.kor_travel_geo_http = httpx.AsyncClient(
            base_url=settings.pinvi_kor_travel_geo_base_url,
            timeout=settings.pinvi_kor_travel_geo_timeout_seconds,
        )
    else:
        app.state.kor_travel_geo_http = None
    try:
        yield
    finally:
        if app.state.kor_travel_geo_http is not None:
            await app.state.kor_travel_geo_http.aclose()
```

```python
# apps/api/app/core/deps.py (의존성)
def get_geocoding_client() -> GeocodingClient:
    http = getattr(app_state(), "kor_travel_geo_http", None)
    if http is None:
        raise HTTPException(503, detail={"code": "GEOCODING_UNAVAILABLE",
                                         "message": "geocoding 서비스가 비활성입니다."})
    return GeocodingClient(http)
GeocodingDep = Annotated[GeocodingClient, Depends(get_geocoding_client)]
```

## 6. 라우터 예시 (reverse — 위치 감사 대상)

```python
# apps/api/app/api/v1/geo.py
router = APIRouter(prefix="/geo", tags=["geo"])

@router.get("/reverse", response_model=Envelope[GeoReverseResponse])
async def geo_reverse(lon: float, lat: float, geo: GeocodingDep,
                      radius_m: int = Query(200, ge=10, le=1000)) -> Envelope[GeoReverseResponse]:
    raw = await geo.reverse(lon=lon, lat=lat, radius_m=radius_m)
    region = _pick_region_candidate(raw.get("candidates", []))   # sppn 제외, 최근접 우선
    return Envelope.of(_to_reverse_response(region))
```

- `lon`/`lat` 쿼리 파라미터를 받으므로 `LocationAuditMiddleware`가 자동 적재한다
  (§8). `/geo/reverse`를 `PURPOSE_BY_PATH`에 `"reverse_geocode"`로 등록한다.
- candidate 정렬/선택은 서비스 레이어. `confidence`는 같은 응답 안에서만 비교.

## 7. 캐싱 / rate-limit

- **검색 자동완성**(`/geo/search`)은 호출량이 많다 — 디바운스(클라이언트 250ms) +
  동일 `(q,type,sig_cd)` 단기 캐시(서버 TanStack 아님, in-process TTL 60s 또는
  Redis는 후속). 구체 정책은 open-decisions 문서.
- reverse/geocode는 좌표·주소 정규화 후 캐시 키. 좌표는 소수 5자리로 quantize해
  키 폭증 방지(역지오코딩 캐시 키, kor-travel-map `_coord_str` 패턴과 동일 사고).
- rate-limit은 Pinvi의 `slowapi` 미들웨어 경계에서. kor-travel-geo 호출 폭주를
  Pinvi가 막는다(kor-travel-geo는 별 서비스라 Pinvi가 자기 쿼터를 책임).

## 8. 위치 감사 (LBS / PIPA)

`/geo/reverse`는 사용자 좌표를 서버로 전송하므로 `app.location_access_log` 자동
적재 대상이다(`docs/architecture/user-location.md` §4.2).

- `apps/api/app/middleware/location_audit.py`의 `PURPOSE_BY_PATH`에
  `"/geo/reverse": "reverse_geocode"` 추가.
- `/geo/search`·`/geo/geocode`는 **주소 문자열** 입력이라 좌표 감사 대상이 아니다.
  단 응답 좌표를 로그(Loki/Sentry)에 평문 적재하지 않는다(PII).
- 좌표 정밀도 노출은 소수 4자리까지(user-location §7).

## 9. 에러 매핑

| 상황 | Pinvi 응답 |
|------|---------------|
| kor-travel-geo 5xx / 네트워크 / 타임아웃 | `503 GEOCODING_UNAVAILABLE` (degrade — 지도/검색은 빈 결과로) |
| v2 `status != "OK"` 또는 candidates 빈 | `200 {data: {candidates: []}}` (정상 빈 결과) |
| 잘못된 좌표/파라미터(한국 범위 밖 등) | `422 VALIDATION_ERROR` (Pinvi가 먼저 검증) |
| `pinvi_kor_travel_geo_enabled=false` | `503 GEOCODING_UNAVAILABLE` |

geocoding 실패가 지도/여행 핵심 흐름을 막지 않도록 **graceful degrade**가 기본
(검색창은 "검색 일시 불가" 안내, 지도 클릭 label은 좌표만 표시).

## 10. 사용처 (Pinvi 기능 매핑)

| 기능 | endpoint | 비고 |
|------|----------|------|
| Trip 목적지 검색 / POI 수동 추가 자동완성 | `/geo/search?type=address\|place` | 디바운스 + 캐시 |
| 지도 클릭/우클릭 "이 지점 주소" | `/geo/reverse` | 위치 감사 |
| "내 위치" → 현재 행정구역 label | `/geo/reverse` (`include_region`) | user-location §4.2 |
| 행정구역 단위 탐색(시군구 선택) | `/geo/search?type=district` | 대표점 = `ST_PointOnSurface` |
| 좌표 주변 행정구역 후보 | `/geo/regions/within-radius` | kor-travel-geo `/v2/regions/within-radius` |
| 공유 링크/딥링크 주소 → 지도 이동 | `/geo/geocode` | |

> feature(관광지/주유소/날씨 등) 검색은 geocoding이 아니다 — kor-travel-map
> OpenAPI HTTP 계약. 주소·행정구역·장소명만 본 문서 경로.

## 11. AI agent 구현 체크리스트

- [ ] `apps/api/app/core/config.py` — `pinvi_kor_travel_geo_base_url` /
      `_timeout_seconds` / `_enabled` 추가 (+ `.env.example`). v2 공개 API key는
      `PINVI_VWORLD_API_KEY`를 재사용하고 별도 `PINVI_KOR_TRAVEL_GEO_API_KEY`를 두지 않는다.
- [ ] `apps/api/app/services/geocoding.py` — `GeocodingClient` + 예외.
      모든 v2 POST에 `key=<PINVI_VWORLD_API_KEY>` query를 붙이고, key 원본을 로그에 남기지 않는다.
- [ ] `apps/api/app/main.py` lifespan — `httpx.AsyncClient` 1개 생성/close.
- [ ] `apps/api/app/core/deps.py` — `GeocodingDep` (503 fallback).
- [ ] `apps/api/app/schemas/geo.py` + `packages/schemas/src/geo.ts` (Zod) —
      candidate / region / response (v2 셰입 → Pinvi 셰입 변환 모델).
- [ ] `apps/api/app/api/v1/geo.py` — `/geo/{search,reverse,geocode}` + 라우터 등록.
- [ ] `/geo/regions/within-radius`가 필요하면 kor-travel-geo
      `/v2/regions/within-radius`를 래핑한다.
- [ ] `location_audit.py` `PURPOSE_BY_PATH`에 `/geo/reverse` 등록.
- [ ] 통합 테스트: `httpx.MockTransport`로 v2 응답 stub → 변환·에러·degrade 검증
      (`apps/api/tests/integration/test_geocoding.py`). 실 kor-travel-geo 의존 금지.
- [ ] rate-limit(`slowapi`) + 캐시 정책 (open-decisions 결정 후).
- [ ] `docs/api/regions.md`의 region 조회를 본 경로로 정합(ADR-025).

## 12. 환경변수

```dotenv
PINVI_KOR_TRAVEL_GEO_BASE_URL=http://localhost:12501   # 운영: http://kor-travel-geo:12501
PINVI_KOR_TRAVEL_GEO_TIMEOUT_SECONDS=3.0
PINVI_KOR_TRAVEL_GEO_ENABLED=true
PINVI_VWORLD_API_KEY=                                # kor-travel-geo v2 `key` query와 모바일 token 발급 공용
```

`PINVI_VWORLD_API_KEY`는 서버 전용 secret이다. 웹의 `NEXT_PUBLIC_VWORLD_API_KEY`와
분리해 관리하고, 모바일 `/mobile/vworld/token` 발급과 `kor-travel-geo` v2 REST
`key` query에만 쓴다. 운영자는 `kor-travel-geo` 쪽 `KTG_VWORLD_API_KEY`도 같은 값으로
설정한다. VWorld/juso 외부 fallback 실행, 공개 API key hash 저장/폐기, 포트·재시도는
**kor-travel-geo 서비스 설정과 DB**가 소유한다(Pinvi가 직접 저장하지 않음).

## 13. 관련 문서

- `docs/api/regions.md` — 행정구역 endpoint (ADR-025로 kor-travel-geo v2 직접 정합).
- `docs/architecture/user-location.md` — 역지오코딩 region label + 위치 감사.
- `docs/architecture/geocoding-open-decisions.md` — 열린 결정(캐시/fallback/MCP 등).
- `docs/kor-travel-map-integration.md` — feature 데이터 경계(OpenAPI HTTP, 본 문서와 분리).
- kor-travel-geo 저장소 `openapi.json` + `docs/api-reference/llm-summary.md` (권위 출처).
