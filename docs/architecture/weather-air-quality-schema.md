# 날씨와 대기질 데이터 스키마

이 문서는 TripMate의 날씨, 기상특보, 대기질 수집 스키마와 법정동 매핑 기준을 설명한다. 데이터 출처와 저장 정책의 단일 기준은 `docs/data-sources.md`다.

## 범위

구현된 데이터셋:

- `weather_short_term`: 기상청 초단기실황, 초단기예보, 단기예보
- `weather_kma_alert`: 기상청 기상특보, 기상정보, 기상속보
- `weather_mid_term`: 기상청 중기예보. `regId`/`stnId`는 기상청 provider region code로 보존하고 TripMate 주소 코드와는 명시적 mapping table로 연결한다.
- `kma_beach_catalog`: 기상청 전국 해수욕장 위치 카탈로그. 내부 표준 장소(`places`)와 1:1로 연결한다.
- `kma_beach_ultra_short_forecast`, `kma_beach_village_forecast`, `kma_beach_wave_height`, `kma_beach_water_temperature`, `kma_beach_tide_sun`: 해수욕장별 예보/파고/수온/조석/일출일몰
- `air_quality_station`: AirKorea 측정소 목록
- `air_quality_forecast`: AirKorea 미세먼지/오존 예보통보
- `air_quality_sido_measurement`: AirKorea 시도별 실시간 측정값

정책은 확정됐지만 아직 구현하지 않은 데이터셋:

- `weather_rest_area`: 휴게소 master와 매칭하지 않는 정책은 확정됐지만 실제 응답 필드와 좌표계 검증이 아직 필요하다.

## API 승인 확인

2026-04-26에 로컬 설정의 data.go.kr 인증키로 smoke call을 수행했다. 인증키 원문은 로그와 문서에 남기지 않는다.

확인 결과:

- 기상청 단기예보 조회서비스 `getUltraSrtNcst`: 정상 응답
- 기상청 기상특보 조회서비스 `getWthrWrnList`: 정상 응답
- 기상청 기상특보 조회서비스 `getWthrInfoList`: 정상 응답
- 기상청 기상특보 조회서비스 `getWthrBrkNewsList`: `NO_DATA` 응답. 권한 오류가 아니라 현재 기간에 속보 데이터가 없는 상태로 확인
- 기상청 중기예보 조회서비스 `getMidFcst`, `getMidLandFcst`, `getMidTa`: 정상 응답
- AirKorea 측정소정보 조회서비스 `getMsrstnList`: 정상 응답
- AirKorea 대기오염정보 조회서비스 `getMinuDustFrcstDspth`: 정상 응답
- AirKorea 대기오염정보 조회서비스 `getCtprvnRltmMesureDnsty`: 정상 응답
- 기상청 관광코스별 관광지 상세 날씨 조회서비스 `getTourStnVilageFcst1`: 정상 응답

현재 확인한 범위에서는 승인되지 않은 API가 없다.

## 수집 주기와 쿼터

AirKorea 두 API는 일 500회 제한을 전제로 설계했다.

