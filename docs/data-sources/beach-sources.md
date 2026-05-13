# 해수욕장 통합 데이터 소스

이 문서는 해수욕장 전용 ETL 인수인계 문서다. 일반 장소(`places`)나 축제(`tour_serving_public_cultural_festival`)와 생명주기가 다르므로, 통합 해수욕장 도메인 테이블(`beach_*`)을 기준으로 조회한다. 기상청 해수욕장 날씨 카탈로그는 기존 `places`, `weather_beach_location`, `weather_serving_beach`에도 저장되지만, 통합 조회를 위해 `beach_profiles`와 `beach_provider_refs`로 동기화한다.

확인일: 2026-04-28 KST

## 공통 보안/저장 원칙

- 인증키 원문은 코드, 문서, DB raw payload, ETL 로그, 실패 알림에 저장하지 않는다.
- KHOA 관측 API는 `TRIPMATE_KHOA_API_KEY`를 사용한다.
- data.go.kr gateway로 이전된 KHOA 생활해양예보지수 v2 API는 `TRIPMATE_KHOA_API_KEY`가 있으면 우선 사용하고, 없으면 `TRIPMATE_DATA_GO_SERVICE_KEY`를 fallback으로 사용한다.
- 해양수산부 data.go.kr 계열은 `TRIPMATE_MOF_BEACH_SERVICE_KEY`를 우선 사용하고, 없으면 `TRIPMATE_DATA_GO_SERVICE_KEY`를 fallback으로 사용한다.
- 모든 좌표는 EPSG:4326, 순서 `longitude`, `latitude`로 저장한다.
- 법정동은 V-WORLD 법정동 serving 경계 기준 `ST_Covers`를 우선 사용한다.
- 해수욕장 좌표가 해상/모래사장에 찍혀 polygon 밖일 수 있으므로 실패 시 약 5km 이내 가장 가까운 법정동을 `postgis_nearest_boundary_5km`로 보조 매핑한다.
- 도로명주소코드와 도로명주소관리번호는 같은 법정동 안에서 Juso 건물명(`sigungu_building_name` 또는 `building_registry_name`)이 해수욕장명과 정확히 1건 일치할 때만 채운다.
- 좌표만으로 도로명주소코드나 도로명주소관리번호를 추정 생성하지 않는다.

## 구현 파일

| 구분 | 파일 |
| --- | --- |
| 모델 | `apps/api/app/models/beach.py` |
| 마이그레이션 | `apps/api/alembic/versions/20260428_0020_beach_domain_tables.py` |
| ETL loader/client | `apps/api/app/etl/beach/sources.py` |
| Dagster job | `apps/api/app/dagster_etl/registry.py` |
| 공개 조회 API | `apps/api/app/api/routes/public.py` |
| 응답 스키마 | `apps/api/app/schemas/public.py` |
| 테스트 | `apps/api/tests/test_beach_source_loader.py` |

## 통합 DB 구조

### `beach_profiles`

해수욕장 통합 프로필이다. 사용자 여행계획에 추가될 수 있는 “해수욕장 리소스”의 기준 row다. 일반 장소 DB와는 별도이지만, 기상청 카탈로그처럼 이미 지도 객체로 승격된 원천은 `map_feature_id`로 느슨하게 연결한다.

주요 컬럼:

- `id`: 내부 UUID
- `canonical_key`: 이름과 좌표 기반 내부 중복 방지 key
- `display_name`, `normalized_name`
- `map_feature_id`: nullable. 기존 표준 지도 객체와 연결할 때만 사용
- `representative_provider`, `representative_dataset_key`
- `longitude`, `latitude`, `geom`
- `legal_dong_code`, `sigungu_code`, `sido_code`
- `road_name_code`, `road_address_management_no`, `road_address`
- `address_snapshot`, `address_mapping_method`
- `beach_width_m`, `beach_length_m`, `beach_material`
- `homepage_url`, `homepage_name`, `image_url`, `emergency_contact`
- `source_specific_attributes`: source-specific 보조 필드
- `collected_at`, `is_active`

### `beach_provider_refs`

원천별 식별자를 통합 해수욕장에 연결한다.

