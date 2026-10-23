# Map transport 상태 연동 (주유소·휴게소·고속도로 돌발·공항) — 설계·실행 계획

> 근거: kor-travel-map ADR-114(소유자 결정 2026-10-23 — PinVi는 transport·weather를 Map REST로만 읽는다),
> PinVi ADR-076(이 문서의 결정 요약). Map 계약은 PinVi #594가 vendor한
> `apps/api/tests/contract/kor-travel-map-openapi-service.json`(Map `e9d0e53c`)의 `/v1/service/transport/*`다.
> 이번 범위는 **transport만**이다. weather는 Map 2단계가 끝난 뒤 별도 작업이다(ADR-068 경로 유지).

## 1. 목표와 범위

소유자 선택: "화면까지".

1. **PinVi API** — Map transport client(기존 `KorTravelMapClient` 관례: service token 헤더, timeout, transient
   재시도, 엄격한 JSON 해석) + web·mobile용 PinVi 엔드포인트. Map이 503이어도 지도·여행 화면은 깨지지 않는다
   (레이어별 `unavailable` 상태로 강등).
2. **Web** — 탐색 지도(`/map`)와 여행 지도(`TripMapView`)에 주유소·휴게소·고속도로 돌발·공항 레이어 토글,
   마커, 상세 대화상자(가격·가격 추이·신선도 "n분 전 갱신").
3. **Mobile** — 지도 화면에 같은 레이어 토글·마커·하단 상세 카드.
4. **테스트** — API 단위·통합(계약 fixture), 계약 게이트(vendored OpenAPI 대비), web 컴포넌트·e2e, mobile
   typecheck/lint.

범위 밖(명시):

- weather(Map 2단계 미완). 기존 `kor-travel-weather` 직접 경로는 그대로 둔다.
- transport 항목을 여행 POI로 **추가**하는 기능. transport `feature_id`는 `make_feature_id` 값이고 Map PG의
  feature UUID(ADR-031·ADR-058의 POI `feature_id`)와 **다른 이름공간**이다. POI·feature 상세·batch 경로에
  넣으면 안 된다(아래 D7).
- 서버 측 캐시. Map이 Valkey에서 읽어 응답이 싸고, 신선도가 이 기능의 핵심이라 PinVi가 한 겹 더 두면
  "n분 전"이 거짓이 된다. web은 기존 지도와 같은 60초 viewport 캐시만 둔다.
- `cursor` 순회(전체 목록). 지도는 viewport 한 페이지(`limit` ≤ 500)와 `truncated`만 쓴다. client는 cursor와
  409(`TRANSPORT_STATE_GENERATION_EXPIRED`) 매핑을 지원하지만 PinVi 엔드포인트로 노출하지 않는다.
- 근처(`lon`·`lat`·`radius_m`) 조회의 PinVi 노출. 여행 지도는 여행 POI에 맞춘 viewport가 곧 "여행 주변"이라
  bbox 하나로 충분하다(YAGNI). client는 Map 계약 그대로 근처 인자를 받는다.

## 2. Map 계약 요약 (vendored service OpenAPI)

| Map 경로                                                         | 쓰는 곳                   |
| ---------------------------------------------------------------- | ------------------------- |
| `GET /v1/service/transport/status`                               | PinVi `/transport/status` |
| `GET /v1/service/transport/{fuel-stations,rest-areas,highway-incidents,airports}` (bbox) | 마커                      |
| `GET /v1/service/transport/{…}/{feature_id}`                     | 상세                      |
| `GET /v1/service/transport/fuel-stations/{feature_id}/price-history` | 가격 추이                 |

- 인증: `require_service_token`(`X-Kor-Travel-Map-Service-Token`). 운영 Map은 토큰을 강제한다. public API key
  fallback은 쓰지 않는다.
- 목록 응답: `data = {items, truncated, freshness}`(휴게소는 `fuel_price_freshness` 추가),
  `meta.page.next_cursor`. 영역 검색은 가까운 순 `limit`건, 한 변 1,000 km 초과면 422.
- 오류: 503 `TRANSPORT_STATE_UNAVAILABLE`(Valkey 미설정·연결 실패)·`TRANSPORT_STATE_NOT_LOADED`(적재 전 — 지금
  주유소가 이 상태), 409 `TRANSPORT_STATE_GENERATION_EXPIRED`(cursor 세대 만료), 404 `NOT_FOUND`, 422 검증.