| dataset_key | DAG | 주기 | 예상 호출량 | 비고 |
| --- | --- | --- | --- | --- |
| `weather_short_term` | `weather_short_term_sigungu_grid` | 30분 | 활성 격자 수 × 48회/일 | 초기 기본값은 시군구 대표 격자다. |
| `weather_kma_alert` | `weather_kma_alert` | 30분 | 3개 endpoint × 48회/일 | 지도 마커로 쓰지 않고 Telegram 알림 원천으로 사용한다. |
| `weather_mid_term` | `weather_mid_term_nationwide` | 하루 2회 | 공식 중기예보 구역코드 수 × 2회/일 | 여행 일정이 단기예보 범위를 벗어날 때 사용한다. 사용자 수에 따라 호출량이 늘지 않게 전국 구역을 주기 수집한다. |
| `kma_beach_catalog` | `kma_beach_catalog_annual` | 매년 5월 15일 04:00 | 참고문서 ZIP 1회/년 | 해수욕장 시즌 전 위치 카탈로그를 장소 DB와 다시 맞춘다. |
| `kma_beach_ultra_short_forecast` | `kma_beach_ultra_short_forecast_hourly` | 6~8월 매시 45분 | 활성 해수욕장 수 × 24회/일 | 초단기예보 1시간 패턴에 맞춘다. |
| `kma_beach_village_forecast` | `kma_beach_village_forecast_3hourly` | 6~8월 하루 8회 | 활성 해수욕장 수 × 8회/일 | 단기예보 3시간 패턴에 맞춘다. |
| `kma_beach_wave_height` | `kma_beach_wave_height_hourly` | 6~8월 매시 35분 | 활성 해수욕장 수 × 24회/일 | 직전 정시 파고 관측값을 조회한다. |
| `kma_beach_water_temperature` | `kma_beach_water_temperature_hourly` | 6~8월 매시 40분 | 활성 해수욕장 수 × 24회/일 | 직전 정시 수온 관측값을 조회한다. |
| `kma_beach_tide_sun` | `kma_beach_tide_sun_daily` | 6~8월 매일 05:10 | 활성 해수욕장 수 × 2 endpoint/일 | 조석과 일출/일몰을 일 단위로 저장한다. |
| `air_quality_station` | `air_quality_station_daily` | 매일 04:20 | 17개 시도 × 1회/일 | `getMsrstnList`, 일 500회 제한 대비 여유가 크다. |
| `air_quality_forecast` | `air_quality_forecast_daily` | 하루 4회 | 3개 항목 × 4회/일 | PM10, PM25, O3 예보통보를 수집한다. |
| `air_quality_sido_measurement` | `air_quality_sido_measurement_hourly` | 매시 25분 | 17개 시도 × 24회/일 = 408회/일 | AirKorea 대기오염정보 일 500회 제한 안에 들어가도록 시간 단위로 제한한다. |

AirKorea 대기오염정보 API는 예보통보와 시도별 측정값이 같은 서비스 묶음이므로, 현재 기본 주기는 합산 약 420회/일이다. 여기에 retry가 발생하면 일 500회를 넘을 수 있으므로 운영에서는 반복 실패 시 DAG 일시정지 또는 주기 완화를 먼저 검토한다.

## 표시 목적

날씨 데이터는 단순한 현재 날씨 카드가 아니라, 여행 일정과 지도에서 직관적으로 비교하는 용도다.

- 지도 기본 표시는 어제, 오늘, 내일의 오전/오후 요약으로 제한한다.
- 지도 마커나 날씨 영역을 클릭하면 시간대별 상세, 기상특보, 대기질까지 확장한다.
- 여행 계획 화면은 해당 여행 날짜의 오전/오후 날씨를 기본으로 보여주고, 클릭 시 상세 예보와 대기질을 함께 보여준다.
- 어제 날씨는 “오늘과 비교”하기 위한 snapshot이다. 장기 과거 관측 DB가 아니라 전날 수집된 serving snapshot을 우선 사용한다.
- 오늘/내일/모레는 초단기예보와 단기예보를 조합한다.
- 단기예보 범위를 벗어난 여행 일정은 중기예보를 사용한다.
- 미세먼지와 공기질은 날씨와 같은 영역에서 함께 보여준다.

## 테이블

### `weather_short_term_grid_mapping`

기상청 단기예보 격자와 TripMate 행정구역 코드를 연결한다.

주요 컬럼:

- `region_code_type`: `sigungu`, `legal_dong`, `administrative_dong` 중 하나
- `region_code`: TripMate 행정구역 코드
- `legal_dong_code`: `address_code_standard.legal_dong_code` FK, nullable
- `sigungu_code`, `sido_code`
- `representative_lon`, `representative_lat`: EPSG:4326 좌표
- `nx`, `ny`: 기상청 DFS 격자
- `mapping_method`: 현재 자동 생성은 `postgis_point_on_surface`
- `source_boundary_version`: 경계 파일 hash

초기 기본 정책은 시군구 경계의 `ST_PointOnSurface`를 대표점으로 삼아 시군구 단위 격자를 만든다. 법정동 상세 격자는 장소 저장/조회 API가 생길 때 필요에 따라 추가한다.