- unique: `provider + provider_dataset_key + provider_beach_id`
- 예: KHOA `BCH001`, KMA `beach_num`, 해양수산부 `num` 또는 이름/좌표 hash

### `beach_source_records`

원천 raw snapshot을 보존한다.

- unique: `provider + dataset_key + source_record_id + response_hash`
- `request_params`는 인증키를 `***`로 마스킹해 저장한다.

### `beach_observations`

KHOA 해수욕장 최신 관측자료를 저장한다.

- unique: `provider + provider_beach_id + observed_at`
- 수온, 파고, 풍속, 풍향, 조석, day1/day2/day3 상태를 저장한다.

### `beach_index_forecasts`

KHOA 해수욕지수 예측 정보를 저장한다.

- unique: `provider + provider_dataset_key + beach_id + forecast_date + forecast_slot`
- 해수욕점수, 총지수, 최고파고, 평균수온, 평균기온, 최고풍속을 저장한다.

### `beach_water_quality_measurements`

해양수산부 해수욕장 수질 적합 여부를 저장한다.

- unique: `provider + source_record_key`
- 조사연도, 조사일자, 회차, 지점, 대장균/장구균 결과, 적합 여부를 저장한다.

## 통합 조회 API

### `GET /public/beaches`

TripMate serving DB에 저장된 해수욕장 통합 목록을 조회한다. 외부 API를 실시간 호출하지 않는다.

Query parameter:

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `sido_code` | 선택 | 시도 법정동 상위 코드 |
| `sigungu_code` | 선택 | 시군구 법정동 상위 코드 |
| `query` | 선택 | 해수욕장명 부분 검색 |
| `limit` | 선택 | 1~300, 기본 100 |
| `offset` | 선택 | 기본 0 |

응답은 각 해수욕장마다 기본 프로필, 원천 provider 목록, 최신 KHOA 관측값, 최신 수질 적합 여부, 향후 해수욕지수 예측, 연결된 KMA 해수욕장 날씨 요약을 포함한다.

### `GET /public/beaches/map-markers`

좌표가 있는 해수욕장을 지도 레이어용 마커로 조회한다.

### `GET /public/beaches/{beach_id}`

단일 해수욕장 통합 상세를 조회한다.

## 1. KHOA 해수욕장 정보

### 기본 정보

| 항목 | 값 |
| --- | --- |
| dataset key | `khoa_beach_observation` |
| 설명 URL | `https://www.khoa.go.kr/oceandata/openapi/openApiDetail.do?id=36&searchCondition=title&searchKeyword=%ED%95%B4%EC%88%98%EC%9A%95&pageNumber=1` |
| API URL | `https://khoa.go.kr/oceandata/api/beach/search.do` |
| 메타데이터 URL | `https://www.khoa.go.kr/oceandata/openapi/getOpenApiInfo.do` (`id=36` POST) |
| API 제목 | 해수욕장 정보 |
| 설명 | 해수욕장별 최신 관측자료(수온, 풍향/풍속)를 제공 |
| API 생성일 | 2025-03-01 |
| API 수정일 | 2025-03-01 |
| 공식 갱신주기 | 상시 |
| 사용자 제공 quota | 10,000건/일 |
| 구현 주기 | 매일 06:20, 18:20 |
| 예상 호출량 | 메타데이터 1회 + 관측소 약 356건/시간. 일 8,544건 수준으로 10,000건/일 미만 |
| 인증 환경변수 | `TRIPMATE_KHOA_API_KEY` |

### 요청 파라미터

| 이름 | 필수 | 구현값/예시 | 설명 |
| --- | --- | --- | --- |
| `DataType` | 필수 | `beach` | API 샘플 기준 고정 |
| `ServiceKey` | 필수 | 환경변수 | KHOA 인증키. 저장 시 `***`로 마스킹 |
| `BeachCode` | 필수 | `BCH001` | 해수욕장 코드. 메타데이터의 `observatoryList.id` |
| `ResultType` | 필수 | `json` | `json` 또는 `xml` |

### 출력 파라미터

