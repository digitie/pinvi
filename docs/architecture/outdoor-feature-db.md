# 산림·등산 Outdoor Feature DB 설계

검토일: 2026-05-18

## 목적

국립공원, 산, 휴양림, 수목원, 트레킹, 등산을 TripMate 지도에서 같은 feature 계약으로 조회하기 위해 `place`, `area`, `route`를 한 DB 계층에 적재한다. 구현은 외부 provider를 감싸는 wrapper를 만들지 않고 `python-krforest-api`와 `python-mois-api` public client/model을 직접 사용한다.

이 문서의 기준은 다음이다.

- 산림청 공간자료와 산 정보는 primary outdoor feature로 승격한다.
- 행정안전부 localdata 인허가 자료는 캠핑장·휴양업처럼 산림 여행을 보조하거나 교차검증하는 support/enrichment feature로 둔다.
- 기존 공공 장소 ETL은 보조 자료로 유지한다. 같은 장소 자동 병합은 보수적으로 하고, source trace와 provider ref를 먼저 쌓는다.
- 사용자 지도/API는 raw provider row가 아니라 `map_features`, detail table, `outdoor_feature_profiles`를 조회한다.

## 구현 상태

이번 구현에서 추가한 핵심 파일은 다음이다.

| 영역 | 파일 |
| --- | --- |
| DB model | `apps/api/app/models/place.py` |
| Alembic migration | `apps/api/alembic/versions/20260518_0026_outdoor_feature_profiles.py` |
| ETL loader | `apps/api/app/etl/outdoor/forest_features.py` |
| Dagster loader/registry | `apps/api/app/dagster_etl/loaders.py`, `apps/api/app/dagster_etl/registry.py` |
| config | `apps/api/app/core/etl_config.py`, `config/etl-datasets.json` |
| tests | `apps/api/tests/test_outdoor_feature_loader.py` |

## 데이터 소스 매핑

| 대상 feature | primary/source | TripMate feature type | outdoor kind | 역할 |
| --- | --- | --- | --- | --- |
| 산·명산 | `krforest.travel.mountain_stories()` | `area` | `mountain` | 산 중심점/기본 설명. 원천이 polygon을 주지 않으면 centroid area로 우선 적재 |
| 휴양림·수목원 | `krforest.travel.recreation_forest_arboretums()` | `place` | `recreation_forest`, `arboretum` | 산림청 SHP 포인트를 primary POI로 사용 |
| 산림교육센터 | `krforest.travel.forest_education_centers()` | `place` | `forest_education` | 가족·체험형 산림 POI |
| 유아숲체험원 | `krforest.travel.kid_forest_centers()` | `place` | `kid_forest` | 가족·체험형 산림 POI |
| 전통마을숲 | `krforest.travel.traditional_village_forests()` | `place` | `village_forest` | 마을 산책/문화형 숲 POI |
| 등산로 | `krforest.travel.forest_trail_file_features()` | `route` | `hiking_trail` | LineString/route geometry primary layer |
| 둘레길·숲길 | `krforest.travel.dulle_trail_features()` | `route` | `trekking_course` | walking/trekking route geometry primary layer |
| 캠핑장 | `python-mois-api` localdata `general_campgrounds`, `auto_campgrounds` | `place` | `campground` | 산행·트레킹 주변 숙박 support feature |
| 전문·종합휴양업 | `python-mois-api` localdata `special_resorts`, `comprehensive_resorts` | `place` | `outdoor_support` | 휴양림/관광 휴양 시설 보조·교차검증 |
| 국립공원 | 현재 krforest/krmois 직접 원천 없음 | `area`, `route`, `place` 예정 | `national_park` | KNPS 또는 V-WORLD 추가 자료가 필요 |

## DB 구조

### `map_features`

공통 지도 feature의 권위 있는 serving table이다. 이번 migration에서 기존 POINT 제약을 완화해 `geom`을 `geometry(Geometry, 4326)`로 승격했다. 이 변경이 없으면 등산로/숲길 LineString을 저장할 수 없다.

사용 기준:

- `feature_type = place`: 휴양림, 수목원, 산림교육센터, 캠핑장 등 점형 POI
- `feature_type = area`: 산, 국립공원, 산림 구역 등 면형 또는 centroid 기반 구역
- `feature_type = route`: 등산로, 둘레길, 숲길 등 선형 경로
- `geom`: 원천 geometry. Point/LineString/Polygon 모두 허용
- `centroid`, `longitude`, `latitude`: 지도 중심, 목록 정렬, 법정동 매핑용 대표점
- `category_code`, `category_name`: TripMate 8자리 카테고리
- `legal_dong_code`, `sigungu_code`, `sido_code`: `RegionServingBoundary` point-in-polygon 결과

