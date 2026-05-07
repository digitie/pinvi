# 데이터 소스 기준

이 문서는 TripMate에서 사용하는 외부 데이터 소스, 저장 계층, 캐시 정책의 단일 기준 문서다.
Airflow DAG, 백엔드 adapter, DB schema, 테스트는 이 문서를 기준으로 구현한다.

현재 주소/Juso/법정동코드/VWorld 경계 DB 스키마의 상세 구조는 `docs/architecture/address-schema.md`를 따른다.

## 1. 공통 원칙

- 대한민국 데이터만 처리한다.
- 외부 데이터는 `raw`와 `serving(normalized)` 레이어로 분리한다.
- `raw`는 원본 재처리, 감사, diff 검증을 위한 적재본이다.
- `serving`은 앱/API/지도 조회용 정규화 데이터다.
- 서비스 로직과 UI는 `raw`를 직접 단일 진실원으로 사용하지 않는다.
- 동일 `region + time window` 데이터가 있으면 외부 API를 반복 호출하지 않는다.
- 외부 API 호출은 adapter/gateway 계층 뒤에서만 수행한다.
- 모든 adapter는 timeout, retry, rate limit, stale-cache fallback을 고려한다.
- 행정구역 기반 aggregation을 기본으로 사용한다. “반경 nkm”은 정확한 원형 거리 검색이 아니라 행정구역 기반 근사다.
- 제공자 약관이 불명확한 필드는 장기 저장하지 않고 “법무/정책 확인 필요”로 표시한다.
- 앱 내 모든 주소 관리는 주소기반산업지원서비스의 도로명주소 한글 전체분 TXT를 기준으로 한다.
- 주소 기준 key는 `legal_dong_code`, `road_name_code`, `administrative_dong_code`, `road_address_management_no`다.
- 주소 기준 key는 모두 문자열로 저장한다. 선행 0 손실을 막기 위해 숫자 타입으로 저장하지 않는다.

## 2. 열린 결정/보완 항목

상태 값:

- 부분 반영: 일부는 코드/문서에 반영됐고, 남은 설계 항목이 있다.
- 보완 필요: 구현 전에 필드, endpoint, 저장 범위, 검증 기준을 더 좁혀야 한다.

확정된 정책은 DS 목록에서 제외하고 각 데이터셋 섹션에 기준으로 남긴다.

| ID | 주제 | 상태 | 결정/다음 행동 |
| --- | --- | --- | --- |
| DS-009 | KTO `KorService2` 표시/저작권/호출 한도 | 부분 반영 | KTO 후보 조회와 전체 return field 저장은 확정됐다. 남은 것은 HTML sanitization, `cpyrhtDivCd`별 출처 표기, 실제 계정 기준 호출 한도 확인이다. |
| DS-010 | `TarRlteTarService1` 연관관광지 활용 범위 | 보완 필요 | 연관관광지 정보를 사용자 UI 추천으로 노출할지, 내부 랭킹 신호로만 쓸지 결정한다. |
| DS-011 | `TarRlteTarService1` 기준월 `baseYm` 관리 | 보완 필요 | 최신 기준월을 자동 탐색할지, 운영 설정값으로 둘지, 수동 갱신할지 결정한다. |
| DS-012 | Naver Search UI/TTL/query 정책 | 부분 반영 | Local/Blog/News/Encyclopedia/Web 활용은 확정됐다. 남은 것은 endpoint별 UI 노출 범위, TTL, 출처 표기, query 템플릿이다. |
| DS-013 | Kakao/Naver/Google provider cache 세부값 | 부분 반영 | 상호명·주소·전화번호 같은 안정 필드는 지속 저장하고, 리뷰는 3개월 저장 후 ETL로 정리한다. 남은 것은 provider별 raw cache TTL과 stale 표시 문구의 세부값이다. |

## 3. 데이터 카탈로그

| 카테고리 | 데이터셋 | 주 용도 | 상태 |
| --- | --- | --- | --- |
| weather | `weather_short_term` | 현재/초단기/단기 예보 | 계획 |
| weather | `weather_mid_term` | 5~11일 예보 | 계획 |
| weather | `weather_observed` | 과거 날씨 근사 | 보류 |
| weather | `weather_rest_area` | 휴게소별 날씨 | 확정: 휴게소 master와 매칭하지 않음 |
| fuel | `fuel_avg_price` | 지역 평균 유가 | 계획 |
| fuel | `fuel_lowest_station` | 지역 최저가 주유소 후보 | 계획 |
| fuel | `fuel_region_code` | OpiNet 유가 지역 코드 기준 | 계획 |
| region | `administrative_boundary` | 시군구 point-in-polygon, 지역 aggregation | 확정 |
| address | `juso_road_address_korean` | 도로명주소 한글 전체분, 앱 주소 기준 테이블 | 확정 |
| address | `juso_related_jibun` | 도로명주소관리번호별 관련 지번 | 확정 |
| address_code | `legal_dong_code_standard` | data.go.kr `국토교통부_전국 법정동` 기반 10자리 행정구역 코드 기준 | 확정 |
| address_code | `juso_address_code_standard` | Juso 주소 기준 key 중 법정동코드 보조 보강 | 확정 |
| rest_area | `rest_area_master` | 휴게소 기본정보 | 계획 |
| rest_area | `rest_area_oil_price` | 휴게소 주유소 가격/업체 | 계획 |
| rest_area | `rest_area_svcs` | 휴게소 편의시설 | 계획 |
| tour_point | `kma_recommended_tour_course` | 관광코스/관광지 후보 | 부분 반영 |
| tour_point | `kto_kor_tour_content` | 한국관광공사 국문 관광정보 원천 | 부분 반영 |
| tour_point | `kto_related_tour_point` | 관광지별 연관 관광지 후보 | 보완 필요 |
| tour_code | `kto_tour_region_code` | KTO 지역/시군구 코드 기준 | 보완 필요 |
| tour_code | `kto_tour_legal_dong_code` | TourAPI 법정동코드조회 API cache | 확정 |
| tour_code | `kto_tour_category_code` | KTO 관광타입/분류체계 코드 기준 | 확정 |
| place | `place_provider_cache` | 장소 검색 후보 TTL cache | 계획 |
| place | `kakao_local_place_search` | Kakao Local 장소/주소/좌표 후보 TTL cache | 계획 |
| place_reference | `naver_search_local_reference` | Naver Local 보조 장소 후보 TTL cache | 부분 반영 |
| place_reference | `naver_search_blog_reference` | Naver Blog 참고 링크 TTL cache | 부분 반영 |
| place_reference | `naver_search_news_reference` | Naver News 참고 링크 TTL cache | 부분 반영 |
| place_reference | `naver_search_encyclopedia_reference` | Naver Encyclopedia 참고 링크 TTL cache | 부분 반영 |
| place_reference | `naver_search_web_reference` | Naver Web 참고 링크 TTL cache | 부분 반영 |
| place_enrichment | Gemini place enrichment | LLM 생성 보강 정보 | 보류, 상세는 `docs/integrations/gemini.md` |

## 4. Weather

기상청과 한국도로공사 등 저장 정책이 정리된 소스를 활용해 전국 날씨 정보를 제공한다.

### 4.1 `weather_short_term`

목적:

- 현재 날씨, 초단기, 48시간 예보
- 여행 장소 주변 날씨 요약

출처:

- data.go.kr / 기상청 단기예보 조회서비스
- https://www.data.go.kr/data/15084084/openapi.do

수집:

- 방식: OpenAPI
- 갱신 주기: 30분
- freshness target: 60분 이내

특징:

- 5km 격자 기반
- 장소 좌표 또는 행정구역 중심 좌표를 기상청 `nx`, `ny`로 변환해야 한다.
- 백엔드 변환 유틸: `apps/api/app/geospatial/kma_grid.py`
- 변환식 기준: KMA DFS Lambert Conformal Conic 격자. 구현 검증값은 https://gist.github.com/fronteer-kr/14d7f779d52a21ac2f16 을 참고한다.

저장:

- `weather_raw_short_term`
- `weather_serving_short_term`

권장 key:

- raw: provider, endpoint, base_date, base_time, nx, ny, response_hash
- serving: nx, ny, forecast_at, category

매핑 정책:

- 장소 좌표가 있으면 장소 좌표를 KMA DFS `nx`, `ny`로 직접 변환한다.
- 장소 좌표가 없거나 행정구역 단위 조회가 필요하면 법정동 경계 기반 대표점을 사용한다.
- 법정동 대표점은 `region_serving_legal_dong_boundary`의 polygon에서 `ST_PointOnSurface`로 계산한다. `ST_Centroid`는 polygon 밖 점이 나올 수 있으므로 기본값으로 쓰지 않는다.
- 장소 저장 시 `좌표 → 법정동 point-in-polygon → 좌표 직접 DFS 변환`을 수행하고, 필요한 경우 법정동 mapping table을 fallback으로 참조한다.
- 동일 `nx + ny + base_date + base_time` 조합은 캐시를 우선 사용하고 API를 반복 호출하지 않는다.

mapping table:

- `weather_short_term_grid_mapping`
- `region_code_type`: `legal_dong`, `administrative_dong`, `sigungu`
- `region_code`
- `representative_lon`
- `representative_lat`
- `nx`
- `ny`
- `mapping_method`: `point_on_surface`, `centroid`, `manual_override`
- `source_boundary_version`
- `updated_at`

category code 정책:

- 기상청 category code 원본은 raw와 serving에 보존한다.
- 앱 표시용 정규화 enum/name은 별도 mapping으로 관리한다.
- 미확인 category code는 저장을 막지 않고 `unknown`으로 표시하며 schema drift 로그를 남긴다.

### 4.2 `weather_mid_term`

목적:

- 5~11일 예보
- 여행 일주일 전 요약 알림

출처:

- data.go.kr / 기상청 중기예보 조회서비스
- https://www.data.go.kr/data/15059468/openapi.do

수집:

- 방식: OpenAPI
- 갱신 주기: 12시간
- freshness target: 24시간 이내

저장:

- `weather_raw_mid`
- `weather_serving_mid`

권장 key:

- raw: provider, endpoint, tm_fc, reg_id, response_hash
- serving: reg_id, forecast_date, forecast_slot

매핑 정책:

- 중기예보 `reg_id`는 단기예보 `nx`, `ny`와 별도의 권역 코드로 관리한다.
- 중기 육상예보 권역 코드와 중기 기온예보 지역 코드는 동일하다고 가정하지 않고 분리 관리한다.
- 장소 좌표는 먼저 법정동 경계 point-in-polygon으로 법정동 코드를 찾고, 법정동 코드에서 시군구 코드를 도출한 뒤 중기예보 mapping을 적용한다.
- 임의의 `reg_id`를 억지로 붙이지 않는다. fallback을 사용하면 API/알림/UI에 fallback 사용 여부와 기준 지역을 남긴다.

mapping table:

- `kma_mid_land_region_mapping`
- `kma_mid_temperature_region_mapping`
- `sigungu_code`
- `sido_code`
- `legal_dong_code_prefix`
- `reg_id`
- `mapping_method`: `exact`, `parent_region`, `nearest_representative`, `manual`
- `priority`
- `valid_from`
- `source_version`
- `updated_at`

fallback 순서:

1. 시군구 exact mapping
2. 시도/권역 parent mapping
3. 공식 코드표상 가장 가까운 대표 지역 또는 수동 검증 mapping
4. 제공 불가 처리

serving 추가 필드:

- `source_region_code`
- `mapping_method`
- `fallback_used`
- `fallback_reason`

### 4.3 `weather_observed` (근사)

목적:

- “어제 오전/오후 날씨” 같은 참고용 과거 날씨

정책:

- 정확한 과거 실황은 보장하지 않는다.
- UI/API에 근사라고 표시한다.
- 필요 시 AWS/ASOS 관측 데이터 연동을 별도 결정한다.

현재 상태:

- 보류. 구현 전 추가 데이터 소스와 품질 기준 결정 필요.

### 4.4 `weather_rest_area`

목적:

- 휴게소별 날씨 정보 제공
- 기상청 단기/중기 예보를 보완해 고속도로 이동 중 휴게소 단위 날씨 제공

출처:

- 한국도로공사_휴게소별 날씨 정보
- API 안내: `https://data.ex.co.kr/openapi/basicinfo/openApiInfoM?apiId=0508`
- 공공데이터포털: `https://www.data.go.kr/data/15076661/openapi.do`

수집:

- 방식: OpenAPI
- 갱신 주기: 1시간
- freshness target: 2시간 이내

저장:

- `weather_raw_rest_area`
- `weather_serving_rest_area`

좌표/주소 정책:

- 응답의 `xValue`, `yValue`, `tmxValue`, `tmyValue`는 raw에 보존한다.
- 좌표계는 구현 전에 실제 응답 샘플로 검증한다.
- V-WORLD Geocoder API를 사용해야 하는 경우에는 임시 조회로만 사용한다.
- Geocoder 응답 원문과 주소 문자열은 저장하지 않는다.
- 저장 대상은 Juso 주소 기준의 `legal_dong_code`와 시군구 코드다.
- 행정구역 매핑은 좌표를 EPSG:4326으로 정규화한 뒤 PostGIS point-in-polygon으로 수행한다.

휴게소 master 매칭 정책:

- `weather_rest_area`는 `rest_area_master`와 join하지 않는다.
- 휴게소 코드, 좌표, 명칭이 비슷해 보여도 좌표/명칭 기반 후보 매칭을 수행하지 않는다.
- serving 테이블도 `matched_rest_area_id`, `match_method`, `match_confidence` 같은 매칭 필드를 두지 않는다.
- 단, 지역 단위 조회를 위해 `legal_dong_code`와 시군구 코드는 저장할 수 있다.
- 휴게소 기본정보가 필요하면 `rest_area_master`를 별도 데이터셋으로 조회한다.

보완 필요:

- 실제 응답 필드명과 좌표계 확인
- `pykex`에는 아직 `weather_rest_area` 전용 메서드가 없다. 구현 전 실제 응답 샘플을 기준으로 `pykex`에 endpoint와 모델 또는 raw wrapper를 먼저 추가한다.

## 5. Fuel

공통 정책:

- OpiNet API 키는 백엔드 설정 파일의 설정 항목으로 둔다.
- 실제 키 값은 소스 코드에 하드코딩하지 않고 환경변수 또는 secret store로 주입한다.
- OpiNet 호출은 `pyopinet`의 `opinet` 패키지를 감싼 backend adapter를 통해 수행한다.
- 현재 backend 의존성은 `apps/api/pyproject.toml`의
  `opinet @ git+https://github.com/digitie/pyopinet.git@ee4998eec98deabc69edc40f76fda1aa6ad4519a`로 고정한다.
- TripMate adapter 위치는 `apps/api/app/etl/fuel/opinet_adapter.py`다.
- API 키와 호출 옵션은 `TRIPMATE_OPINET_API_KEY`, `TRIPMATE_OPINET_TIMEOUT_SECONDS`,
  `TRIPMATE_OPINET_MAX_RETRIES`, `TRIPMATE_OPINET_RETRY_BACKOFF_SECONDS` 설정으로 주입한다.