| 이름 | 저장 컬럼 | 설명 |
| --- | --- | --- |
| `beach_code` | `beach_observations.provider_beach_id` | KHOA 해수욕장 코드 |
| `beach_name` | `beach_profiles.display_name` 보조 | 해수욕장명 |
| `obs_post_name` | `beach_observations.observation_station_name` | 관측소명 |
| `obs_time` | `beach_observations.observed_at` | 관측 시각. KST timezone-aware datetime |
| `tide` | `beach_observations.tide` | 조석 상태 |
| `wave_height` | `beach_observations.wave_height_m` | 파고(m) |
| `water_temp` | `beach_observations.water_temperature_c` | 수온(섭씨) |
| `wind_speed` | `beach_observations.wind_speed_ms` | 풍속(m/s) |
| `wind_direct` | `beach_observations.wind_direction` | 풍향 |
| `obs_last_req_cnt` | `beach_observations.quota_snapshot` | provider가 응답하는 호출량 스냅샷 |
| `day1_am_status` 등 | `beach_observations.forecast_status` | day1/day2/day3 오전/오후 상태 JSON |

### 내부 처리

1. 메타데이터 AJAX에서 `observatoryList`를 읽어 해수욕장 코드, 이름, 좌표를 확보한다.
2. 각 `BeachCode`별 관측 API를 호출한다.
3. `beach_profiles`를 이름+좌표로 기존 KMA/MOF 프로필과 병합한다.
4. `beach_provider_refs`에 KHOA code를 저장한다.
5. `beach_source_records`에는 마스킹된 request params와 raw payload hash를 저장한다.
6. `beach_observations`에는 시간별 최신 관측 row를 upsert한다.

## 2. KHOA 해수욕지수

### 기본 정보

| 항목 | 값 |
| --- | --- |
| dataset key | `khoa_beach_index_forecast` |
| 설명 URL | `https://www.khoa.go.kr/oceandata/openapi/odmi/odmiApiDetail.do?apiId=SV_AP_01_002` |
| API URL | `http://apis.data.go.kr/1192136/fcstBeachv2` |
| data.go.kr 대응 API | `https://www.data.go.kr/data/15142484/openapi.do` |
| API ID | `SV_AP_01_002` |
| 설명 | 전국 주요 해수욕장의 파고, 수온, 바람, 기온 등 해양·기상정보를 융합해 해수욕 가능 정도를 5단계 지수화 |
| 포털 수정일 | 2026-03-13 |
| 공식 갱신주기 | 실시간 |
| 사용자 제공 quota | 개발계정 10,000건 |
| 구현 주기 | 매일 06:30, 18:30 |
| 인증 환경변수 | `TRIPMATE_KHOA_API_KEY`, fallback `TRIPMATE_DATA_GO_SERVICE_KEY` |

### 요청 파라미터

| 이름 | 필수 | 구현값/예시 | 설명 |
| --- | --- | --- | --- |
| `serviceKey` | 필수 | 환경변수 | KHOA 인증키. 저장 시 `***`로 마스킹. 전송 시 decoded key는 URL encoding하고, 이미 percent-encoding된 key는 이중 인코딩하지 않는다. |
| `type` | 필수 | `json` | `json` 또는 `xml` |
| `reqDate` | 선택 | `YYYYMMDD` | 요청일시. job logical date를 사용 |
| `pageNo` | 선택 | `1` | 기본 1 |
| `numOfRows` | 선택 | `300` | 공식 최대 300 |
| `include` | 선택 | 미사용 | provider 필터 |
| `exclude` | 선택 | 미사용 | provider 필터 |
| `placeCode` | 선택 | 미사용 | 특정 지점 코드 |

### 출력 파라미터