- 가격 추이: `history.status = available|unavailable` + `reason`(`disabled` 등). 지금은 transport가 추이를
  내보내지 않아 Map이 `disabled`로 준다 — 화면은 "아직 제공되지 않음"으로 보인다.
- 마커 스타일: 항목마다 `marker_icon`(maki)·`marker_color`(P-xx)가 온다. PinVi 팔레트(`resolveMarkerStyle`)가
  그대로 해석한다.

## 3. 결정

### D1. 경계 — Map REST만

PinVi는 transport 데이터를 Map `/v1/service/transport/*`로만 읽는다(Map ADR-114 결정 5). kor-travel-transport를
직접 부르지 않는다. 웹·모바일은 PinVi API만 부른다(외부 API 직접 호출 금지, agent-guide §7.4).

### D2. client — `KorTravelMapClient` 확장, transport 전용 오류 의미

`app/clients/kor_travel_map.py`에 transport 메서드 4개(목록·상세·가격 추이·상태)를 더한다. 새 httpx client를
만들지 않는다(같은 base URL·토큰·API 호출 로깅 hook을 공유).

- 응답은 기존 관례대로 envelope의 `data` dict를 돌려준다(transport-only, ADR-005). PinVi schema 매핑은
  서비스 계층이 한다.
- 오류 매핑은 기존 feature 경로와 **다르다** — 409가 rate limit이 아니라 cursor 만료이고, 503이 일시 장애가
  아니라 "적재 전"일 수 있다:

  | Map 응답                    | client 예외                                       | 재시도   |
  | --------------------------- | ------------------------------------------------- | -------- |
  | timeout·연결 실패           | `KorTravelMapTransportUnavailable(code=None)`     | 기존 횟수 |
  | 5xx(503 `TRANSPORT_STATE_*` 포함) | `KorTravelMapTransportUnavailable(code=<code>)` | **안 함** |
  | 401·403                     | `KorTravelMapTransportUnavailable(code="UPSTREAM_AUTH")` + warning 로그 | 안 함 |
  | 404                         | `KorTravelMapFeatureNotFound`                     | —        |
  | 409                         | `KorTravelMapTransportCursorExpired`              | —        |
  | 그 밖 4xx                   | `KorTravelMapBadRequest(code)`                    | —        |
  | 200인데 JSON·envelope 위반  | `KorTravelMapContractError`                       | —        |

  5xx를 재시도하지 않는 이유: `NOT_LOADED`는 결정적이고 Valkey 장애는 수백 ms 안에 풀리지 않는다. 레이어 4개를
  병렬로 부르는 마커 요청이 0.2+0.4 s 백오프를 4번 기다리게 할 이유가 없다. 다음 지도 이동이 곧 재시도다.
  이를 위해 `_send`에 `retry_server_errors`(기본 `True`) 인자 하나를 더한다 — 기존 호출은 동작이 같다.
- `feature_id`는 Map path 패턴(`^[A-Za-z0-9_-]{1,128}$`)을 PinVi 라우터에서 먼저 검증한다(경로 주입 차단,
  Map에 닿기 전 422).

### D3. 해석 — PinVi 모델 + 계약 게이트

- 서비스 계층이 Map `data`를 PinVi Pydantic 모델로 검증한다. 모델은 **소비하는 필드만** 갖고 추가 필드는
  무시한다(Map의 additive 변경에 깨지지 않음 — 내부 소비자는 계약을 SHA로 핀하지 않는다는 운영 원칙). 검증 실패는
  해당 레이어 `unavailable(UPSTREAM_CONTRACT)`.
- 계약 게이트 `tests/unit/test_kor_travel_map_transport_contract.py`:
  1. client가 보내는 query 집합 ⊆ vendored 경로 선언(그리고 Map 경로 query 집합 exact 핀 — FastAPI가 모르는
     query를 조용히 버리는 무증상 클래스 차단, 기존 게이트와 같은 이유).
  2. PinVi 모델이 소비하는 필드가 vendored schema의 properties에 있고, 모델에서 필수인 필드는 Map에서도
     required다(타입 포함).
  3. 테스트 fixture(Map 응답 예시)가 vendored schema에 맞는다(작은 OpenAPI 부분 검증기 — `$ref`·`anyOf`·
     `type`·`required`·`additionalProperties:false`·`enum`·`const`). fixture가 계약을 흉내만 내는 낡은 대역이
     되는 것을 막는다.