### `outdoor_feature_profiles`

산림·등산 도메인 전용 profile이다. 공통 feature에서 표현하기 어려운 outdoor 속성을 별도로 둔다.

| 컬럼 | 의미 |
| --- | --- |
| `feature_id` | `map_features.id` 1:1 FK |
| `outdoor_kind` | `national_park`, `mountain`, `recreation_forest`, `arboretum`, `hiking_trail`, `trekking_course`, `campground` 등 |
| `feature_role` | `primary`, `support`, `safety`, `enrichment` |
| `source_provider`, `source_dataset_key` | `python-krforest-api`, `python-mois-api`와 dataset key |
| `confidence` | 원천 신뢰도. krforest 공간자료는 높게, krmois 보조자료는 중간으로 둔다 |
| `distance_m`, `duration_min`, `difficulty` | 경로형 feature의 거리/소요시간/난이도 |
| `reservation_url`, `safety_note`, `extra` | 예약/안전/원천별 long-tail 속성 |

### Source trace

원천 재처리와 교차검증을 위해 기존 source trace 테이블을 그대로 사용한다.

- `source_records`: provider dataset, source id, raw payload hash, raw geometry
- `map_feature_source_links`: feature와 source record 연결, match method, confidence
- `map_feature_provider_refs`: provider별 stable id/name/address/phone 참조
- `map_feature_web_links`: 공식 홈페이지/예약 URL

## Primary와 Support 기준

산림청 자료는 outdoor feature의 primary layer로 둔다. 산림청 SHP/route 파일은 지도 geometry가 있고, 산림청 산 정보 API는 산 이름/주소/높이/설명을 제공하므로 TripMate의 산림 지도 레이어를 직접 구성할 수 있다.

행정안전부 localdata 인허가 자료는 산림·등산 목적지 자체라기보다 주변 편의·숙박·휴양업 보조자료다. 따라서 `feature_role = support` 또는 `enrichment`로 저장한다. 예를 들어 등산로 주변 캠핑장을 추천하거나, 휴양림·휴양업 명칭/좌표가 기존 공공데이터와 충돌할 때 교차검증 후보를 만드는 데 쓴다.

기존 공공 장소 ETL(`public_recreation_forest`, `public_arboretum_basic`, `public_campground`)은 계속 보조자료로 사용한다. 다만 서로 다른 provider의 같은 장소를 이름만으로 자동 병합하면 오탐 위험이 커서, 현재 구현은 provider dataset/source id 기준 멱등 upsert를 우선한다. 후속으로는 provider ref, 법정동, 좌표 거리, normalized name을 조합한 `FeatureMappingCandidate` 기반 검수 흐름을 추가하는 것이 안전하다.

## 인덱스 설계

성능 기준은 지도 bbox/반경 조회, 목록 검색, source 재처리, 도메인 필터를 분리하는 것이다.

| 쿼리 | 사용 인덱스 |
| --- | --- |
| 지도 bbox/공간 필터 | `ix_map_features_geom` GiST |
| 대표점 반경/근접 정렬 | `ix_map_features_centroid` GiST |
| feature type/status/visible | `ix_map_features_type`, `ix_map_features_status_visible` |
| 카테고리 필터 | `ix_map_features_category` |
| 행정구역 필터 | `ix_map_features_legal_dong`, `ix_map_features_sigungu` |
| 이름 검색 | `ix_map_features_search`, `ix_map_features_name_trgm` |
| outdoor kind/role 필터 | `ix_outdoor_feature_profiles_kind_role` |
| provider 재수집/디버깅 | `ix_outdoor_feature_profiles_source`, `ix_source_records_provider_dataset`, provider ref unique index |
| 법정동 point-in-polygon | `ix_rsb_geom`, `ix_rsb_level_code` |

JSONB 전체 GIN index는 추가하지 않았다. outdoor long-tail 속성은 쓰기량과 필드 변동성이 크므로, 실제 필터 요구가 생긴 필드만 표현식 index로 승격한다.

## ETL 함수

외부 활용/테스트에서 바로 부를 수 있는 함수는 다음이다.

