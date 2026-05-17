# ADR: python-kma-api 기반 기상청 연동 경계

## 상태

Accepted

## 배경

TripMate의 기상청 단기/중기/특보 수집은 data.go.kr 기반 KMA API와 DFS `nx`, `ny` 격자 변환에 의존한다. 같은 KMA 계약과 좌표 변환 로직이 여러 프로젝트에서 재사용될 수 있으므로, TripMate 내부에 별도 중간 계층과 로컬 격자 구현을 유지하면 공용 라이브러리와 동작이 갈라질 위험이 있다.

## 결정

- KMA DFS 격자 변환은 `kma.wgs84_to_kma_grid()`와 `kma.kma_grid_to_wgs84()`를 직접 사용한다.
- KMA 단기/초단기 예보는 `kma.KmaClient`를 직접 사용한다.
- KMA 중기예보, 특보, 정보, 속보, 관광코스 날씨처럼 data.go.kr의 다른 KMA service/operation 호출은 `kma.DataGoKrClient`를 직접 사용한다.
- TripMate backend에는 KMA 전용 중간 계층을 새로 만들지 않는다. ETL loader가 필요로 하는 TripMate row 형태로 바꾸는 최소 변환만 `apps/api/app/etl/weather/client.py` 경계에 둔다.
- endpoint별 typed model, pagination 편의 API, provenance metadata, credential sanitization 같은 provider 공통 기능이 부족하면 TripMate에 래퍼를 늘리지 않고 `python-kma-api`에 upstream한다.
- `python-kma-api` 기준 버전은 `apps/api/pyproject.toml`의 git commit pin으로 고정한다.

## 결과

- 로컬 `apps/api/app/geospatial/kma_grid.py` 구현은 제거한다.
- weather ETL과 테스트는 `python-kma-api` 공개 API를 직접 import한다.
- KMA provider 변경이나 버그 수정은 공용 라이브러리에서 먼저 해결하고, TripMate는 commit pin 갱신으로 따라간다.

## 검증

- `apps/api/tests/test_kma_grid.py`는 `python-kma-api`의 `GridPoint`, `LatLon`, 격자 변환, credential sanitization/cache key 계약을 검증한다.
- `apps/api/tests/test_weather_loader.py`는 KMA no-data 응답이 빈 row 목록으로 처리되는지 검증한다.