### D4. PinVi 엔드포인트 (`/transport`, 로그인 필요 — `/weather/markers-in-bounds`와 같은 수준)

| PinVi                                                       | 성공 셰입                                                     | 실패                                                    |
| ----------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------- |
| `GET /transport/status`                                     | `{enabled, layers:[{layer, available, reason, freshness}]}`   | **5xx 없음**(Map 장애는 레이어별 `available=false`)     |
| `GET /transport/markers-in-bounds?bbox&zoom&layers&limit`   | `{bbox, zoom, layers:[TransportLayerResult]}`                 | **5xx 없음**(레이어별 `status`)                         |
| `GET /transport/fuel-stations/{id}` 외 3종                  | `{layer, item, freshness, fuel_price_freshness?}`             | 404 `TRANSPORT_FEATURE_NOT_FOUND`, 503 `TRANSPORT_UNAVAILABLE` |
| `GET /transport/fuel-stations/{id}/price-history?product_key&days` | `{feature_id, status, reason, items, truncated, freshness}` | 404, 503(주유소 자체를 못 읽을 때만)                    |

- `layer` 값: `fuel_station`·`rest_area`·`highway_incident`·`airport`(JSON·query). URL path는 Map과 같은 복수
  kebab.
- `TransportLayerResult = {layer, status: ok|unavailable|disabled, reason, freshness, fuel_price_freshness,
  truncated, items}`. `reason`: `NOT_LOADED`·`STORE_UNAVAILABLE`·`UPSTREAM_UNAVAILABLE`·`UPSTREAM_AUTH`·
  `UPSTREAM_CONTRACT`·`DISABLED`.
- 레이어는 `asyncio.gather`로 병렬 호출하고 **각각 독립 강등**한다. 한 레이어 실패가 다른 레이어를 지우지 않는다.
- bbox는 국내 범위(`124 ≤ lon ≤ 132`, `33 ≤ lat ≤ 39`)와 교차해 Map에 보낸다. 넓은 화면의 저배율 viewport가
  Map의 한 변 1,000 km 상한(422)에 걸리지 않게 하고, 교차가 비면 Map을 부르지 않고 `ok`·빈 목록이다.
- `limit` 기본 200, 상한 500(Map 상한). 레이어마다 같은 값.
- 상세 503은 사용자가 연 대화상자 안에서만 보인다(지도·여행 화면 본문은 영향 없음).
- 가격 추이 `days`(1~90, 기본 30)는 PinVi가 `since = now − days`로 바꿔 보낸다. `product_key`는 PinVi 표준
  유종 키(`gasoline` 등)를 받고 Map에는 보내지 않은 채(Map은 오피넷 코드 필터만 있다) 응답을 거른다 — 주유소당
  5유종 × 기본 200행이라 비용이 작다.

### D5. 기능 플래그

`PINVI_KOR_TRAVEL_MAP_TRANSPORT_ENABLED`(기본 `false`, weather marker 플래그와 같은 관례).

- 꺼짐: `/transport/status` → `{enabled:false, layers:[]}`, markers → 요청한 레이어 모두 `disabled`, 상세·추이 →
  503 `TRANSPORT_DISABLED`. **Map을 부르지 않는다.**
- web·mobile은 `/transport/status.enabled`가 `false`면 레이어 컨트롤 자체를 숨긴다 — 꺼진 동안 사용자 경험은
  지금과 같다.

### D6. 표시

- 레이어별 최소 줌(웹·모바일 공용 `@pinvi/domain`): 공항 5, 고속도로 돌발 7, 휴게소 8, 주유소 11. 그 아래에서는
  요청하지 않고 컨트롤에 "확대하면 보여요"를 띄운다(주유소 1.2만 곳이 전국 viewport에 500건 잘려 보이는 것을
  피한다).
- 마커: Map `marker_icon`·`marker_color` → `resolveMarkerStyle`(upstream tier). 웹은 `MakiMarker`, 모바일은
  `vworld-map-rn` `markers`(팔레트 hex).
