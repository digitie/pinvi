# 데이터 소스 기준

이 문서는 TripMate 외부 데이터 소스의 색인이다. 상세 API 계약은 `docs/data-sources/` 하위의 소스별 문서를 필요할 때만 읽는다.

## 공통 원칙

- 지리 범위는 대한민국으로 한정한다.
- 사용자 화면 요청마다 외부 API를 직접 호출하지 않고, 가능한 한 Dagster ETL 또는 명시적 cache miss 흐름으로 수집한다.
- 공공데이터 raw payload는 재처리, diff, schema drift 감지를 위해 저장할 수 있다.
- Kakao/Naver/Google 같은 일반 장소 provider 원문 전체는 장기 저장하지 않는다.
- 앱/API/UI는 raw가 아니라 serving table 또는 내부 표준 지도 객체(`map_features`)를 우선 사용한다.
- provider 응답을 공통 지도 feature, source trace, weather/price value로 바꾸는 계약은 `python-krtour-map`을 기준으로 한다.
- 축제처럼 기간성이 강한 이벤트 데이터는 일반 장소와 자동 병합하지 않고 별도 serving table을 유지한다. 여행계획에서는 `trip_plan_items`가 장소, 축제, 향후 경로형 리소스를 연결한다.
- API key, bot token, 개인 API key는 DB/로그/문서 예시에 원문을 남기지 않는다.
- 모든 수집 시각은 KST(`Asia/Seoul`) 기준 timezone-aware `collected_at`으로 저장한다.
- 좌표는 웹/API serving 기준 EPSG:4326, 순서 `longitude`, `latitude`를 사용한다.
- V-WORLD SHP 원천 geometry는 EPSG:5179 raw로 보존하고, serving layer는 EPSG:4326으로 변환한다.
- 행정구역 기반 “반경 nkm” 리포트는 정확한 원형 거리 검색이 아니라 행정구역 근사일 수 있으며 UI/문서에서 근사라고 밝힌다.

## 소스별 상세 문서

| 영역 | 문서 | 현재 구현 상태 |
| --- | --- | --- |
| 주소/행정구역 | `docs/data-sources/address-region.md` | Juso 월간 도로명주소, data.go.kr 법정동코드, V-WORLD SHP 적재 구현 |
| 날씨/대기질 | `docs/data-sources/weather-air-quality.md` | 기상청 단기/중기/특보/해수욕장 날씨, AirKorea 측정소/예보/시도 측정 구현 |
| feature 날씨 정규화 | `docs/architecture/weather-air-quality-schema.md` | KMA식 `timeline_bucket`과 provider 원천 `forecast_style` 분리 기준 정리 |
| 해수욕장 통합 | `docs/data-sources/beach-sources.md` | KHOA 해수욕장 관측/해수욕지수, 해양수산부 해수욕장정보/수질적합, KMA 해수욕장 날씨 통합 조회 구현 |
| 해양 체험지수 | `docs/architecture/khoa-ocean-index-schema.md` | KHOA 갯벌체험지수/바다갈라짐 체험지수 구현 |
| 유가 | `docs/data-sources/fuel-opinet.md` | OpiNet 지역코드, 전국 평균가, 시군구 최저가 구현 |
| 휴게소 | `docs/data-sources/rest-area-expressway.md` | 한국도로공사 휴게소 기본정보, 유가, 편의시설 구현 |
| 관광/축제 | `docs/data-sources/tour-festival.md` | KMA 관광코스 CSV/상세날씨, 전국문화축제 구현 |
| KTO TourAPI | `docs/api/kto-tourapi.md` | visitkorea client 설정 경계와 직접 사용 계약 구현 |
| 공공 장소 | `docs/data-sources/public-places.md` | 수목원/휴양림/박물관미술관/캠핑장 표준 장소 적재 구현 |
| Provider 정책/TODO | `docs/data-sources/provider-policy-and-todo.md` | Kakao/Naver/Google 저장 정책, KASI/MCP/후속 API TODO |
| YouTube 여행 정보 | `docs/architecture/youtube-travel-intelligence.md` | 구현 전 설계/TODO. Gemini YouTube URL 분석과 MCP 분리 구조 |

## 구현된 수집 스케줄 요약

모든 cron은 KST 기준이며 값은 `config/etl-datasets.json`과 Dagster job/schedule이 단일 구현 기준이다.

