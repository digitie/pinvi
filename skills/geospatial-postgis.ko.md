# Skill: Geospatial 및 PostGIS

지도, 좌표, SRID, 거리 계산, 행정구역, shp 파일, 공간 질의가 관련되면 이 skill을 사용한다.

## 고정 규칙
- SRID를 항상 명시한다.
- 좌표 순서를 항상 확인한다. 기본은 longitude, latitude다.
- 권위 있는 공간 연산은 PostGIS를 우선 사용한다.
- Shapely는 전처리, 검증, fixture, 오프라인 변환에 활용한다.
- 행정구역 근사 로직을 “정확한 반경 검색”이라고 쓰지 않는다.

## 모델링 지침
- raw geometry와 정규화된 region identifier를 함께 저장한다.
- geometry 출처와 import 시각을 남긴다.
- shp 원본 적재 테이블과 서비스용 테이블을 분리한다.
- geometry 컬럼에 적절한 인덱스를 둔다.

## 질의 지침
각 기능이 아래 중 무엇인지 먼저 밝힌다:
- point-in-polygon
- 거리 기반 nearby search
- 행정구역 교차 조회
- bounding-box prefilter + 정밀 spatial filter

## 테스트 지침
항상 아래 fixture를 준비한다:
- 경계점
- 근처지만 다른 구역인 점
- 잘못된 geometry
- 인접 시군구

## 데이터 반입 지침
shp 업데이트 시:
- source snapshot date 기록
- encoding과 CRS 검증
- region key 정규화
- import 멱등성 보장
- row count와 변경된 지역 로그 기록