- 신선도: `source_collected_at ?? loaded_at` 기준 "n분 전 갱신"(1분 미만 "방금", 60분 이상 "n시간 전", 하루 이상
  "n일 전"), `stale=true`면 "오래된 정보" 표시. 계산은 `@pinvi/domain`의 순수 함수.
- 상세 대화상자(웹 `TransportDetailDialog`, 공용 `useModalDialog`): 이름·주소·전화·편의시설, 유종별 현재가
  (판매 안 함은 "판매 안 함"), 휴게소는 휴게소 유가, 돌발은 유형·처리 상태·노선·방향·발생 시각, 공항은 IATA·ICAO.
  주유소는 "가격 추이"를 열면 추이를 부르고, `unavailable`이면 이유와 함께 "아직 제공되지 않음".
- 레이어 상태가 `unavailable`이면 그 토글에 "일시적으로 불러올 수 없음"(Map 장애·적재 전 구분 없이 사용자 문구는
  하나 — 운영 사유는 `data-reason`과 API 로그로).
- 고속도로 돌발은 현재 화면 안의 목록(발생 시각 내림차순)도 컨트롤 패널에 보여 준다 — 지도 없이도(VWorld 키 없는
  CI 포함) 상세를 열 수 있는 경로다.
- 탐색 지도·여행 지도는 같은 훅(`useTransportLayers`)과 컴포넌트를 쓴다. 레이어 on/off는 화면 상태로만 둔다
  (저장하지 않음).

### D7. 이름공간 분리

transport `feature_id`는 PinVi의 feature 상세(`/features/{id}`)·POI 추가·`FeatureDetailModalController`로
흘려보내지 않는다. 웹의 transport 선택 상태는 feature 선택 상태와 별개이고(동시에 두 팝업이 뜨지 않게 서로를
닫는다), 상세는 `/transport/*`만 부른다.

### D8. 모바일

`app/(app)/map.tsx`: 레이어 칩(가로 스크롤), `onCameraChanged`(디바운스) → bbox 요청(react-query, 키는 반올림한
bbox·줌·레이어), `markers`에 transport 마커를 더하고 `onFeaturePress` → 하단 상세 카드(현재가·신선도). 가격
추이는 모바일 1차 범위에서 빼고 "웹에서 보기" 대신 현재가만 보인다(모바일 차트 의존성 추가 회피).

## 4. 배포 전제 (Manager)

- **운영 pinvi-api에 Map service token이 없다.** Manager `docker-compose.yml` pinvi-api 블록은
  `PINVI_KOR_TRAVEL_MAP_SERVICE_TOKEN`을 넘기지 않고, 운영 Map은 `KOR_TRAVEL_MAP_API_SERVICE_TOKEN`을 강제한다
  (`require_service_token`). 그대로 켜면 모든 레이어가 `UPSTREAM_AUTH`로 `unavailable`이다. Manager PR로
  `PINVI_KOR_TRAVEL_MAP_SERVICE_TOKEN: ${KOR_TRAVEL_MAP_API_SERVICE_TOKEN:-}`와
  `PINVI_KOR_TRAVEL_MAP_TRANSPORT_ENABLED`를 pinvi-api 블록에 더해야 한다(이 PR 범위 밖, 머지·배포 안 함).
