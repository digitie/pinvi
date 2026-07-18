# kor-travel-map 통합 — OpenAPI HTTP 계약 (목표)

본 문서는 Pinvi(`apps/api` + `apps/web`)가 별도 저장소
`kor-travel-map`의 **OpenAPI HTTP 계약**을 사용하는 표준이다.
ADR-026 + ADR-027 기준이며, 과거 ADR-002의 "함수 직접 호출" 정책을 대체한다.

> **✅ 현재 상태 (2026-06-10 갱신)**: 위 계약은 더 이상 "목표"가 아니라 **실재한다**.
> `kor-travel-map` `origin/main` `0e45bd7` 기준 — FastAPI :12701에 `/v1` 전 표면
> (사용자 read 8종 + admin/ops/debug, ADR-048 T-216a~g 머지 완료: RFC7807
> problem+json, envelope payload/meta 분리, batch `found`, in-bounds `max_items`),
> 기계 정본 `packages/kor-travel-map-admin/openapi.user.json`·`openapi.json`, prose 정본
> `docs/rest-api.md`(전 표면) + `docs/pinvi-rest-api.md`(Pinvi 소비 view).
> **2026-06-24 추가**: 최신 kor_travel_map API 패키지 분리 후 기계 정본 경로는
> `packages/kor-travel-map-api/openapi.user.json`·`openapi.json`이다. public REST
> surface는 설정에 따라 `key` query를 요구할 수 있고, Pinvi는 service token이 없을
> 때 `PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY` 또는 `PINVI_VWORLD_API_KEY`를 사용한다.
> 2026-06-06의 "미존재(debug-ui 8087뿐)" 실측은 **stale 본 체크아웃(b775c74) 오판**
> 이었다 — 형제 repo 실측은 반드시 `git fetch` 후 origin/main 기준으로 할 것.
> **구체 엔드포인트 계약은 `docs/integrations/kor-travel-map-rest-api.md`가 정본 view**이고,
> 본 문서는 경계/패턴 개요만 유지한다. 충돌 시 kor_travel_map `openapi.user.json` 우선.

## 1. 경계

```
Pinvi apps/api
  ├─ app schema, 사용자/여행/POI/첨부/권한 소유
  ├─ kor-travel-map OpenAPI HTTP client
  └─ kor-travel-geo v2 REST client
          │
          │ HTTP, JSON, OpenAPI
          ▼
kor-travel-map 독립 프로그램
  ├─ API/Admin API: http://127.0.0.1:12701
  ├─ feature / provider_sync schema 소유
  └─ 자체 Dagster/Provider 적재 소유
```

- Pinvi는 `kor-travel-map`을 import하거나 `feature` /
  `provider_sync` schema에 직접 접근하지 않는다.
- Pinvi는 `feature_id`와 snapshot을 `app` schema에 저장하고, 최신 feature 정보는
  kor-travel-map HTTP API로 batch/read 조회한다.
- kor-travel-map의 provider raw 변환, feature 적재, dedup, source record, admin/offline
  upload는 kor-travel-map 저장소 책임이다.
- Geocoding/주소/행정구역은 kor-travel-map을 경유하지 않고 `kor-travel-geo` v2 REST를
  직접 호출한다(`docs/integrations/kor-travel-geo.md`, ADR-025).

## 2. 설정

```dotenv
PINVI_KOR_TRAVEL_MAP_API_BASE_URL=http://localhost:12701
# admin "API"도 :12701 (/v1/admin/*)이다.
PINVI_KOR_TRAVEL_MAP_ADMIN_BASE_URL=http://localhost:12701
# public REST key query fallback. service token이 있으면 key query를 붙이지 않는다.
PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY=
# kor_travel_map admin proxy gate가 켜진 운영 API용.
PINVI_KOR_TRAVEL_MAP_ADMIN_PROXY_SECRET=
PINVI_KOR_TRAVEL_MAP_ADMIN_ACTOR=pinvi-admin
# /v1/ops/datasets*·/v1/ops/pipeline* scope별 server principal
PINVI_KOR_TRAVEL_MAP_OPS_READ_TOKEN=
PINVI_KOR_TRAVEL_MAP_OPS_CANCEL_TOKEN=
```