| dataset key | Dagster job | 주기/시각 |
| --- | --- | --- |
| `legal_dong_code_standard` | `legal_dong_code_standard_quarterly` | 2/5/8/11월 15일 04:30 |
| `juso_road_address_korean` | `juso_monthly_address_dataset` | 매월 10-31일 04:00, 해당 월 성공분 있으면 skip |
| `vworld_boundary_upload` | CLI/manual | 자동 다운로드 없음 |
| `fuel_region_code` | `opinet_region_code_quarterly` | 1/4/7/10월 1일 04:00 |
| `fuel_avg_price` | `opinet_avg_price_daily` | 매일 05:20, 13:20, 21:20 |
| `fuel_lowest_station` | `opinet_lowest_station_daily` | 매일 05:40, 13:40, 21:40 |
| `rest_area_master` | `rest_area_master_monthly` | 매월 1일 04:10 |
| `rest_area_oil_price` | `rest_area_oil_price_daily` | 매일 06:10, 18:10 |
| `rest_area_svcs` | `rest_area_service_monthly` | 매월 1일 04:30 |
| `weather_short_term` | `weather_short_term_sigungu_grid` | 30분마다 |
| `weather_kma_alert` | `weather_kma_alert` | 30분마다 |
| `weather_mid_term` | `weather_mid_term_nationwide` | 매일 06:20, 18:20 |
| `air_quality_station` | `air_quality_station_daily` | 매일 04:20 |
| `air_quality_forecast` | `air_quality_forecast_daily` | 매일 05:15, 11:15, 17:15, 23:15 |
| `air_quality_sido_measurement` | `air_quality_sido_measurement_hourly` | 매시 25분 |
| `kma_recommended_tour_course` | `kma_recommended_tour_course_annual` | 매년 3월 1일 05:00 |
| `kma_beach_catalog` | `kma_beach_catalog_annual` | 매년 5월 15일 04:00 |
| `kma_beach_ultra_short_forecast` | `kma_beach_ultra_short_forecast_hourly` | 6/7/8월 매시 45분 |
| `kma_beach_village_forecast` | `kma_beach_village_forecast_3hourly` | 6/7/8월 02/05/08/11/14/17/20/23시 20분 |
| `kma_beach_wave_height` | `kma_beach_wave_height_hourly` | 6/7/8월 매시 35분 |
| `kma_beach_water_temperature` | `kma_beach_water_temperature_hourly` | 6/7/8월 매시 40분 |
| `kma_beach_tide_sun` | `kma_beach_tide_sun_daily` | 6/7/8월 매일 05:10 |
| `khoa_beach_observation` | `khoa_beach_observation_twice_daily` | 매일 06:20, 18:20 |
| `khoa_beach_index_forecast` | `khoa_beach_index_forecast_twice_daily` | 매일 06:30, 18:30 |
| `khoa_mudflat_index_forecast` | `khoa_mudflat_index_forecast_twice_daily` | 매일 06:40, 18:40 |
| `khoa_sea_split_index_forecast` | `khoa_sea_split_index_forecast_twice_daily` | 매일 06:50, 18:50 |
| `mof_beach_info` | `mof_beach_info_annual` | 매년 5월 15일 04:00 |
| `mof_beach_water_quality` | `mof_beach_water_quality_annual` | 매년 5월 15일 04:20 |
| `public_cultural_festival` | `public_cultural_festival_quarterly` | 2/5/8/11월 12일 04:35 |
| `public_arboretum_basic` | `public_arboretum_basic_annual` | 매년 7월 5일 04:05 |
| `public_tourist_information_center` | `public_tourist_information_center_annual` | 매년 7월 5일 04:10 |
| `public_recreation_forest` | `public_recreation_forest_semiannual` | 1/7월 15일 04:15 |
| `public_museum_art_gallery` | `public_museum_art_gallery_annual` | 매년 7월 15일 04:25 |
| `public_campground` | `public_campground_daily` | 매일 04:45 |

## 공통 요청/응답 처리

- data.go.kr 계열은 대부분 `serviceKey`, `pageNo`, `numOfRows`, JSON 응답 타입 파라미터를 사용한다.
- data.go.kr 표준 OpenAPI 응답은 `response.header.resultCode/resultMsg`, `response.body.items.item`, `totalCount` 구조를 우선 해석한다.
- OpiNet은 `certkey`, 한국도로공사는 `key`, 기상청은 `ServiceKey`, AirKorea와 일부 data.go.kr 표준 API는 `serviceKey`를 사용한다.
- pagination guard는 구현에서 1,000 page로 둔다.
- raw table은 endpoint, request params/window, response hash, raw payload, collected_at을 남긴다.
- serving table은 UI/API에 필요한 정규화 필드, provider 기준시각, 주소/좌표 매핑 결과를 남긴다.

## 관련 설계 문서

- 주소/경계 스키마: `docs/architecture/address-schema.md`
- 장소 정규화: `docs/architecture/place-schema.md`
- 휴게소 스키마: `docs/architecture/rest-area-schema.md`
- 날씨/대기질 스키마: `docs/architecture/weather-air-quality-schema.md`
- 해수욕장 통합 스키마: `docs/architecture/beach-schema.md`
- KHOA 해양 체험지수 스키마: `docs/architecture/khoa-ocean-index-schema.md`
- 기상청 관광코스 스키마: `docs/architecture/kma-tour-course-schema.md`
- 공공 장소 ETL 스키마: `docs/architecture/public-place-etl-schema.md`
- Provider library 직접 사용 기준: `docs/architecture/provider-library-direct-use.md`
- python-krtour-map 통합 기준: `docs/architecture/krtour-map-library.md`

## MCP 상태

- `youtube_place_mcp`, `address_code_lookup_mcp`는 TODO 후보로만 유지한다.
- 별도 사용자 지시가 있기 전까지 MCP 설계, 구현, 스캐폴딩, 의존성 추가, 테스트 추가를 하지 않는다.
- YouTube 여행 정보 수집은 `docs/architecture/youtube-travel-intelligence.md`에 설계만 남겨둔다. 실제 MCP 서버와 DB migration은 후속 구현 지시 전까지 만들지 않는다.