- API 오류, quota 초과, 빈 응답은 백엔드 설정 파일의 데이터셋별 ETL retry 설정을 따른다. 기본값은 5분 간격 최대 3회 retry다.
- 설정된 retry 이후에도 실패하면 해당 DAG run에 실패 건을 기록하고 다음 schedule로 넘긴다.
- 실패 시 기존 serving 데이터가 있으면 삭제하지 않는다.
- 유종 enum은 `gasoline`, `premium_gasoline`, `diesel`, `lpg`다.
- OpiNet provider fuel code와 provider 코드명은 변환하지 않고 원문 값을 함께 보존한다.
- 앱 내부 조회와 필터는 provider fuel code를 위 유종 enum으로 mapping한 값을 사용한다.
- pyopinet `ProductCode.KEROSENE`의 `C004`는 provider code/name을 보존하되, TripMate 내부
  `fuel_type` enum에는 매핑하지 않는다.
- 가격 단위는 원/L다.
- 가격 기준일/기준시각은 `timestamp` 필드에 저장한다. 원천이 날짜와 시각을 분리 제공하면 적재 시 적절한 timezone 기준으로 timestamp로 변환한다.
- 평균가와 최저가 응답은 모두 저장한다.
- 평균가/최저가/지역코드 API의 응답 필드는 raw와 serving에 모두 보존한다. serving에서는 주요 조회용 필드만 별도 column으로 정규화하고, 전체 provider field는 JSON payload로 함께 보존한다.
- OpiNet 지역코드는 법정동코드와 mapping한다. mapping은 별도 테이블로 관리하고, OpiNet 조회/캐시 key에는 provider region code를 그대로 사용한다.
- pyopinet의 `FuelType`, ProductCode mapping, normalized record, `AreaCode` helper,
  Station 좌표/상품 context를 우선 사용한다.
- pyopinet의 시도 prefix 매핑은 시도 2자리 변환에만 사용한다. 시군구 4자리 provider code와
  법정동코드의 상세 매핑은 `fuel_region_legal_dong_mapping`에서 관리한다.

### 5.1 `fuel_avg_price`

목적:

- 평균 유가
- 여행지 주변 유가 정보를 표시할 때 비교 기준값으로 사용

출처:

- 한국석유공사 전국 주유소 평균가격
- https://www.opinet.co.kr/user/custapi/openApiInfoDtl.do?apiId=4
- API 정보 PDF: `https://drive.google.com/file/d/1eL1UonpVCdfPe8Mx5SSmflIYx2ZjnWrf/view?usp=drive_link`
- pyopinet method: `OpinetClient.get_national_average_price()`

수집:

- 갱신 주기: 하루 3회
- freshness target: 12시간 이내

저장:

- `fuel_raw_avg`
- `fuel_serving_avg`

권장 key:

- raw: provider, endpoint, region_code, legal_dong_code, collected_at, response_hash
- serving: region_code, legal_dong_code, timestamp, fuel_type

저장 정책:

- 평균가 응답의 모든 return field를 저장한다.
- provider fuel code와 provider 코드명은 pyopinet normalized field와 raw payload를 기준으로 원문 그대로 저장한다.
- 내부 `fuel_type`은 `gasoline`, `premium_gasoline`, `diesel`, `lpg` 중 하나로 정규화한다.
- 가격은 원/L로 저장한다.
- 현재 backend adapter는 pyopinet의 `date`, `float`, enum 변환 결과를 받아 `price_timestamp`를
  `Asia/Seoul` 자정 기준 datetime으로 정규화한다.

### 5.2 `fuel_lowest_station`

목적:

- 지역 최저가 주유소 후보

출처:

- 한국석유공사 지역별 최저가 주유소 TOP20
- https://www.opinet.co.kr/user/custapi/openApiInfoDtl.do?apiId=2
- API 정보 PDF: `https://drive.google.com/file/d/1eL1UonpVCdfPe8Mx5SSmflIYx2ZjnWrf/view?usp=drive_link`
- pyopinet method: `OpinetClient.get_lowest_price_top20()`
- 주변 주유소 후보 조회가 필요하면 pyopinet `OpinetClient.search_stations_around()`를 사용한다.

수집:

- 갱신 주기: 하루 3회 또는 상류 갱신 주기와 동일
- freshness target: 12시간 이내
- 일부 유종만 제공되면 제공되지 않은 유종은 `N/A`로 표시한다.
- 주유소 정보는 별도 장기 저장하지 않고 여행지 주변 정보로 저장할 때만 보관한다.
- 여행지가 바뀌는 등 주변 주유소 정보가 무효해지면 삭제한다.

저장:

- `fuel_raw_station`
- `fuel_serving_station`

저장 정책:

- 최저가 응답의 모든 return field를 저장한다.
- provider fuel code와 provider 코드명은 pyopinet normalized field와 raw payload를 기준으로 원문 그대로 저장한다.
- `lowTop10.do`/`aroundAll.do` 응답에 `PRODNM`이 없으면 provider fuel code는 요청 context로 보존하되,
  provider fuel name은 `None`일 수 있다.
- 내부 `fuel_type`은 `gasoline`, `premium_gasoline`, `diesel`, `lpg` 중 하나로 정규화한다.
- 가격은 원/L로 저장한다.
- 가격 기준일/기준시각은 `timestamp` 필드에 저장한다.
- provider station id는 pyopinet `Station.provider_station_id`를 사용한다.
- 좌표는 pyopinet `Station.coordinates`의 WGS84 `lon`/`lat`과 KATEC `x`/`y`를 함께 보존한다.
- provider 응답에 `TRADE_DT`/`TRADE_TM`이 있으면 pyopinet `Station.trade_date`/`trade_time`을
  `Asia/Seoul` 기준 timestamp로 정규화한다.

보완 필요:

- provider 응답에서 가격 기준일/기준시각을 얻는 경우의 DB 저장 column 확정

### 5.3 `fuel_region_code`

목적:

- 한국석유공사 OpiNet 지역 코드 기준 테이블
- 평균가/최저가 API 조회용 region code 제공

출처:

- 한국석유공사 지역코드
- https://www.opinet.co.kr/user/custapi/openApiInfoDtl.do?apiId=5
- API 정보 PDF: `https://drive.google.com/file/d/1eL1UonpVCdfPe8Mx5SSmflIYx2ZjnWrf/view?usp=drive_link`
- pyopinet method: `OpinetClient.get_area_codes()`

수집:

- 갱신 주기: 3달에 1번
- 처음 데이터를 얻어올 때에는 `area` 파라미터 없이 요청하여 두 자리 시도별 코드를 얻는다.
- 각 두 자리 시도별 코드를 `area` 파라미터에 넣어 네 자리 시군구 코드를 얻어서 저장한다.

저장:

- `fuel_raw_region_code`
- `fuel_serving_region_code`
- `fuel_region_legal_dong_mapping`

지역 코드 정책:

- OpiNet 지역코드는 `legal_dong_code` 또는 TripMate 행정구역 코드와 일치하지 않는다.
- OpiNet 지역코드와 Juso `legal_dong_code` 사이의 별도 mapping table을 만든다.
- mapping table은 OpiNet region code, OpiNet region name, mapping된 `legal_dong_code`, mapping source, confidence 또는 status, updated_at을 포함한다.
- OpiNet 지역코드는 fuel 데이터셋 내부 provider 기준 코드로 원문 그대로 보존한다.
- 유가 API 조회와 캐시 key에는 OpiNet region code를 그대로 사용한다.
- 앱의 지역 기반 조회와 다른 데이터셋 join에는 mapping된 `legal_dong_code`를 사용한다.
- 현재 backend adapter는 pyopinet `AreaCode.code_level`, `parent_sido_code`,
  `bjd_sido_prefix`를 사용한다.

보완 필요:

- 사라진 region code, 이름 변경, 행정구역 개편 시 처리 정책

## 6. Region

### 6.1 `administrative_boundary`

목적:

- 시도/시군구/법정동 매핑
- 장소 좌표의 행정구역 판정
- 행정구역 기반 날씨/유가/주변 리포트

출처:

- VWorld / 전국 연속수치지형도 행정경계 SHP
- 데이터셋: `N3A_G0010000`, `N3A_G0100000`, `N3A_G0110000`
- 형식: SHP
- 기준 문서: `연속수치지형도_데이터_설명서.pdf`

수집:

- 방식: 관리자 페이지에서 ZIP 직접 업로드
- 갱신 주기: 매월 15일 확인
- freshness target: 월 1회
- VWorld에서 백엔드가 직접 다운로드하지 않는다.
- ZIP 파일명으로 레이어를 판정한다.
  - `N3A_G0010000.zip`: 행정경계(시도)
  - `N3A_G0100000.zip`: 행정경계(시군구)
  - `N3A_G0110000.zip`: 행정경계(읍면동/법정동코드)
- SHP/DBF encoding은 `cp949`로 읽는다.

좌표계:

- 원본 SHP 좌표계: EPSG:5179, Korea 2000 Unified Coordinate System
- raw 레이어: EPSG:5179 원본 geometry 보존
- serving 레이어: EPSG:4326 변환본 생성
- 웹 지도 출력과 API 응답 좌표는 EPSG:4326 사용

저장:

- `region_boundary_import_batch`: 관리자 업로드 ZIP 단위 적재 기록
- `region_raw_vworld_boundary`: 원본 비교와 재처리를 위한 EPSG:5179 SHP 적재본
- `region_serving_boundary`: 지도 표시, point-in-polygon, 행정구역 조회를 위한 EPSG:4326 변환본
- `address_code_standard`: data.go.kr `국토교통부_전국 법정동` 기준 테이블. SHP `BJCD`와 조인할 수 있도록 `sido_code`, `sigungu_code`, `legal_dong_code`를 모두 문자열로 보존한다.

SHP 필드:

| DBF 필드 | 의미 | 저장 필드 |
| --- | --- | --- |
| `UFID` | VWorld feature id | `ufid` |
| `BJCD` | 법정동코드 또는 행정구역 단계 코드 | `region_code`, `legal_dong_code` |
| `NAME` | 명칭 | `region_name` |
| `DIVI` | 구분 코드 | `divi` |
| `SCLS` | 통합코드 | `scls` |
| `FMTA` | 제작정보 | `fmta` |

정규화:

- `BJCD`는 10자리 문자열로 저장하고 숫자 변환하지 않는다.
- 시도 코드는 `BJCD[0:2] + "00000000"`으로 관리한다.
- 시군구 코드는 `BJCD[0:5] + "00000"`으로 관리한다.
- 법정동 경계는 `BJCD`를 `address_code_standard.legal_dong_code`와 exact match한다.
- SHP에는 존재하지만 최신 코드 기준에는 없는 행정구역 코드가 있을 수 있으므로, serving에는 `address_code_standard_code` nullable FK와 `address_code_matched`를 함께 둔다.

공간 연산:

- 행정구역 point-in-polygon 판정은 PostGIS에서 수행한다.
- 법정동 단위 point-in-polygon 판정이 필요한 경우 `region_serving_boundary`에서 `boundary_level = 'legal_dong'`을 사용한다.
- 장소 좌표는 API/웹 입력 기준 EPSG:4326으로 받는다.
- raw 원본 검증이나 SHP 갱신 비교는 EPSG:5179 raw 레이어 기준으로 수행한다.
- 서비스 조회는 EPSG:4326 serving 레이어를 우선 사용한다.
- 좌표에서 특정 반경에 걸치는 시도/시군구/법정동을 찾을 때는 PostGIS `ST_DWithin`을 사용하되, 결과 설명은 행정구역 경계 기반 조회라고 표현한다.
- “반경 nkm” 리포트는 행정구역 polygon과 반경의 교차/근접 기준이며, 장소 자체의 정확한 원형 거리 검색과 구분한다.

테스트:

- row count 변화
- invalid geometry
- SRID 불일치
- 경계점 point-in-polygon
- 인접 시군구

### 6.2 `juso_road_address_korean`

목적:

- 앱 내 모든 주소 저장과 조회의 기준 테이블 제공
- 도로명주소, 지번, 법정동코드, 도로명코드, 행정동코드, 도로명주소관리번호를 같은 기준으로 연결
- 외부 provider 주소 문자열을 내부 주소 기준 key로 정규화할 때 기준원으로 사용

출처:

- 주소기반산업지원서비스 주소 데이터 다운로드
- 기준 페이지: `https://business.juso.go.kr/jst/jstAddressDownload`
- 필드 기준: 위 페이지의 `데이터 구성` 탭 중 `도로명주소 한글`의 `전체분`, `관련지번` 테이블
- 상세 레이아웃 참고 PDF: `https://drive.google.com/file/d/1rt6ye4Rdv_Sf04V-W_B55Xo_3Gu-R08l/view?usp=drive_link`

수집:

- 방식: 압축 파일 다운로드 후 TXT 2종 적재
- 갱신 주기: 매월 1회
- freshness target: 월 1회
- 별도 연계신청/인증 없이 웹페이지에서 다운로드한다.
- 매월 10일에 `[YYYY][MM]_도로명주소 한글_전체분.zip` 형식의 압축 파일을 받는다.
- 압축 파일 안에서 `rnaddrkor_*.txt`는 도로명주소 한글 전체분, `jibun_rnaddrkor_*.txt`는 관련 지번 파일로 적재한다.
- 전체자료는 시도별로 구분되어 제공될 수 있으므로 `*`에는 지역명이 들어갈 수 있다.
- 웹페이지 다운로드 자동화가 필요하면 Playwright 또는 HTTP client를 사용할 수 있다.
- Juso 다운로드 retry 기본값은 5분 간격 최대 3회다. 실제 값은 데이터셋별 ETL 설정을 따른다.
- retry 소진 후에도 실패하면 실패 로그, 관리자 로그인 알림, 관리자 권한 사용자 Telegram 시스템 알림을 생성한다.
- 증분 전략은 쓰지 않는다. 매번 전체 파일을 받아 raw/staging에 적재한 뒤 serving 주소 기준 테이블을 전체 파일 기준으로 갱신한다.
- 실행일이 DB의 여행계획 날짜에 포함되면 주소 DB 업데이트를 수행하지 않는다.
- 10일 이후 실행일이 DB의 어떤 여행계획 날짜에도 포함되지 않는 첫 날짜에 전체 파일 기준 업데이트를 수행한다.
- 다운로드만 가능한 경우에는 파일과 metadata를 보관하고 serving 교체는 다음 허용일로 넘긴다.
- 다운로드 파일명, 압축 내부 TXT 파일명, encoding은 구현 시 실제 파일로 검증한다.

저장:

- raw: `address_raw_juso_road_address`
- raw: `address_raw_juso_related_jibun`
- serving: `address_serving_juso_road_address`
- serving: `address_serving_juso_related_jibun`
- code/view: `address_code_standard`
- raw에는 원본 TXT row, source file name, source year-month, file hash, row number, ingested_at을 저장한다.
- serving은 앱 주소 조회와 FK 참조를 위한 정규화 테이블이다.
- `address_code_standard`는 Juso 전체분에서 삭제/재생성하지 않는다. 법정동코드 CSV가 canonical source이고, Juso는 CSV 적재 전 개발/초기 실행 상황에서 누락 코드를 보강하는 역할만 한다.

앱 주소 기준 key:

| 내부 필드 | 원천 필드 | 설명 |
| --- | --- | --- |
| `road_address_management_no` | 도로명주소관리번호 | 도로명주소 한글 전체분 PK1, 관련지번 연계 key |
| `legal_dong_code` | 법정동코드 | 주소의 법정동 기준 코드 |
| `road_name_code` | 도로명코드 | 시군구코드 5자리 + 도로명번호 7자리 |
| `administrative_dong_code` | 행정동코드 | 참고용 행정동 코드. 주소 기준 key로 저장하되 법정동코드 대체값으로 쓰지 않는다. |

주소 저장 공통 규칙:

- 주소를 저장하는 모든 도메인 테이블은 가능한 경우 `road_address_management_no`, `legal_dong_code`, `road_name_code`, `administrative_dong_code`를 함께 저장한다.
- `administrative_dong_code`가 없는 원천은 `NULL`을 허용하되, 임의 추정으로 채우지 않는다.

### 6.4 `legal_dong_code_standard`

> 최신 기준: canonical source는 data.go.kr `국토교통부_전국 법정동` CSV다. 아래 기존 VWorld 업로드 설명보다 이 문장과 13장의 결정 사항이 우선한다. VWorld `LSCT_LAWDCD.zip` 3컬럼 CSV는 legacy/manual fallback으로만 둔다.

목적:

- 앱 전체 주소 코드의 canonical FK target 제공
- Juso 주소 데이터, VWorld SHP 경계, 추후 장소/지오코딩 결과가 같은 10자리 코드 체계를 사용하도록 정규화

출처:

- data.go.kr `국토교통부_전국 법정동` CSV
- 방식: 관리자 페이지에서 ZIP 직접 업로드
- 자동 다운로드 없음

수집:

- ZIP 안에 CSV 1개가 있다고 가정한다.
- CSV encoding은 `cp949`다.
- 필드는 `법정동코드`, `법정동명`, `폐지여부`다.
- `폐지여부` 값은 `존재`, `폐지`를 지원한다.

저장:

- raw: `address_raw_legal_dong_code`
- serving/canonical: `address_code_standard`

정규화:

- `address_code_standard.legal_dong_code`는 모든 주소 코드의 안정 PK다.
- 테이블명/컬럼명은 기존 법정동코드 용어를 유지하지만, 실제로는 시도/시군구/법정동 레벨을 모두 담는다.
- `code_level`은 `sido`, `sigungu`, `legal_dong` 중 하나다.
- `sido_code`, `sigungu_code`는 10자리 문자열로 저장한다.
- 코드와 주소 key는 숫자로 캐스팅하지 않는다.
- 세종특별자치시처럼 부모 시도 코드가 별도 행으로 없을 수 있으므로, 부모명 파생은 CSV 전체 코드 집합을 기준으로 fallback을 허용한다.
- data.go.kr 기준에서는 VWorld 시도 SHP의 세종특별자치시 `BJCD=3600000000`이 exact match 된다. legacy code table처럼 `3600000000`이 없고 `3611000000`만 있는 경우에만 시도 경계에서 이름 정규화 fallback으로 `address_code_standard_code`를 연결한다.

업데이트/FK 정책:

- CSV 업데이트 시 `address_code_standard` row를 물리 삭제하지 않는다.
- 최신 CSV에서 사라진 코드는 `is_active = false`, `is_discontinued = true`, `source_status = 'missing_from_latest_upload'`로 보존한다.
- CSV에 `폐지`로 표시된 코드는 `is_active = false`, `is_discontinued = true`로 저장한다.
- 신규 UI 검색에서는 inactive/discontinued 코드를 숨긴다.
- 기존 주소, 장소, SHP, 여행 기록이 참조하는 FK는 유지한다.
- Juso 주소 serving과 VWorld SHP serving은 가능한 경우 `address_code_standard.legal_dong_code`를 FK로 참조한다.
- 네 key는 모두 문자열로 저장한다.
- 도로명주소관리번호가 있는 경우 주소 row의 우선 식별자는 `road_address_management_no`다.
- 도로명주소관리번호가 없는 좌표 기반 데이터는 PostGIS point-in-polygon, 법정동 경계 polygon, 주소 기준 테이블을 사용해 `legal_dong_code`와 시군구 코드를 채운다. 도로명코드와 도로명주소관리번호는 추정하지 않는다.
- 외부 provider의 주소 문자열은 표시 참고값일 뿐 주소 기준원으로 승격하지 않는다.
- V-WORLD Geocoder 응답 주소/원문은 이 기준 테이블의 대체 원천으로 장기 저장하지 않는다.
- 지오코딩 또는 provider 검색으로 얻은 주소는 저장 전에 Juso 주소 기준 테이블의 `road_address_management_no`, `legal_dong_code`, `road_name_code`, `administrative_dong_code` 중 하나 이상에 연결을 시도한다.
- 도로명주소관리번호가 매칭되면 가장 강한 FK로 사용한다. 없으면 법정동코드, 도로명코드, 행정동코드 순서로 가능한 FK를 함께 남긴다.
- FK는 주소 기준 테이블 갱신으로 사라질 수 있으므로 도메인 테이블에서 nullable이어야 한다.
- 여행 장소 저장 시에는 FK와 별도로 저장 당시의 주소 문자열, provider 주소 문자열, 도로명/지번 표시 주소, 좌표, 주소 기준 key snapshot을 함께 저장한다.
- 주소가 폐지되거나 건물이 사라져 더 이상 참조 FK가 없어도 기존 여행 장소 조회와 일정 표시는 저장 당시 주소 snapshot으로 동작해야 한다.
- 폐지 주소는 신규 UI 주소 검색 결과에서 숨긴다.

전체분 TXT 필드:

| 순번 | 내부 필드 | 원천 필드 | 비고 |
| --- | --- | --- | --- |
| 1 | `road_address_management_no` | 도로명주소관리번호 | PK1 |
| 2 | `legal_dong_code` | 법정동코드 | 문자 10 |
| 3 | `sido_name` | 시도명 |  |
| 4 | `sigungu_name` | 시군구명 |  |
| 5 | `legal_eupmyeondong_name` | 법정읍면동명 |  |
| 6 | `legal_ri_name` | 법정리명 |  |
| 7 | `mountain_yn` | 산여부 | `0`: 대지, `1`: 산 |
| 8 | `jibun_main_no` | 지번본번(번지) |  |
| 9 | `jibun_sub_no` | 지번부번(호) |  |
| 10 | `road_name_code` | 도로명코드 | PK2, 시군구코드(5)+도로명번호(7) |
| 11 | `road_name` | 도로명 |  |
| 12 | `underground_yn` | 지하여부 | PK3, `0`: 지상, `1`: 지하, `2`: 공중, `3`: 수상 |
| 13 | `building_main_no` | 건물본번 | PK4 |
| 14 | `building_sub_no` | 건물부번 | PK5 |
| 15 | `administrative_dong_code` | 행정동코드 | 참고용 |
| 16 | `administrative_dong_name` | 행정동명 | 참고용 |
| 17 | `postal_code` | 기초구역번호(우편번호) |  |
| 18 | `previous_road_address` | 이전도로명주소 |  |
| 19 | `effective_date` | 효력발생일 | `YYYYMMDD` |
| 20 | `apartment_yn` | 공동주택구분 |  |
| 21 | `change_reason_code` | 이동사유코드 | `31`: 신규, `34`: 수정, `63`: 폐지 |
| 22 | `building_registry_name` | 건축물대장건물명 |  |
| 23 | `sigungu_building_name` | 시군구용건물명 |  |
| 24 | `note` | 비고 |  |

관련지번 TXT 필드:

| 순번 | 내부 필드 | 원천 필드 | 비고 |
| --- | --- | --- | --- |
| 1 | `road_address_management_no` | 도로명주소관리번호 | PK1, 전체분 연계 key |
| 2 | `legal_dong_code` | 법정동코드 | PK2 |
| 3 | `sido_name` | 시도명 |  |
| 4 | `sigungu_name` | 시군구명 |  |
| 5 | `legal_eupmyeondong_name` | 법정읍면동명 |  |
| 6 | `legal_ri_name` | 법정리명 |  |
| 7 | `mountain_yn` | 산여부 | PK3, `0`: 대지, `1`: 산 |
| 8 | `jibun_main_no` | 지번본번(번지) | PK4 |
| 9 | `jibun_sub_no` | 지번부번(호) | PK5 |
| 10 | `road_name_code` | 도로명코드 | 시군구코드(5)+도로명번호(7) |
| 11 | `underground_yn` | 지하여부 | `0`: 지상, `1`: 지하, `2`: 공중, `3`: 수상 |
| 12 | `building_main_no` | 건물본번 |  |
| 13 | `building_sub_no` | 건물부번 |  |
| 14 | `change_reason_code` | 이동사유코드 | `31`: 신규, `34`: 변동, `63`: 폐지 |

현행화 정책:

- 매월 전체 파일을 기준으로 serving 주소 테이블을 재생성 또는 교체한다.
- serving 교체는 staging 적재, row count/schema 검증, index/FK 검증이 끝난 뒤 원자적으로 수행한다.
- `change_reason_code`는 raw/staging 검증 metadata로만 사용한다.
- serving/code 기준 테이블에는 최신 유효 주소만 남긴다.
- 폐지 주소와 변경 이전 주소 코드는 serving/code 기준 테이블에서 삭제하고 유지하지 않는다.
- `change_reason_code=63` row는 신규 UI 검색과 serving 주소 기준 테이블에서 제외한다.
- `change_reason_code=34`는 변경 신호로만 해석한다. 변경 이전 key row는 유지하지 않고, 최신 전체 파일에 남은 현재 유효 row만 serving에 둔다.
- 같은 일자의 같은 파일은 file hash 기준으로 idempotent 하게 skip한다.
- 실행일이 DB의 여행계획 날짜에 포함되면 serving 교체를 skip하고 기존 주소 기준 테이블을 유지한다.
- 10일 이후 실행일이 DB의 어떤 여행계획 날짜에도 포함되지 않는 첫 날짜에 serving 교체를 수행한다.
- skip된 날짜와 이유는 Airflow task log와 별도 JSONL 로그에 남긴다.
- skip된 일자는 일자별 증분 replay를 수행하지 않는다. 다음 허용일에 해당 월 전체 파일을 기준으로 갱신한다.

보완 필요:

- TXT 구분자, encoding의 실제 샘플 검증

## 7. Rest Area

공통 정책:

- 한국도로공사 OpenAPI 응답 row 전체는 raw snapshot으로 보관한다.
- 한국도로공사 OpenAPI 호출은 `kex-openapi`의 `kex_openapi.KexClient`를 직접 사용한다.
- TripMate backend에는 한국도로공사 전용 adapter/wrapper를 두지 않는다. TripMate에 필요한 endpoint, 모델, enum, 변환 보강은 먼저 `pykex`에 반영한다.
- 현재 backend 의존성은 `apps/api/pyproject.toml`의 `kex-openapi @ git+https://github.com/digitie/pykex.git@329d5a1219a8f41a83448d619a33fcaf6da23f13`을 따른다.
- API 키와 호출 옵션은 `TRIPMATE_KEX_EX_API_KEY`, `TRIPMATE_KEX_GO_API_KEY`, `TRIPMATE_KEX_TIMEOUT_SECONDS`, `TRIPMATE_KEX_MAX_RETRIES`, `TRIPMATE_KEX_RETRY_BACKOFF_SECONDS` 설정으로 주입한다.
- 기존 로컬 설정명인 `TRIPMATE_EXPRESSWAY_API_KEY`, `TRIPMATE_DATA_GO_SERVICE_KEY`도 fallback으로 읽는다.
- raw에는 최소한 `provider`, `endpoint`, `source_api_id`, `source_key`, `collected_at`, `source_snapshot_date`, `response_hash`, `payload_json`을 둔다.
- 앱/API 조회는 serving 테이블을 사용한다.
- serving에는 앱에서 직접 조회하는 안정 필드만 정규화한다. provider 원문 전체를 serving 도메인 필드로 펼치지 않는다.
- raw를 직접 도메인 로직의 단일 진실원으로 쓰지 않는다.
- 한 번에 100개를 초과해 요청하지 않는다. `pykex` 메서드 기본값이 더 크더라도 TripMate ETL에서는 `num_of_rows=100`을 명시한다.
- pagination은 응답 건수가 page size보다 작거나 0이면 종료한다.
- 방어적으로 max page guard를 둔다.
- `rest_area_oil_price` / `rest_area_svcs`에서 FK 불일치가 발생하면 raw 적재는 보존하고 serving row는 skip한다.
- FK 불일치 row는 Airflow task log와 별도로 `logs/etl/rest_area_fk_mismatch/<dataset>/<dag_run_id>.jsonl`에 JSON Lines로 남긴다.
- FK 불일치 로그에는 최소한 `dataset`, `dag_id`, `run_id`, `source_endpoint`, `source_key`, `serviceAreaCode`, `collected_at`, `reason`을 기록한다.
- FK 불일치는 DAG 실패로 즉시 중단하지 않고 skip count metric으로 남긴다. 단, 오류율 임계치를 넘으면 DAG를 실패 처리한다.

### 7.1 `rest_area_master`

목적:

- 전국 고속도로 휴게소 기본정보

출처:

- pykex: `KexClient.restarea.route_facilities()`
- 한국도로공사_노선별 휴게시설 현황
- Request URL: `https://data.ex.co.kr/openapi/business/serviceAreaRoute`
- 관련 후보: 한국도로공사_고속도로휴게소코드정보(하이쉼마루), API 안내 `https://data.ex.co.kr/openapi/basicinfo/openApiInfoM?apiId=0615`, 공공데이터포털 `https://www.data.go.kr/data/15062047/openapi.do`

비고:

- 2026-05-07 기준 `pykex`는 `RestAreaRouteFacility` 모델로 `serviceAreaCode`, `serviceAreaCode2`, `serviceAreaName`, `routeCode`, `routeName`, `direction`, `telNo`, `svarAddr`, `brand`, `convenience`, `maintenanceYn`, `truckSaYn`, `batchMenu`를 노출한다.
- 실제 live 응답에서 `serviceAreaName`이 비어 있는 row와 `X` boolean flag가 확인되어 `pykex`에서 허용한다.
- 하이쉼마루 코드정보 `apiId=0615`의 실제 Request URL과 응답 샘플은 별도 live 검증 후 `pykex`에 추가한다. 그 전까지 TripMate 구현은 `route_facilities()`를 master 후보 소스로 사용한다.

수집:

- 갱신 주기: 월 1회

저장:

- `rest_area_raw_master`
- `rest_area_serving_master`

권장 key:

- `svar_cd`: `pykex` `RestAreaRouteFacility.service_area_code` / provider `serviceAreaCode`

serving 필드 예:

- `svar_cd`: `service_area_code`
- `name`: `service_area_name`
- `direction`
- `route_code`
- `route_name`
- `address`
- `lon`, `lat`: provider가 좌표를 제공하는 경우만 저장
- `parking_capacity`
- `phone`
- `operation_status`
- `source_snapshot_date`
- `updated_at`

### 7.2 `rest_area_oil_price`

목적:

- 휴게소 주유소별 가격과 업체 현황

