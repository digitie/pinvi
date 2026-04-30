# 전국문화축제표준데이터 스키마

이 문서는 공공데이터포털 `전국문화축제표준데이터`를 TripMate에 적재하는 기준이다.

## 목적

- 전국 지방자치단체가 등록한 표준 문화축제 데이터를 주기적으로 수집한다.
- 로그인 화면의 월별 축제 정보, 향후 지도 축제 레이어, 사용자 여행 일정 주변 축제 후보의 원천으로 사용한다.
- 축제는 장소와 다른 DB 테이블에 저장한다. 필요하면 법정동코드, 주소, 좌표, join key를 통해 내부 `places`와 연결할 수 있지만 자동 병합하지 않는다.
- 사용자가 축제를 여행계획에 추가하면 `trip_plan_items.resource_type = festival`과 `trip_plan_items.festival_id`로 연결한다.

## 출처

- 공공데이터포털: https://www.data.go.kr/data/15013104/standard.do
- 데이터명: 전국문화축제표준데이터
- 갱신주기: 분기
- 공공데이터포털 확인일: 2026-04-28
- 확인 당시 수정일: 2026-02-10
- 제공 항목: 축제명, 개최장소, 축제시작일자, 축제종료일자, 축제내용, 주관기관명, 주최기관명, 후원기관명, 전화번호, 홈페이지주소, 관련정보, 소재지도로명주소, 소재지지번주소, 위도, 경도, 데이터기준일자
- 포털 안내상 개별 기관 데이터는 매월 초 전국 단위로 병합되며, 전체 데이터가 필요하면 API 활용을 권장한다.

## 수집 정책

- dataset key: `public_cultural_festival`
- provider: `data_go_kr`
- OpenAPI path: `tn_pubr_public_cltur_fstvl_api`
- page size: 500
- schedule: 분기 갱신 기준으로 2월/5월/8월/11월 12일 04:35 KST
- freshness target: 93일
- retry: `config/etl-datasets.json`의 dataset별 설정을 따른다.
- 사용자 요청마다 외부 API를 호출하지 않고, ETL cache를 UI/API에서 조회한다.

주기 결정 근거:

- 공식 `갱신주기`는 분기이므로 `public_cultural_festival`은 분기 ETL로 운영한다.
- 포털이 개별 기관 데이터를 매월 초 병합한다고 안내하므로 분기 첫 달 1일이 아니라 12일에 실행한다. 이는 월초 병합, 기관별 지연, 포털 수정일 반영 시차를 흡수하기 위한 정책이다.
- 현재 포털 예시 수정일이 2026-02-10이므로 2/5/8/11월 12일 04:35 KST는 “분기 갱신 이후 이틀 정도의 여유”를 둔 운영값이다.
- 일정 화면, 지도 마커, 로그인 화면은 serving table만 조회한다. 사용자가 축제 화면을 열 때마다 data.go.kr을 호출하지 않는다.

## 저장 테이블

`tour_raw_public_cultural_festival`:

- provider raw snapshot을 append-only에 가깝게 저장한다.
- 같은 `provider + source_record_id + response_hash`는 중복 저장하지 않는다.
- 원문 row 전체를 `raw_payload` JSONB에 저장한다.

`tour_serving_public_cultural_festival`:

- 앱 조회용 정규화 테이블이다.
- `provider + source_record_id`를 unique key로 사용한다.
- ETL 시작 시 기존 serving row를 `is_active=false`로 바꾸고, 이번 수집에서 다시 확인된 row를 `is_active=true`로 갱신한다.
- 장소 테이블(`places`)과 별도 생명주기를 가진다. 축제는 기간성이 강하므로 일반 장소와 같은 row로 합치지 않는다.

핵심 컬럼:

| 컬럼 | 설명 |
| --- | --- |
| `source_record_id` | provider 안정 id가 없으므로 이름, 기간, 장소, 주소, 제공기관코드를 해시한 내부 source id |
| `place_join_key` | `data_go_kr:public_cultural_festival:{source_record_id}` |
| `festival_name` | 정규화 축제명 |
| `normalized_festival_name` | 검색용 소문자/공백 정규화 이름 |
| `venue_name` | 개최장소 |
| `event_start_date`, `event_end_date` | 축제 기간 |
| `event_status` | `upcoming`, `ongoing`, `ended`, `unknown` |
| `festival_content` | 축제내용 정규화 텍스트 |
| `mnnst_name`, `auspc_instt_name`, `suprt_instt_name` | 주관/주최/후원 |
| `phone_number`, `homepage_url`, `related_info` | 연락/링크/관련정보 |
| `road_address`, `jibun_address`, `address_snapshot` | 주소 snapshot |
| `longitude`, `latitude`, `geom` | EPSG:4326 좌표 |
| `legal_dong_code` | Juso 주소 매칭 또는 PostGIS point-in-polygon으로 얻은 법정동코드 |
| `road_name_code`, `road_address_management_no` | Juso 도로명주소 exact match 시 채움 |
| `sigungu_code`, `sido_code` | 법정동코드에서 도출 |
| `address_mapping_method` | `juso_road_address_exact`, `juso_jibun_address_exact`, `postgis_point_in_polygon`, `unmapped` |
| `provider_institution_code`, `provider_institution_name` | 제공기관 코드/명 |
| `reference_date` | 데이터기준일자 |
| `raw_payload` | 원문 row |
| `collected_at` | KST 수집시각 |

## 지도 표시 정책

축제 지도 표시는 장소 마커와 다른 독립 레이어다.

- 기본 레이어 key: `festival`
- 기본 색상: coral/red 계열 `#ff5a5f`
- 기본 icon: Maki `music`
- 공개 marker API: `GET /public/festivals/map-markers`
- 상세 API: `GET /public/festivals/{festival_id}`

지도 UI 동작:

1. 기본 지도에는 축제 마커를 자동 표시하지 않는다.
2. 지도 위 상세보기/레이어 버튼에서 사용자가 `축제`를 체크하면 축제 마커를 켠다.
3. 마커를 클릭하면 축제명, 일정, 개최장소, 운영시간에 해당하는 provider 텍스트, 연락처, 홈페이지, 주소를 보여준다.
4. 상세의 “추가” 버튼은 로그인한 사용자가 선택한 여행 날짜에 축제를 추가한다.
5. 추가 결과는 `trip_plan_items`에 저장하며, 축제 원천 row가 바뀌어도 사용자가 저장한 일정 표시가 깨지지 않도록 snapshot을 함께 저장한다.

현재 `전국문화축제표준데이터`에는 명확한 운영시간 전용 필드가 없다. 따라서 운영시간은 우선 상세 설명/관련정보 텍스트를 보여주고, 운영시간 전용 필드가 있는 다른 provider가 추가될 때 별도 정규화한다.

## 주소 매핑

1. 도로명주소가 있으면 `address_serving_juso_road_address.full_road_address` exact match를 먼저 시도한다.
2. 지번주소가 있으면 `address_serving_juso_related_jibun.full_jibun_address` exact match를 시도한다.
3. 주소 exact match가 실패하고 좌표가 있으면 `region_serving_boundary`의 법정동 polygon에 대해 PostGIS `ST_Covers`로 매핑한다.
4. 모두 실패해도 축제 row는 저장하되 `address_mapping_method='unmapped'`로 둔다.

문자열 기반 fuzzy matching은 하지 않는다. 도로명주소/지번주소가 provider마다 공백, 괄호, 건물명 표기가 달라질 수 있기 때문이다. fuzzy matching이 필요하면 별도 검증/운영 UI를 둔 뒤 추가한다.

## 좌표 정책

- provider의 `longitude`, `latitude`는 EPSG:4326으로 간주한다.
- DB/PostGIS는 `ST_MakePoint(lon, lat)` 순서를 사용한다.
- 좌표가 없거나 숫자로 파싱되지 않으면 geometry는 null로 두고 주소 매핑만 시도한다.

## 검증 기준

- pagination이 `numOfRows=500`으로 동작하는지 확인한다.
- raw row 중복 방지와 serving upsert idempotency를 검증한다.
- 도로명주소 exact match, 지번주소 exact match, 좌표 fallback, unmapped를 각각 테스트한다.
- `event_status`가 KST 수집일 기준으로 계산되는지 테스트한다.
- Airflow DAG import smoke와 `config/etl-datasets.json` 계약을 검증한다.
