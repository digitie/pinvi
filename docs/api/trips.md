# 여행 계획 API

이 문서는 구현된 여행 계획 endpoint의 현재 계약을 기록한다. 여행 CRUD, 참여자, 날짜별 참여 여부는 아직 전체 구현 전이며, 현재는 지도/상세 화면에서 장소나 축제 같은 리소스를 여행 날짜에 추가하는 최소 기반을 먼저 둔다.

## 인증

여행 계획 API는 일반 사용자 httpOnly cookie 세션을 요구한다. `POST /auth/login`으로 받은 `tripmate_session` cookie가 필요하다.

현재 인가 기준:

- 여행 작성자(`trips.user_id`) 본인은 자신의 여행 날짜에 일정 항목을 추가할 수 있다.
- 관리자는 운영 확인 목적상 추가할 수 있다.
- 여행 참여자/편집자 권한 테이블은 아직 구현 전이므로, owner/editor/member 세부 인가는 후속 구현에서 `trip_members` 기준으로 확장한다.

## `POST /trips/{trip_id}/days/{trip_day_id}/items`

여행 날짜에 일정 항목을 추가한다. 이 endpoint는 지도 객체, 축제, 향후 둘레길/드라이브 코스 같은 리소스를 같은 일정 타임라인에 올릴 수 있도록 `resource_type`을 둔다.

요청 예시: 지도 객체 추가

```json
{
  "resource_type": "place",
  "map_feature_id": "00000000-0000-4000-8000-000000000011",
  "note": "점심 후보"
}
```

요청 예시: 축제 추가

```json
{
  "resource_type": "festival",
  "festival_id": "00000000-0000-4000-8000-000000000010",
  "note": "저녁 공연 보기"
}
```

요청 예시: 미래 경로형 리소스 임시 추가

```json
{
  "resource_type": "trail",
  "resource_key": "trail-provider:sample-course-1",
  "title_snapshot": "숲길 산책 코스",
  "address_snapshot": "강원특별자치도 평창군 일대"
}
```

요청 필드:

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `resource_type` | Y | `place`, `event`, `route`, `area`, `notice`, `festival`, `trail`, `scenic_road`, `custom` |
| `sort_order` | N | 날짜 안 표시 순서. 생략하면 마지막 다음 순서로 자동 부여 |
| `map_feature_id` | 조건부 | `resource_type`이 `place`, `event`, `route`, `area`, `notice`일 때 내부 `map_features.id` |
| `festival_id` | 조건부 | `resource_type=festival`일 때 `tour_serving_public_cultural_festival.id` |
| `resource_key` | 조건부 | 아직 전용 테이블이 없는 `trail`, `scenic_road`, `route` 같은 미래 리소스의 임시 key |
| `title_snapshot` | 조건부 | 미래 리소스 또는 직접 입력 항목에는 필수. 장소/축제는 원천 이름을 기본값으로 사용 |
| `address_snapshot` | N | 저장 당시 주소 문자열. 원천 주소가 있으면 기본값으로 채움 |
| `starts_at`, `ends_at` | N | 항목의 시작/종료 시각. timezone-aware KST 사용 |
| `operating_hours_snapshot` | N | 저장 당시 운영시간 문자열 |
| `longitude`, `latitude` | N | 원천 좌표가 있으면 기본값으로 채움. EPSG:4326, 경도/위도 순서 |
| `note` | N | 사용자 메모 |
| `resource_metadata` | N | 작은 보조 metadata. provider 원문 전체 저장 용도로 쓰지 않음 |

응답:

```json
{
  "id": "00000000-0000-4000-8000-000000000020",
  "trip_day_id": "00000000-0000-4000-8000-000000000003",
  "resource_type": "festival",
  "sort_order": 1,
  "map_feature_id": null,
  "festival_id": "00000000-0000-4000-8000-000000000010",
  "resource_key": null,
  "title_snapshot": "서울 봄 축제",
  "address_snapshot": "서울특별시 종로구 세종대로 1",
  "starts_at": null,
  "ends_at": null,
  "operating_hours_snapshot": null,
  "longitude": "126.97800000",
  "latitude": "37.56650000",
  "note": "저녁 공연 보기",
  "resource_metadata": {}
}
```

오류:

- `401 Unauthorized`: 일반 사용자 로그인이 필요함
- `403 Forbidden`: 해당 여행을 수정할 권한이 없음
- `404 Not Found`: 여행, 여행 날짜, 장소, 축제 row를 찾을 수 없음
- `422 Unprocessable Entity`: `resource_type`과 식별자 조합이 맞지 않음

## DB 연결 기준

현재 테이블은 `trip_plan_items`다.

- `trip_plan_items.trip_day_id -> trip_days.id`
- `trip_plan_items.map_feature_id -> map_features.id`
- `trip_plan_items.festival_id -> tour_serving_public_cultural_festival.id`

지도 객체와 축제 FK는 서로 동시에 채우지 않는다. 나중에 축제 외에도 둘레길, 드라이브 코스, 경로형 데이터가 추가될 수 있으므로, 일정 타임라인은 `trip_place`처럼 장소 전용 이름이 아니라 `trip_plan_items`로 둔다.

장소/축제 원천 row가 바뀌어도 사용자가 저장한 일정 항목의 표시가 바로 깨지지 않도록 `title_snapshot`, `address_snapshot`, 좌표, 운영시간 snapshot을 함께 보존한다.