출처:

- pykex: `KexClient.restarea.fuel_prices()`
- 한국도로공사_주유소별 가격,업체 현황
- API 안내: `https://data.ex.co.kr/openapi/basicinfo/openApiInfoM?apiId=0312`
- Request URL: `https://data.ex.co.kr/openapi/business/curStateStation`

수집:

- 갱신 주기: 12시간
- freshness target: 24시간 이내

저장:

- `rest_area_raw_oil_price`
- `rest_area_serving_oil_price`

join:

- `serviceAreaCode`를 `rest_area_serving_master.svar_cd`와 연결한다.
- FK 불일치 시 raw는 저장하고 serving row는 skip한다.
- skip된 row는 `logs/etl/rest_area_fk_mismatch/rest_area_oil_price/<dag_run_id>.jsonl`에 별도로 기록한다.

serving 필드 예:

- `rest_area_id`
- `serviceAreaCode`
- `station_name`: `pykex` `RestAreaFuelPrice.service_area_name`
- `provider_fuel_code`
- `provider_fuel_name`
- `fuel_type`: `gasoline`, `premium_gasoline`, `diesel`, `lpg`, `unknown`
- `price_per_liter_krw`
- `price_at`: provider가 가격 기준시각을 제공하면 그 값을 저장한다.
- `price_time_source`: `provider_timestamp` 또는 `collected_at`
- `collected_at`
- `source_snapshot_date`

가격 기준시각 정책:

- provider 기준시각이 있으면 `price_at`에 저장한다.
- provider 기준시각이 없으면 `price_at = collected_at`으로 저장하고 `price_time_source = collected_at`으로 남긴다.
- 가격 단위는 원/L로 해석한다. 단, provider 문서나 샘플에서 단위가 달라지면 schema drift 로그를 남기고 serving 반영을 중단한다.
- `pykex` `RestAreaFuelPrice`는 현재 `gasoline_price`, `diesel_price`, `lpg_price`를 컬럼형 가격으로 노출한다. serving 단계에서 유종별 row로 펼칠 때 provider 유종 코드/명칭은 TripMate 내부 상수로 명시하고, 앱 내부 표시는 `fuel_type` enum을 사용한다.

### 7.3 `rest_area_svcs`

목적:

- 노선별, 방향별 휴게소 편의시설 현황

출처:

- pykex: `KexClient.restarea.convenience_facilities()`
- 한국도로공사_노선별, 방향별 휴게소 편의시설 현황
- API 안내: `https://data.ex.co.kr/openapi/basicinfo/openApiInfoM?apiId=0316`
- Request URL: `https://data.ex.co.kr/openapi/business/conveniServiceArea`

비고:

- 2026-05-07 기준 `pykex` live test는 통과했지만, 실제 응답 schema 승격 전까지 이 endpoint를 `Page[dict]`로 반환한다.

수집:

- 갱신 주기: 월 1회

저장:

- `rest_area_raw_svcs`
- `rest_area_serving_svcs`

join:

- `serviceAreaCode`를 `rest_area_serving_master.svar_cd`와 연결한다.
- FK 불일치 시 raw는 저장하고 serving row는 skip한다.
- skip된 row는 `logs/etl/rest_area_fk_mismatch/rest_area_svcs/<dag_run_id>.jsonl`에 별도로 기록한다.

serving 필드 예:

- `rest_area_id`
- `serviceAreaCode`
- `provider_service_code`
- `provider_service_name`
- `display_name`
- `available`
- `quantity`
- `status`
- `source_snapshot_date`
- `collected_at`

표시 정책:

- provider 편의시설 코드/명칭은 그대로 보존한다.
- 앱 표시명은 별도 mapping으로 관리한다.
- 다국어 표시는 초기 범위에 포함하지 않고 한국어 표시명을 기준으로 한다.
- 미확인 편의시설 코드는 저장을 막지 않고 `display_name = provider_service_name`으로 표시하며 schema drift 로그를 남긴다.

## 8. Tour Point

### 8.1 `kma_recommended_tour_course`

목적:

- 관광코스 정보 제공
- 여행지 주변 관광지/관광코스 후보 제공

출처:

- 기상청_관광코스별 관광지 상세 날씨 조회서비스
- 참고문서: `https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000002889827&fileDetailSn=1`
- 공공데이터포털: `https://www.data.go.kr/data/15056912/openapi.do`

수집:

- 방식: CSV 파일 다운로드
- 갱신 주기: 연 1회 확인

저장:

- raw: `tour_course_raw_point`
- serving: `kma_recommended_tour_course`
- raw에는 원본 CSV row, source file metadata, file hash, source snapshot date를 저장한다.
- 원본 zip/csv 파일 자체는 raw row와 file hash 적재가 끝나면 삭제할 수 있다.

serving 필드:

| 필드 | 타입 | nullable | 의미 |
| --- | --- | --- | --- |
| `theme_category_code` | string | no | CSV `테마분류` 원본 코드. 예: `TH05` |
| `theme_category` | enum | no | 앱 내부 테마 enum. 알 수 없는 코드는 `unknown` |
| `course_id` | string | no | CSV `코스 아이디` |
| `tour_point_source_id` | string | no | CSV `관광지 아이디` |
| `source_region_id` | string | no | CSV `지역 아이디` 원문 |
| `source_region_legal_dong_code` | string | yes | `지역 아이디`가 Juso 법정동코드로 검증된 경우 저장 |
| `name` | string | no | CSV `관광지명` |
| `lng` | numeric | no | EPSG:4326 경도 |
| `lat` | numeric | no | EPSG:4326 위도 |
| `course_order` | integer | yes | CSV `코스순서` |
| `travel_time_minutes` | integer | yes | CSV `이동시간` |
| `indoor_outdoor` | enum | yes | CSV `실내구분`. `indoor`, `outdoor`, `unknown` |
| `theme_name` | string | no | CSV `테마명` 원본 표시명 |
| `road_address_management_no` | string | yes | Juso 도로명주소관리번호 |
| `legal_dong_code` | string | yes | Juso 법정동코드 |
| `road_name_code` | string | yes | Juso 도로명코드 |
| `administrative_dong_code` | string | yes | Juso 행정동코드 |
| `address_snapshot` | string | yes | V-WORLD reverse geocoding으로 얻은 저장 당시 주소 snapshot |
| `marker_source_type` | enum | no | `kma_recommended_tour_course` 고정 |
| `source_file_hash` | string | no | 원천 CSV 파일 hash |
| `source_snapshot_date` | date | yes | 원천 snapshot 기준일. 파일에서 얻을 수 없으면 null |

테마 category enum:

- 원본 `theme_category_code`와 `theme_name`은 항상 보존한다.
- `theme_category`는 앱 내부 필터, 마커 스타일, API category filter에 쓰는 값이다.
- 초기 enum은 원천 코드가 확인되는 대로 `theme_category_code`별 mapping table로 관리한다.
- 현재 확인된 `TH05`와 `종교/역사/전통`은 `religion_history_tradition`으로 mapping한다.
- `theme_name`의 `/` 구분값은 UI 표시명으로는 그대로 유지한다. 내부 enum 생성을 위해 런타임에 임의로 split하지 않는다.
- 새로운 `theme_category_code`가 들어오면 적재 실패로 보지 않고 `theme_category=unknown`으로 serving에 올린 뒤 schema drift 로그에 남긴다.
- 마커 색상과 아이콘은 `theme_category` 기준으로 선택한다. `unknown`은 “기상청 추천 여행코스” 기본 marker style을 사용한다.

CSV 파싱 정책:

- `기상청27_관광코스별_관광지_상세설명서.zip` 압축 파일의 `기상청27_관광코스별_관광지_지점정보.csv` 파일을 원천으로 사용한다.
- CSV encoding은 Windows 11 Notepad에서 ANSI로 표시되는 한국어 Windows ANSI 계열로 취급한다.
- 구현 기본값은 `cp949` 또는 동등한 `ms949` decoder다.
- 내부 저장과 처리 문자열은 UTF-8로 정규화한다.
- decoding 실패 row는 serving으로 올리지 않고 raw row, byte offset 또는 row number, 실패 사유를 별도 로그에 남긴다.
- delimiter는 `,`이다.
- 현재 확인된 필드명은 `테마분류`, `코스 아이디`, `관광지 아이디`, `지역 아이디`, `관광지명`, `경도(도)`, `위도(도)`, `코스순서`, `이동시간`, `실내구분`, `테마명`이다.
- 예시 row:

```csv
테마분류,코스 아이디,관광지 아이디,지역 아이디,관광지명,경도(도),위도(도),코스순서,이동시간,실내구분,테마명
TH05,177,17703,4822051000,(통영)세병관(통제영지),128.423238,34.847749,3,2,실외,종교/역사/전통
TH05,177,17704,4822051000,(통영)충렬사,128.417847,34.846626,4,3,실외,종교/역사/전통
```

좌표/주소 정책:

- serving 데이터의 위경도는 EPSG:4326 `lat`, `lng`로 정규화한다.
- `경도(도)`는 `lng`, `위도(도)`는 `lat`으로 저장한다.
- CSV의 `지역 아이디`는 10자리 코드 형태이므로 Juso `legal_dong_code` 후보로 검증한다.
- `지역 아이디`가 Juso `legal_dong_code`에 존재하고 좌표 기반 행정구역 판정과 모순되지 않으면 `source_region_legal_dong_code`로 저장한다.
- 위경도에서 주소를 얻기 위한 reverse geocoding provider는 항상 V-WORLD Geocoder를 사용한다.
- V-WORLD Geocoder는 이 흐름에서 별도 quota가 없는 provider로 취급하며, quota 기반 throttling 설정을 두지 않는다.
- V-WORLD 호출 실패는 provider call 단위로 최대 5회 retry한다. 이 retry 횟수는 관리자 페이지의 데이터셋별 ETL retry 설정으로 바꾸지 않는 고정값이다.
- 5회 retry 후에도 실패하면 해당 좌표의 geocoding 실패 로그를 남기고, 주소 매핑이 serving 품질이나 화면 표시 품질에 영향을 주는 경우 관리자 UI 또는 관련 화면에 알림을 표시한다.
- V-WORLD 응답 원문 전체는 장기 저장하지 않는다.
- V-WORLD reverse geocoding으로 얻은 주소는 Juso 주소DB 매핑 입력값으로만 사용한다.
- 매핑 후보 key는 Juso 도로명주소 한글 레이아웃의 `road_address_management_no`, `legal_dong_code`, `road_name_code`, `administrative_dong_code`다.
- `road_address_management_no`가 매칭되면 가장 강한 주소 FK로 저장한다.
- 도로명주소관리번호가 없으면 `legal_dong_code`, `road_name_code`, `administrative_dong_code` 중 확인 가능한 key를 저장한다.
- 도로명주소관리번호와 도로명코드는 추정 생성하지 않는다. Juso 주소DB 또는 V-WORLD reverse geocoding 결과에서 검증 가능한 경우에만 저장한다.
- 매칭되지 않는 경우에도 좌표, 관광지명, `지역 아이디`, 저장 당시 V-WORLD reverse geocoding 주소 snapshot은 보존하고 주소 FK는 nullable로 둔다.
- 주소 또는 행정구역 코드가 필요하면 좌표 기반 point-in-polygon과 Juso 주소 기준 테이블로 `legal_dong_code`와 시군구 코드를 채운다.
- 관광코스 상세 날씨 API와 CSV 지점정보의 연결 key가 없으므로 별도 매칭 테이블을 만들지 않는다.
- 주소 문자열 기반 fuzzy matching은 기본 매칭 경로로 수행하지 않는다. 정확한 주소 구성요소 또는 검증 가능한 key 기반 매칭만 허용한다.

Juso key 매핑 우선순위:

| 우선순위 | key | 사용 조건 |
| --- | --- | --- |
| 1 | `road_address_management_no` | V-WORLD reverse geocoding 주소가 Juso 도로명주소 row와 정확히 매칭될 때 |
| 2 | `legal_dong_code` | CSV `지역 아이디`, V-WORLD reverse geocoding 법정동, point-in-polygon 결과가 Juso 코드와 검증될 때 |
| 3 | `road_name_code` | V-WORLD reverse geocoding 결과에 도로명코드 또는 도로명+건물번호가 있고 Juso row로 검증될 때 |
| 4 | `administrative_dong_code` | 행정동코드가 V-WORLD reverse geocoding 또는 Juso row에서 검증될 때 |

지도/UI 정책:

- UI에서는 여행지 주변 관광지 및 관광코스를 지도 마커 또는 검색 후보 리스트 형태로 표시할 수 있다.
- 지도 마커는 “기상청 추천 여행코스” 출처가 드러나는 전용 색상과 아이콘을 사용한다.
- 실제 색상과 아이콘은 `theme_category` 기준으로 결정한다.
- `theme_category=unknown`은 “기상청 추천 여행코스” 기본 색상과 아이콘을 사용한다.
- 마커 클릭 상세 설명에는 같은 `테마분류`의 여행지를 `코스순서` 순으로 모아 볼 수 있는 링크를 제공한다.
- 코스 링크는 최소한 `테마분류`, `테마명`, 정렬 기준 `코스순서`를 query 또는 route state로 전달할 수 있어야 한다.
- 같은 `테마분류` 안에 여러 `코스 아이디`가 있으면 UI는 `코스 아이디`별로 묶고 각 묶음 안에서 `코스순서`로 정렬한다.
- 클릭한 마커의 `코스 아이디`는 초기 포커스 또는 강조 표시용으로 전달할 수 있지만, 같은 `테마분류` 전체 목록을 숨기는 필수 필터로 쓰지 않는다.

보완 필요:

- Juso 주소DB 매핑 실패 시 관리자 검토 queue를 둘지 여부
- `theme_category`별 실제 마커 색상과 아이콘 디자인 값

### 8.2 `kto_kor_tour_content`

목적:

- 한국관광공사 국문 관광정보를 관광지/문화시설/행사/여행코스/레포츠/숙박/쇼핑/음식점 후보 원천으로 제공
- 지도 주변 후보, 지역별 관광지 목록, 여행 계획 장소 후보의 공공데이터 기반 보강

출처:

- 사용자 제공 Drive 문서: `https://drive.google.com/file/d/1uX_SsUrRXzAHdHMWniKD_BB5BWwz_cs6/view?usp=sharing`
- 포함 문서: `한국관광공사_개방데이터_활용매뉴얼(국문)_v4.4.docx`
- 포함 코드 파일: `신분류체계정보 관광타입정보 연계 정의서.xlsx`
- 서비스명: `KorService2`

주요 endpoint:

- `areaBasedList2`: 지역/시군구 기반 관광정보 조회
- `locationBasedList2`: 좌표 기반 관광정보 조회. `mapX`는 WGS84 경도, `mapY`는 WGS84 위도이며 `radius` 최대값은 20,000m다.
- `searchKeyword2`: 키워드 기반 관광정보 조회
- `searchFestival2`: 행사/공연/축제 조회
- `searchStay2`: 숙박 조회
- `detailCommon2`: 기본정보, 대표 이미지, 분류, 지역 정보, 주소, 좌표, 개요 조회
- `detailIntro2`: 휴무일, 이용시간, 주차시설 등 타입별 소개정보 조회
- `detailInfo2`: 반복 상세정보 조회. 여행코스는 코스정보, 숙박은 객실정보를 포함할 수 있다.
- `detailImage2`: 이미지 URL과 이미지 저작권 유형 조회
- `areaBasedSyncList2`: 표출 여부와 수정일 기준 동기화 목록 조회
- `ldongCode2`: TourAPI 법정동 코드 조회
- `lclsSystmCode2`: 분류체계 코드 조회