kor-travel-map 쪽 런북에서는 동일 API URL을 `KOR_TRAVEL_MAP_API_URL`로 부를 수 있다.
Pinvi 설정 prefix는 항상 `PINVI_*`다.

운영 admin base URL은 HTTP(S), host `127.0.0.1|host.docker.internal`, port `12701`, root
path만 허용한다. 비운영은 ops token 두 값이 모두 비었을 때만 opt-out하며, 하나라도 설정하면
read/cancel token 모두 32자 이상·Unicode whitespace 없음·서로 다름을 강제한다.

## 3. Pinvi/user-facing OpenAPI

최신 `openapi.user.json`의 Pinvi 사용 표면:

| 메서드 | 경로 | Pinvi 용도 |
|--------|------|---------------|
| `GET` | `/v1/features/in-bounds` | 지도 viewport feature 조회 (서버 클러스터, `max_items`) |
| `GET` | `/v1/features/search` | feature 텍스트 검색 |
| `GET` | `/v1/features/nearby` (+`/by-target`) | 반경/기준 feature 주변 조회 |
| `GET` | `/v1/features/{feature_id}` | feature 상세 조회 |
| `GET` | `/v1/features/{feature_id}/weather` | 날씨 카드 |
| `POST` | `/v1/features/batch` | POI/일정 응답 조립용 batch 조회 (응답 `data.found`+`missing`, ServiceToken) |
| `GET` | `/v1/categories` | 카테고리 카탈로그 |
| `GET` | `/v1/public/beaches*` | Pinvi `/public/beaches*` 공개 해수욕장 목록·상세·marker |
| `GET` | `/v1/public/festivals*` | Pinvi `/public/festivals*` 공개 축제 월별 목록·상세·marker |
| `POST` | `/v1/admin/features*` (change API) | Pinvi Admin 승인 제안 반영 (admin 도메인 전용, §2.9 of integrations doc) |
| `POST/GET` | `/v1/admin/feature-update-requests*` | 재적재 — kor_travel_map 운영자 전용, Pinvi 제품 비노출 (DEC-05) |

응답 envelope는 kor-travel-map 계약의 `{data, meta}`를 따른다. Pinvi는 이 응답을
자기 API 응답 셰입으로 다시 감싸거나 필요한 필드만 투영할 수 있지만, 원천 필드명
의미를 바꾸지 않는다.

좌표는 전 구간 WGS84 `(lon, lat)`이며 bbox는
`min_lon, min_lat, max_lon, max_lat` 순서다.

## 4. 전체 Admin/ops OpenAPI

최신 `openapi.json`에는 user-facing 표면 외에 다음 운영 표면이 있다. Pinvi
Admin이 직접 프록시할 때만 사용하고, 일반 사용자 API에서는 노출하지 않는다.

| 영역 | 대표 경로 |
|------|----------|
| feature update request | `/v1/admin/feature-update-requests`, `/run-now`, `/cancel` |
| dedup/enrichment review | `/v1/admin/dedup-reviews`, `/v1/admin/enrichment-reviews` |
| feature 관리 | `/v1/admin/features*`(change API 포함), `/v1/admin/features/{id}/deactivate` |
| 이슈 큐 | `/v1/admin/issues*` |
| offline upload | `/v1/admin/offline-uploads/*` |
| POI cache target | `/v1/admin/poi-cache-targets/*` |
| backup/restore | `/v1/admin/backups*`, `/v1/admin/restore/*` |
| ops/consistency | `/v1/ops/consistency/*`, `/v1/ops/health-deep` |
| dataset/pipeline | `/v1/ops/datasets*`, `/v1/ops/pipeline/{overview,executions}`와 canonical cancellation |
| debug | `/v1/debug/etl/*`, `/v1/debug/mois-license` |

