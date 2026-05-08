# ADR: 기상청 DFS 격자 변환 유틸

## 상태

Superseded by `docs/decisions/20260507-pykma-weather-client-boundary.md`

## 배경

기상청 단기/초단기 예보 API는 WGS84 위경도 대신 DFS `nx`, `ny` 격자를 사용한다.
TripMate는 여행 장소 좌표와 행정구역 중심 좌표를 날씨 수집 key로 변환해야 하므로,
백엔드와 ETL이 공유할 수 있는 순수 Python 변환 유틸이 필요하다.

## 결정

- 백엔드에 `apps/api/app/geospatial/kma_grid.py`를 추가한다.
- 2026-05-07부터 로컬 `apps/api/app/geospatial/kma_grid.py` 구현은 제거하고, 공용 라이브러리 `pykma`의 `wgs84_to_kma_grid()`와 `kma_grid_to_wgs84()` 공개 API로 대체한다.
- 변환 함수는 `wgs84_to_kma_grid(latitude, longitude)`와 `kma_grid_to_wgs84(nx, ny)`로 둔다.
- 좌표 순서는 WGS84 입력/출력에서 `latitude`, `longitude`로 명시한다.
- 반환값은 `KmaGridPoint(nx, ny)`와 `Wgs84Point(latitude, longitude)` dataclass를 사용한다.
- 구현은 KMA DFS Lambert Conformal Conic 상수를 사용하고, fronteer-kr gist의 검증값을 테스트 fixture로 참고한다.
- 이 유틸은 단기/초단기 예보용 격자 변환만 해결한다. 중기예보 권역 `reg_id` mapping은 별도 테이블로 설계한다.

## 결과/영향

- 날씨 adapter와 Dagster job은 외부 geocoder 저장 없이 장소 좌표를 기상청 격자로 변환할 수 있다.
- 행정구역 중심좌표 → 격자 mapping table은 이 유틸을 사용해 생성할 수 있다.
- 중기예보 권역 mapping은 아직 DS-004의 남은 보완 항목이다.

## 검증

- 서울, 부산, 제주 샘플 좌표의 WGS84 → DFS 격자 변환 테스트를 둔다.
- 동일 샘플의 DFS 격자 → WGS84 역변환 테스트를 둔다.
- 잘못된 위도와 잘못된 grid 값은 `ValueError`로 방어한다.

