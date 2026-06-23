# geocoding 열린 결정 (사용자 판단 대기)

본 문서는 Pinvi geocoding(`kor-travel-geo` v2 REST 직접 호출, ADR-025) 설계에서
**사용자 의사결정이 필요한 열린 항목**을 모은다. 각 항목은 현재 잠정값(에이전트가
"가장 적절한 방향"으로 둔 기본값)과 선택지, 영향, 추천을 적는다. 결정되면 해당
항목을 ADR(또는 ADR-025 amendment)로 박고 본 문서에서 "결정됨"으로 표시한다.

> 작성 기준(사용자 지시): "의사결정이 필요한 부분은 문서로 따로 남길 것." 즉
> 구현을 막지 않도록 **잠정 기본값으로 진행**하되, 되돌리기 비용이 있는 선택은
> 여기서 가시화한다.

## D1. `regions.md`의 기존 endpoint를 어떻게 처리할 것인가

- **맥락**: 기존 `docs/api/regions.md`는 `GET /regions/covering-point`,
  `GET /regions/within-radius`를 kor-travel-map 함수 경유로 정의했다. ADR-025는
  geocoding/region을 kor-travel-geo v2 직접으로 옮겼고, 최신 kor-travel-geo에는
  `/v2/regions/within-radius`가 있다.
- **선택지**:
  - (A) `/regions/*`를 **유지하되 내부 구현만** kor-travel-geo v2(`/v2/reverse`
    `include_region`, `/v2/search?type=district`)로 교체. 기존 응답 셰입 보존.
  - (B) `/regions/*`를 폐기하고 `/geo/*`로 일원화(응답 셰입도 candidate 기반).
  - (C) 둘 다 유지(중복).
- **잠정 기본값**: **(A)** — endpoint 경로/응답 셰입은 유지(프론트 영향 최소),
  내부만 v2로. `within-radius`는 kor-travel-geo `/v2/regions/within-radius`로 래핑.
- **추천**: (A). v0.1.0에서 경로 안정성 우선. v1.0에서 (B) 재검토.

## D2. `fallback="api"` (외부 VWorld/juso fallback) 사용 여부

- **맥락**: v2 geocode/reverse는 `fallback="api"`로 kor-travel-geo가 외부 API
  (vworld/juso)까지 조회하게 할 수 있다. 비용·약관·한도·캐시·출처표기가 얽힘.
- **선택지**: (A) 항상 `none`(로컬 PostGIS만) / (B) 검색 실패 시에만 `api` /
  (C) 항상 `api`.
- **잠정 기본값**: **(A) `none`**. 로컬 도로명주소 전자지도로 대부분 커버되고,
  외부 호출은 비용·약관 리스크.
- **추천**: (A)로 출시 → 로컬 miss율 모니터링 후 (B) 검토. (B/C)는 kor-travel-geo
  서비스의 키/한도 정책과 함께 별도 ADR.

## D3. 캐싱 계층

- **맥락**: 자동완성(`/geo/search`)은 호출량이 많다.
- **선택지**: (A) 캐시 없음 / (B) in-process TTL(LRU, 단일 노드) / (C) Redis.
- **잠정 기본값**: **(B) in-process TTL 60s** + 클라이언트 디바운스 250ms. Odroid
  단일 노드(현 단계)에 충분.
- **추천**: (B)로 시작. Sprint 5 실시간/다중 워커 진입 시 (C) 재검토(WebSocket
  broker와 함께).

## D4. reverse 좌표 캐시 키 quantize 자릿수

- **맥락**: 역지오코딩 캐시 키를 좌표 그대로 쓰면 키가 폭증한다.
- **잠정 기본값**: 소수 **5자리**(~1.1m) quantize. (kor-travel-map 감사 체인은 6자리
  저장, 캐시는 더 거칠어도 됨.)
- **추천**: 5자리. region label 용도엔 충분, 키 수 통제.

## D5. `within-radius`(반경 내 행정구역) 대응

- **맥락**: 기존 `/regions/within-radius`는 "좌표 반경 내 여러 행정구역"을 준다.
  최신 `kor-travel-geo` v2에는 `POST /v2/regions/within-radius`가 추가됐다.
- **결정됨**: Pinvi `/regions/within-radius`는 endpoint 경로/응답 envelope을 유지하고,
  내부에서 `kor-travel-geo` `POST /v2/regions/within-radius`를 래핑한다.
- **영향**: 별도 PostGIS 공간 쿼리나 `kor-travel-map` 경유를 Pinvi에 두지 않는다. 후보 정렬과
  거리/신뢰도 계산은 `kor-travel-geo` 응답을 그대로 따른다.

## D6. geocoding의 MCP 외부 노출 (ADR-019 연계)

- **맥락**: Sprint 6 MCP 외부 인터페이스(ADR-019)에 geocoding tool(주소검색/역지오)
  을 넣을지.
- **잠정 기본값**: **미포함**(v1.0). MCP는 trip/feature read 우선.
- **추천**: v1.1에서 `search_address` tool 검토. 좌표 입력 tool은 위치 감사·약관
  검토 필요.

## D7. 네트워크 · 인증 모델 (Pinvi ↔ kor-travel-geo REST)

- **맥락**: v2 REST 호출의 신뢰 경계.
- **결정됨 (ADR-048)**: 기본 네트워크 경계는 같은 docker network 내부 호출
  (`http://kor-travel-geo:12501`)을 유지하되, `kor-travel-geo` v2 공개 REST 계약에 맞춰
  Pinvi가 모든 v2 POST에 `key=<PINVI_VWORLD_API_KEY>` query를 붙인다.
- **key 소유**: 별도 `PINVI_KOR_TRAVEL_GEO_API_KEY`는 두지 않는다. 운영자는
  `PINVI_VWORLD_API_KEY`와 `kor-travel-geo`의 `KTG_VWORLD_API_KEY`를 같은 값으로 설정하고,
  공개 API key hash 저장/폐기/검증은 `kor-travel-geo`가 소유한다.
- **로그 원칙**: Pinvi는 key 원본이나 query 포함 upstream URL을 로그에 남기지 않는다.
  외부 노출·cross-host 배치가 필요하면 mTLS/서비스 토큰 여부를 별도 ADR로 재검토한다.

## D8. v2 `point_precision` / `match_kind` 활용 깊이

- **맥락**: v2 후보는 `point_precision`(exact/interpolated/centroid/approximate),
  `match_kind`(road/parcel/region/sppn/...)를 준다.
- **잠정 기본값**: region label·검색에선 `sppn` 제외 + 최근접/최고 score 1건 선택.
  precision은 UI에 노출 안 함(내부 정렬 보조).
- **추천**: 출시 후 "정확도 낮음" 배지 등 UX 필요 시 precision 노출 검토.

## 결정 로그

| ID | 상태 | 결정/ADR |
|----|------|----------|
| D1 | open (잠정 A) | — |
| D2 | open (잠정 none) | — |
| D3 | open (잠정 in-proc TTL) | — |
| D4 | open (잠정 5자리) | — |
| D5 | decided | `POST /v2/regions/within-radius` 래핑 |
| D6 | open (잠정 미포함) | — |
| D7 | decided | ADR-048 |
| D8 | open (잠정 최소 활용) | — |

## 관련 문서

- `docs/decisions.md` ADR-025 — geocoding은 kor-travel-geo v2 REST 직접.
- `docs/integrations/kor-travel-geo.md` — v2 통합 계약(본 결정들의 잠정값 반영).
- `docs/api/regions.md` — region endpoint (D1/D5 대상).
- ADR-019 — MCP 외부 인터페이스 (D6 연계).
