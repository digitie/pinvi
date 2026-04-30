# 한국천문연구원 날짜·천문 정보 설계

이 문서는 한국천문연구원 OpenAPI를 TripMate 여행 날짜/장소 정보에 연결하기 위한 설계 기준이다. 구현은 후속 작업으로 진행한다.

## 사용 API

| 데이터셋 | data.go.kr | 서비스 | 용도 | 갱신/한도 |
| --- | --- | --- | --- | --- |
| `kasi_special_day` | https://www.data.go.kr/data/15012690/openapi.do | 특일 정보 | 여행 날짜가 공휴일, 국경일, 24절기인지 표시 | 실시간, 개발계정 10,000건 |
| `kasi_lunisolar_day` | https://www.data.go.kr/data/15012679/openapi.do | 음양력 정보 | 음력 날짜, 간지, 윤달 여부, 율리우스 적일 표시 | 실시간, 개발계정 10,000건 |
| `kasi_rise_set` | https://www.data.go.kr/data/15012688/openapi.do | 출몰시각 정보 | 저장 장소의 일출/일몰/월출/월몰 표시 | 실시간, 개발계정 10,000건 |

모든 요청/응답 시각 해석은 KST(`Asia/Seoul`) 기준으로 한다.

## 수집 트리거

`kasi_special_day`:

- 사용자가 여행 날짜를 생성하거나 업데이트할 때 해당 날짜의 특일 정보를 조회한다.
- 별도 사용자 action이 없어도 월 1회 다음 12개월 범위를 ETL로 갱신한다.
- 같은 날짜에 대한 fresh cache가 있으면 API를 다시 호출하지 않는다.

`kasi_lunisolar_day`:

- 사용자가 여행 날짜를 생성하거나 업데이트할 때 해당 날짜의 음양력 정보를 조회한다.
- 월 1회 특일 정보와 같은 범위를 ETL로 갱신한다.

`kasi_rise_set`:

- 여행 세부 계획에서 저장 장소 또는 방문 장소의 날짜/좌표가 생성·변경될 때 조회한다.
- 날짜 + 좌표 격자 또는 날짜 + 장소 id 기준 cache를 둔다.
- 좌표가 없으면 조회하지 않고 UI에는 “좌표 없음” 상태를 남긴다.

## DB 설계안

`calendar_special_day`:

| 컬럼 | 설명 |
| --- | --- |
| `solar_date` | KST 기준 양력 날짜, PK 일부 |
| `special_day_kind` | `holiday`, `national_day`, `solar_term`, `anniversary`, `etc` |
| `name` | 특일명 |
| `is_holiday` | 공휴일 여부 |
| `sequence` | 같은 날짜 다건 정렬 |
| `raw_payload` | provider 응답 원문 |
| `collected_at` | KST 수집시각 |

`calendar_lunisolar_day`:

| 컬럼 | 설명 |
| --- | --- |
| `solar_date` | 양력 날짜 PK |
| `lunar_year`, `lunar_month`, `lunar_day` | 음력 날짜 |
| `is_leap_month` | 윤달 여부 |
| `ganji_year`, `ganji_month`, `ganji_day` | provider가 주는 간지 정보 |
| `julian_day` | 율리우스 적일 |
| `raw_payload` | provider 응답 원문 |
| `collected_at` | KST 수집시각 |

`place_rise_set_time`:

| 컬럼 | 설명 |
| --- | --- |
| `id` | PK |
| `trip_place_id` 또는 `place_id` | 구현 시 여행 장소 모델 기준으로 선택 |
| `target_date` | 여행 날짜 |
| `longitude`, `latitude` | EPSG:4326 좌표 snapshot |
| `sunrise_at`, `sunset_at` | KST 일출/일몰 |
| `moonrise_at`, `moonset_at` | KST 월출/월몰 |
| `civil_twilight_morning`, `civil_twilight_evening` | 시민박명 |
| `nautical_twilight_morning`, `nautical_twilight_evening` | 항해박명 |
| `astronomical_twilight_morning`, `astronomical_twilight_evening` | 천문박명 |
| `raw_payload` | provider 응답 원문 |
| `collected_at` | KST 수집시각 |

## UI 노출

- 여행 날짜 chip/tooltip: 공휴일, 국경일, 24절기, 음력 날짜를 간단히 표시한다.
- 여행 날짜 상세: 음력 상세, 간지, provider 원문 기준 날짜를 표시한다.
- 여행 장소 상세: 해당 날짜의 일출/일몰/월출/월몰을 보여준다.

## 보완 결정

- `place_rise_set_time`을 사용자 여행 장소(`trip_place`)에 붙일지, 내부 표준 장소(`places`)에 붙일지 구현 시 여행 계획 스키마 확정 후 결정한다.
- 특일 정보의 provider endpoint별 상세 kind mapping은 실제 응답 샘플 기반으로 확정한다.