관광타입 코드:

| contentTypeId | 의미 |
| --- | --- |
| 12 | 관광지 |
| 14 | 문화시설 |
| 15 | 행사/공연/축제 |
| 25 | 여행코스 |
| 28 | 레포츠 |
| 32 | 숙박 |
| 38 | 쇼핑 |
| 39 | 음식점 |

수집:

- 방식: OpenAPI
- Python client: `pykrtourapi`의 `KrTourApiClient`를 직접 사용한다. TripMate backend에는 KTO adapter/gateway 래퍼를 만들지 않는다.
- API 계약 문서: `docs/api/kto-tourapi.md`
- 운영 runbook: `docs/runbooks/kto-tourapi.md`
- 기본 응답 형식: `_type=json`
- 필수 공통 파라미터: `serviceKey`, `MobileOS`, `MobileApp`
- 설정값: `TRIPMATE_KTO_SERVICE_KEY`, `TRIPMATE_KTO_MOBILE_APP`, `TRIPMATE_KTO_MOBILE_OS`, `TRIPMATE_KTO_TIMEOUT_SECONDS`, `TRIPMATE_KTO_MAX_RETRIES`
- 기본 조회는 사용자가 이미 저장한 장소를 기준으로 수행한다.
- 좌표 기반 후보는 저장한 장소의 좌표를 `locationBasedList2`의 `mapX`, `mapY`로 전달하고 `radius=15000`으로 조회한다.
- 지역 기반 후보는 저장한 장소 좌표를 geocode한 주소에서 시도/시군구를 얻고, 이를 KTO 지역/시군구 코드로 변환해 `areaBasedList2`에 전달한다.
- `locationBasedList2`와 `areaBasedList2` 결과를 사용자에게 함께 보여준다.
- 두 endpoint에서 같은 `contentid`가 중복되면 UI에서는 하나의 후보로 병합 표시하되, 어떤 endpoint에서 발견됐는지는 provenance로 남긴다.
- 사용자가 KTO 후보를 여행지로 저장하면 TripMate 여행지 DB에 추가한다.
- `contentTypeId`는 기본적으로 제한하지 않고 전체 관광타입을 대상으로 조회한다. UI 필터가 추가되면 관광지/문화시설/행사/여행코스/레포츠/숙박/쇼핑/음식점 타입별 필터를 endpoint parameter로 전달할 수 있다.
- 상세 화면에 필요한 경우 `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2`를 후속 조회할 수 있다.
- `areaBasedSyncList2`는 전체 bulk 적재의 1차 기준으로 사용하지 않는다. 향후 전국 관광정보 사전 적재가 필요할 때 별도 설계한다.

저장:

- raw: `tour_raw_kto_kor_content`
- serving: `tour_serving_kto_kor_content`
- trip place snapshot: `trip_place_kto_content_snapshot`
- code: `tour_code_kto_region`, `tour_code_kto_legal_dong`, `tour_code_kto_category`
- raw에는 provider, endpoint, request params, collected_at, response_hash, source document version, response payload 전체를 저장한다.
- serving에는 `contentid`, `contenttypeid`, `title`, `addr1`, `addr2`, `zipcode`, `tel`, `homepage`, `mapx`, `mapy`, `mlevel`, `createdtime`, `modifiedtime`, `showflag`, `cpyrhtDivCd`, `lDongRegnCd`, `lDongSignguCd`, `lclsSystm1/2/3`, 대표 이미지 URL 등 조회 응답의 모든 return field를 보존한다.
- `trip_place_kto_content_snapshot`에는 사용자가 여행지로 저장한 시점의 KTO return field 전체를 JSON payload로 저장하고, TripMate place/trip_place와 provider reference를 연결한다.
- `mapx`는 `lng`, `mapy`는 `lat`으로 저장하고 EPSG:4326으로 취급한다.
- `overview`, `detailIntro2`, `detailInfo2`, `detailImage2`를 조회했다면 각 endpoint의 return field 전체를 별도 detail snapshot으로 저장한다.
- 이미지 바이너리는 저장하지 않는다. API가 반환한 이미지 URL, 저작권 코드, 관련 메타데이터는 return field로 저장한다.
- KTO `KorService2`는 공공 관광정보 원천으로 취급하므로 “응답값 전체 저장”을 허용한다. 이 예외는 Kakao/Naver/Google 같은 일반 장소 provider 원문 장기 저장 정책에 적용하지 않는다.
- `pykrtourapi` `Page.raw`와 item별 `raw`를 저장 기준으로 삼되, request provenance metadata가 부족한 경우 TripMate 래퍼를 새로 만들지 말고 `pykrtourapi`에 metadata 지원을 upstream한다.
- 현재 `pykrtourapi` 응답 객체는 Pydantic model이므로 후속 저장 로직은 `model_dump()`와 `raw` payload를 함께 사용할 수 있다.

코드 정책:

- TourAPI `lDongRegnCd`, `lDongSignguCd`는 KTO 서비스 조회용 코드로 별도 관리한다.
- 이 코드를 TripMate `legal_dong_code`와 동일한 코드로 간주하지 않는다.
- 법정동코드는 `ldongCode2` 법정동코드조회 API를 활용한다.
- `ldongCode2` 응답은 `tour_code_kto_legal_dong`에 캐싱해 같은 코드 조회 API call을 반복하지 않는다.
- `ldongCode2` cache는 장기 cache로 취급하고, 명시적 refresh 또는 schema drift 감지 시 갱신한다.
- 행정구역/법정동 기준 조인은 PostGIS point-in-polygon과 Juso 주소 기준 테이블을 우선한다.
- `신분류체계정보 관광타입정보 연계 정의서.xlsx`는 전체 row를 `tour_code_kto_category`에 저장한다.
- `tour_code_kto_category`는 별도 업데이트 주기를 두지 않는다. 문서 파일을 새로 받거나 사용자가 명시적으로 갱신을 지시할 때만 교체한다.
- `lclsSystm1/2/3`와 `contentTypeId` 매핑은 `tour_code_kto_category`에서 조회한다.

사용자 표시/저장 흐름:

- 사용자가 저장한 장소 상세 또는 주변 후보 화면에서 KTO 후보를 표시한다.
- `locationBasedList2` 결과는 “저장 장소 반경 15km” 후보로 표시한다.
- `areaBasedList2` 결과는 “같은 시도/시군구” 후보로 표시한다.
- 각 후보에는 제목, 관광타입, 주소, 거리 또는 지역 기준, 이미지 URL이 있으면 이미지, 출처, 발견 endpoint를 표시한다.
- 사용자가 후보를 선택해 저장하면 TripMate 여행지 DB에 새 여행지로 추가한다.
- 자동 병합은 하지 않는다. 같은 `contentid` 또는 같은 좌표/명칭의 기존 여행지가 있으면 중복 가능성을 UI에서 알려주고 사용자가 저장 여부를 결정한다.

보완 필요:

- `overview`, `homepage`, `detailIntro2`, `detailInfo2` 텍스트의 HTML sanitization 기준
- `cpyrhtDivCd`별 UI 출처 표기, 이미지 표시, 텍스트 변경 가능 여부
- OpenAPI 호출 한도, 유료/승인 조건, rate limit 값을 실제 계정 기준으로 확인

### 8.3 `kto_related_tour_point`

목적:

- 선택한 관광지와 연관성이 높은 관광지/음식/숙박 후보를 추천 신호로 제공
- 여행 일정 작성 시 “함께 볼 만한 장소” 후보를 제공하되, TripMate 내부 place와 자동 병합하지 않는다.

출처:

- 사용자 제공 Drive 문서: `https://drive.google.com/file/d/1pdo5OgRmqibKwFH-PTyEBMb9uzmbQCK-/view?usp=drive_link`
- 포함 문서: `한국관광공사_개방데이터_활용매뉴얼(관광지별연관관광지정보)_v4.1.docx`
- 포함 코드 파일: `한국관광공사_개방데이터_관광지_시군구_코드정보_v1.0.xlsx`
- 서비스명: `TarRlteTarService1`
- 문서 기준 데이터 갱신주기: 일 1회

주요 endpoint:

- `areaBasedList1`: `baseYm`, `areaCd`, `signguCd` 기반 관광지별 연관관광지 정보 조회
- `searchKeyword1`: `baseYm`, `areaCd`, `signguCd`, `keyword` 기반 관광지별 연관관광지 정보 조회

응답 핵심 필드:

- 기준 관광지: `tAtsCd`, `tAtsNm`, `areaCd`, `areaNm`, `signguCd`, `signguNm`
- 연관 관광지: `rlteTatsCd`, `rlteTatsNm`, `rlteRegnCd`, `rlteRegnNm`, `rlteSignguCd`, `rlteSignguNm`
- 분류/순위: `rlteCtgryLclsNm`, `rlteCtgryMclsNm`, `rlteCtgrySclsNm`, `rlteRank`
- 공통: `baseYm`, `numOfRows`, `pageNo`, `totalCount`, `resultCode`, `resultMsg`

수집:

- 방식: OpenAPI
- Python client: `pykrtourapi`의 `TourApiHubClient`를 직접 사용한다. typed model이 부족한 영역은 TripMate adapter로 보완하지 않고 `pykrtourapi`에 upstream한다.
- 기본 응답 형식: `_type=json`
- 기준월 `baseYm`을 명시해 월 단위 snapshot으로 관리한다.
- `areaCd`, `signguCd`는 포함 XLSX의 `areaCd`, `sigunguCd`를 기준으로 한다. API 문서의 `signguCd`와 XLSX의 `sigunguCd` 표기 차이는 같은 TourAPI 시군구 코드로 정규화하되, 법정동코드로 취급하지 않는다.
- 지역별 후보는 `areaBasedList1`, 특정 관광지명 기반 후보는 `searchKeyword1`을 사용한다.

저장:

- raw: `tour_raw_kto_related`
- serving: `tour_serving_kto_related`
- code: `tour_code_kto_related_region`
- raw에는 request params, response_hash, `baseYm`, collected_at, source document version을 저장한다.
- serving에는 기준 관광지 코드/명칭, 연관 관광지 코드/명칭, 지역 코드/명칭, 분류명, 순위를 저장한다.
- 좌표가 제공되지 않는 데이터이므로 좌표/명칭 기반 자동 매칭을 하지 않는다.
- `kto_kor_tour_content`, Kakao, Naver, 사용자 저장 place와 자동으로 합치지 않는다. 사용자가 후보를 선택하면 그 시점에 별도 provider reference로 남긴다.

보완 필요:

- `baseYm` 최신값 탐색 방식. 매월 최신 기준월을 자동 탐색할지, 설정값으로 고정할지 결정
- 전체/관광지/음식/숙박 유형별 최대 50위 추천을 UI에 어떻게 노출할지 결정
- 연관 관광지 코드를 장기 provider identifier로 사용할 수 있는지 약관/안정성 검토
- 추천 후보가 실제 좌표를 갖지 않을 때 Kakao 검색을 후속으로 호출할지 여부. 기본값은 자동 호출하지 않음

## 9. Place Provider Policy

외부 지도 API(Kakao/Naver/Google)는 다음 규칙을 따른다.

- 외부 제공자 데이터는 약관을 위반하지 않는 범위에서만 저장한다.
- “전부 저장”을 목표로 삼지 않는다.
- 공급자 원문 데이터와 내부 정규화 데이터를 분리 저장한다.
- UI와 도메인 로직은 내부 정규화 스키마만 의존한다.
- 상호명, 주소, 전화번호처럼 잘 바뀌지 않는 안정 필드는 정규화해 지속 저장할 수 있다.
- 리뷰는 수집 또는 갱신 시점부터 3개월만 저장한다.
- 여행계획 어디에도 포함되어 있지 않은 provider place의 리뷰와 비안정 부가정보는 마지막 참조 후 3개월이 지나면 ETL로 삭제한다.
- 정책이 불명확한 비안정 필드는 기본적으로 장기 저장하지 않는다.
- 약관 검토가 필요한 경우, 코드와 문서에 “법무/정책 확인 필요”를 명시한다.
- provider 간 동일 장소 추정은 자동 병합하지 않는다. Kakao, KTO, Naver, 사용자 입력은 출처가 다른 후보로 유지하고, 사용자가 저장한 장소만 내부 place로 승격한다.

영구 저장 가능:

- 내부 place id
- 사용자 입력 이름
- 사용자 메모
- 좌표 (`lat`, `lng`)
- 정규화 주소
- provider 원천 상호명
- provider 원천 주소
- provider 원천 전화번호
- 행정구역 코드
- provider 목록
- provider identifier
- 내부 ranking/선택 결과

TTL 캐시:

- provider raw response JSON
- 외부 설명문/부가 텍스트
- 세부 영업정보/평점/사진 URL 등 권리·약관 영향이 큰 필드

리뷰 보존:

- provider 리뷰는 정규화 테이블에 최대 3개월 저장한다.
- 리뷰 원문, 작성자 표시명, 평점, 작성일, provider review id가 있으면 함께 저장할 수 있다.
- 리뷰가 연결된 provider place가 TripMate 여행계획 어디에도 포함되어 있지 않은 상태로 마지막 참조 후 3개월이 지나면 ETL cleanup 대상이다.
- provider place가 여행계획에 포함되어 있어도 리뷰 row 자체는 수집 또는 갱신 후 3개월이 지나면 stale로 표시하고 재조회 또는 삭제 대상이 된다.
- 상호명, 주소, 전화번호 같은 안정 필드는 리뷰 cleanup으로 삭제하지 않는다.

표시 전용 또는 재조회 대상:

- 사용 시점에 다시 조회해야 하는 데이터
- 지도 화면과 검색 dropdown 후보
- 상세 정보 패널의 외부 제공자 정보

금지 또는 주의:

- provider 원문 전체를 영구 저장
- Google 데이터와 타 지도 혼합 표시
- Naver raw 검색 결과 전체 DB화

Google 보수 규칙:

- `place_id`, 상호명, 주소, 전화번호 같은 안정 필드는 장기 저장 가능 대상으로 취급한다.
- 그 외 Google Maps Content는 사전 fetch, 캐시, 저장이 일반적으로 제한된다.
- Google Places/Geocoding 계열 콘텐츠는 비 Google 지도 옆이나 위에 결합 사용하지 않는다.
- Google 리뷰는 3개월 보존 정책과 provider 표시 정책을 따른다.

Naver 보수 규칙:

- Naver Search raw response는 부하 감소 목적의 TTL cache로만 저장한다.
- Naver Local에서 얻은 상호명, 주소, 전화번호 같은 안정 필드는 정규화해 지속 저장할 수 있다.
- Naver Blog/News/Encyclopedia/Web 결과는 참고 링크 TTL cache로 취급하고 장기 장소 설명 원천으로 삼지 않는다.

