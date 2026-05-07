# 공개 API

공개 API는 로그인 전 화면과 일반 사용자 화면에서 인증 없이 조회해도 되는 데이터만 제공한다. 외부 provider를 직접 호출하지 않고 TripMate serving 테이블을 조회한다.

## `GET /public/beaches`

해수욕장 통합 목록을 조회한다. KHOA 관측/해수욕지수, 해양수산부 해수욕장정보/수질, KMA 해수욕장 날씨를 `beach_profiles` 기준으로 묶어 반환한다.

Query parameter:

- `sido_code`: 선택. 시도 코드.
- `sigungu_code`: 선택. 시군구 코드.
- `query`: 선택. 해수욕장명 부분 검색.
- `limit`: 1~300, 기본값 100.
- `offset`: 기본값 0.

응답:

```json
{
  "count": 1,
  "beaches": [
    {
      "id": "00000000-0000-4000-8000-000000000020",
      "display_name": "해운대해수욕장",
      "longitude": "129.16038400",
      "latitude": "35.15869700",
      "legal_dong_code": "2635010500",
      "sigungu_code": "2635000000",
      "sido_code": "2600000000",
      "road_name_code": null,
      "road_address_management_no": null,
      "road_address": null,
      "address_snapshot": "부산광역시 해운대구 우동",
      "address_mapping_method": "postgis_point_in_polygon",
      "beach_width_m": "50.00",
      "beach_length_m": "1500.00",
      "beach_material": "백사장",
      "homepage_url": "https://example.kr",
      "homepage_name": "해운대해수욕장",
      "image_url": "https://example.kr/beach.jpg",
      "emergency_contact": "051-000-0000",
      "source_providers": ["data_go_kr", "khoa", "kma"],
      "latest_observation": {
        "observed_at": "2026-05-01T09:00:00+09:00",
        "water_temperature_c": "21.500",
        "wave_height_m": "0.300"
      },
      "latest_water_quality": {
        "survey_year": 2026,
        "survey_date": "2026-05-01",
        "suitability": "적합"
      },
      "upcoming_index_forecasts": [
        {
          "forecast_date": "2026-05-01",
          "forecast_slot": "AM",
          "index_score": "82.000",
          "total_index": "좋음"
        }
      ],
      "latest_weather": []
    }
  ]
}
```

동작 기준:

- 외부 API를 호출하지 않고 `beach_*`와 `weather_serving_beach` serving 데이터를 조회한다.
- 일반 장소와 다른 데이터 타입이므로 축제처럼 별도 리소스로 취급한다.
- `map_feature_id`가 연결된 해수욕장만 KMA 해수욕장 날씨 요약을 함께 반환한다.
- 도로명주소코드가 없으면 null로 반환한다. 좌표 기반 추정값을 만들지 않는다.

## `GET /public/beaches/map-markers`

지도 해수욕장 레이어에 표시할 마커 목록을 조회한다.

Query parameter:

- `limit`: 반환할 마커 수. 1~1000, 기본값 500.

응답:

```json
{
  "layer_key": "beach",
  "display_name": "해수욕장",
  "markers": [
    {
      "id": "00000000-0000-4000-8000-000000000020",
      "title": "해운대해수욕장",
      "longitude": "129.16038400",
      "latitude": "35.15869700",
      "marker_color": "#0ea5e9",
      "marker_icon": "waves",
      "layer_key": "beach"
    }
  ]
}
```

## `GET /public/beaches/{beach_id}`

단일 해수욕장 통합 상세를 조회한다. 응답 구조는 `GET /public/beaches`의 개별 `beaches[]` 항목과 같다.

## `GET /public/festivals/monthly`

로그인 화면의 월별 축제 목록을 조회한다.

Query parameter:

- `year`: 조회 연도. 생략하면 KST 기준 현재 연도.
- `month`: 조회 월. 생략하면 KST 기준 현재 월.
- `limit`: 반환할 축제 수. 1~50, 기본값 12.