- 환경변수·OpenAPI 외 DB 변경 없음(Alembic 없음).
- 켜는 순서: ① 운영 Map 이미지에 `/v1/service/transport/*` 포함(지금 e9d0e53c) ② Map Valkey(Manager #544) ③ Map
  `transport_state_*` job 적재(주유소는 transport fuel export가 503이라 아직 `NOT_LOADED`) ④ pinvi-api에 Map
  service token ⑤ `PINVI_KOR_TRAVEL_MAP_TRANSPORT_ENABLED=true` ⑥ 로그인 후 `GET /transport/status`로 레이어별
  `available`·`reason` 확인(`UPSTREAM_AUTH`면 ④, `STORE_UNAVAILABLE`면 ②, `NOT_LOADED`면 ③).

## 5. 테스트

- API 단위: client 오류 매핑·재시도 유무·query 구성(`httpx.MockTransport`), 서비스 강등·bbox 교차·추이 필터.
- API 통합(로그인·라우터): 플래그 off(Map 미호출), 정상, Map 503 레이어 강등, 상세 404/503, 추이 unavailable.
- 계약 게이트(D3).
- `@pinvi/domain` 단위(신선도 문구·줌 게이트·가격 포맷), `@pinvi/schemas` 파싱.
- web Vitest: 컨트롤(상태·줌 안내·돌발 목록)과 상세 대화상자(가격·추이 unavailable·신선도).
- web e2e(`/map`, API mock): status enabled → 컨트롤 표시, disabled → 숨김.
- mobile: `npm run typecheck`·`lint`.

## 6. 진행

- [x] 설계 적대 리뷰 1회 반영
- [x] API client·서비스·라우터·테스트
- [x] packages(schemas·api-client·domain)
- [x] web 컨트롤·마커·상세 + 테스트
- [x] mobile
- [x] 문서(ADR-076, `docs/api/transport.md`, `kor-travel-map-rest-api.md` 현황, journal·resume·tasks, `.env.example`)
- [x] 코드 적대 리뷰 2회 반영
- [ ] PR, CI green

## 7. 설계 적대 리뷰 반영 (2026-10-23, 1회)

리뷰 결과를 아래처럼 반영했다. 본문 D1~D8과 충돌하면 이 절이 우선한다.

- **P0 공유 여행 화면** — `SharedTripView`도 `TripMapView`를 쓰고 비로그인이다. `/transport/*`는 로그인 필요라
  401 → `/login` 이동이 난다. → `TripMapView`에 `transportLayers` prop(기본 꺼짐)을 두고 로그인 여행 상세
  (`TripDetail`)에서만 켠다. 공유 화면은 훅을 실행하지 않는다(e2e로 "공유 화면은 `/transport/*`를 부르지 않는다"
  단언).
- **P0 배포 순서** — §4에 Map 쪽 전제(이미지에 `/v1/service/transport` 포함·Valkey·`transport_state_*` 적재)부터
  플래그까지의 순서를 적는다. 운영 확인은 `/transport/status`.
- **P1 목록·상태의 4xx** — 목록·상태 서비스는 `KorTravelMapError`를 전부 잡아 레이어 `unavailable`로 내린다.
  reason에 `UPSTREAM_REJECTED`(Map 404·422·409 등 4xx)를 더한다.
- **P1 지연** — transport 읽기는 **재시도 0회**(timeout·연결 실패 포함, `_send(max_attempts=1)`)이고 마커·상태는
  레이어별 3초 기한(`asyncio.wait_for`)을 둔다. 기한을 넘긴 레이어만 `unavailable(UPSTREAM_UNAVAILABLE)`.
- **P1 상태 매핑** — Map `/status`는 Valkey 장애 시 503이다 → `enabled:true` + 레이어 전부 `unavailable`.
  `transport.rest_area_fuel_prices`는 레이어가 아니므로 무시한다. Map `error` 문자열은 넘기지 않고 enum reason만 쓴다.
- **P1 신선도 시계** — 나이는 기기 시계와 타임스탬프 차가 아니라 **Map `age_seconds` + 응답을 받은 뒤 흐른 시간**
  으로 계산하고 음수는 0으로 고정한다. 오래됨 판정은 Map `stale`만 쓴다(캐시를 거쳐도 받은 시각을 함께 둔다).
- **P1 모바일 마커 id** — transport 마커 id는 `transport:<layer>:<feature_id>`, press 핸들러가 접두로 가른다(순수
  함수 + domain 단위 테스트).
- **P1 since·유종** — `since`는 KST aware(`kst_now()`, SKILL.md DO NOT 10)로 만들고 httpx `params`가 인코딩한다
  (테스트 고정). `product_key`는 PinVi enum으로 하드코딩하지 않고 응답 값으로 거른다 — 모르는 키는 빈 목록.
- **P2 truncated** — Map 영역 검색은 상자 중심에서 가까운 순으로 자른 뒤 사각형 밖을 거른다. `truncated`면 "일부만
  표시 — 확대하세요"를 띄우고 개수로 완전성을 추론하지 않는다. 돌발 목록은 `occurred_at` 내림차순, null은 뒤.
- **P2 이름공간 근거** — Map PG feature_id는 rev 309 이후 UUID다(리뷰가 본 옛 체크아웃은 `f_…` 형식). transport
  `feature_id`는 `make_feature_id` 문자열이다. 형식이 달라도 상태·컴포넌트를 분리해 섞지 않는다(D7 유지).
- **P2 coord null** — 마커 변환에서 좌표 없는 항목은 뺀다(목록·상세에는 보인다).
- **P2 계약 게이트** — 저장소에 `jsonschema`가 없다. 부분 검증기는 fixture가 쓰는 구성(`$ref`·`anyOf`·`type`·
  `required`·`additionalProperties`·`enum`·`const`)만 다루는 테스트 내부 함수로 둔다.
- **P2 문서·모바일** — `docs/api/README.md` 색인에 `transport.md`를 더한다. 모바일은 현재가만 보이고 웹 링크는 두지
  않는다. 신선도·줌 게이트·마커 id는 `@pinvi/domain` 단위 테스트가 웹·모바일 공용으로 덮는다.
- **P2 reason 노출** — 로그인 사용자에게 enum reason(`NOT_LOADED` 등)만 노출하고 Map 원문 메시지는 넘기지 않는다
  (ADR-076에 의도로 적는다).

## 8. 구현 중 바뀐 것

- D2의 "transport 메서드를 `kor_travel_map.py`에" → **별도 모듈 `app/clients/kor_travel_map_transport.py`**. 기존 Map 계약 게이트
  (`test_kor_travel_map_contract.py`)가 client 모듈의 `"/v1/..."` 리터럴을 user 계약 표와 양방향으로 묶어서, transport 경로를
  거기 넣으면 그 게이트의 표·probe 전부를 transport로 넓혀야 했다. 별도 모듈은 같은 연결(`KorTravelMapClient` 인스턴스)을 감싸
  쓰고, 자기 게이트(`test_kor_travel_map_transport_contract.py`)가 경로 리터럴을 vendored transport 경로와 양방향으로 묶는다.

## 9. 코드 적대 리뷰 2회 반영 (2026-10-23)

리뷰 A(API)·B(web/mobile) 각 1회. P0 없음.

- **API**: 범위 밖 bbox가 `BBox` 검증 오류로 500이 되던 경로 → transport 라우터 전용 파서가 국내 범위로 clamp(비숫자만 400).
  `httpx.DecodingError` 등 `TransportError`가 아닌 httpx 오류도 `unavailable`로. service token이 비어 있으면 Map을 부르지 않고
  `UPSTREAM_AUTH`. route 404(옛 Map)는 "항목 없음"이 아니라 `UPSTREAM_REJECTED`. 시각 필드는 `AwareDatetime`(naive 거부).
  상태 freshness 하나·목록 항목 하나가 깨져도 그 레이어/항목만 강등. 가격 추이 `reason`은 Map enum만(모르면
  `upstream_contract`), 응답 `feature_id` 대조. 계약 게이트: 실제로 나간 query를 MockTransport로 기록, 필드 JSON 타입 포함
  대조(Map ⊆ PinVi) + 그 대조가 빨개지는지 자기 검사, 데이터셋 이름은 Map 소스 기준 핀(OpenAPI상 자유 문자열).
- **web**: 요청 실패 시 요청한 레이어를 "불러올 수 없음"으로 표시, 꺼져 있으면 30초 tick 없음, 콜백 identity 고정, 토글 시
  디바운스 취소, 선택 마커 강조, 컨트롤 터치 타깃 44px·`text-sm`, 가격 추이는 최근 순 정렬 후 자름.
- **mobile**: 카드 신선도는 카드를 연 시각 기준, `keepPreviousData`·abort signal·레이어당 limit 100, 국내 밖이면 요청 안 함,
  선택은 id로 들고 현재 결과에서 다시 찾음(레이어를 끄면 카드 닫힘).
- 남긴 것: e2e로 마커 데이터 흐름(`/transport/markers-in-bounds` → legend)을 보려면 지도 `onLoad`가 필요한데 CI에는 VWorld 키가
  없다(기존 지도 e2e와 같은 제약). 응답 해석은 `packages/schemas` 단위 테스트(UTC `Z`·null), 표시는 Vitest 컴포넌트 테스트가
  덮는다. lax 모드 강제 변환(`strict=True`)과 PinVi 쪽 rate limit 추가는 범위 밖으로 둔다(기존 전역 rate limit 미들웨어가 적용).
