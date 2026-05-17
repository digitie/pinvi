# 지도 객체 통합 스키마 설계안

## 상태

이 문서는 TripMate의 장소, 행사, 경로, 구역, 공지성 데이터를 하나의 지도 객체 모델로 관리하기 위한 **구현 기준 문서**다.

2026-04-29 기준 백엔드는 `places` 중심 구조를 신규 `map_features` 중심 구조로 대체했다. 기존 `places`, `place_source_records`, `place_source_links`, `place_provider_refs`, `place_web_links`는 Alembic `20260429_0021_map_feature_schema.py`에서 다음 테이블로 이관된다.

- 지도 객체: `map_features`
- 장소 상세: `place_details`
- 원천 레코드: `source_records`
- 원천 연결: `map_feature_source_links`
- provider 참조: `map_feature_provider_refs`
- 웹 링크: `map_feature_web_links`
- 전국문화축제표준데이터: `tour_serving_public_cultural_festival`, `tour_raw_public_cultural_festival`
- 여행 일정: `trips`, `trip_days`, `trip_plan_items.map_feature_id`

축제 serving table은 아직 별도 테이블을 유지한다. 사용자가 지도 객체로 승격된 행사·장소·경로·구역·공지 데이터를 여행 일정에 넣을 때는 `trip_plan_items.map_feature_id`를 사용한다.

## 설계 목표

TripMate에는 지도에 올라가는 데이터와 지도 데이터를 설명하거나 묶는 데이터가 섞여 들어온다. 이를 한 테이블에 모두 넣으면 `content`처럼 좌표가 없을 수 있는 데이터 때문에 geometry 제약이 흐려지고, 반대로 모든 데이터에 좌표를 optional로 두면 지도 viewport 조회 성능과 데이터 품질 기준이 약해진다.

따라서 최상위 개념을 아래처럼 나눈다.

지도에 실제로 올라가는 객체:

- `place`: 장소, 시설, 상점, 주차장, 화장실, 충전소, 전망 지점
- `event`: 축제, 공연, 전시, 장터, 체험
- `route`: 산책로, 등산로, 자전거길, 드라이브 코스
- `area`: 국립공원, 해변, 관광특구, 시장 권역, 제한 구역
- `notice`: 폐쇄, 공사, 교통통제, 혼잡, 기상특보 같은 지도상 공지

지도 객체를 묶거나 설명하는 콘텐츠:

- `content`: 기사, 큐레이션 목록, 여행 템플릿, 가이드

핵심 결정은 다음과 같다.

1. `content`는 `map_feature`에 넣지 않고 별도 테이블로 둔다.
2. `map_feature`는 지도에 그릴 수 있는 객체만 담고 geometry를 필수로 둔다.
3. 세부 분류는 `place_detail`, `event_detail`, `route_detail`, `area_detail`, `notice_detail`에서 처리한다.
4. 외부 원천 row는 `source_record`에 두고, 지도 객체와의 연결·후보 매핑은 별도 테이블로 관리한다.
5. 태그와 미디어는 지도 객체와 콘텐츠가 모두 사용할 수 있게 공통 테이블로 둔다.

## 현재 구조와의 차이

### 현재 `places`와 새 `map_feature`

기존 `places`는 장소 전용 canonical table이었다. 좌표 타입도 `POINT`만 전제로 했다. 새 구조에서는 `place`뿐 아니라 `event`, `route`, `area`, `notice`도 지도에서 같은 방식으로 조회해야 하므로 공통 지도 객체 테이블을 사용한다.

구현된 마이그레이션 방향:

- `places` row는 `map_feature(feature_type='place')` + `place_detail`로 이관한다.
- `places.primary_category_code`는 우선 `map_feature.category_code` 또는 `place_detail`의 상세 분류 보조값으로 옮긴다.
- 현재 `places.source_specific_attributes`는 `place_detail.extra` 또는 `source_record.raw_data`로 역할을 나눈다.
- 기존 `place_source_records`는 범용 `source_records`로 흡수한다.

### 현재 축제 테이블과 새 `event`

현재 전국문화축제표준데이터는 장소와 다른 serving table에 저장되어 있다. 이는 기간성 데이터라는 점에서 올바른 분리였지만, 지도 레이어와 여행계획 item은 앞으로 `event`라는 공통 feature type을 바라보는 것이 더 단순하다.

마이그레이션 방향:

- `tour_serving_public_cultural_festival` row는 `map_feature(feature_type='event')` + `event_detail(event_kind='festival')` 후보가 된다.
- 사용자가 직접 저장한 축제는 `trip_plan_items.map_feature_id`를 통해 이벤트 feature를 참조하도록 바꾼다.

### 현재 `trip_plan_items`

현재 `trip_plan_items`는 `resource_type`, `map_feature_id`, `festival_id`, `resource_key`를 가진다. `place`, `event`, `route`, `area`, `notice`는 `map_feature_id`로 연결하고, 기존 전국문화축제표준데이터 serving row는 아직 `festival_id`로 연결한다.

확정 기준:

- `place_id`는 제거하고 `map_feature_id`로 대체한다.
- 신규 지도 객체 일정 항목은 `map_feature_id`를 사용한다.
- 기존 전국문화축제표준데이터는 event 승격 전까지 `festival_id` 호환 경로를 유지한다.
- 지도 객체가 아닌 콘텐츠를 일정에 넣을 필요가 생기면 별도 `content_id` 또는 `trip_plan_item_content_link`를 검토한다. 기본 일정 stop은 `map_feature`를 참조한다.

## 네이밍 기준

