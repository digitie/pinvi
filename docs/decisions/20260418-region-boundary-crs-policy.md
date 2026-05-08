# ADR: 행정구역 경계 원천 데이터와 좌표계 보존 정책

## 상태

Accepted

## 배경

TripMate는 대한민국 국내 여행 앱이며, 장소 좌표를 행정구역과 매칭하고 날씨/유가 리포트를 지역 기준으로 제공해야 한다. 행정구역 경계 데이터는 원본 좌표계를 보존해야 SHP 갱신, 원본 비교, 재처리 검증이 가능하다.

## 결정

- 행정구역 원천 데이터는 V-WORLD `법정구역정보` SHP를 사용한다.
- raw 레이어는 원본 SHP의 EPSG:5179 geometry를 그대로 적재한다.
- serving 레이어는 웹 지도와 API 조회를 위해 EPSG:4326 변환본을 생성한다.
- 행정구역 point-in-polygon 판정은 PostGIS에서 수행한다.
- 웹 지도 출력과 API 응답은 EPSG:4326을 사용한다.
- 원본 비교, SHP 갱신 검증, 재처리는 EPSG:5179 raw 레이어를 기준으로 수행한다.

## 대안

- EPSG:4326 변환본만 저장: 앱 조회는 단순해지지만 원본 비교와 갱신 검증이 어려워진다.
- 모든 조회를 EPSG:5179로 처리: 원본 보존에는 좋지만 웹 지도/API 응답과의 변환 경계가 흐려진다.

## 결과/영향

- DB schema는 raw boundary와 serving boundary를 분리해야 한다.
- ETL은 SHP 적재와 4326 변환 단계를 모두 가져야 한다.
- 공간 테스트는 raw 좌표계 보존, serving 변환, point-in-polygon 결과를 분리해서 검증해야 한다.
- UI와 API 문서는 “반경 nkm” 리포트가 행정구역 기반 근사임을 계속 표시해야 한다.

## 후속 작업

- Alembic migration에서 raw/serving geometry SRID를 명시한다.
- 행정구역 Dagster ETL job에 원본 적재, 변환, 품질 검증 단계를 둔다.
- 좌표 fixture 기반 PostGIS 테스트를 추가한다.
