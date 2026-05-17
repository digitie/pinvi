# Provider Library 직접 사용 및 인터페이스 안정화 기준

이 문서는 TripMate가 외부 공공/민간 데이터 라이브러리를 사용하는 기준이다. 핵심 원칙은 명확하다. TripMate 안에 provider별 adapter, gateway, wrapper 계층을 새로 만들지 않는다. 라이브러리 공개 클라이언트와 typed model을 직접 사용하고, 부족한 인터페이스는 해당 라이브러리에서 빠르게 안정화한다. 기존 호출부가 새 provider 계약과 맞지 않으면 adapter/wrapper로 감싸지 말고 관련 코드를 직접 수정한다.

## 절대 원칙

- TripMate backend에는 `KtoAdapter`, `KmaGateway`, `ProviderWrapper` 같은 중간 계층을 만들지 않는다.
- ETL 파일은 provider 호출을 감추는 wrapper가 아니라, 라이브러리 typed model을 TripMate DB row로 저장하는 loader/source 경계만 담당한다.
- adapter/wrapper 증식은 코드 흐름을 우회시키고 직관성과 유지보수성을 떨어뜨리므로 절대 지양한다.
- 수정량을 줄여야 할 때는 앱 내부에 새 우회 계층을 만들지 않고 `python-*-api`의 endpoint, typed model, pagination, cursor, 오류 모델을 먼저 안정화한다.
- endpoint, pagination, 오류 분류, metadata, raw payload, 증분 cursor가 부족하면 TripMate에 임시 wrapper를 늘리지 않고 해당 `python-*-api` 라이브러리에 upstream한다.
- old name 호환 alias는 같은 변경 안에서 제거한다. 장기 호환 wrapper를 남기면 코드 흐름이 두 갈래가 되어 유지보수가 어려워진다.
- 빠른 안정화를 위해 공개 함수명, typed model, provider metadata, raw payload 보존 규칙, exception 계층을 라이브러리 쪽에서 먼저 고정한다.

## 로컬 라이브러리 기준

`F:\dev` 아래 실제 디렉터리와 README/pyproject를 확인한 기준이다.

| 라이브러리 | import | TripMate 역할 |
| --- | --- | --- |
| `python-kraddr-base` | `kraddr.base` | POI category, map feature type, 주소/좌표 DTO, 법정동/도로명 코드, KMA/KATEC/AirKorea 좌표 값 객체 같은 공통 타입 |
| `python-kraddr-geo` | `kraddr.geo` | Juso 검색 API, 도로명주소 TXT 파싱/적재, PostGIS 기반 주소점/경계 조회 |
| `python-vworld-api` | `vworld` | VWorld 검색, geocoder, 2D GetFeature, WMS/WFS/WMTS/TMS, 법정경계/공간 조회 보강 |
| `python-krmois-api` | `mois` | 행안부 지방행정 인허가 195개 업종 OpenAPI/파일 다운로드, EPSG:5174 좌표 변환, 인허가 feature의 1차 원천 |
| `python-visitkorea-api` | `visitkorea` | KTO `KorService2`, `TourApiHubClient`, 행사/관광/숙박/상세/이미지/동기화 조회, 축제 event 증분 업데이트 |
| `python-mcst-api` | `mcst` | 문화체육관광부/산하기관의 여행, 여가, 숙박, 문화시설, 도서관 위치/운영 정보 보강 |
| `python-krforest-api` | `krforest` | 숲길, 둘레길, 백두대간, 명산, 산악날씨, 휴양림, 국립공원/산림 공간자료와 안전 데이터 |
| `python-opinet-api` | `opinet` | 주유소/충전소 가격, KATEC/WGS84 좌표 변환, 제품/상표/정렬 코드와 예외 매핑 |
| `python-krex-api` | `krex`, `kex_openapi` | 한국도로공사 교통량, 실시간 소통, 통행료, 영업소, 휴게소, 휴게소별 날씨 |
| `python-kma-api` | `kma` | KMA 초단기실황/초단기예보/단기예보, 중기/특보 data.go.kr 호출, APIHub, DFS 격자 변환 |
| `python-krairport-api` | `krairport` | KAC/IIAC 공항 운항, 주차, 혼잡도, 시설, 공항 메타데이터, 공항/세계 날씨 |
| `python-khoa-api` | `khoa` | 국립해양조사원 ODMI 해양/해수욕장/관측소/해양지수 데이터 |
| `python-airkorea-api` | `airkorea` | AirKorea 측정소, 예보통보, 시도 실시간 측정값, 대기질 등급/오염물질 값 |