사용자 설계안의 논리명은 `map_feature`, `place_detail`처럼 단수형이다. 현재 코드베이스는 `places`, `trip_plan_items`, `place_source_records`처럼 대체로 복수형 테이블을 사용한다.

실제 구현 추천:

| 논리명 | 구현 추천 테이블명 | 이유 |
| --- | --- | --- |
| `map_feature` | `map_features` | SQLAlchemy 모델 `MapFeature`와 기존 복수형 convention 정합성 |
| `place_detail` | `place_details` | 1:1 상세 테이블이지만 기존 convention 유지 |
| `event_detail` | `event_details` | 동일 |
| `route_detail` | `route_details` | 동일 |
| `area_detail` | `area_details` | 동일 |
| `notice_detail` | `notice_details` | 동일 |
| `content` | `contents` 또는 `content_items` | `content`가 추상 명사라 검색성이 낮음. 추천은 `content_items` |
| `content_feature_link` | `content_feature_links` | 다대다 link convention |
| `source_record` | `source_records` | 기존 `place_source_records`와 연결 |
| `feature_mapping_candidate` | `feature_mapping_candidates` | 후보가 여러 개 쌓임 |

문서에서는 읽기 편의를 위해 논리명을 함께 사용하되, migration 작성 시에는 구현 추천 테이블명을 기준으로 한다.

## 타입과 Enum 기준

제안 SQL은 PostgreSQL native enum을 사용한다. 그러나 현재 TripMate 백엔드는 SQLAlchemy 2 + Alembic에서 문자열 컬럼과 `CheckConstraint`를 주로 사용한다. `place_kind`, `resource_type`, `event_status` 등도 문자열 기반이다.

추천:

- `feature_type`처럼 최상위 타입이 매우 안정적인 값은 PostgreSQL enum 또는 `varchar + check` 둘 다 가능하다.
- 현재 코드 스타일과 migration 유연성을 우선하면 `String(32)` + `CheckConstraint`를 추천한다.
- `source_name`은 enum으로 고정하지 않는다. TripMate provider는 `data_go_kr`, `juso`, `vworld`, `opinet`, `ex`, `kma`, `airkorea`, `kasi`, `kakao`, `naver`, `google`, `manual`, `system`처럼 계속 늘어난다. source는 `provider`, `dataset_key` 문자열 조합으로 관리하는 편이 안전하다.
- `place_kind`, `event_kind`, `route_kind`, `area_kind`, `notice_kind`, `content_kind`는 처음에는 `varchar + check`로 시작하고, 관리자에서 코드표를 수정해야 하는 단계가 오면 기준 테이블로 분리한다.

최초 허용값:

| 컬럼 | 허용값 |
| --- | --- |
| `feature_type` | `place`, `event`, `route`, `area`, `notice` |
| `place_kind` | `tourist_spot`, `restaurant`, `cafe`, `hotel`, `parking`, `toilet`, `ev_charger`, `viewpoint` |
| `event_kind` | `festival`, `performance`, `exhibition`, `market`, `activity` |
| `route_kind` | `walking`, `hiking`, `cycling`, `driving`, `scenic` |
| `area_kind` | `national_park`, `beach`, `tourism_zone`, `market_area`, `restricted_area` |
| `notice_kind` | `closure`, `construction`, `traffic_control`, `congestion`, `weather_warning` |
| `content_kind` | `article`, `curated_list`, `itinerary_template`, `guide` |

확장 후보는 바로 enum에 넣지 말고 실제 데이터셋이 들어올 때 추가한다. 예를 들어 박물관/미술관은 `place_kind='tourist_spot'` 또는 후속 `museum` 확장 후보이고, 축제 취소 공지는 `notice_kind='closure'` 또는 `event_detail.is_cancelled`로 처리할 수 있다.

## PostgreSQL extension

필수 extension:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

`postgis`는 geometry 저장, bbox 조회, point-in-polygon, centroid 계산에 필요하다. `pg_trgm`은 한국어 장소명과 주소 문자열 검색의 초기 품질을 보완하는 데 사용한다.

초기 migration에서 이미 `postgis`가 활성화되어 있다면 새 migration에서 중복 생성해도 `IF NOT EXISTS` 때문에 안전하다. downgrade에서 extension을 drop하지 않는다. 다른 테이블이나 운영 데이터가 같은 extension에 의존할 수 있기 때문이다.

## 공통 지도 객체

### `map_features`

`map_features`는 지도 viewport 조회, marker 표시, 검색, 여행 일정 연결의 공통 기준이다.

권장 SQLAlchemy 모델 타입:

- PK는 현재 코드베이스와 맞춰 `UUID`를 사용한다.
- geometry는 `Geometry("GEOMETRY", srid=4326, spatial_index=False)`로 선언하고, Alembic에서 GiST index를 명시 생성한다.
- centroid는 `Geometry("POINT", srid=4326, spatial_index=False)`로 둔다.
- timestamps는 기존 `TimestampMixin`과 KST 정책을 따른다.