Naver Search 상세 정책:

- 공통 출처:
  - Blog: `https://developers.naver.com/docs/serviceapi/search/blog/blog.md`
  - Local: `https://developers.naver.com/docs/serviceapi/search/local/local.md`
  - News: `https://developers.naver.com/docs/serviceapi/search/news/news.md`
  - Encyclopedia: `https://developers.naver.com/docs/serviceapi/search/encyclopedia/encyclopedia.md`
  - Web: `https://developers.naver.com/docs/serviceapi/search/web/web.md`
- 역할:
  - Local은 Kakao Local을 보완하는 보조 장소 후보와 참고 링크로 사용한다.
  - Blog는 장소/관광지의 후기, 여행 맥락, 최신 블로그 언급 참고 링크로 사용한다.
  - News는 장소/지역의 최신 이슈, 행사, 폐쇄/공사/사고 등 여행 판단 참고 링크로 사용한다.
  - Encyclopedia는 장소 배경지식과 명칭 disambiguation 참고 링크로 사용한다.
  - Web은 공식·일반 웹문서 탐색 참고 링크로 사용한다.
- 인증: 백엔드 설정/secret store에 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`을 둔다. 요청 헤더는 `X-Naver-Client-Id`, `X-Naver-Client-Secret`을 사용한다.
- 공통 호출 한도: 문서 기준 검색 API 하루 25,000회. 실제 앱 계정 한도와 변경 여부는 운영 전에 확인한다.
- 공통 요청 파라미터: `query`는 필수이며 UTF-8 인코딩한다.
- 공통 응답 envelope: `lastBuildDate`, `total`, `start`, `display`, `items[]`를 받는다.
- `title`, `description` 등 HTML 문자열에는 검색어 일치 영역을 감싸는 `<b>` 태그가 포함될 수 있으므로 UI 표시 전 HTML sanitization을 거친다.
- raw JSON은 TTL cache로만 둔다. 사용자가 직접 북마크/메모로 저장한 내용은 provider 원문이 아니라 사용자 소유 데이터로 저장한다.
- Naver 검색 결과는 장소 마스터, 주소/좌표의 단일 진실원, 평점 원천, 장기 관광지 설명 원천으로 사용하지 않는다.
- Naver Local 후보를 사용자가 선택해 저장하는 경우 내부 place에는 provider 이름, provider reference, 사용자 표시명, 정규화 주소, 검증된 좌표, 상호명, 주소, 전화번호, 선택 시각 등 안정 필드를 남길 수 있다.
- Local의 `mapx`, `mapy`는 provider 좌표 필드로 보존하되, 앱의 `lat`, `lng`로 쓰기 전 adapter에서 좌표계/단위 변환과 검증을 수행한다.
- 실패 처리: 인증 실패, 일 호출 한도 초과, `query` 인코딩 오류, endpoint별 `display`/`start`/`sort` 오류를 구분해 adapter error code로 남긴다.

Naver Search endpoint별 정책:

| dataset | endpoint | 용도 | 요청 파라미터 | 주요 item field | 저장 |
| --- | --- | --- | --- | --- | --- |
| `naver_search_local_reference` | `GET https://openapi.naver.com/v1/search/local.json` | 보조 장소 후보, 주소/전화/카테고리 참고 | `query` 필수, `display` 기본 1·최대 5, `start` 기본 1·최대 1, `sort=random|comment` | `title`, `link`, `category`, `description`, `telephone`, `address`, `roadAddress`, `mapx`, `mapy` | TTL cache. 사용자가 선택한 경우 상호명·주소·전화번호 등 안정 필드만 장기 저장 |
| `naver_search_blog_reference` | `GET https://openapi.naver.com/v1/search/blog.json` | 후기/여행 맥락 참고 링크 | `query` 필수, `display` 기본 10·최대 100, `start` 기본 1·최대 1000, `sort=sim|date` | `title`, `link`, `description`, `bloggername`, `bloggerlink`, `postdate` | TTL cache |
| `naver_search_news_reference` | `GET https://openapi.naver.com/v1/search/news.json` | 최신 이슈/행사/안전 참고 링크 | `query` 필수, `display` 기본 10·최대 100, `start` 기본 1·최대 1000, `sort=sim|date` | `title`, `originallink`, `link`, `description`, `pubDate` | TTL cache |
| `naver_search_encyclopedia_reference` | `GET https://openapi.naver.com/v1/search/encyc.json` | 배경지식/명칭 확인 참고 링크 | `query` 필수, `display` 기본 10·최대 100, `start` 기본 1·최대 1000 | `title`, `link`, `description`, `thumbnail` | TTL cache |
| `naver_search_web_reference` | `GET https://openapi.naver.com/v1/search/webkr.json` | 공식·일반 웹문서 참고 링크 | `query` 필수, `display` 기본 10·최대 100, `start` 기본 1·최대 1000 | `title`, `link`, `description` | TTL cache |

보완 필요:

- Naver Search 결과를 사용자 UI에 직접 노출할 범위. 기본값은 Local과 Blog를 사용자 후보/참고로 노출하고, News/Encyclopedia/Web은 상세 참고 탭 또는 Gemini Deep Research 입력으로 활용한다.
- Naver Search endpoint별 TTL 기간과 검색 결과 출처 표기 방식 확정
- endpoint별 query 템플릿. 예: `{장소명} 여행`, `{지역명} {장소명}`, `{장소명} 후기`, `{장소명} 공식`, `{지역명} 축제`

Kakao 보수 규칙:

- Kakao Local API는 장소 검색/주소·좌표 변환에 적합한 공식 API로 사용한다.
- Kakao 원문 응답 전체 영구 저장을 기본 정책으로 두지 않는다.
- Kakao 응답은 내부 정규화 안정 필드 추출과 필요 최소한의 TTL 캐시 위주로 처리한다.
- Kakao에서 얻은 상호명, 주소, 전화번호 같은 안정 필드는 지속 저장할 수 있다.
- Kakao 약관/운영정책 확인 없이 “원문 전체 장기 저장 가능”으로 가정하지 않는다.

Kakao Local 상세 정책:

- 출처: `https://developers.kakao.com/docs/ko/local/common`, `https://developers.kakao.com/docs/ko/local/dev-guide`
- 역할: 장소 검색 후보의 1차 provider로 사용한다. 주소→좌표, 좌표→주소, 좌표→행정구역, 좌표계 변환은 보조 adapter로 사용한다.
- 사전 설정: Kakao Developers 앱 생성 후 카카오맵 API 사용 설정이 필요하다.
- 인증: 백엔드 설정/secret store에 REST API key를 두고 요청 헤더 `Authorization: KakaoAK ${REST_API_KEY}`를 사용한다.
- 주요 endpoint: `search/keyword`, `search/category`, `search/address`, `geo/coord2regioncode`, `geo/coord2address`, `geo/transcoord`
- 키워드 검색 파라미터: `query` 필수. `category_group_code`, `x`, `y`, `radius`, `rect`, `page`, `size`, `sort`를 사용한다. 지도 주변 정렬은 중심 좌표와 `sort=distance`를 함께 사용한다.
- 카테고리 검색 파라미터: `category_group_code` 필수. 중심 좌표(`x`, `y`, `radius`) 또는 사각 영역(`rect`)을 함께 사용한다.
- 장소 검색 응답은 `meta`와 `documents[]`로 구성된다. `meta.pageable_count`는 노출 가능 문서 수이며 최대 45다.
- 장소 후보 필드: `id`, `place_name`, `category_name`, `category_group_code`, `category_group_name`, `phone`, `address_name`, `road_address_name`, `x`, `y`, `place_url`, `distance`
- 좌표 순서: Kakao 응답의 `x`는 경도(`lng`), `y`는 위도(`lat`)다.
- 우선 사용할 카테고리 그룹: `AT4` 관광명소, `CT1` 문화시설, `AD5` 숙박, `FD6` 음식점, `CE7` 카페, `PK6` 주차장, `OL7` 주유소/충전소
- raw response는 query/page/location 단위 TTL cache로만 저장한다.
- 사용자가 후보를 선택해 저장하면 내부 place에는 provider 이름, provider place id, 사용자 표시명, 좌표, 정규화 주소, 상호명, 주소, 전화번호, 카테고리, 선택 시각 등 안정 필드를 남길 수 있다.
- `place_url`, 외부 카테고리 전체 문자열, 평점, 사진 URL은 상세 표시 또는 재조회용으로 취급하고, 장기 저장 여부는 구현 전 약관 검토 후 확정한다.
- 전체 카테고리를 광범위하게 순회하는 bulk crawler로 사용하지 않는다. 사용자 검색, 지도 viewport, 제한된 주변 후보 조회를 기본 패턴으로 둔다.

보완 필요:

- Kakao Local raw TTL. 기본 후보는 1~24시간 범위에서 결정
- `place_url`, 외부 카테고리 전체 문자열, 평점, 사진 URL의 장기 저장 여부
- 카테고리 그룹별 앱 노출 우선순위와 검색 query/radius 기본값
- Kakao 쿼터 초과 시 stale cache 표시 문구와 fallback 규칙

V-WORLD Geocoder 보수 규칙:

- Geocoder API 2.0은 실시간 조회용으로 취급한다.
- 기상청 관광코스 CSV의 위경도 → 주소 변환에는 V-WORLD Geocoder를 고정 provider로 사용한다.
- 이 흐름에서 V-WORLD Geocoder quota는 없는 것으로 취급한다.
- V-WORLD Geocoder 호출 실패는 provider call 단위로 최대 5회 retry한다. 이 retry 횟수는 데이터셋별 ETL retry 설정과 별개인 고정값이다.
- 5회 retry 후에도 실패하면 좌표, dataset key, source row number, 에러 유형, 마지막 응답 상태를 로그에 남긴다.
- 실패가 주소 매핑 품질이나 화면 표시 품질에 영향을 주면 관리자 UI 또는 관련 화면에 알림을 표시한다.
- Geocoder 응답 주소/결과 원문은 기본적으로 DB에 저장하지 않는다.
- 지오코딩 결과를 저장해야 하는 요구가 생기면 구현 전에 정책/약관을 재검토한다.
- 주소/행정구역/법정동코드 매핑은 Geocoder 저장 대신 Juso 주소 기준 테이블과 PostGIS point-in-polygon을 우선 사용한다.

## 10. Cache Policy

| 데이터 | 캐시 키 | TTL/Freshness |
| --- | --- | --- |
| weather_short_term | nx + ny + base_date + base_time | 30~60분 |
| weather_mid_term | reg_id + tm_fc | 12~24시간 |
| weather_rest_area | provider source id 또는 source coordinates + observed_at | 1~2시간 |
| fuel_avg_price | region_code + price_date + fuel_type | 8~12시간 |
| fuel_lowest_station | region_code + collected_at | 8~12시간 |
| rest_area_master | source snapshot date | 월 1회 |
| rest_area_oil_price | service area code + collected_at | 12~24시간 |
| rest_area_svcs | service area code + source snapshot date | 월 1회 |
| juso_road_address_korean | source year-month + file hash | 매월 10일 이후 |
| juso_related_jibun | source year-month + file hash | 매월 10일 이후 |
| kma_recommended_tour_course | source snapshot date + file hash | 연 1회 |
| kto_kor_tour_content | endpoint + saved_place_id 또는 좌표/지역 params + page + contentTypeId/filter | 사용자 조회 TTL cache, 저장 snapshot 장기 보존 |
| kto_related_tour_point | baseYm + areaCd + signguCd + keyword/page | 월 1회 |
| kto_tour_region_code | source snapshot date + file hash | 분기 1회 |
| kto_tour_legal_dong_code | ldongCode2 request params | 장기 cache, 명시적 refresh |
| kto_tour_category_code | source document version + file hash | 업데이트 주기 없음, 수동 교체 |
| kakao_local_place_search | provider + endpoint + query/category + center/rect + radius + page + sort | 1~24시간 |
| naver_search_local_reference | provider + query + display + start + sort | 1~6시간 |
| naver_search_blog_reference | provider + query + display + start + sort | 1~6시간 |
| naver_search_news_reference | provider + query + display + start + sort | 15분~6시간 |
| naver_search_encyclopedia_reference | provider + query + display + start | 1~7일 |
| naver_search_web_reference | provider + query + display + start | 1~24시간 |
| place provider | provider + query + search center + page | 1~24시간 |
| place_provider_stable_profile | provider + provider place id | 지속 저장 |
| place_provider_review | provider + provider place id + provider review id 또는 content hash | 3개월 |

## 11. Airflow Policy

- 모든 DAG는 idempotent 해야 한다.
- source, schedule, freshness target, retry policy, 저장 대상 테이블을 DAG에 명시한다.
- raw → serving(normalized) 단계를 분리한다.
- 동일 데이터가 존재하면 skip한다.
- 모든 ETL의 retry 간격, retry 횟수, 실패 임계치, 실패 알림 여부는 데이터셋별로 다르게 설정한다.
- 데이터셋별 ETL 설정의 기준은 백엔드 설정 파일이다. DB 값이나 관리자 페이지 입력값을 단일 진실원으로 두지 않는다.
- 데이터셋별 설정은 `dataset_key`, `schedule`, `retry_interval_minutes`, `retry_max_attempts`, `failure_count_threshold`, `row_error_rate_threshold`, `admin_page_alert_enabled`, `telegram_alert_enabled`, `is_enabled`를 포함한다.
- 설정 파일 변경은 배포 또는 서비스 reload 절차를 통해 반영한다.
- ETL retry 기본값은 데이터셋별 설정이 없을 때만 5분 간격 3회로 fallback한다.
- 실패 시 retry하되, stale serving 데이터 사용 가능 여부를 로그에 남긴다.
- 설정된 retry를 모두 소진하면 실패 로그를 남기고 관리자 로그인 시 표시할 알림을 생성한다.
- retry 소진 알림 중 시스템 에러/로그 정보는 관리자 권한 사용자 Telegram으로만 발송한다.
- 일반 권한 사용자의 Telegram에는 시스템 에러/로그 정보를 보내지 않는다.
- Telegram 알림 대상은 각 사용자 소유의 활성화·검증된 Telegram target을 사용한다.
- 관리자 권한 사용자에게 활성 Telegram target이 없으면 관리자 페이지 알림과 로그만 남긴다.
- 관리자 알림은 TripMate 관리자 페이지에서 조회한다.
- 관리자/권리자 권한 부여는 pgAdmin 등 DB 관리 도구로 직접 처리한다. 앱은 사용자 테이블 또는 권한 테이블의 구분 필드만 참조한다.
- 앱 UI에서 관리자 승격/강등 기능은 만들지 않는다.
- 수집 건수, 수집 윈도우, cache hit/miss, FK skip 건수와 별도 FK mismatch 로그파일 경로를 로그에 남긴다.
- ETL 실패, retry, skip, schema drift, FK mismatch, 관리자 알림 생성 로그는 명시적으로 삭제하기 전까지 무기한 보관한다.
- 로그 자동 만료 TTL은 두지 않는다. 삭제가 필요하면 별도 운영 절차로 수행하고 삭제 대상과 시각을 감사 로그에 남긴다.

Telegram 권한별 메시지 범위:

| 대상 | 여행 정보 | 여행 데이터 실패 메시지 | 시스템 에러/로그 |
| --- | --- | --- | --- |
| 관리자 권한 사용자 | 발송 | 발송 | 발송 |
| 일반 권한 사용자 | 발송 | 발송 | 발송하지 않음 |

- 여행 정보는 여행 일정, 장소, 날씨, 유가, 이동/준비 정보처럼 사용자가 여행 알림으로 기대하는 내용이다.
- 날씨, 유가, 주변 정보처럼 여행 정보에 포함되는 데이터 생성이 실패한 경우에는 해당 데이터 섹션을 누락하지 않고 사용자용 에러 메시지로 대체한다.
- 사용자용 에러 메시지는 조치 가능한 짧은 문구로 작성하고, dataset key, stack trace, raw response body, API key, token, 내부 로그 경로는 포함하지 않는다.
- 관리자 권한 사용자에게는 같은 여행 정보 메시지에 시스템 에러 요약과 로그 참조 정보를 함께 포함할 수 있다.
- 관리자용 시스템 에러/로그 정보에는 dataset key, DAG/run id, 실패 단계, retry 횟수, 마지막 오류 분류, stale serving 사용 여부, 내부 로그 참조 id 또는 경로를 포함할 수 있다.
- 관리자용 메시지에도 token 원문, API key, 원본 응답 body 전체는 포함하지 않는다.

데이터셋별 retry/실패 임계치 초기 설정:

아래 값은 DAG/task 수준의 retry 기본값이다. provider call 내부 retry가 별도로 확정된 경우에는 해당 provider 규칙을 따른다. 예를 들어 기상청 관광코스 CSV의 V-WORLD reverse geocoding 호출은 5회 retry 고정이다.
실제 운영값은 백엔드 설정 파일의 데이터셋별 설정을 따른다.
`failure_count_threshold`는 retry를 모두 소진한 DAG run이 몇 회 발생하면 운영 장애 상태로 볼지의 기본값이다. retry 소진 실패 로그와 관리자 알림은 임계치 도달 전에도 남긴다.

| dataset_key | 수집 주기 | retry 기본값 | `failure_count_threshold` 기본값 | 실패 알림 |
| --- | --- | --- | --- | --- |
| `weather_short_term` | 30분 | 5분 간격 3회 | 3회 | 관리자 페이지 + 관리자 Telegram. 여행 알림에서는 사용자용 에러 메시지 |
| `weather_mid_term` | 12시간 | 10분 간격 3회 | 2회 | 관리자 페이지 + 관리자 Telegram. 여행 알림에서는 사용자용 에러 메시지 |
| `weather_rest_area` | 1시간 | 5분 간격 3회 | 3회 | 관리자 페이지 + 관리자 Telegram. 여행 알림에서는 사용자용 에러 메시지 |
| `fuel_avg_price` | 하루 3회 | 5분 간격 3회 | 3회 | 관리자 페이지 + 관리자 Telegram. 여행 알림에서는 사용자용 에러 메시지 |
| `fuel_lowest_station` | 하루 3회 | 5분 간격 3회 | 3회 | 관리자 페이지 + 관리자 Telegram. 여행 알림에서는 사용자용 에러 메시지 |
| `fuel_region_code` | 3달 1회 | 30분 간격 3회 | 1회 | 관리자 페이지 + 관리자 Telegram |
| `administrative_boundary` | 월 1회 | 30분 간격 3회 | 1회 | 관리자 페이지 + 관리자 Telegram |
| `juso_road_address_korean` | 매월 10일 이후 | 5분 간격 3회 | 1회 | 관리자 페이지 + 관리자 Telegram |
| `juso_related_jibun` | 매월 10일 이후 | 5분 간격 3회 | 1회 | 관리자 페이지 + 관리자 Telegram |
| `rest_area_master` | 월 1회 | 30분 간격 3회 | 1회 | 관리자 페이지 + 관리자 Telegram |
| `rest_area_oil_price` | 12시간 | 10분 간격 3회 | 2회 | 관리자 페이지 + 관리자 Telegram. 여행 알림에서는 사용자용 에러 메시지 |
| `rest_area_svcs` | 월 1회 | 30분 간격 3회 | 1회 | 관리자 페이지 + 관리자 Telegram |
| `kma_recommended_tour_course` | 연 1회 | 30분 간격 3회 | 1회 | 관리자 페이지 + 관리자 Telegram. 여행 알림에서는 사용자용 에러 메시지 |
| `kto_kor_tour_content` | 사용자 조회/cache miss | Airflow retry 대상 아님. adapter retry와 UI 오류 처리 | 해당 없음 | UI 오류 + 로그 |
| `kto_related_tour_point` | 월 1회 | 10분 간격 3회 | 1회 | 관리자 페이지 + 관리자 Telegram |
| `place_provider_retention_cleanup` | 매일 | 10분 간격 3회 | 3회 | 관리자 페이지 + 관리자 Telegram |

## 12. Validation Checklist

공통:

- schema drift 감지
- 중복 row 방지
- key 필드 누락 감지
- 응답 일부 실패 처리
- retry/idempotency
- freshness 만료 처리
- 데이터셋별 백엔드 설정 파일값에 따른 ETL retry 간격/횟수/실패 임계치 적용
- retry 소진 후 실패 로그, 관리자 로그인 알림, 관리자 Telegram 시스템 알림 생성
- ETL 실패, retry, skip, schema drift, FK mismatch 로그가 명시적 삭제 전까지 자동 만료되지 않는지 확인
- 일반 권한 사용자 Telegram에는 여행 정보만 발송되고 시스템 에러/로그가 포함되지 않는지 확인
- 여행 정보에 포함되는 데이터 실패 시 일반 권한 사용자에게 데이터 대신 사용자용 에러 메시지가 발송되는지 확인
- 관리자 권한 사용자의 여행 알림에는 여행 정보와 시스템 에러/로그 요약이 함께 포함될 수 있는지 확인
- 관리자/권리자 구분 필드가 없는 사용자는 ETL 설정/알림 화면 접근 불가

공간:

- SRID 확인
- 좌표 순서 확인
- invalid geometry
- point-in-polygon 경계 케이스
- 주소 저장 테이블의 `road_address_management_no`, `legal_dong_code`, `road_name_code`, `administrative_dong_code` 동반 저장 확인

Juso 주소 TXT:

- 압축 파일 안의 전체분/관련지번 TXT 2종 존재 여부 확인
- 압축 파일명 `[YYYY][MM]_도로명주소 한글_전체분.zip` 확인
- 내부 파일명 `rnaddrkor_*.txt`, `jibun_rnaddrkor_*.txt` 확인
- source year-month, file hash, row number 기록 확인
- `road_address_management_no`, `legal_dong_code`, `road_name_code`, `administrative_dong_code`를 문자열로 저장하는지 검증
- 전체분 PK 조합과 관련지번 PK 조합 중복 검증
- 관련지번의 `road_address_management_no`가 전체분과 연결되는지 검증
- 전체분 24개 필드와 관련지번 14개 필드 순서 검증
- `change_reason_code`를 raw/staging metadata로만 쓰고 serving/code에는 최신 유효 주소만 남기는지 검증
- 폐지 주소와 변경 이전 주소 코드가 serving/code 기준 테이블에서 삭제되는지 검증
- 폐지 주소가 신규 UI 주소 검색 결과에서 숨겨지는지 검증
- 같은 전체 파일 재처리 idempotency 검증
- 실행일이 DB의 여행계획 날짜에 포함될 때 serving 교체 skip 검증
- 10일 이후 DB의 어떤 여행계획 날짜에도 포함되지 않는 첫 날짜에 업데이트되는지 검증
- 지오코딩 결과가 주소 기준 key 중 하나 이상에 연결되는지 검증
- 여행 장소 저장 시 주소 FK가 nullable이고 저장 당시 주소 snapshot으로 조회 가능한지 검증

휴게소:

- pagination 종료 조건
- 100개 초과 요청 방지
- master와 oil/svcs join 실패 처리
- weather_rest_area가 rest_area_master와 매칭되지 않는지 schema/API 확인

관광코스:

- CSV `cp949`/`ms949` decoding과 UTF-8 내부 문자열 정규화 확인
- CSV delimiter 확인
- 필수 좌표/명칭/category 필드 누락 감지
- `theme_category_code`, `theme_name` 원본 보존 확인
- `TH05`/`종교/역사/전통` → `religion_history_tradition` mapping 확인
- 알 수 없는 `theme_category_code`가 `theme_category=unknown`으로 적재되고 schema drift 로그가 남는지 확인
- `경도(도)` → `lng`, `위도(도)` → `lat` 좌표 순서 확인
- 원본 file hash와 snapshot date 기록
- reverse geocoding provider가 V-WORLD로 고정되어 있는지 확인
- V-WORLD quota 설정을 요구하지 않는지 확인
- V-WORLD 호출 실패 시 provider call 단위 5회 고정 retry, 실패 로그, 필요 시 UI 알림 생성 확인
- V-WORLD reverse geocoding 응답 원문 장기 미저장 확인
- V-WORLD reverse geocoding 주소가 Juso 주소 기준 key 매핑 입력값으로만 쓰이는지 확인
- `road_address_management_no`, `legal_dong_code`, `road_name_code`, `administrative_dong_code` 우선순위 매핑 검증
- 주소 매칭 실패 시 주소 FK nullable과 저장 당시 주소 snapshot 보존 확인
- 주소 문자열 기반 fuzzy matching 미수행 확인
- “기상청 추천 여행코스” marker source 구분값 확인
- 마커 색상/아이콘이 `theme_category` 기준으로 선택되고 `unknown`은 기본 marker style을 쓰는지 확인
- 마커 상세에서 같은 `테마분류` 목록 링크와 `코스순서` 정렬 기준 전달 확인

KTO TourAPI:

- `resultCode`, `resultMsg`, `totalCount`, pagination 종료 조건 확인
- `contentid`, `contenttypeid`, `modifiedtime`, `showflag` 필수성 확인
- `mapx`/`mapy` 좌표 순서와 WGS84 취급 확인
- 저장한 장소 좌표 기준 `locationBasedList2` 호출 시 `radius=15000` 적용 확인
- geocode 주소의 시도/시군구를 KTO 지역/시군구 코드로 변환해 `areaBasedList2`를 호출하는지 확인
- `locationBasedList2`와 `areaBasedList2` 결과를 함께 보여주고 중복 `contentid`를 UI에서 병합 표시하는지 확인
- 사용자가 KTO 후보를 저장하면 TripMate 여행지 DB와 KTO snapshot이 생성되는지 확인
- KTO 조회 응답의 모든 return field가 raw/serving/snapshot에 보존되는지 확인
- `ldongCode2` 법정동코드조회 API 결과 cache hit/miss와 장기 cache 동작 확인
- `contentTypeId`와 `lclsSystm1/2/3` 코드 mapping 검증
- `신분류체계정보 관광타입정보 연계 정의서.xlsx` 전체 row가 `tour_code_kto_category`에 적재되는지 검증
- `tour_code_kto_category`에 자동 업데이트 주기가 없는지 검증
- `cpyrhtDivCd`별 이미지/텍스트 표시 정책 준수
- TourAPI 지역/시군구 코드를 `legal_dong_code`로 오인하지 않는지 검증
- `kto_related_tour_point`를 내부 place와 자동 병합하지 않는지 검증

Kakao Local:

- REST API key 누락, 쿼터 초과, timeout, retry 처리 확인
- `x`는 `lng`, `y`는 `lat`으로 저장하는지 검증
- `page`, `size`, `radius`, `rect`, `sort` 파라미터 경계값 검증
- `meta.is_end`, `pageable_count` 기반 pagination 종료 검증
- raw response 장기 저장 금지와 TTL 만료 처리 검증

Naver Search:

- Client ID/Secret 누락, 403 권한 오류, 일 호출 한도 초과 대응 확인
- endpoint별 `display`, `start`, `sort` 경계값 검증
- Local Search는 `display` 1~5, `start=1`, `sort=random|comment` 검증
- Blog/News Search는 `display` 1~100, `start` 1~1000, `sort=sim|date` 검증
- Encyclopedia/Web Search는 `display` 1~100, `start` 1~1000 검증
- UTF-8 query encoding 검증
- `title`, `description` 등 HTML 문자열의 `<b>` 태그 sanitization 검증
- Local `mapx`, `mapy`를 앱 `lat`, `lng`로 쓰기 전 좌표계/단위 변환과 검증을 수행하는지 확인
- Local 사용자가 선택한 후보만 내부 place 안정 필드로 승격되는지 검증
- Blog/News/Encyclopedia/Web 검색 결과를 장기 장소 데이터베이스로 저장하지 않는지 검증
- endpoint별 TTL 만료와 cache key 분리 검증

정책:

- Kakao/Naver/Google 등 일반 장소 provider raw response 전체 장기 저장 금지
- Kakao/Naver/Google 안정 필드인 상호명, 주소, 전화번호 지속 저장 허용
- provider 리뷰 3개월 보존과 미사용 provider place cleanup ETL 준수
- KTO `KorService2`는 공공 관광정보 원천으로서 이 문서에 명시된 return field 전체 저장 예외 적용
- V-WORLD Geocoder 응답 저장 금지
- Google/Naver/Kakao 보수 규칙 준수

## 13. 법정동코드 기준 데이터 최신 결정

### 13.1 canonical source

`address_code_standard`의 canonical source는 공공데이터포털 `국토교통부_전국 법정동` 파일데이터로 한다.

- URL: https://www.data.go.kr/data/15063424/fileData.do
- 데이터명: `국토교통부_전국 법정동`
- 현재 관측 파일명: `국토교통부_전국 법정동_20250807`
- 형식: CSV
- 필드: `법정동코드`, `시도명`, `시군구명`, `읍면동명`, `리명`, `순위`, `생성일자`, `삭제일자`, `과거법정동코드`
- 다운로드 방식: 상세 페이지 HTML의 JSON-LD `contentUrl`을 추출해 CSV를 직접 다운로드한다.

기존 VWorld `LSCT_LAWDCD.zip`의 3컬럼 CSV는 legacy/manual fallback으로만 둔다.

### 13.2 기존 VWorld CSV와 data.go.kr CSV 차이

VWorld `LSCT_LAWDCD.zip`:

- 필드가 `법정동코드`, `법정동명`, `폐지여부`뿐이다.
- `존재`/`폐지` 상태만 알 수 있다.
- 생성일자, 삭제일자, 과거법정동코드가 없어 장기 FK 관리와 변경 추적이 약하다.

data.go.kr `국토교통부_전국 법정동`:

- 시도/시군구/읍면동/리 분리 필드를 제공한다.
- `생성일자`, `삭제일자`, `과거법정동코드`를 제공한다.
- `삭제일자`가 비어 있으면 active, 값이 있으면 deleted로 처리한다.
- TripMate의 장기 주소 코드 기준으로 더 적합하다.

### 13.3 schedule