`/health`·`/version`만 비버전 경로다 (구 `/debug/health`·`/debug/version`은 kor_travel_map
T-214h clean cut으로 제거됨). **admin/ops/debug API도 전부 :12701**이다. 구현과
테스트는 OpenAPI 파일을 우선한다.

## 5. Pinvi API 매핑

| Pinvi API | kor-travel-map 호출 | 비고 |
|--------------|----------------|------|
| `GET /features/in-bounds` | `GET /v1/features/in-bounds` | query passthrough 후 Pinvi 응답으로 투영 (`max_items`, 서버 클러스터) |
| `GET /features/{feature_id}` | `GET /v1/features/{feature_id}` | 상세 화면 |
| `GET /features/nearby` | `GET /v1/features/nearby` (기준 feature 시 `/by-target`) | cursor 페이지네이션 |
| `GET /search` feature 영역 | `GET /v1/features/search` | 주소 후보는 `kor-travel-geo` v2 search |
| `GET /trips/{trip_id}` POI join | `POST /v1/features/batch` | `feature_id[]` batch, 응답 `data.found`/`missing` |
| POI 생성 feature 검증 | `POST /v1/features/batch` | `missing`이면 snapshot fallback 정책 적용 |
| 사용자 feature 제안 승인 반영 | `POST/PATCH/DELETE /v1/admin/features*` (change API) | Pinvi Admin 도메인 전용 (DEC-05, T-179/T-180) |

## 6. HTTP client 패턴

```python
class KorTravelMapClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def features_batch(self, feature_ids: list[str]) -> dict:
        resp = await self._http.post(
            "/v1/features/batch",
            json={"feature_ids": feature_ids},
        )
        resp.raise_for_status()
        return resp.json()  # {"data": {"found": {...}, "missing": [...]}, "meta": {...}}
```

- `httpx.AsyncClient`는 FastAPI lifespan에서 1개 생성해 재사용한다.
- 네트워크/5xx/timeout은 Pinvi API에서 `503 FEATURE_SERVICE_UNAVAILABLE`로
  매핑한다. POI snapshot fallback이 가능한 read 경로는 degraded 응답을 허용한다.
- kor-travel-map HTTP client wrapper는 **네트워크 transport** 역할만 한다. provider
  변환/feature 정규화 같은 도메인 wrapper를 만들지 않는다.

## 7. 데이터 저장 정책

- `app.trip_day_pois.feature_id`는 kor-travel-map `feature_id` 문자열을 저장한다.
  cross-schema FK는 두지 않는다.
- `feature_snapshot`은 POI 생성 시점의 표시 캐시다. 최신 정보는
  `POST /v1/features/batch`로 가져오고, 실패하면 snapshot을 표시한다. inactive로
  전환된 feature는 `found`에 status와 함께 내려온다(kor_travel_map D-12, 2026-06-10) —
  "철회/폐업됨" 표시로 구분하고 `missing`(삭제/없음)과 다르게 다룬다.
- kor-travel-map 최신 정보와 snapshot이 달라도 Pinvi가 `feature` schema를 직접
  수정하지 않는다. 필요 시 feature update request를 생성한다.

## 8. AI agent 체크리스트

- [ ] 최신 kor-travel-map `main`의 `openapi.user.json`과 `openapi.json`을 먼저 확인한다.
- [ ] Pinvi 설정은 `PINVI_KOR_TRAVEL_MAP_API_BASE_URL` /
      `PINVI_KOR_TRAVEL_MAP_ADMIN_BASE_URL`만 사용한다.
- [ ] `kor-travel-map` import, `AsyncKorTravelMapClient`, `feature` schema ORM/SQL을
      Pinvi 사용자 경로에 추가하지 않는다.
- [ ] feature read 구현은 `httpx.MockTransport` 기반 계약 테스트를 먼저 작성한다.
- [ ] OpenAPI 경로가 prose 문서와 충돌하면 OpenAPI 파일을 우선하고 문서 drift를
      양쪽 저장소에 기록한다.