권장 컬럼:

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | UUID PK | Y | 내부 지도 객체 ID |
| `feature_type` | varchar(32) | Y | `place`, `event`, `route`, `area`, `notice` |
| `name` | varchar(255) | Y | 지도와 목록의 대표 이름 |
| `subtitle` | varchar(255) | N | 보조 제목 |
| `summary` | text | N | 짧은 설명 |
| `description` | text | N | 상세 설명 |
| `category_code` | varchar(32) | N | TripMate 카테고리 또는 source별 표시 분류. 장소 8자리 카테고리는 선행 0 보존 |
| `category_name` | varchar(120) | N | 화면 표시 카테고리 |
| `geom` | geometry(GEOMETRY, 4326) | Y | 지도 객체의 실제 geometry |
| `geometry_kind` | varchar(16) | Y | `point`, `line`, `polygon`, `mixed` |
| `centroid` | geometry(POINT, 4326) | Y | marker, 정렬, 근처 검색 기준점 |
| `address` | varchar(700) | N | 전체 주소 snapshot |
| `road_address` | varchar(500) | N | 도로명주소 snapshot |
| `jibun_address` | varchar(500) | N | 지번주소 snapshot |
| `sido_code` | varchar(10) | N | 시도 코드. 법정동코드 기반 도출값 |
| `sigungu_code` | varchar(10) | N | 시군구 코드 |
| `legal_dong_code` | varchar(10) FK | N | `address_code_standard.legal_dong_code` 참조, `ON DELETE SET NULL` |
| `admin_dong_code` | varchar(10) | N | 행정동코드 |
| `road_name_code` | varchar(12) | N | 도로명코드 |
| `road_address_management_no` | varchar(64) | N | 도로명주소관리번호 |
| `phone` | varchar(120) | N | 대표 전화번호 |
| `website_url` | text | N | 대표 웹사이트 |
| `search_text` | tsvector | N | DB 검색 보조. 한글 검색은 trigram을 함께 사용 |
| `popularity_score` | numeric(10,3) | Y | 인기 점수, 기본 0 |
| `priority_score` | numeric(10,3) | Y | 지도/추천 우선순위, 기본 0 |
| `status` | varchar(32) | Y | `draft`, `active`, `inactive`, `temporarily_closed`, `deleted` |
| `is_visible` | boolean | Y | 지도/검색 노출 여부 |
| `primary_source_record_id` | UUID FK | N | 대표 원천 row. `source_records.id` 참조 |
| `extra` | jsonb | Y | 공통 컬럼으로 승격하지 않은 보조 값 |
| `created_at` | timestamptz | Y | KST 저장 시각 |
| `updated_at` | timestamptz | Y | KST 수정 시각 |

권장 제약:

- `feature_type IN ('place', 'event', 'route', 'area', 'notice')`
- `geometry_kind IN ('point', 'line', 'polygon', 'mixed')`
- `status IN ('draft', 'active', 'inactive', 'temporarily_closed', 'deleted')`
- `centroid IS NOT NULL`
- `ST_SRID(geom) = 4326`
- `ST_SRID(centroid) = 4326`
- `GeometryType(centroid) = 'POINT'`
- `legal_dong_code`는 주소 기준 테이블 FK이며 주소가 사라져도 feature 자체는 유지되도록 `ON DELETE SET NULL`

주의:

- `map_features.geom`은 필수다. 좌표나 polygon이 없는 원천 row는 아직 지도 객체가 아니므로 `source_records` 또는 provider serving table에 남긴다.
- 전체 시스템 에러, ETL 실패 알림, 관리자 공지는 `notice`가 아니다. `notice`는 지도상 장소·구역·경로와 연결되는 사용자 지도 공지에만 사용한다.
- 상세 테이블과 `feature_type`의 정합성은 단순 FK/CheckConstraint만으로 보장할 수 없다. 예를 들어 `place_details.feature_id`가 참조한 row의 `feature_type='place'`인지 DB check로 직접 확인할 수 없다. service layer 검증과 migration contract test를 기본으로 하고, 필요하면 DB trigger를 추가한다.

권장 인덱스:

- `BTREE(feature_type)`
- `BTREE(status, is_visible)`
- `BTREE(category_code)`
- `BTREE(legal_dong_code)`
- `BTREE(sigungu_code)`
- `GIST(geom)`
- `GIST(centroid)`
- `GIN(search_text)`
- `GIN(name gin_trgm_ops)`
- 필요할 때만 `extra` 표현식 index 또는 부분 GIN index

`extra` 전체 GIN index는 초기 기본값으로 두지 않는다. JSONB 쓰기 비용과 index bloat가 생길 수 있으므로 실제 필터 요구가 생긴 필드에만 표현식 index를 만든다.

## centroid와 검색 텍스트

### centroid 생성

PostGIS에서 `centroid`는 다음 방식으로 보정한다.

- `point`: 입력 point를 그대로 사용한다.
- `line`: 기본은 `ST_PointOnSurface(geom)`를 사용한다. 경로 중간점이 UX상 더 낫다는 요구가 생기면 `ST_LineInterpolatePoint`로 전환한다.
- `polygon`: `ST_PointOnSurface(geom)`를 사용한다. `ST_Centroid`는 polygon 밖으로 나갈 수 있으므로 marker 기준점에는 부적합할 수 있다.
- `mixed`: 대표 geometry를 별도 선정하거나 `ST_PointOnSurface`를 사용하되, 지도 표현 정책을 source별로 문서화한다.

구현 선택지:

1. DB trigger에서 `centroid`를 자동 생성한다.
2. loader/service에서 `centroid`를 계산해 저장하고 DB에서는 `NOT NULL`과 SRID만 검증한다.

추천은 DB trigger다. ETL이 여러 경로로 들어와도 marker 기준점이 누락되지 않는다. 단, SQLAlchemy 테스트에서는 trigger 생성 migration과 model metadata 테스트를 함께 둔다.

### 검색 텍스트

제안 SQL의 `to_tsvector('simple', ...)`은 영문, 숫자, 주소 토큰 검색에는 도움이 되지만 한국어 형태소 검색으로 충분하지 않다. TripMate 초기 검색은 다음 조합을 추천한다.