| 함수 | 입력 | 출력 |
| --- | --- | --- |
| `load_krforest_spatial_points(session, dataset_key, records, collected_at=None)` | krforest `ForestSpatialPoint` iterable | `OutdoorFeatureLoadResult` |
| `load_krforest_spatial_features(session, dataset_key, records, collected_at=None)` | krforest `ForestSpatialFeature` iterable | `OutdoorFeatureLoadResult` |
| `load_krforest_standard_recreation_forests(session, records, collected_at=None)` | krforest `StandardRecreationForest` iterable | `OutdoorFeatureLoadResult` |
| `load_krforest_mountain_story_areas(session, records, collected_at=None)` | `mountain_stories()` raw item iterable | `OutdoorFeatureLoadResult` |
| `load_mois_outdoor_license_records(session, slug, records, collected_at=None)` | `python-mois-api` `LocalDataRecord` iterable | `OutdoorFeatureLoadResult` |
| `load_default_krforest_outdoor_features(session, client, collected_at=None)` | `krforest.ForestClient` | dataset별 결과 dict |
| `load_default_mois_outdoor_license_features(session, files_client, collected_at=None)` | `mois.LocalDataFileClient` | slug별 결과 dict |

Dagster dataset key와 기본 스케줄:

- `krforest_outdoor_feature`: 3월/9월 20일 04:30
- `krmois_outdoor_license`: 3월/6월/9월/12월 20일 04:50

## 검증

Windows Python 환경에서 다음을 확인했다.

- `test_outdoor_feature_loader.py`: PostGIS test DB에 krforest place/area/route와 krmois support place를 실제 insert
- `map_features.geom`이 LineString route를 저장하는지 검증
- `RegionServingBoundary` point-in-polygon 법정동 매핑 검증
- source record, source link, provider ref, outdoor profile, place/area/route detail 생성 검증
- 거리 `3.2km`를 `3200m`, 소요시간 `2시간 30분`을 `150분`으로 정규화 검증
- 관련 model/migration/config 테스트 42건 통과

현재 Windows Python에는 `dagster` 패키지가 없어 `tests/test_dagster_etl.py`는 collection 단계에서 실행하지 못했다. WSL2 환경도 현재 `python`/`rg`가 없어 TripMate 지침의 WSL2 검증은 수행하지 못했다.

## 예상 이슈

- 국립공원 경계/탐방로는 krforest/krmois만으로 채울 수 없다. KNPS 국립공원 경계, 탐방로, 출입통제, 시설 POI 또는 V-WORLD 주제도/용도지역 자료가 필요하다.
- 산 정보 API가 polygon을 주지 않는 경우 산 feature는 centroid 기반 `area`로 저장된다. 면적/능선/산역 경계가 필요하면 별도 산 경계 자료가 필요하다.
- 등산로/숲길 route geometry는 원천별 위치 정확도와 위상 연결성이 다를 수 있다. 내비게이션 대체가 아니라 참고 레이어로 표시해야 한다.
- krmois 인허가 좌표는 사업장 주소 중심점이다. 등산로 입구, 실제 캠핑장 부지 polygon, 주차장 위치와 다를 수 있다.
- source id가 불안정한 원천은 명칭/주소/좌표 정정 시 새 feature로 들어올 수 있다. 운영 검수용 중복 후보 workflow가 필요하다.
- 전국 단위 route를 한 번에 목록 검색하면 geometry payload가 커질 수 있다. API는 목록에서는 centroid/요약만 반환하고 상세에서 geometry를 내려주는 흐름이 안전하다.

## 추가 확보 권장 자료

| 우선순위 | 자료 | 용도 |
| --- | --- | --- |
| 높음 | KNPS 국립공원 경계 SHP/GeoJSON | `national_park` area feature primary source |
| 높음 | KNPS 탐방로/탐방지원센터/주차장/대피소/야영장 POI | 국립공원 route/place 구성 |
| 높음 | V-WORLD 또는 공공데이터포털 국립공원·공원구역 도형 | KNPS 경계 교차검증 |
| 중간 | 산림청 명산등산로, 100대명산 파일데이터 | mountain과 hiking route 연결, 추천 코스 보강 |
| 중간 | 산악기상 관측지점과 산불/산사태 위험 자료 | route/place safety overlay |
| 낮음 | 휴양림 예약/시설 상세 파일 | 휴양림 상세 화면, 예약 링크/시설 정보 보강 |