응답:

```json
{
  "year": 2026,
  "month": 5,
  "months": [
    {"month": 1, "count": 0},
    {"month": 2, "count": 0},
    {"month": 3, "count": 1},
    {"month": 4, "count": 2},
    {"month": 5, "count": 1}
  ],
  "festivals": [
    {
      "id": "00000000-0000-4000-8000-000000000010",
      "source_record_id": "b6f2...",
      "festival_name": "서울 봄 축제",
      "venue_name": "광장 일대",
      "event_start_date": "2026-04-24",
      "event_end_date": "2026-05-05",
      "event_status": "ongoing",
      "road_address": "서울특별시 종로구 세종대로 1",
      "jibun_address": "서울특별시 종로구 청운동 1",
      "sigungu_code": "1111000000",
      "sido_code": "1100000000",
      "longitude": "127.000000",
      "latitude": "37.500000",
      "homepage_url": "https://example.kr"
    }
  ]
}
```

동작 기준:

- `tour_serving_public_cultural_festival.is_active = true`인 row만 반환한다.
- 축제 기간이 선택 월과 겹치면 해당 월의 축제로 계산한다.
- 날짜가 없는 축제 row는 monthly 목록에서 제외한다.
- 월별 count도 같은 기간 겹침 기준을 사용한다.
- 좌표와 주소는 provider 값과 TripMate 매핑 결과를 그대로 보여준다. fuzzy 주소 보정은 하지 않는다.
- `id`는 TripMate DB row UUID이며, 축제 상세 조회와 여행 일정 항목 추가에 사용한다.

## `GET /public/festivals/map-markers`

지도 축제 레이어에 표시할 마커 목록을 조회한다. 로그인 여부와 무관하게 공개 축제 데이터 중 좌표가 있는 row만 반환한다.

Query parameter:

- `limit`: 반환할 마커 수. 1~1000, 기본값 500.

응답:

```json
{
  "layer_key": "festival",
  "display_name": "축제",
  "markers": [
    {
      "id": "00000000-0000-4000-8000-000000000010",
      "source_record_id": "b6f2...",
      "title": "서울 봄 축제",
      "event_start_date": "2026-04-24",
      "event_end_date": "2026-05-05",
      "event_status": "ongoing",
      "longitude": "127.00000000",
      "latitude": "37.50000000",
      "marker_color": "#ff5a5f",
      "marker_icon": "music",
      "layer_key": "festival"
    }
  ]
}
```

지도 UI 기준:

- 기본 상태에서는 축제 마커를 자동으로 켜지 않는다.
- 지도 위 상세보기/레이어 버튼에서 `축제`를 체크하면 이 API 결과를 표시한다.
- 마커 색상은 축제 전용 coral/red 계열이며, icon은 Maki `music`을 기본값으로 사용한다.

## `GET /public/festivals/{festival_id}`

축제 마커 클릭 또는 축제 목록 상세에서 사용할 상세 정보를 조회한다.

응답에는 `GET /public/festivals/monthly`의 축제 요약 필드에 더해 아래 정보를 포함한다.

- `festival_content`
- `mnnst_name`, `auspc_instt_name`, `suprt_instt_name`
- `phone_number`
- `related_info`
- `address_snapshot`
- `road_name_code`
- `road_address_management_no`
- `provider_institution_name`
- `reference_date`
- `marker_color`, `marker_icon`

이 상세 화면의 “추가” 버튼은 로그인 사용자가 선택한 여행 날짜에 `POST /trips/{trip_id}/days/{trip_day_id}/items`를 호출해 `resource_type = festival` 일정 항목을 만든다.

프론트엔드:

- `/login` 화면은 `GET /public/festivals/monthly`를 사용한다.
- API 오류가 나면 개발/초기 검증용 fallback 축제 샘플을 표시하고 오류 메시지를 함께 노출한다.