### `weather_raw_short_term`

기상청 단기예보 계열 raw row를 저장한다.

주요 컬럼:

- `endpoint`
- `nx`, `ny`
- `base_date`, `base_time`
- `forecast_date`, `forecast_time`
- `category_code`
- `raw_payload`
- `response_hash`
- `collected_at`

현재 수집 endpoint는 `getUltraSrtNcst`, `getUltraSrtFcst`, `getVilageFcst`다. endpoint별 발표 기준시각은 loader에서 KST 기준으로 계산한다.
raw는 동일 응답 재수집도 보존한다. 중복 제거와 최신 조회는 serving 테이블에서 처리한다.
`collected_at`은 KST 기준 timezone-aware datetime으로 저장한다.

### `weather_serving_short_term`

앱/API 조회용 단기예보 계열 정규화 테이블이다.

unique 기준:

- `endpoint`, `nx`, `ny`, `base_date`, `base_time`, `forecast_date`, `forecast_time`, `category_code`

주요 컬럼:

- `observed_at`, `forecast_at`: 기상청 발표 날짜/시간을 KST로 해석해 저장
- `category_code`: 원천 category code
- `category_name`: 앱 표시명
- `normalized_category`: 내부 category
- `value`, `unit`
- `raw_payload`
- `collected_at`

미확인 category는 적재를 막지 않고 `normalized_category = 'unknown'`으로 저장한다.
`collected_at`은 KST 기준 timezone-aware datetime으로 저장한다.

### `weather_beach_location`

기상청 해수욕장 카탈로그와 내부 표준 지도 객체(`map_features`)를 연결하는 위치 테이블이다.

주요 컬럼:

- `provider`: `kma`
- `beach_num`: 기상청 해수욕장 번호. 참고문서 xlsx의 `순번`
- `beach_name`
- `map_feature_id`: `map_features.id` FK
- `nx`, `ny`: 기상청 DFS 격자
- `longitude`, `latitude`, `geom`: EPSG:4326 표준 좌표
- `legal_dong_code`: V-WORLD 법정동 경계 point-in-polygon 결과
- `road_name_code`, `road_address_management_no`: 같은 법정동 내 Juso 건물명 정확 일치가 1건일 때만 채운다.
- `address_mapping_method`: `juso_building_name_in_legal_dong`, `postgis_point_in_polygon`, `postgis_nearest_boundary_5km`, `unmapped`
- `source_file_name`, `source_file_hash`, `source_row_number`
- `raw_payload`
- `collected_at`
- `is_active`

해수욕장 좌표가 해상/모래사장 쪽으로 찍혀 법정동 polygon 밖일 수 있으므로, point-in-polygon 실패 시 약 5km 이내 가장 가까운 법정동 경계를 보조 매핑으로 사용한다. 좌표만으로 도로명주소코드나 도로명주소관리번호를 만들지 않는다. 원천 xlsx에 주소가 없으므로 매칭 근거가 부족하면 null로 둔다.

### `weather_raw_beach`

해수욕장 날씨 API 요청 단위 raw snapshot이다.

주요 컬럼:

- `provider`: `kma`
- `endpoint`: `getUltraSrtFcstBeach`, `getVilageFcstBeach`, `getWhBuoyBeach`, `getTwBuoyBeach`, `getTideInfoBeach`, `getSunInfoBeach`
- `beach_num`
- `request_params`
- `raw_payload`: 요청 파라미터와 `items` 배열을 함께 저장
- `response_hash`
- `collected_at`

unique 기준은 `provider + endpoint + beach_num + response_hash`다. 같은 응답을 retry로 다시 받아도 raw 중복 저장을 막는다.

### `weather_serving_beach`

앱/API 조회용 해수욕장 날씨 정규화 테이블이다.

unique 기준:

- `provider`, `endpoint`, `beach_num`, `source_record_key`, `category_code`

주요 컬럼:

- `beach_location_id`: `weather_beach_location.id` FK
- `map_feature_id`: `map_features.id` FK
- `base_date`, `base_time`
- `forecast_date`, `forecast_time`
- `source_observed_time`
- `observed_at`, `forecast_at`
- `category_code`, `category_name`, `normalized_category`
- `value`, `unit`
- `station_name`: 조석 관측소명/ID처럼 endpoint별 보강 정보
- `raw_payload`
- `collected_at`
- `is_active`

초단기/단기예보 category는 기존 단기예보 category spec을 재사용한다. 파고는 `WH/wave_height/m`, 수온은 `TW/water_temperature/deg_c`, 조위는 `TIDE/tide_level/cm`, 일출/일몰은 `SUNRISE`, `SUNSET`으로 저장한다. 파고/수온/조위/일출일몰 응답의 `-`, `:`, 빈 시각처럼 관측·이벤트 시각이 없는 무자료 표시는 raw에만 보존하고 serving row로 승격하지 않는다.

### `weather_kma_alert_station_code`

기상특보/정보/속보 응답에서 관측된 지점코드 `stnId`를 저장한다.

현재 구현은 응답에서 관측된 `stnId`, `stnNm`을 누적한다. 사용자가 요청한 “참고문서의 지점코드 전체 적재”는 후속 보완으로 남아 있다. 참고문서 구조가 고정되면 별도 parser로 전체 지점코드를 선적재해야 한다.

### `weather_raw_kma_alert`, `weather_serving_kma_alert`

기상특보, 기상정보, 기상속보를 raw/serving으로 분리 저장한다.

주요 컬럼:

- `alert_type`: `warning`, `information`, `breaking_news`
- `stn_id`
- `title`
- `tm_fc`
- `tm_seq`
- `raw_payload`
- `collected_at`

이 데이터는 지도 마커로 표시하지 않는다. Telegram 여행 알림에서 여행일/지역과 관련된 위험 정보를 보여주는 용도로 사용한다.
`collected_at`은 KST 기준 timezone-aware datetime으로 저장한다.

### `weather_mid_forecast_region`

기상청 중기예보 API가 요구하는 공식 provider region code를 저장한다.

주요 컬럼:

- `provider`: `kma`
- `endpoint`: `getMidFcst`, `getMidLandFcst`, `getMidTa`
- `region_kind`: `outlook_station`, `land`, `temperature`
- `provider_region_id`: 기상청 `stnId` 또는 `regId`
- `region_name`
- `parent_region_id`
- `source_version`
- `raw_payload`
- `collected_at`
- `is_active`

이 테이블의 `provider_region_id`는 Juso 법정동코드나 시군구코드가 아니다. 예를 들어 `11B00000` 같은 중기육상예보 `regId`, `11B10101` 같은 중기기온예보 `regId`, `108` 같은 중기전망 `stnId`를 그대로 보존한다.

초기 seed는 `config/kma-mid-term-regions.json`에서 읽는다. 운영 중 공식 코드표가 바뀌면 이 설정 파일을 갱신하고 loader를 재실행한다.

### `weather_mid_region_address_mapping`

TripMate 주소 코드와 기상청 중기예보 provider region code의 연결을 명시적으로 저장한다.

주요 컬럼:

- `provider`, `endpoint`, `provider_region_kind`, `provider_region_id`
- `sido_code`
- `sigungu_code`
- `legal_dong_code_prefix`
- `mapping_method`: `exact`, `parent_region`, `manual` 등
- `priority`
- `valid_from`
- `source_version`
- `raw_payload`
- `is_active`

이 매핑은 자동 fuzzy matching이 아니다. 시도/시군구/법정동 prefix 중 더 구체적인 매핑을 우선하고, 같은 범위에서는 `priority`가 낮은 값을 먼저 사용한다. 여행 장소 좌표는 먼저 법정동 경계 point-in-polygon으로 TripMate 주소 코드를 얻고, 그 뒤 이 테이블을 통해 중기예보 구역으로 변환한다.
scope 컬럼 일부가 null일 수 있으므로 unique 제약은 PostgreSQL `NULLS NOT DISTINCT`로 둔다. 같은 provider region과 같은 주소 scope가 중복 적재되는 일을 DB 레벨에서 막기 위함이다.

### `weather_raw_mid_term`

기상청 중기예보 raw row를 저장한다.