| 이름 | 저장 컬럼 | 설명 |
| --- | --- | --- |
| `bbchNm` | `beach_profiles.display_name` | 해수욕장명 |
| `lat` | `beach_profiles.latitude` | 위도 |
| `lot` | `beach_profiles.longitude` | 경도. provider field명이 `lot`임 |
| `predcYmd` | `beach_index_forecasts.forecast_date` | 예측 날짜 |
| `predcNoonSeCd` | `beach_index_forecasts.forecast_slot` | 오전/오후 등 시간 구분 |
| `lastScr` | `beach_index_forecasts.index_score` | 해수욕점수 |
| `totalIndex` | `beach_index_forecasts.total_index` | 해수욕지수 |
| `maxWvhgt` | `beach_index_forecasts.max_wave_height_m` | 최고파고 |
| `avgWtem` | `beach_index_forecasts.avg_water_temperature_c` | 평균수온 |
| `avgArtmp` | `beach_index_forecasts.avg_air_temperature_c` | 평균기온 |
| `maxWspd` | `beach_index_forecasts.max_wind_speed_ms` | 최고풍속 |

### 운영 주의

- 공식 설명상 현재 일자 기준 7일 예측정보를 제공한다. “오늘 기준 앞으로 1년” 범위 전체를 한 번에 받는 API가 아니라, 앞으로 1년 동안 Dagster가 갱신 주기에 맞춰 계속 수집하는 방식이다.
- 포털 갱신주기는 실시간이지만 지도/여행 계획용 캐시 데이터이므로 기본 job는 하루 2회만 호출한다.
- 갯벌체험지수와 바다갈라짐 체험지수는 해수욕장 통합 테이블이 아니라 `ocean_activity_index_*` 테이블에 저장한다. 상세 스키마는 `docs/architecture/khoa-ocean-index-schema.md`를 참고한다.
- 2026-04-30 운영 검증에서 `fcstBeachv2`는 `TRIPMATE_KHOA_API_KEY`, `TRIPMATE_DATA_GO_SERVICE_KEY`, `reqDate` 지정/미지정 모두 HTTP 500을 반환했다. 2026-04-30 22:36 KST에 `TRIPMATE_KHOA_API_KEY`를 명시적으로 percent-encoded query 값으로 만들어 다시 실행해도 HTTP 500 `Unexpected errors`였다. `SERVICE KEY IS NOT REGISTERED`가 아니라 provider gateway 오류/승인 상태 문제로 분류하고, endpoint가 정상화되면 같은 job를 재실행한다.

## 3. 해양수산부 해수욕장 수질적합 여부 서비스

### 기본 정보

| 항목 | 값 |
| --- | --- |
| dataset key | `mof_beach_water_quality` |
| 설명 URL | `https://www.data.go.kr/data/15056705/openapi.do` |
| API URL | `https://apis.data.go.kr/1192000/service/OceansBeachSeawaterService1/getOceansBeachSeawaterInfo1` |
| 서비스명 | `OceansBeachSeawaterService` |
| 버전 | 1.1 |
| 설명 | 전국 해수욕장의 백사장/수질 적합 여부와 대장균·장구균 결과 |
| 포털 수정일 | 2023-09-25 |
| 첨부문서 갱신주기 | 년 1회 |
| 구현 주기 | 매년 5월 15일 04:20 |
| 사용자 제공 quota | 10,000건/일 |
| 인증 환경변수 | `TRIPMATE_MOF_BEACH_SERVICE_KEY`, fallback `TRIPMATE_DATA_GO_SERVICE_KEY` |

포털 화면에는 갱신주기가 `실시간`으로 보일 수 있으나, 첨부 활용가이드는 데이터 갱신주기를 `년 1회`로 명시한다. TripMate는 첨부문서의 데이터 갱신주기를 우선한다.

### 요청 파라미터

| 이름 | 필수 | 구현값/예시 | 설명 |
| --- | --- | --- | --- |
| `ServiceKey` | 필수 | 환경변수 | data.go.kr 인증키. 저장 시 `***`로 마스킹 |
| `pageNo` | 선택 | 1부터 반복 | 페이지 번호 |
| `numOfRows` | 선택 | `300` | 페이지 크기 |
| `resultType` | 선택 | `json` | 기본은 XML이나 구현은 JSON 사용 |
| `SIDO_NM` | 필수 | `부산`, `인천` 등 | 시도명 |
| `RES_YEAR` | 필수 | job logical date 연도와 직전 연도 | 조사연도 |

수집 시도명 목록:

`부산`, `인천`, `울산`, `경기`, `강원`, `충남`, `전북`, `전남`, `경북`, `경남`, `제주`

### 출력 파라미터

| 이름 | 저장 컬럼 | 설명 |
| --- | --- | --- |
| `num` | provider ref/source id 보조 | provider row 번호 |
| `sidoNm` | raw/source 보조 | 시도명 |
| `gugunNm` | raw/source 보조 | 구군명 |
| `staNm` | `beach_profiles.display_name` | 정점명/해수욕장명 |
| `resNum` | `beach_water_quality_measurements.survey_round` | 조사 회차 |
| `resLoc` | `survey_location` | 조사지점 |
| `res1` | `ecoli_result` | 대장균 결과 |
| `res2` | `enterococcus_result` | 장구균 결과 |
| `resYn` | `suitability` | 수질 적합 여부 |
| `resYear` | `survey_year` | 조사연도 |
| `resDate` | `survey_date` | 조사일자 |
| `resKnd` | `survey_kind` | 조사 종류 |
| `resLocDetail` | `survey_location_detail` | 조사지점 상세 |
| `lat` | `latitude` | 위도 |
| `lon` | `longitude` | 경도 |

## 4. 해양수산부 해수욕장정보 서비스

### 기본 정보

| 항목 | 값 |
| --- | --- |
| dataset key | `mof_beach_info` |
| 설명 URL | `https://www.data.go.kr/data/15058519/openapi.do` |
| API URL | `https://apis.data.go.kr/1192000/service/OceansBeachInfoService1/getOceansBeachInfo1` |
| 서비스명 | `OceansBeachInfoService1` |
| 버전 | 1.0 |
| 설명 | 시도명으로 해수욕장 폭, 총연장, 특징, 관련사이트, 이미지, 비상연락처, 위경도 조회 |
| 포털 수정일 | 2020-10-05 |
| 첨부문서 갱신주기 | 년 1회 |
| 구현 주기 | 매년 5월 15일 04:00 |
| 사용자 제공 quota | 10,000건/일 |
| 인증 환경변수 | `TRIPMATE_MOF_BEACH_SERVICE_KEY`, fallback `TRIPMATE_DATA_GO_SERVICE_KEY` |

포털 화면에는 갱신주기가 `실시간`으로 보일 수 있으나, 첨부 활용가이드는 데이터 갱신주기를 `년 1회`로 명시한다. TripMate는 첨부문서의 데이터 갱신주기를 우선한다.

### 요청 파라미터

| 이름 | 필수 | 구현값/예시 | 설명 |
| --- | --- | --- | --- |
| `ServiceKey` | 필수 | 환경변수 | data.go.kr 인증키. 저장 시 `***`로 마스킹 |
| `pageNo` | 선택 | 1부터 반복 | 페이지 번호 |
| `numOfRows` | 선택 | `300` | 페이지 크기 |
| `SIDO_NM` | 필수 | `제주` | 시도명 |
| `resultType` | 선택 | `json` | 기본은 XML이나 구현은 JSON 사용 |

### 출력 파라미터

| 이름 | 저장 컬럼 | 설명 |
| --- | --- | --- |
| `num` | provider ref/source id 보조 | provider row 번호 |
| `sidoNm` | raw/source 보조 | 시도명 |
| `gugunNm` | raw/source 보조 | 구군명 |
| `staNm` | `beach_profiles.display_name` | 해수욕장명 |
| `beachWid` | `beach_profiles.beach_width_m` | 해변폭 |
| `beachLen` | `beach_profiles.beach_length_m` | 해변총연장 |
| `beachKnd` | `beach_profiles.beach_material` | 특징/해변 종류 |
| `linkAddr` | `beach_profiles.homepage_url` | 관련사이트 |
| `linkNm` | `beach_profiles.homepage_name` | 관련사이트 이름 |
| `beachImg` | `beach_profiles.image_url` | 이미지 URL |
| `linkTel` | `beach_profiles.emergency_contact` | 비상연락처 |
| `lat` | `beach_profiles.latitude` | 위도 |
| `lon` | `beach_profiles.longitude` | 경도 |

## 5. 기상청 전국 해수욕장 날씨

