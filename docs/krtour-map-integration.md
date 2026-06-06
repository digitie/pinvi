# krtour-map 통합 — OpenAPI HTTP 계약 (목표)

본 문서는 TripMate(`apps/api` + `apps/web`)가 별도 저장소
`python-krtour-map`의 **OpenAPI HTTP 계약**을 사용하는 표준이다.
ADR-026 + ADR-027 기준이며, 과거 ADR-002의 "함수 직접 호출" 정책을 대체한다.

> **⚠️ 현재 상태 정정 (2026-06-06, ADR-027)**: 아래 계약은 **krtour-map이 신규로
> 구축해야 할 목표**다. 2026-06-06 `python-krtour-map` `main`(`HEAD=b775c74`) 실측
> 결과, 이 문서가 가정했던 `packages/krtour-map-admin/openapi.user.json`·
> `openapi.json`·`docs/tripmate-rest-api.md`·`docs/openapi-admin-contract.md`·포트
> 9011·`/tripmate/features/batch`는 **실재하지 않는다.** krtour-map의 실제 HTTP 표면은
> 인증 없는 debug-UI(`krtour-map-debug-ui`, 포트 8087, `GET /features` bbox·
> `GET /features/{id}`)뿐이다. TripMate가 필요로 하는 능력의 권위 명세는
> **`docs/krtour-map-requirements.md`** 이며, krtour-map은 이를 보고 운영급 HTTP
> 서비스를 신설한다. 아래 §3~§7 계약은 그 신설 대상의 목표 셰입이다.

향후 권위 산출물(krtour-map이 생성 예정):

- `python-krtour-map`의 user-facing OpenAPI (TripMate/user-facing 권위 계약)
- `python-krtour-map`의 전체 OpenAPI (Admin/ops/debug 포함)
- krtour-map 측 TripMate 통합 문서

## 1. 경계

```
TripMate apps/api
  ├─ app schema, 사용자/여행/POI/첨부/권한 소유
  ├─ krtour-map OpenAPI HTTP client
  └─ kraddr-geo v2 REST client
          │
          │ HTTP, JSON, OpenAPI
          ▼
python-krtour-map 독립 프로그램
  ├─ API:   http://127.0.0.1:9011
  ├─ Admin: http://127.0.0.1:9012
  ├─ feature / provider_sync schema 소유
  └─ 자체 Dagster/Provider 적재 소유
```

- TripMate는 `python-krtour-map`을 import하거나 `feature` /
  `provider_sync` schema에 직접 접근하지 않는다.
- TripMate는 `feature_id`와 snapshot을 `app` schema에 저장하고, 최신 feature 정보는
  krtour-map HTTP API로 batch/read 조회한다.
- krtour-map의 provider raw 변환, feature 적재, dedup, source record, admin/offline
  upload는 krtour-map 저장소 책임이다.
- Geocoding/주소/행정구역은 krtour-map을 경유하지 않고 `kraddr-geo` v2 REST를
  직접 호출한다(`docs/integrations/kraddr-geo.md`, ADR-025).

## 2. 설정

```dotenv
TRIPMATE_KRTOUR_MAP_API_BASE_URL=http://localhost:9011
TRIPMATE_KRTOUR_MAP_ADMIN_BASE_URL=http://localhost:9012
```

krtour-map 쪽 런북에서는 동일 API URL을 `KRTOUR_MAP_API_URL`로 부를 수 있다.
TripMate 설정 prefix는 항상 `TRIPMATE_*`다.

## 3. TripMate/user-facing OpenAPI

최신 `openapi.user.json`의 TripMate 사용 표면:

| 메서드 | 경로 | TripMate 용도 |
|--------|------|---------------|
| `GET` | `/features/in-bounds` | 지도 viewport feature 조회 |
| `GET` | `/features/search` | feature 텍스트 검색 |
| `GET` | `/features/nearby/by-target` | 기준 feature 주변 feature 조회 |
| `GET` | `/features/{feature_id}` | feature 상세 조회 |
| `POST` | `/tripmate/features/batch` | POI/일정 응답 조립용 batch 조회 |
| `POST` | `/admin/feature-update-requests` | feature 갱신 요청 enqueue |
| `GET` | `/admin/feature-update-requests/{request_id}` | 갱신 요청 상태 조회 |

응답 envelope는 krtour-map 계약의 `{data, meta}`를 따른다. TripMate는 이 응답을
자기 API 응답 셰입으로 다시 감싸거나 필요한 필드만 투영할 수 있지만, 원천 필드명
의미를 바꾸지 않는다.