주요 컬럼:

- `endpoint`
- `region_kind`
- `provider_region_id`
- `tm_fc`
- `raw_payload`
- `response_hash`
- `collected_at`

raw는 endpoint와 provider region code별 응답을 보존한다. 중복 제거와 최신 조회는 serving 테이블에서 처리한다.

### `weather_serving_mid_term`

앱/API 조회용 중기예보 정규화 테이블이다.

unique 기준:

- `endpoint`, `region_kind`, `provider_region_id`, `tm_fc`, `forecast_date`, `forecast_slot`

주요 컬럼:

- `source_region_code`
- `forecast_date`
- `forecast_slot`: `am`, `pm`, `daily`
- `weather_summary`
- `rain_probability`
- `min_temperature`
- `max_temperature`
- `mapping_method`
- `fallback_used`
- `fallback_reason`
- `display_priority`
- `raw_payload`
- `collected_at`

`getMidLandFcst`는 3~7일차 오전/오후 예보와 8~10일차 일 단위 예보를 펼쳐 저장한다. `getMidTa`는 3~10일차 최저/최고 기온을 일 단위로 저장한다. `getMidFcst`는 전망 전문 성격이므로 `daily` 요약으로 저장한다.

### `air_quality_raw_station`, `air_quality_serving_station`

AirKorea 측정소 목록을 저장한다.

주요 컬럼:

- `station_name`
- `mang_name`
- `address`
- `sido_name`
- `item`
- `installation_year`
- `longitude`, `latitude`
- `legal_dong_code`: `address_code_standard.legal_dong_code` FK, nullable
- `sigungu_code`
- `mapping_method`
- `raw_payload`

AirKorea 응답의 `dmX`, `dmY`는 현재 smoke 응답 기준으로 `dmX = 위도`, `dmY = 경도`로 해석한다. 저장 전 PostGIS point-in-polygon으로 법정동 경계를 찾는다. 경계 데이터가 없거나 좌표가 없으면 `mapping_method = 'unmapped'`로 저장한다.

### `air_quality_raw_forecast`, `air_quality_serving_forecast`

AirKorea 미세먼지/오존 예보통보를 저장한다.

주요 컬럼:

- `inform_code`: `PM10`, `PM25`, `O3`
- `data_time`
- `inform_data`
- `inform_overall`
- `inform_cause`
- `inform_grade`
- `action_knack`
- `raw_payload`
- `collected_at`

예보통보는 권역 텍스트가 섞인 원문 성격이 강하므로, serving에는 주요 표시 필드와 원문 payload를 함께 둔다.
대기질 UI 임계치와 Telegram 문구 기준은 아직 제품 UI에서 확정하지 않았다. 따라서 현재 스키마는 PM10, PM25, O3 예보통보의 원문, 등급, 원인, 행동요령 등 provider가 주는 정보를 최대한 보존하고, 나중에 UI 계층에서 임계치와 표현 방식을 얹을 수 있게 한다.

### `air_quality_raw_sido_measurement`, `air_quality_serving_sido_measurement`

AirKorea 시도별 실시간 측정값을 저장한다.

unique 기준:

- `sido_name`, `station_name`, `data_time`

주요 컬럼:

- `sido_name`
- `station_name`
- `mang_name`
- `data_time`
- `khai_value`, `khai_grade`
- `pm10_value`, `pm10_grade`
- `pm25_value`, `pm25_grade`
- `no2_value`, `no2_grade`
- `o3_value`, `o3_grade`
- `co_value`, `co_grade`
- `so2_value`, `so2_grade`
- `pm10_flag`, `pm25_flag`, `no2_flag`, `o3_flag`, `co_flag`, `so2_flag`
- `raw_payload`
- `collected_at`

시도별 측정값도 UI 임계치를 미리 강제하지 않는다. 원천이 제공하는 통합대기환경지수, 미세먼지, 초미세먼지, 이산화질소, 오존, 일산화탄소, 아황산가스 값을 모두 저장하고, 지도/여행 알림에서 필요한 표현은 별도 표시 정책으로 결정한다.

## 법정동 매핑 기준