- 이름: `pg_trgm` 기반 `GIN(name gin_trgm_ops)`
- 주소: `pg_trgm` 또는 정규화 주소 컬럼 인덱스
- 카테고리/지역 필터: btree
- 영문/숫자/provider id: `search_text tsvector`

검색 품질을 높이는 전용 검색 엔진은 나중에 붙인다. 현재 DB에서는 `pg_trgm`과 명시적 필터 조합이 가장 단순하고 안정적이다.

## 상세 테이블

상세 테이블은 모두 `feature_id`를 PK/FK로 갖는 1:1 확장 테이블이다. 삭제 동작은 `ON DELETE CASCADE`를 사용한다.

### `place_details`

장소성 POI의 세부 정보다.

필수:

- `feature_id`
- `place_kind`

권장 컬럼:

- `opening_hours jsonb`
- `closed_days text`
- `admission_fee text`
- `price_level smallint`
- `reservation_required boolean`
- `reservation_url text`
- `parking_available boolean`
- `pet_allowed boolean`
- `stroller_accessible boolean`
- `wheelchair_accessible boolean`
- `indoor boolean`
- `outdoor boolean`
- `checkin_time time`
- `checkout_time time`
- `recommended_duration_min integer`
- `extra jsonb not null default '{}'`
- `created_at`, `updated_at`

제약:

- `place_kind IN ('tourist_spot', 'restaurant', 'cafe', 'hotel', 'parking', 'toilet', 'ev_charger', 'viewpoint')`
- `price_level IS NULL OR price_level BETWEEN 0 AND 5`
- `recommended_duration_min IS NULL OR recommended_duration_min >= 0`

현재 공공 장소 ETL의 수목원, 휴양림, 박물관/미술관, 캠핑장은 우선 `place`로 들어갈 수 있다. 다만 `museum`, `campground`, `arboretum`, `recreation_forest` 같은 세부 kind가 필요해지면 `place_kind` 확장 또는 별도 subtype table을 검토한다.

### `event_details`

기간성이 있는 행사다.

필수:

- `feature_id`
- `event_kind`
- `start_date`
- `end_date`

권장 컬럼:

- `start_time time`
- `end_time time`
- `venue_name text`
- `venue_feature_id UUID FK map_features(id) ON DELETE SET NULL`
- `organizer text`
- `host text`
- `sponsor text`
- `contact_phone text`
- `official_url text`
- `reservation_url text`
- `fee_info text`
- `is_free boolean`
- `age_limit text`
- `is_cancelled boolean not null default false`
- `cancellation_reason text`
- `recurrence_rule text`
- `extra jsonb not null default '{}'`
- `created_at`, `updated_at`

제약:

- `event_kind IN ('festival', 'performance', 'exhibition', 'market', 'activity')`
- `end_date >= start_date`
- `end_time IS NULL OR start_time IS NULL OR end_time >= start_time`

전국문화축제표준데이터는 `event_kind='festival'` 후보가 된다. 운영시간 필드가 없으므로 `start_time`, `end_time`을 비워두고 provider 텍스트를 `extra`나 `description`에 남긴다.

### `route_details`

선형 geometry를 가진 경로다.

필수:

- `feature_id`
- `route_kind`

권장 컬럼:

- `distance_m integer`
- `duration_min integer`
- `difficulty varchar(32)`
- `start_name text`
- `end_name text`
- `start_feature_id UUID FK map_features(id) ON DELETE SET NULL`
- `end_feature_id UUID FK map_features(id) ON DELETE SET NULL`
- `elevation_gain_m integer`
- `elevation_loss_m integer`
- `min_elevation_m integer`
- `max_elevation_m integer`
- `is_loop boolean not null default false`
- `recommended_season text`
- `surface_type varchar(32)`
- `accessibility_note text`
- `safety_note text`
- `extra jsonb not null default '{}'`
- `created_at`, `updated_at`

제약:

- `route_kind IN ('walking', 'hiking', 'cycling', 'driving', 'scenic')`
- `distance_m IS NULL OR distance_m >= 0`
- `duration_min IS NULL OR duration_min >= 0`

경로 geometry는 원칙적으로 `LINESTRING` 또는 `MULTILINESTRING`이다. 단순 경유지 모음만 있고 선형 geometry가 없는 원천은 `source_record` 또는 `content`로 먼저 저장하고, 지도에 올릴 route는 geometry 생성 후 승격한다.

### `route_waypoints`

경로의 경유지는 별도 테이블로 둔다.

권장 컬럼:

- `id UUID PK`
- `route_feature_id UUID FK route_details(feature_id) ON DELETE CASCADE`
- `seq integer not null`
- `name text`
- `description text`
- `geom geometry(POINT, 4326) not null`
- `related_feature_id UUID FK map_features(id) ON DELETE SET NULL`
- `created_at timestamptz`

제약과 인덱스:

- `UNIQUE(route_feature_id, seq)`
- `seq >= 1`
- `GIST(geom)`
- `BTREE(route_feature_id, seq)`

### `area_details`

면 또는 복합 polygon으로 표현되는 구역이다.

필수:

- `feature_id`
- `area_kind`

권장 컬럼:

- `managing_org text`
- `contact_phone text`
- `website_url text`
- `rules text`
- `fee_info text`
- `open_season_start date`
- `open_season_end date`
- `area_size_m2 numeric(16,2)`
- `is_restricted boolean not null default false`
- `restriction_note text`
- `extra jsonb not null default '{}'`
- `created_at`, `updated_at`

제약:

- `area_kind IN ('national_park', 'beach', 'tourism_zone', 'market_area', 'restricted_area')`
- `area_size_m2 IS NULL OR area_size_m2 >= 0`
- 계절 시작/종료는 연도 없는 반복 기간일 수 있으므로 `DATE`보다 `MMDD` 문자열이 나을 수 있다. 실제 구현 전 데이터셋을 보고 결정한다.

해수욕장처럼 좌표만 있고 실제 해변 polygon이 없는 데이터는 `place` 또는 `area` 중 하나를 선택해야 한다. 지도에 점 마커만 보이면 `place`, 해변 구역 polygon이 있으면 `area`를 추천한다.

### `notice_details`

지도 위에서 사용자에게 보여줄 상태·통제 정보다.

필수:

- `feature_id`
- `notice_kind`
- `severity`
- `message`

권장 컬럼:

- `valid_from timestamptz`
- `valid_to timestamptz`
- `related_feature_id UUID FK map_features(id) ON DELETE SET NULL`
- `detail text`
- `source_url text`
- `is_resolved boolean not null default false`
- `resolved_at timestamptz`
- `extra jsonb not null default '{}'`
- `created_at`, `updated_at`

제약:

- `notice_kind IN ('closure', 'construction', 'traffic_control', 'congestion', 'weather_warning')`
- `severity IN ('info', 'warning', 'critical')`
- `valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from`
- `resolved_at IS NULL OR is_resolved = true`

기상특보 전체를 지도 marker로 모두 만들지는 않는다. 지도에 표현할 구역 geometry가 있거나 특정 feature와 연결될 때만 `notice`로 승격한다. 시스템 에러/ETL 실패 알림은 관리자 알림/Telegram 시스템 알림이지 `notice`가 아니다.

## 콘텐츠

### `content_items`

콘텐츠는 지도 객체가 아니다. 좌표가 없을 수 있으므로 `map_features`에 넣지 않는다.

예:

- 비 오는 날 추천 장소
- 아이와 가기 좋은 실내 관광지
- 벚꽃 명소 모음
- 축제 주변 주차장 안내
- 1박 2일 여행 템플릿

권장 컬럼:

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | UUID PK | Y | 콘텐츠 ID |
| `content_kind` | varchar(32) | Y | `article`, `curated_list`, `itinerary_template`, `guide` |
| `title` | varchar(255) | Y | 제목 |
| `subtitle` | varchar(255) | N | 부제 |
| `summary` | text | N | 요약 |
| `body` | text | N | 본문 |
| `slug` | varchar(255) unique | N | 공개 URL slug |
| `author_name` | varchar(120) | N | 작성자 표시명 |
| `source_provider` | varchar(40) | N | 원천 provider |
| `source_url` | text | N | 원문 URL |
| `publish_start_at` | timestamptz | N | 공개 시작 |
| `publish_end_at` | timestamptz | N | 공개 종료 |
| `is_published` | boolean | Y | 공개 여부 |
| `priority_score` | numeric(10,3) | Y | 노출 우선순위 |
| `extra` | jsonb | Y | 보조 값 |
| `created_at` | timestamptz | Y | 생성 시각 |
| `updated_at` | timestamptz | Y | 수정 시각 |

`hero_media_id` 직접 FK는 두지 않는 것을 추천한다. `media_assets`와 `content_media`를 먼저 만들고, `content_media.role='hero'`로 대표 이미지를 표현하면 migration 순환과 대표 이미지 변경 이력이 더 단순해진다.

### `content_feature_links`

콘텐츠와 지도 객체의 연결이다.

권장 컬럼:

- `content_id UUID FK content_items(id) ON DELETE CASCADE`
- `feature_id UUID FK map_features(id) ON DELETE CASCADE`
- `role varchar(32) not null default 'related'`
- `sort_order integer not null default 0`
- `note text`

제약:

- `PRIMARY KEY(content_id, feature_id, role)`
- `role IN ('main', 'stop', 'related', 'nearby', 'recommended')`
- `sort_order >= 0`

## 원천 데이터

### `source_records`

외부 provider, 공공데이터, 수동 입력의 원천 row를 저장한다.

권장 컬럼:

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | UUID PK | Y | 원천 row ID |
| `provider` | varchar(40) | Y | `data_go_kr`, `kakao`, `naver`, `google`, `manual`, `system` 등 |
| `dataset_key` | varchar(120) | Y | `public_cultural_festival` 등 |
| `source_entity_type` | varchar(32) | Y | 원천의 타입. `place`, `event`, `route`, `area`, `notice`, `content` 등 |
| `source_entity_id` | varchar(255) | Y | provider 안정 ID 또는 내부 hash |
| `raw_name` | varchar(255) | N | 원천 이름 |
| `raw_address` | varchar(700) | N | 원천 주소 |
| `raw_longitude` | numeric(12,8) | N | 정규화 경도 |
| `raw_latitude` | numeric(12,8) | N | 정규화 위도 |
| `raw_geom` | geometry(GEOMETRY, 4326) | N | 정규화 geometry |
| `raw_start_date` | date | N | 원천 시작일 |
| `raw_end_date` | date | N | 원천 종료일 |
| `raw_data` | jsonb | N | 저장 가능한 원천 payload |
| `raw_payload_hash` | varchar(128) | Y | payload 또는 안정 필드 hash |
| `fetched_at` | timestamptz | N | provider에서 가져온 시각 |
| `imported_at` | timestamptz | Y | TripMate 적재 시각 |
| `expires_at` | timestamptz | N | TTL 대상 원천 만료 시각 |

권장 제약:

- `UNIQUE(provider, dataset_key, source_entity_type, source_entity_id, raw_payload_hash)`
- 최신 serving 판단은 별도 `is_active` 또는 source link에서 처리한다.

제안 SQL의 `source_record(feature_id, content_id)` 직접 FK는 장기적으로 줄이는 것이 좋다. 하나의 source row가 여러 후보 feature와 연결될 수 있고, 반대로 하나의 feature가 여러 source row에서 만들어질 수 있기 때문이다.

추천 구조:

- `source_records`: 원천 row 자체
- `map_feature_source_links`: 원천 row와 지도 객체의 확정 연결
- `content_source_links`: 원천 row와 콘텐츠의 확정 연결
- `feature_mapping_candidates`: 원천 row 사이 또는 feature 후보 사이의 병합 후보

Kakao/Naver/Google 원문 전체는 장기 저장하지 않는다. `source_records.raw_data`는 공공데이터나 저장 허용 provider에만 사용한다. 상업 provider는 안정 필드만 승격하고 원문 전체는 TTL cache 정책을 따른다.

### `map_feature_source_links`

권장 컬럼:

- `feature_id UUID FK map_features(id) ON DELETE CASCADE`
- `source_record_id UUID FK source_records(id) ON DELETE CASCADE`
- `match_method varchar(40) not null`
- `confidence integer not null`
- `is_primary_source boolean not null default false`
- `created_at timestamptz not null`

제약:

- `PRIMARY KEY(feature_id, source_record_id)`
- `confidence BETWEEN 0 AND 100`

### `content_source_links`

권장 컬럼:

- `content_id UUID FK content_items(id) ON DELETE CASCADE`
- `source_record_id UUID FK source_records(id) ON DELETE CASCADE`
- `match_method varchar(40) not null`
- `confidence integer not null`
- `is_primary_source boolean not null default false`
- `created_at timestamptz not null`

제약:

- `PRIMARY KEY(content_id, source_record_id)`
- `confidence BETWEEN 0 AND 100`

## 매핑 후보

### `feature_mapping_candidates`

서로 다른 source row가 같은 현실 객체일 가능성을 저장한다. 자동 병합하지 않고 후보로 남긴다.

권장 컬럼:

- `id UUID PK`
- `source_record_id_a UUID FK source_records(id) ON DELETE CASCADE`
- `source_record_id_b UUID FK source_records(id) ON DELETE CASCADE`
- `candidate_feature_type varchar(32) not null`
- `confidence_score numeric(5,2) not null`
- `name_score numeric(5,2)`
- `date_score numeric(5,2)`
- `address_score numeric(5,2)`
- `distance_score numeric(5,2)`
- `org_score numeric(5,2)`
- `decision varchar(32) not null default 'pending'`
- `decision_reason text`
- `decided_by_user_id UUID`
- `decided_at timestamptz`
- `created_at timestamptz not null`

권장 제약:

- `confidence_score BETWEEN 0 AND 100`
- `source_record_id_a <> source_record_id_b`
- `decision IN ('pending', 'auto_approved', 'approved', 'rejected')`
- `candidate_feature_type IN ('place', 'event', 'route', 'area', 'notice')`
- `(source_record_id_a, source_record_id_b)` unique

중요한 보정:

- `(a, b)`와 `(b, a)`가 중복으로 생기지 않게 loader에서 항상 작은 UUID를 `a`로 넣는다.
- DB에서도 `source_record_id_a < source_record_id_b` check를 둘 수 있다. PostgreSQL UUID 비교가 가능하므로 canonical ordering을 제약으로 강제하는 것을 추천한다.

## 태그

태그는 지도 객체와 콘텐츠 모두에 붙을 수 있다.

테이블:

- `tags`
- `map_feature_tags`
- `content_tags`

권장 컬럼:

`tags`:

- `id UUID PK`
- `name varchar(80) unique not null`
- `slug varchar(120) unique not null`
- `description text`
- `created_at timestamptz`

`map_feature_tags`:

- `feature_id UUID FK map_features(id) ON DELETE CASCADE`
- `tag_id UUID FK tags(id) ON DELETE CASCADE`
- `PRIMARY KEY(feature_id, tag_id)`

`content_tags`:

- `content_id UUID FK content_items(id) ON DELETE CASCADE`
- `tag_id UUID FK tags(id) ON DELETE CASCADE`
- `PRIMARY KEY(content_id, tag_id)`

`slug`는 영문/숫자/하이픈 기반으로 정규화하고, 한글 표시는 `name`에 둔다.

## 미디어

### `media_assets`

사진, 썸네일, 지도 아이콘, 출처 정보를 저장한다.

권장 컬럼:

- `id UUID PK`
- `media_type varchar(32) not null default 'image'`
- `url text not null`
- `thumbnail_url text`
- `storage_key text`
- `width integer`
- `height integer`
- `title text`
- `alt_text text`
- `source_provider varchar(40)`
- `source_url text`
- `license text`
- `credit text`
- `extra jsonb not null default '{}'`
- `created_at timestamptz`

제약:

- `media_type IN ('image', 'video', 'icon')`
- `width IS NULL OR width > 0`
- `height IS NULL OR height > 0`

외부 이미지 URL은 provider 약관과 라이선스를 확인해야 한다. 장기 저장이 가능한 이미지는 RustFS(S3 compatible object storage)에 저장하고, `storage_key`에는 RustFS bucket 내부 object key를 기록한다. 그렇지 않은 이미지는 링크/썸네일 정책을 별도로 둔다.

RustFS 기준:

- 파일 본문은 Postgres에 저장하지 않는다.
- API는 `POST /storage/upload-urls`에서 presigned PUT URL을 발급한다.
- object key는 `user-uploads/{purpose}/{user_id}/yyyy/mm/{uuid}.{ext}` 형식을 기본으로 한다.
- 공개 URL은 저장값이 아니라 `storage_key`에서 파생되는 값으로 본다. CDN 또는 public reverse proxy가 없으면 도메인 API가 presigned GET URL을 발급한다.

### 링크 테이블

- `map_feature_media`
- `content_media`

공통 컬럼:

- 대상 ID
- `media_id UUID FK media_assets(id) ON DELETE CASCADE`
- `role varchar(32) not null`
- `sort_order integer not null default 0`

권장 role:

- 지도 객체: `thumbnail`, `hero`, `gallery`, `icon`
- 콘텐츠: `hero`, `thumbnail`, `body`, `gallery`

대표 이미지는 `role='hero'`와 `sort_order=0`으로 표현한다. 한 대상에 hero가 여러 개 생기는 것을 막으려면 부분 unique index를 둔다.

예:

```sql
CREATE UNIQUE INDEX uq_map_feature_media_one_hero
ON map_feature_media (feature_id)
WHERE role = 'hero';
```

## 여행 일정 연결

현재 `trip_plan_items`는 `map_feature_id`, `festival_id`, `resource_key`를 갖는다.

현재 기준:

- `map_feature_id UUID NULL REFERENCES map_features(id) ON DELETE RESTRICT`
- `resource_type` 허용값은 `place`, `event`, `route`, `area`, `notice`, `festival`, `trail`, `scenic_road`, `custom`
- 기존 `place_id`는 제거했다.
- 기존 `festival_id`는 전국문화축제 serving table 호환용으로 유지한다.
- `title_snapshot`, `address_snapshot`, `longitude`, `latitude`, `starts_at`, `ends_at`은 유지

이유:

- 사용자가 여행 일정에 저장한 시점의 이름, 주소, 좌표는 snapshot으로 보존해야 한다.
- 원천 row나 feature가 나중에 비활성화되어도 과거 여행 일정은 깨지면 안 된다.
- 축제, 둘레길, 드라이브 코스, 통제 구역 같은 신규 타입이 들어와도 FK 컬럼을 계속 추가하지 않아도 된다.

## 지도 viewport 조회

추천 쿼리:

```sql
SELECT
    id,
    feature_type,
    name,
    subtitle,
    category_code,
    category_name,
    geometry_kind,
    ST_AsGeoJSON(geom)::json AS geometry,
    ST_AsGeoJSON(centroid)::json AS centroid,
    popularity_score,
    priority_score
FROM map_features
WHERE is_visible = TRUE
  AND status = 'active'
  AND feature_type IN ('place', 'event', 'route', 'area', 'notice')
  AND geom && ST_MakeEnvelope(:min_lng, :min_lat, :max_lng, :max_lat, 4326)
ORDER BY priority_score DESC, popularity_score DESC
LIMIT 500;
```

후속 최적화:

- marker만 필요한 zoom level에서는 `centroid && envelope`를 먼저 사용할 수 있다.
- polygon/route geometry가 큰 경우 vector tile 또는 simplification table을 별도로 둔다.
- 지도에서는 처음부터 모든 상세 필드를 가져오지 않고, marker 목록과 상세 조회를 분리한다.

## 지도 상세 조회

상세 조회는 `feature_type`을 먼저 확인한 뒤 해당 상세 테이블을 join한다.

예:

```sql
SELECT f.*, p.*
FROM map_features f
JOIN place_details p ON p.feature_id = f.id
WHERE f.id = :feature_id
  AND f.feature_type = 'place';
```

`event`, `route`, `area`, `notice`도 같은 패턴이다.

API에서는 `feature_type`별 response schema를 분리한다. 하나의 거대한 nullable schema로 모든 타입을 반환하지 않는다.

## 검토 중 발견한 오류와 보정 사항

1. `content_detail`을 `map_feature` 아래에 두면 geometry 없는 콘텐츠를 표현하기 어렵다. 최종 구조는 `content_items`와 `content_feature_links` 분리가 맞다.
2. `map_feature.geom NOT NULL`은 content를 분리하는 조건에서만 맞다. 지도에 올리지 못하는 원천 row는 `source_records`에 머문다.
3. 현재 백엔드는 UUID PK를 쓰므로 `BIGSERIAL`보다 UUID를 추천한다.
4. `source_name` PostgreSQL enum은 현재 provider 확장 속도와 맞지 않는다. `provider`, `dataset_key` 문자열 조합을 추천한다.
5. `source_record(feature_id, content_id)` 직접 FK는 하나의 원천 row가 여러 후보와 연결될 수 있는 요구와 충돌한다. link table을 추천한다.
6. `feature_mapping_candidate`의 `(a, b)` unique는 `(b, a)` 중복을 막지 못한다. canonical ordering check 또는 loader 정렬이 필요하다.
7. `hero_media_id` 직접 FK는 `media_asset` 생성 순서와 대표 이미지 변경 정책을 복잡하게 만든다. `content_media.role='hero'`를 추천한다.
8. 상세 테이블의 `feature_type` 정합성은 FK만으로 보장되지 않는다. service 검증과 DB trigger 중 하나가 필요하다.
9. `to_tsvector('simple')`만으로 한국어 검색은 부족하다. `pg_trgm` 인덱스와 지역/카테고리 필터를 함께 사용한다.
10. `extra JSONB` 전체 GIN index는 초기 기본값으로 두지 않는다. 실제 query가 있는 필드에 표현식 index를 둔다.
11. `notice`는 지도 공지다. 관리자 시스템 에러, ETL 실패, Telegram 시스템 알림은 별도 운영 알림 테이블에 둔다.
12. 현재 `trip_plan_items`를 새 `trip_plan` 테이블로 다시 만들 필요는 없다. 기존 `trips`, `trip_days`, `trip_plan_items`를 확장하는 방식이 맞다.