주의: 로컬 `python-krmois-api` 디렉터리의 현재 pyproject 이름은 `python-mois-api`이고 import 이름은 `mois`다. TripMate 문서와 provider 명명은 사용자 지정 기준인 `python-krmois-api`를 사용하되, 배포 패키지명 정합성은 라이브러리 쪽에서 후속으로 맞춘다.

## Feature DB 적재 기준

기본 feature 위치 체계는 `python-kraddr-geo`와 `python-vworld-api`가 제공하는 주소/좌표/경계 정보다. 이 데이터는 feature 자체의 주 원천이라기보다 `map_feature_source_links.source_role = 'base_address'` 또는 `base_coordinate`로 연결한다.

실질적으로 `map_features`에 올라가는 1차 영업/장소 정보는 `python-krmois-api` 인허가 데이터부터 시작한다. KRMOIS에 없는 정보이거나 보완이 필요한 정보는 provider별 public client를 직접 호출해 `source_records`, `map_feature_source_links`, `map_feature_overrides`에 남긴다.

- 축제: KRMOIS에 없으므로 `python-visitkorea-api`의 행사/축제와 동기화 API를 직접 사용해 `feature_type='event'`와 `event_details` 후보로 저장한다. 증분 cursor는 `provider_sync_state(provider='visitkorea', dataset_key='event')`에 둔다.
- 카페/독립서점: `python-mcst-api` 결과는 KRMOIS 인허가 feature와 중복될 가능성이 높으므로 신규 feature보다 보강/수정이 기본이다. KRMOIS 값을 손보면 `map_feature_overrides`에 provider, field_path, source_value, override_value, reason, status를 남겨 admin에서 구분한다.
- 해수욕장: KRMOIS에 없으면 `python-khoa-api` 해수욕장/관측소 데이터를 사용해 `place` 또는 polygon이 있는 경우 `area`로 추가한다.
- 휴양림: `python-krforest-api` 휴양림 정보는 KRMOIS feature가 있으면 보강하고, 없으면 `place` 또는 `area` 후보로 추가한다.
- 트래킹/둘레길/국립공원: `python-krforest-api`는 `area`, `route` 비중이 높다. 선형 geometry가 있으면 `route_details`, 구역 geometry가 있으면 `area_details`를 우선 사용한다.

## Weather 병합 기준

날씨/환경 정보는 KMA의 시간축과 예보 스타일을 기준으로 병합한다. KMA 초단기실황, 초단기예보, 단기예보, 중기예보를 `forecast_style = nowcast | ultra_short | short | mid` 기준으로 세우고, 다른 provider 데이터는 같은 feature/time window에 끼워 넣는다.

| source | `weather_domain` | 병합 위치 |
| --- | --- | --- |
| `python-kma-api` | `kma_ultra_short_nowcast`, `kma_ultra_short_forecast`, `kma_short_forecast`, `kma_mid_forecast` | 전체 weather timeline의 기준 |
| `python-krex-api` | `rest_area_weather` | 휴게소 feature의 observed/short context |
| `python-krairport-api` | `airport_weather` | 공항 feature의 observed/forecast context |
| `python-visitkorea-api` | `tourist_spot_weather` | 관광지 feature의 보강 날씨 |
| `python-airkorea-api` | `air_quality` | feature 주변 측정소/시도 대기질 |
| `python-khoa-api` | `beach_marine` | 해수욕장/해양 feature의 파고, 수온, 조석, 해양지수 |

정규화 값은 `map_feature_weather_values`에 저장한다. provider 원문은 `source_records.raw_data`와 `map_feature_weather_values.payload`에 보존하고, feature와의 원천 연결은 `map_feature_source_links.source_role = 'weather_context'`로 남긴다.

## DB 계약

2026-05-16 기준 TripMate 코드에는 다음 보강 테이블/컬럼을 둔다.

- `map_feature_source_links.source_role`: 주소 기반, 좌표 기반, 1차 원천, 보강, 보정, 중복 후보, media, weather context를 구분한다.
- `map_feature_overrides`: KRMOIS 등 1차 원천 값을 수정/보강한 이력을 admin에서 검토할 수 있게 저장한다.
- `map_feature_weather_values`: KMA 스타일 forecast/observed timeline 안에 휴게소, 공항, 관광지, 대기질, 해수욕장 해양 값을 같이 넣는다.
- `provider_sync_state`: VisitKorea 행사 증분, MCST 보강, KRForest/KHOA 주기 수집처럼 provider별 cursor와 실패 상태를 저장한다.

이 DB 계약은 adapter/wrapper 존재를 전제로 하지 않는다. 각 ETL은 라이브러리 공개 client를 직접 만들고, 반환된 typed model을 위 테이블에 저장한다.