날씨/대기질 매핑의 권위 있는 공간 판정은 PostGIS를 사용한다.

- 단기예보: `region_serving_boundary`의 시군구 경계를 `ST_PointOnSurface`로 대표점화하고 KMA DFS `nx`, `ny`로 변환한다.
- 측정소: AirKorea 측정소 좌표를 EPSG:4326 point로 보고 법정동 경계에 `ST_Covers`를 적용한다.
- 기상특보/정보/속보: 지점코드 기반 텍스트 정보이며 좌표나 주소를 제공하지 않으므로 법정동 FK를 붙이지 않는다.
- 중기예보: `regId`는 기상청 중기예보 API가 요구하는 예보구역코드다. Juso 법정동코드도 아니고 단기예보 DFS `nx`, `ny`도 아니다. 공식 코드표를 `weather_mid_forecast_region`에 저장하고, TripMate 주소 코드와의 연결은 `weather_mid_region_address_mapping` 같은 명시적 mapping table로 관리한다. 시군구 이름이 비슷하다는 이유로 임의 자동 매핑하지 않는다.

PostGIS 경계가 아직 적재되지 않은 초기 환경에서는 날씨 격자 mapping이 0건일 수 있다. 이 경우 DAG는 API를 호출하지 않고 0건 적재로 종료할 수 있다. 운영에서는 VWorld 시군구/법정동 경계 적재 후 날씨 DAG를 활성화한다.

## 현재 구현 한계

- `weather_short_term`은 `getUltraSrtNcst`, `getUltraSrtFcst`, `getVilageFcst` 수집과 저장까지 구현했다. 어제/오늘 비교용 조회 API와 Telegram 여행 알림 조립은 아직 연결되지 않았다.
- `weather_mid_term`은 공식 중기예보 구역 seed, 주소 코드 mapping table, raw/serving schema, loader, Airflow DAG까지 구현했다. 다만 `config/kma-mid-term-regions.json`의 수동 seed는 운영 전 공식 최신 코드표와 한 번 더 대조해야 한다.
- 기상특보 지점코드는 응답에서 관측된 코드만 누적한다. 참고문서 기반 전체 지점코드 선적재는 후속이다.
- AirKorea 좌표 필드 해석은 smoke 응답 기준이다. 운영 전 실제 여러 시도 샘플로 `dmX`, `dmY`가 계속 위도/경도 순서인지 확인한다.
- AirKorea 대기오염정보는 일 500회 제한 안에 맞췄지만 retry가 반복되면 초과할 수 있다.
- 여행 알림 메시지 생성, 관리자 Telegram 발송 worker, UI 조회 API는 아직 연결되지 않았다.
- 기상청 관광코스별 상세 날씨 API는 사용자 저장 장소 또는 여행 장소 주변 target을 받아 cache/수집하는 loader까지 구현했다. 아직 사용자 저장 장소/여행 장소 도메인과 Airflow 자동 연결은 없다.

## 검증

추가된 테스트:

- `tests/test_weather_loader.py`
- `tests/test_kma_tour_course_loader.py`
- `tests/test_etl_config.py`
- `tests/test_airflow_dags.py`
- `tests/test_migration_contract.py`
- `tests/test_model_metadata.py`

검증 범위:

- API key 누락 시 client 실패
- 기상청 `NO_DATA` 응답 empty 처리
- 초단기실황 raw 저장과 serving upsert
- 초단기예보/단기예보 endpoint 수집과 serving upsert
- 중기예보 공식 region seed, 주소 mapping, raw/serving upsert
- 중기예보 `regId`/`stnId`가 법정동코드와 별도 체계인지 확인
- 기상청 발표시각 KST 저장
- 시군구 경계 대표점에서 KMA DFS grid 생성
- 기상특보 지점코드 누적
- AirKorea 측정소 좌표를 법정동 경계에 매핑
- AirKorea 예보/측정값 raw/serving 저장과 오염물질 등급/flag 보존
- 관광코스 상세 날씨가 전체 전국 수집이 아니라 주변 target 중심 cache로 동작하는지 확인
- Airflow DAG schedule/retry 계약
- Alembic migration 문자열 계약