좌표는 전 구간 WGS84 `(lon, lat)`이며 bbox는
`min_lon, min_lat, max_lon, max_lat` 순서다.

## 4. 전체 Admin/ops OpenAPI

최신 `openapi.json`에는 user-facing 표면 외에 다음 운영 표면이 있다. TripMate
Admin이 직접 프록시할 때만 사용하고, 일반 사용자 API에서는 노출하지 않는다.

| 영역 | 대표 경로 |
|------|----------|
| feature update request | `/admin/feature-update-requests`, `/run-now`, `/cancel` |
| dedup review | `/admin/dedup-review` |
| feature 관리 | `/admin/features`, `/admin/features/{feature_id}/deactivate` |
| offline upload | `/admin/offline-uploads/*` |
| POI cache target | `/admin/poi-cache-targets/*` |
| ops/consistency | `/ops/consistency/*`, `/ops/import-jobs`, `/ops/metrics` |
| dagster summary | `/ops/dagster/summary` |
| debug | `/debug/health`, `/debug/version`, `/debug/etl/*`, `/debug/mois-license` |

`docs/tripmate-rest-api.md`의 prose에는 `/version` 언급이 남아 있을 수 있으나,
2026-06-04 최신 OpenAPI에서 확인한 구현 경로는 `/debug/version`이다. 구현과
테스트는 OpenAPI 파일을 우선한다.

## 5. TripMate API 매핑

| TripMate API | krtour-map 호출 | 비고 |
|--------------|----------------|------|
| `GET /features/in-bounds` | `GET /features/in-bounds` | query passthrough 후 TripMate 응답으로 투영 |
| `GET /features/{feature_id}` | `GET /features/{feature_id}` | 상세 화면 |
| `GET /features/nearby` | `GET /features/nearby/by-target` 또는 search/bounds 조합 | 기준 feature가 있을 때 by-target 우선 |
| `GET /search` feature 영역 | `GET /features/search` | 주소 후보는 `kraddr-geo` v2 search |
| `GET /trips/{trip_id}` POI join | `POST /tripmate/features/batch` | `feature_id[]` batch 조회 |
| POI 생성 feature 검증 | `POST /tripmate/features/batch` | 없으면 snapshot fallback 정책 적용 |
| 사용자 feature 갱신 요청 | `POST /admin/feature-update-requests` | Admin/ops 권한 또는 내부 서비스 권한 필요 |

## 6. HTTP client 패턴

```python
class KrtourMapClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def features_batch(self, feature_ids: list[str]) -> dict:
        resp = await self._http.post(
            "/tripmate/features/batch",
            json={"feature_ids": feature_ids},
        )
        resp.raise_for_status()
        return resp.json()
```

- `httpx.AsyncClient`는 FastAPI lifespan에서 1개 생성해 재사용한다.
- 네트워크/5xx/timeout은 TripMate API에서 `503 FEATURE_SERVICE_UNAVAILABLE`로
  매핑한다. POI snapshot fallback이 가능한 read 경로는 degraded 응답을 허용한다.
- krtour-map HTTP client wrapper는 **네트워크 transport** 역할만 한다. provider
  변환/feature 정규화 같은 도메인 wrapper를 만들지 않는다.

## 7. 데이터 저장 정책

- `app.trip_day_pois.feature_id`는 krtour-map `feature_id` 문자열을 저장한다.
  cross-schema FK는 두지 않는다.
- `feature_snapshot`은 POI 생성 시점의 표시 캐시다. 최신 정보는
  `/tripmate/features/batch`로 가져오고, 실패하면 snapshot을 표시한다.
- krtour-map 최신 정보와 snapshot이 달라도 TripMate가 `feature` schema를 직접
  수정하지 않는다. 필요 시 feature update request를 생성한다.

## 8. AI agent 체크리스트

- [ ] 최신 krtour-map `main`의 `openapi.user.json`과 `openapi.json`을 먼저 확인한다.
- [ ] TripMate 설정은 `TRIPMATE_KRTOUR_MAP_API_BASE_URL` /
      `TRIPMATE_KRTOUR_MAP_ADMIN_BASE_URL`만 사용한다.
- [ ] `python-krtour-map` import, `AsyncKrtourMapClient`, `feature` schema ORM/SQL을
      TripMate 사용자 경로에 추가하지 않는다.
- [ ] feature read 구현은 `httpx.MockTransport` 기반 계약 테스트를 먼저 작성한다.
- [ ] OpenAPI 경로가 prose 문서와 충돌하면 OpenAPI 파일을 우선하고 문서 drift를
      양쪽 저장소에 기록한다.