기상청 해수욕장 날씨 상세는 `docs/data-sources/weather-air-quality.md`를 따른다. 통합 해수욕장 도메인에서는 다음 방식으로 결합한다.

- `weather_beach_location` active row를 `beach_profiles`에 동기화한다.
- `weather_beach_location.beach_num`은 `beach_provider_refs(provider='kma', provider_dataset_key='kma_beach_catalog')`로 저장한다.
- `weather_beach_location.map_feature_id`가 있으면 `beach_profiles.map_feature_id`에 보존한다.
- 공개 API는 `beach_profiles.map_feature_id`로 `weather_serving_beach`의 최신 category 값을 함께 반환한다.

## Dagster job와 스케줄

| dataset key | job | 주기 | 근거 |
| --- | --- | --- | --- |
| `khoa_beach_observation` | `khoa_beach_observation_twice_daily` | 매일 06:20, 18:20 | Dagster는 하루 2회만 관측 상세 API를 호출하고 12시간 캐시 안에서는 기존 raw/domain row를 재사용한다. |
| `khoa_beach_index_forecast` | `khoa_beach_index_forecast_twice_daily` | 매일 06:30, 18:30 | data.go.kr gateway KHOA v2 API. 포털 갱신주기는 실시간이나 캐시 정책상 하루 2회 |
| `khoa_mudflat_index_forecast` | `khoa_mudflat_index_forecast_twice_daily` | 매일 06:40, 18:40 | data.go.kr gateway KHOA v2 API. `ocean_activity_index_*`에 저장 |
| `khoa_sea_split_index_forecast` | `khoa_sea_split_index_forecast_twice_daily` | 매일 06:50, 18:50 | data.go.kr gateway KHOA v2 API. `ocean_activity_index_*`에 저장 |
| `mof_beach_info` | `mof_beach_info_annual` | 매년 5월 15일 04:00 | 첨부문서 데이터 갱신주기 `년 1회`, 해수욕장 시즌 전 |
| `mof_beach_water_quality` | `mof_beach_water_quality_annual` | 매년 5월 15일 04:20 | 첨부문서 데이터 갱신주기 `년 1회`, 해수욕장 시즌 전. 현재 연도 데이터가 아직 없을 수 있어 현재 연도와 직전 연도를 함께 조회 |

## 매핑/병합 규칙

1. `provider + dataset_key + provider_beach_id`가 이미 있으면 해당 `beach_profile`을 갱신한다.
2. provider ref가 없으면 정규화 이름이 같고 좌표가 약 0.03도 이내인 기존 프로필을 찾는다.
3. 좌표가 없으면 정규화 이름이 같은 첫 프로필을 재사용한다.
4. 그래도 없으면 새 `beach_profile`을 만든다.
5. 주소 매핑 품질은 `juso_building_name_in_legal_dong` > `postgis_point_in_polygon` > `postgis_nearest_boundary_5km` > `unmapped` 순으로 더 좋은 값만 덮어쓴다.
6. source-specific 장문/부가 필드는 `source_specific_attributes` 또는 source별 typed table에 둔다.

## 운영 한계/TODO

- KHOA 생활해양예보지수 v2 API는 포털 quota가 충분하지만 사용자 화면 요청마다 직접 호출하지 않는다. 해수욕/갯벌/바다갈라짐 지수는 하루 2회 DB 캐시를 기본으로 한다.
- MOF 두 API는 포털 화면과 첨부문서의 갱신주기 표기가 다르다. 현재는 첨부문서의 `년 1회`를 신뢰한다.
- 수질 API는 시즌 전 현재 연도 데이터가 비어 있을 수 있다. Dagster는 현재 연도와 직전 연도를 함께 수집하고, 공개 API는 조사일자 기준 최신 row를 보여준다.
- Juso 도로명주소 serving table이 비어 있으면 도로명주소코드 매핑은 0건이 정상이다. Juso 적재 후 해수욕장 ETL을 다시 실행한다.
- 별도 사용자 지시 전까지 MCP 구현은 하지 않는다. 해수욕장 API 수집은 Dagster ETL로만 유지한다.
