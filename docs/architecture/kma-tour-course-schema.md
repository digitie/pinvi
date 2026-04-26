# 기상청 추천 관광코스 스키마

이 문서는 기상청 추천 관광코스 CSV/ZIP 적재와 지도 마커 원천 스키마를 설명한다. 데이터 출처와 저장 정책의 단일 기준은 `docs/data-sources.md`다.

## 범위

구현된 데이터셋:

- `kma_recommended_tour_course`

원천:

- 기상청 관광코스별 관광지 상세 날씨 조회서비스 참고문서의 관광코스 지점 CSV
- 공공데이터포털: `https://www.data.go.kr/data/15056912/openapi.do`

현재 구현은 코스/관광지 기준정보 CSV/ZIP을 DB화하고, OpenAPI `getTourStnVilageFcst1`는 사용자 저장 장소 또는 여행 장소 주변 target을 기준으로 cache/수집하는 loader까지 제공한다. 코스별 상세 날씨는 전체 관광코스를 전국 주기 수집하지 않는다. 사용자 저장 장소/여행 장소 도메인이 연결되면 그 좌표를 target으로 넘겨 주변 관광코스만 갱신한다.

## 파일과 인코딩

지원 입력:

- `.csv`
- `.zip` 안의 첫 번째 `.csv`

CSV 필드:

- `테마분류`
- `코스 아이디`
- `관광지 아이디`
- `지역 아이디`
- `관광지명`
- `경도(도)`
- `위도(도)`
- `코스순서`
- `이동시간`
- `실내구분`
- `테마명`

인코딩:

- 우선 `cp949`
- 다음 `ms949`
- 마지막 `utf-8-sig`

Windows 11 Notepad에서 ANSI로 표시되는 파일을 기본값으로 가정한다. 내부 저장 문자열은 UTF-8로 정규화한다.

## 테이블

### `tour_course_raw_kma_point`

CSV row 원문을 보존한다.

주요 컬럼:

- `source_file_name`
- `source_file_hash`
- `source_encoding`
- `source_snapshot_date`
- `row_number`
- `theme_category_code`
- `course_id`
- `spot_id`
- `region_id`
- `spot_name`
- `raw_payload`
- `response_hash`
- `collected_at`

unique 기준:

- `source_file_hash`, `row_number`

같은 파일 hash를 다시 적재하면 같은 hash의 raw/serving row를 먼저 삭제하고 다시 넣는다. 같은 파일 재실행이 unique 제약으로 실패하지 않도록 하기 위한 정책이다.

### `kma_recommended_tour_course`

앱/API/지도 조회용 serving 테이블이다.

주요 컬럼:

- `source_file_name`
- `source_file_hash`
- `source_encoding`
- `source_snapshot_date`
- `theme_category_code`: 원천 `테마분류`
- `theme_category`: 내부 enum
- `theme_name`: 원천 `테마명`
- `course_id`
- `spot_id`
- `region_id`
- `spot_name`
- `longitude`, `latitude`: EPSG:4326
- `course_order`
- `travel_time_minutes`
- `indoor_type`
- `legal_dong_code`: `address_code_standard.legal_dong_code` FK, nullable
- `sigungu_code`
- `sido_code`
- `address_snapshot`
- `address_mapping_method`
- `marker_source_type`: `kma_recommended_tour_course`
- `raw_payload`
- `collected_at`

unique 기준:

- `source_file_hash`, `spot_id`

### `tour_course_raw_kma_spot_weather`

기상청 관광코스별 관광지 상세 날씨 OpenAPI 응답 raw row를 저장한다.

주요 컬럼:

- `endpoint`: `getTourStnVilageFcst1`
- `course_id`
- `spot_id`
- `base_date`, `base_time`
- `forecast_date`, `forecast_time`
- `category_code`
- `raw_payload`
- `response_hash`
- `collected_at`

raw는 주변 target에 의해 호출된 관광코스별 응답을 그대로 보존한다. 같은 응답이 반복 수집되어도 감사와 재처리를 위해 raw row는 append한다.

### `tour_course_serving_kma_spot_weather`

앱/API 조회용 관광코스 상세 날씨 cache 테이블이다.

unique 기준:

- `course_id`, `spot_id`, `base_date`, `base_time`, `forecast_date`, `forecast_time`, `category_code`

주요 컬럼:

- `source_file_hash`
- `theme_category_code`
- `course_id`, `spot_id`, `spot_name`
- `longitude`, `latitude`
- `legal_dong_code`, `sigungu_code`, `sido_code`
- `base_date`, `base_time`
- `forecast_date`, `forecast_time`
- `category_code`
- `category_name`
- `normalized_category`
- `value`
- `unit`
- `raw_payload`
- `collected_at`