- 수집 주기: 3개월 1회
- 권장 실행: 2월/5월/8월/11월 15일 04:30 KST
- 실패 시 retry interval/count는 데이터셋별 ETL 설정 파일에서 관리한다.
- backend loader는 최신 CSV 다운로드와 적재 함수를 제공한다.
- Airflow DAG는 `dags/legal_dong_code_standard.py`에 있으며 `legal_dong_code_standard_quarterly`로 등록된다.
- DAG schedule은 `30 4 15 2,5,8,11 *`이고, Airflow timezone은 운영 환경에서 `Asia/Seoul`로 맞춘다.

### 13.4 schema and FK policy

- `address_code_standard.legal_dong_code`는 PK이며 물리 삭제하지 않는다.
- 최신 다운로드에서 누락된 코드는 `is_active=false`, `is_discontinued=true`, `source_status='missing_from_latest_download'`로 유지한다.
- 삭제일자가 있는 코드는 `is_active=false`, `is_discontinued=true`, `source_status='deleted'`로 유지한다.
- 이 정책은 Juso 주소, VWorld SHP, 여행 장소, geocoding snapshot FK가 업데이트 중 깨지지 않게 하기 위한 것이다.

추가 보존 필드:

- `source_sort_order`
- `source_created_date`
- `source_deleted_date`
- `previous_legal_dong_code`

### 13.5 VWorld SHP relationship

- VWorld SHP serving row는 `region_serving_boundary.address_code_standard_code`로 `address_code_standard.legal_dong_code`를 nullable FK 참조한다.
- exact code match를 우선한다.
- data.go.kr 기준에서는 시도 SHP의 세종특별자치시 `BJCD=3600000000`이 exact match 된다.
- legacy code table처럼 `3600000000`이 없고 `3611000000`만 있는 경우에는 시도 레이어에서만 이름 정규화 fallback을 사용한다.

### 13.6 verification

2026-04-25에 data.go.kr 페이지에서 직접 다운로드한 CSV를 확인했다.

- file size: 3,799,696 bytes
- parsed rows: 49,878
- active rows: 20,556
- deleted rows: 29,322
- temp PostgreSQL load: `address_code_standard` 49,878 rows, `address_raw_legal_dong_code` 49,878 rows

## 14. 남은 일

### 14.1 의사결정 필요

- DS-009: KTO `KorService2` HTML sanitization 기준, `cpyrhtDivCd`별 저작권/출처 표기 방식, 실제 계정 기준 OpenAPI 호출 한도 확인
- DS-010: `TarRlteTarService1` 연관관광지 후보를 UI 추천으로 노출할지, 내부 랭킹 신호로만 쓸지 결정
- DS-011: `TarRlteTarService1` `baseYm` 최신 기준월 관리 방식 결정. 자동 탐색, 운영 설정값, 또는 수동 갱신 중 선택
- DS-012: Naver Search endpoint별 UI 노출 범위, TTL, 출처 표기, query 템플릿 확정
- DS-013: Kakao/Naver/Google provider별 raw cache TTL, stale 표시 문구, 리뷰 cleanup ETL 세부 동작 확정

### 14.2 구현 준비 TODO

- `weather_short_term`: `weather_short_term_grid_mapping`, category code mapping, raw/serving schema, `nx + ny + base_date + base_time` cache key 구현
- `weather_mid_term`: `kma_mid_land_region_mapping`, `kma_mid_temperature_region_mapping`, fallback metadata, raw/serving schema 구현
- `weather_rest_area`: 실제 응답 샘플 기준 필드명과 좌표계 확인
- `fuel_avg_price`: pyopinet `NormalizedFuelAverage` 기반 provider code/name 보존, 내부 유종 enum mapping, `Asia/Seoul` 기준 날짜 정규화 adapter 구현 완료. 남은 일은 raw/serving schema와 DB 적재 구현이다.
- `fuel_lowest_station`: pyopinet `NormalizedFuelStation` 기반 TOP20/주변 주유소 adapter, station id, 좌표, 주소, provider code/name, 선택적 가격 기준시각 보존 구현 완료. 남은 일은 raw/serving schema와 DB 적재 구현이다.
- `fuel_region_code`: pyopinet `NormalizedFuelRegionCode` 기반 시도/시군구 code adapter와 시도 prefix 법정동 매핑 구현 완료. 남은 일은 `fuel_region_legal_dong_mapping` DB schema와 시군구 상세 매핑 적재 구현이다.
- `etl_dataset_config`: 데이터셋별 schedule, retry 간격/횟수, 실패 임계치, 관리자 페이지 알림 여부, Telegram 알림 여부를 담는 백엔드 설정 파일 schema와 loader 구현
- `etl_admin_notifications`: retry 소진/skip/실패 알림을 관리자 로그인 시 표시하는 알림 테이블 구현
- `etl_telegram_notifications`: retry 소진 실패를 관리자 권한 사용자 Telegram target으로 발송하고, 일반 권한 사용자에게는 시스템 에러/로그를 보내지 않는 작업 구현
- `trip_telegram_notifications`: 여행 정보 메시지 생성 시 날씨/유가/주변 정보 데이터 실패 구간을 사용자용 에러 메시지로 대체하고, 관리자 권한 사용자에게는 시스템 에러/로그 요약을 함께 포함하는 로직 구현
- `user_privileged_flag`: pgAdmin 등으로 부여할 관리자/권리자 구분 필드 추가. 앱에서는 승격/강등 UI를 만들지 않음
- `administrative_boundary`: V-WORLD SHP raw EPSG:5186 적재와 serving EPSG:4326 변환 파이프라인 구현
- `legal_dong_boundary`: 법정동 단위 SHP raw EPSG:5186 적재와 serving EPSG:4326 변환, `legal_dong_code` 기반 point-in-polygon 구현
- `juso_road_address_korean`: 매월 10일 이후 전체 주소 ZIP 다운로드, `rnaddrkor_*.txt` raw/staging/serving 교체, code 문자열 보존, 주소 저장 테이블 공통 FK/검증 정책 구현
- `juso_related_jibun`: 매월 10일 이후 `jibun_rnaddrkor_*.txt` raw/serving 적재, 도로명주소관리번호 연계 구현
- `place`/주소 저장 도메인: 주소 FK nullable 설계와 저장 당시 주소 snapshot 필드 구현
- `rest_area_master`: pykex `KexClient.restarea.route_facilities()` 계약 테스트 완료. 남은 일은 raw 전체 row snapshot, serving 안정 필드, 월 1회 snapshot 정책 구현이다.
- `rest_area_oil_price`: pykex `KexClient.restarea.fuel_prices()` 계약 테스트 완료. 남은 일은 raw 전체 row snapshot, serving 안정 필드, 가격 기준시각 정책, 유종별 row 전개, 내부 유종 enum 구현이다.
- `rest_area_svcs`: pykex `KexClient.restarea.convenience_facilities()` raw row 계약 테스트 완료. 남은 일은 실제 응답 샘플 기반 schema 승격 여부 결정, raw 전체 row snapshot, serving 안정 필드, provider 편의시설 코드/명칭 보존, 한국어 표시명 mapping 구현이다.
- `kma_recommended_tour_course`: 확정 serving 필드, `theme_category_code` 원본 보존, 내부 `theme_category` enum mapping, `unknown` fallback, `cp949`/`ms949` CSV decoding, raw CSV row, file hash, EPSG:4326 `lat`/`lng`, V-WORLD reverse geocoding, Juso 주소 기준 key 매핑 구현
- `vworld_reverse_geocoding`: quota 설정 없이 호출하고, provider call 실패 시 5회 고정 retry, 실패 로그, 필요 시 UI 알림을 남기는 adapter 구현
- `kma_recommended_tour_course` UI: “기상청 추천 여행코스” marker source style 구분값, 같은 `테마분류` 목록 링크, `코스순서` 정렬 구현
- `kto_kor_tour_content`: 저장 장소 좌표 기반 `locationBasedList2` 반경 15km 조회, geocode 주소 기반 `areaBasedList2` 조회, 결과 UI 표시, 사용자 저장 시 여행지 DB 추가와 KTO return field 전체 snapshot 저장 구현
- `kto_related_tour_point`: `TarRlteTarService1` raw/serving schema, `baseYm` snapshot, 지역 코드 적재 구현
- `kto_tour_region_code`: geocode 주소의 시도/시군구를 `areaBasedList2` 입력 코드로 변환하는 KTO 지역/시군구 코드 테이블 구현
- `kto_tour_legal_dong_code`: `ldongCode2` 법정동코드조회 API cache 테이블과 cache hit/miss 처리 구현
- `kto_tour_category_code`: `신분류체계정보 관광타입정보 연계 정의서.xlsx` 전체 DB 적재와 수동 교체 절차 구현
- `place_provider_cache`: Kakao 우선 adapter와 TTL 캐시 구현, Naver Local은 보조 후보로 확장, Google은 정책 검토 후 확장
- `place_provider_stable_profile`: Kakao/Naver/Google에서 얻은 상호명, 주소, 전화번호 안정 필드 지속 저장 구현
- `place_provider_review`: provider 리뷰 3개월 보존 정책과 stale 표시 구현
- `place_provider_retention_cleanup`: 여행계획 어디에도 포함되지 않은 provider place의 리뷰/비안정 부가정보를 마지막 참조 3개월 후 삭제하는 daily ETL 구현
- `kakao_local_place_search`: keyword/category/address/coord adapter, cache key, normalized candidate schema 구현
- `naver_search_local_reference`: Local Search adapter, 좌표 변환/검증, sanitized reference schema, TTL cache 구현
- `naver_search_blog_reference`: Blog Search adapter, sanitized reference schema, TTL cache 구현
- `naver_search_news_reference`: News Search adapter, sanitized reference schema, TTL cache 구현
- `naver_search_encyclopedia_reference`: Encyclopedia Search adapter, sanitized reference schema, TTL cache 구현
- `naver_search_web_reference`: Web Search adapter, sanitized reference schema, TTL cache 구현

### 14.3 검증 TODO

- 모든 OpenAPI/CSV parser에 schema drift와 필수 key 누락 테스트 추가
- raw → serving 변환 idempotency 테스트 추가
- cache hit/miss와 stale-cache fallback 테스트 추가
- 데이터셋별 백엔드 설정 파일값 기반 ETL retry 간격/횟수/실패 임계치 적용 테스트 추가
- retry 소진 후 실패 로그, 관리자 로그인 알림, 관리자 Telegram 시스템 알림 생성 테스트 추가
- 일반 권한 사용자 Telegram에는 시스템 에러/로그가 포함되지 않는지 테스트 추가
- 여행 정보 포함 데이터 실패 시 데이터 대신 사용자용 에러 메시지가 발송되는지 테스트 추가
- 관리자 권한 사용자의 여행 알림에는 여행 정보와 시스템 에러/로그 요약이 함께 포함되는지 테스트 추가
- 관리자/권리자 구분 필드 기반 관리자 페이지 접근 제어와 Telegram 알림 대상 선정 테스트 추가
- OpiNet pyopinet `AreaCode` helper 재사용 단위 테스트 추가 완료. 남은 일은 DB mapping table 테스트다.
- OpiNet API 실패 시 관리자 ETL retry 설정을 적용하고 기본값은 5분 간격 3회로 동작하는 테스트 추가
- OpiNet 평균가/최저가 adapter의 원/L 가격, 날짜 정규화, provider code/code name 보존 테스트 추가 완료. 남은 일은 raw/serving DB persistence 테스트다.
- 유종 enum `gasoline`/`premium_gasoline`/`diesel`/`lpg`와 provider code/code name 보존 단위 테스트 추가 완료.
- PostGIS point-in-polygon 경계 테스트 추가
- 법정동 경계 polygon SRID, invalid geometry, point-in-polygon, `legal_dong_code` 매핑 테스트 추가
- 휴게소 oil/svcs FK 불일치 skip과 별도 JSONL 로그파일 생성 테스트 추가
- `weather_rest_area`가 `rest_area_master`와 매칭되지 않는지 schema/API 테스트 추가
- 관광코스 CSV `cp949`/`ms949` decoding, delimiter, 좌표 순서, V-WORLD reverse geocoding 원문 미저장 테스트 추가
- 관광코스 serving 필드 타입/nullable, `theme_category_code` 원본 보존, 내부 `theme_category` enum mapping, `unknown` fallback 테스트 추가
- 관광코스 V-WORLD reverse geocoding 5회 고정 retry, 실패 로그, 필요 시 UI 알림 생성 테스트 추가
- 관광코스 V-WORLD reverse geocoding 주소 → Juso 주소 기준 key 매핑 우선순위와 매칭 실패 시 nullable FK/snapshot 보존 테스트 추가
- 관광코스 marker source style 구분값과 같은 `테마분류` 목록 링크/`코스순서` 정렬 테스트 추가
- 주소 저장 테이블이 `road_address_management_no`, `legal_dong_code`, `road_name_code`, `administrative_dong_code`를 함께 저장하는지 schema 검증 추가
- Juso 주소 TXT 전체분 24개 필드/관련지번 14개 필드 parser의 필드 순서, 문자열 보존, 이동사유코드 처리 테스트 추가
- Juso 전체 파일 교체가 원자적으로 수행되고 10일에 여행 일정이 있으면 serving 교체를 skip하는 테스트 추가
- 10일 이후 여행 계획이 없는 첫 날짜에 Juso 업데이트가 수행되는 테스트 추가
- 장소 저장 시 주소 FK가 사라져도 주소 snapshot으로 조회되는 테스트 추가
- Kakao/Naver/Google 등 일반 장소 provider raw response 전체 장기 저장 금지 정책 테스트 또는 schema 검증 추가
- Kakao/Naver/Google 안정 필드인 상호명, 주소, 전화번호 지속 저장 schema 검증 추가
- provider 리뷰 3개월 보존, stale 표시, 여행계획 미포함 3개월 후 cleanup ETL 테스트 추가
- KTO `KorService2` return field 전체 저장 예외가 KTO 테이블과 여행지 snapshot에만 적용되는지 schema 검증 추가
- KTO `locationBasedList2` 반경 15km 조회, `areaBasedList2` 시도/시군구 코드 조회, 중복 `contentid` 병합 표시 테스트 추가
- KTO 후보 저장 시 여행지 DB row와 KTO return field 전체 snapshot이 생성되는지 테스트 추가
- KTO `ldongCode2` 법정동코드조회 API cache hit/miss와 장기 cache 테스트 추가
- KTO `contentTypeId`, `lclsSystm`, `lDongRegnCd/lDongSignguCd` 코드 mapping 테스트 추가
- KTO `신분류체계정보 관광타입정보 연계 정의서.xlsx` 전체 적재와 자동 업데이트 미수행 테스트 추가
- KTO 이미지/텍스트 `cpyrhtDivCd` 정책 검증 테스트 추가
- `kto_related_tour_point`가 좌표/명칭 기반 자동 병합을 수행하지 않는지 검증 추가
- Kakao Local 좌표 순서, pagination, raw TTL, 쿼터 fallback 테스트 추가
- Naver Search Local/Blog/News/Encyclopedia/Web endpoint별 파라미터 경계값, HTML sanitization, TTL 만료 테스트 추가
- Naver Local 좌표 변환/검증과 사용자 선택 후보의 내부 place 안정 필드 승격 테스트 추가
- Naver Blog/News/Encyclopedia/Web 결과가 참고 링크 TTL cache로만 남는지 검증 추가