## 구현 상태와 다음 순서

완료:

1. `map_features`, 상세 테이블, `source_records`, link table, media/tag table migration 추가
2. 기존 `places`를 `map_features(feature_type='place')`로 이관하는 migration 추가
3. 공공 장소 ETL 신규 적재 경로를 `map_features + place_details`로 전환
4. 해수욕장 날씨·해수욕장 프로필의 장소 FK를 `map_feature_id`로 전환
5. `trip_plan_items.place_id`를 `map_feature_id`로 대체

남은 작업:

1. 전국문화축제표준데이터를 `map_features(feature_type='event') + event_details` 후보로 승격
2. 지도 viewport API를 `map_features` 기준으로 추가
3. `route`, `area`, `notice`, `content` 실제 ETL/관리 API 추가
4. `feature_mapping_candidates`를 이용한 원천 간 매핑 후보 검토 UI 추가

## 테스트 기준

구현 시 최소 테스트:

- model metadata: geometry SRID, GiST index, FK index, check constraint 확인
- migration contract: 핵심 테이블, 컬럼, 제약, 인덱스 존재 확인
- centroid trigger: point, line, polygon 입력 시 centroid 생성 확인
- feature type detail 정합성: `place`가 아닌 feature에 `place_detail`을 붙이지 못하게 service 또는 trigger 검증
- source record idempotency: 같은 provider row 반복 적재 시 중복 방지
- mapping candidate: `(a,b)`와 `(b,a)` 중복 방지
- public festival backfill: 축제 row가 event 후보로 만들어지는지 확인
- trip item: `map_feature_id`가 null이어도 snapshot 일정이 깨지지 않는지 확인
- 지도 viewport: bbox 조건, feature type 필터, status/is_visible 필터 확인
- 한국어 이름 검색: trigram 검색 smoke

## 확정된 의사결정

1. 실제 테이블명은 기존 코드 convention에 맞춰 복수형 `map_features`, `place_details` 등을 사용한다.
2. PostgreSQL native enum 대신 `varchar + check constraint`를 사용한다.
3. `place_kind`는 우선 `tourist_spot`, `restaurant`, `cafe`, `hotel`, `parking`, `toilet`, `ev_charger`, `viewpoint` 최소값으로 시작한다.
4. 해수욕장처럼 점과 구역 성격이 모두 있는 데이터는 현재 point 원천이면 `place`, polygon 원천이 들어오면 `area`로 승격한다.
5. `notice`는 geometry가 있는 지도 공지만 다룬다. 관리자 시스템 에러와 ETL 실패 알림은 운영 알림 테이블에 둔다.
6. 기존 `places`는 즉시 `map_features`로 대체한다. 신규 코드와 API는 `places.id`가 아니라 `map_features.id` 또는 도메인별 `map_feature_id`를 사용한다.

## 2026-05-16 provider 원천/보정 보강

TripMate는 provider별 adapter/wrapper 계층을 만들지 않고, `python-*-api` 라이브러리 공개 client와 typed model을 직접 사용한다. 중복 수정을 줄여야 하면 앱에 우회 계층을 쌓지 않고 해당 라이브러리의 public interface를 빠르게 안정화한다.

새 provider 보강은 다음 DB 계약을 사용한다.

- `map_feature_source_links.source_role`: `base_address`, `base_coordinate`, `primary`, `enrichment`, `correction`, `duplicate_candidate`, `media`, `weather_context`로 원천 역할을 구분한다.
- `map_feature_overrides`: KRMOIS 등 1차 원천 값을 운영자가 수정/보강한 기록을 provider, dataset, source row, field path 단위로 저장한다.
- 날씨/대기질/해양 값은 `python-krtour-map` weather value 계약과 feature DB에 저장한다.
- `provider_sync_state`: VisitKorea 행사 증분, MCST/Forest/KHOA 주기 수집 cursor와 실패 상태를 저장한다.

주소/좌표 기반은 `python-kraddr-geo`와 `python-vworld-api`가 제공한다. 이 값은 feature 생성의 기반이지만 실질적인 영업/장소 원천은 `python-krmois-api` 인허가 데이터부터 시작한다. KRMOIS에 없거나 보완이 필요한 정보만 다른 provider로 추가한다.

예시:

- VisitKorea 축제는 KRMOIS에 없으므로 `feature_type='event'`와 `event_details(event_kind='festival')` 후보로 저장하고, 증분 cursor는 `provider_sync_state(provider='visitkorea', dataset_key='event')`에 둔다.
- MCST 카페/독립서점은 KRMOIS에 이미 있을 가능성이 높으므로 신규 feature보다 `map_feature_overrides` 보강을 우선한다.
- KHOA 해수욕장은 KRMOIS에 없으면 `place` 또는 `area` 후보로 추가하고, 해양/해수욕장 날씨 값은 `python-krtour-map` weather value 계약에 둔다.
- KRForest 휴양림은 KRMOIS feature가 있으면 보강하고 없으면 `place`/`area` 후보로 추가한다. 트래킹, 둘레길, 국립공원은 `route`와 `area` 비중이 높다.