이 테이블은 사용자 저장 장소 또는 여행 장소 주변 관광코스를 빠르게 보여주기 위한 cache다. `legal_dong_code`, `sigungu_code`, `sido_code`는 관광코스 CSV 적재 시 좌표 기반 point-in-polygon으로 얻은 값을 그대로 복사한다. 이 단계에서도 V-WORLD reverse geocoding이나 Juso 상세 주소 key 매핑은 수행하지 않는다.
`spot_id`, `base_date`, `forecast_date` 같은 provider 필드는 응답에 따라 null일 수 있으므로 serving unique 제약은 PostgreSQL `NULLS NOT DISTINCT`로 둔다. 같은 course/category/time cache가 null 값 때문에 중복 저장되는 일을 막기 위함이다.

## 테마 매핑

원천 `theme_category_code`와 `theme_name`은 항상 보존한다.

초기 내부 enum:

| 원천 코드 | 내부 enum |
| --- | --- |
| `TH01` | `nature` |
| `TH02` | `culture_art` |
| `TH03` | `leisure` |
| `TH04` | `food` |
| `TH05` | `history_tradition` |

알 수 없는 코드는 적재 실패로 보지 않고 `theme_category = 'unknown'`으로 저장한다.

## 좌표와 주소 매핑

CSV의 `경도(도)`는 `longitude`, `위도(도)`는 `latitude`로 저장한다. 둘 다 EPSG:4326으로 취급한다.

현재 구현된 매핑:

- 좌표가 있으면 `region_serving_boundary`의 법정동 경계에 PostGIS `ST_Covers`를 적용한다.
- 매칭되면 `legal_dong_code`, `sigungu_code`, `sido_code`를 저장한다.
- 매칭되지 않으면 주소 FK는 null로 두고 `address_mapping_method = 'unmapped'`로 저장한다.
- CSV의 `지역 아이디`는 원문 `region_id`로 보존하지만 법정동코드와 같다고 가정하지 않는다.

명시적으로 하지 않는 매핑:

- V-WORLD reverse geocoding으로 주소 문자열 snapshot을 만들지 않는다.
- reverse geocoding 결과를 Juso 도로명주소관리번호, 도로명코드, 행정동코드와 연결하지 않는다.
- 좌표/명칭 기반 후보 매칭이나 주소 문자열 fuzzy matching을 하지 않는다.

V-WORLD reverse geocoding 기반 상세 주소 매핑은 검토했던 대안이다. 관광코스 CSV는 이미 좌표를 제공하므로, 현재 기준선에서는 PostGIS point-in-polygon으로 법정동/시군구를 판정하는 방식이 더 단순하고 재현 가능하다. 이 대안은 현재 후속 TODO가 아니며, 향후 상세 주소 snapshot이 꼭 필요한 새 제품 결정이 있을 때만 다시 설계한다.

## 지도와 UI 연결

지도 마커는 `marker_source_type = 'kma_recommended_tour_course'`를 기준으로 일반 POI와 구분한다.

후속 UI 요구:

- “기상청 추천 여행코스” 전용 색상/아이콘 사용
- 마커 상세에서 같은 `theme_category_code`와 `course_id`의 관광지를 `course_order` 순서로 볼 수 있는 링크 제공
- 색상/아이콘은 추후 제품 결정값을 따른다.

## Airflow

DAG:

- `kma_recommended_tour_course_annual`

설정:

- schedule: `0 5 1 3 *`
- retry: 30분 간격 3회
- 환경변수: `TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH`

`TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH`가 없으면 DAG는 skip한다. 파일은 운영자가 Airflow 컨테이너에서 접근 가능한 경로에 업로드하거나 배치한다.

관광코스 상세 날씨는 현재 Airflow 정기 DAG로 전체 수집하지 않는다. 저장 장소/여행 장소 도메인이 구현된 뒤, 해당 좌표 목록을 target으로 넘기는 cache 갱신 task를 별도 연결한다.

## 검증

추가된 테스트:

- `tests/test_kma_tour_course_loader.py`
- `tests/test_airflow_dags.py`
- `tests/test_migration_contract.py`
- `tests/test_model_metadata.py`

검증 범위:

- cp949 CSV decoding
- ZIP 안의 CSV 선택
- 같은 파일 hash 재실행 idempotency
- raw/serving row 생성
- 좌표 순서 보존
- 좌표 기반 법정동 point-in-polygon 매핑
- V-WORLD reverse geocoding과 Juso 상세 주소 key 매핑을 수행하지 않는지 확인
- `TH05` → `history_tradition` 매핑
- `marker_source_type` 고정값
- 관광코스 상세 날씨가 전체 코스 전국 수집이 아니라 주변 target 중심으로만 cache되는지 확인
- 상세 날씨 raw/serving upsert와 KST `collected_at` 저장
