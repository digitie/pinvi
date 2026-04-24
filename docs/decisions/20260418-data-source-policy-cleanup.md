# ADR: 데이터 소스 기준 문서 정리와 보수적 저장 정책

## 상태

Accepted

## 배경

`docs/data-sources.md`가 휴게소, V-WORLD, 기상/유가, 장소 provider 정책을 함께 다루면서 일부 표현이 충돌했다. 특히 V-WORLD Geocoder 결과를 table에 저장하려는 문구와 “Geocoder 결과 저장 금지” 정책이 동시에 존재했다.

## 결정

- `docs/data-sources.md`를 외부 데이터 소스와 저장 정책의 단일 기준 문서로 유지한다.
- V-WORLD `법정구역정보` SHP는 행정구역 경계 원천 데이터로 사용한다.
- 행정구역 raw 레이어는 EPSG:5186 원본을 보존하고, serving 레이어는 EPSG:4326 변환본을 둔다.
- V-WORLD Geocoder API 2.0 응답 주소/결과 원문은 기본적으로 DB에 저장하지 않는다.
- 행정구역 매핑은 Geocoder 저장 대신 PostGIS point-in-polygon을 우선 사용한다.
- 한국도로공사 OpenAPI 응답은 raw snapshot으로 보관할 수 있으나, 앱/API 조회는 serving 테이블만 사용한다.
- `weather_rest_area`는 휴게소 master와 매칭하지 않는 독립 날씨 데이터로 둔다.
- 휴게소 oil/svcs 데이터의 FK 불일치는 raw 적재를 보존하고 serving 단계에서 skip한다.
- FK 불일치로 skip된 row는 Airflow task log와 별도 JSON Lines 로그파일에 기록한다.

## 대안

- Geocoder 결과를 주소 보강 데이터로 저장: 구현은 편하지만 V-WORLD 저장 정책과 충돌할 수 있다.
- 휴게소 OpenAPI 결과를 도메인 테이블에 그대로 저장: 빠르지만 raw/serving 경계가 흐려지고 재처리/품질 검사가 어렵다.
- oil/svcs FK 불일치 시 DAG 즉시 실패: 데이터 정합성은 강하지만 상류 데이터 일시 오류에 취약하다.
- oil/svcs FK 불일치를 quarantine 테이블에 저장: DB에서 추적하기는 쉽지만 현재 요구 범위보다 무겁고 serving schema가 불필요하게 늘어난다.

## 결과/영향

- `weather_rest_area`는 V-WORLD Geocoder로 주소를 저장하지 않는다.
- `weather_rest_area`는 휴게소 master와 join하지 않는다.
- `weather_rest_area`는 좌표/명칭 기반 후보 매칭, fuzzy/nearest matching, match confidence를 저장하지 않는다.
- 데이터 구현 전에 `docs/data-sources.md`의 DS-* 보완 항목을 먼저 해소해야 한다.

## 후속 작업

- 한국석유공사 API endpoint, region code, 유종 enum을 확정한다.
- 기상청 격자/중기예보 권역 mapping table을 설계한다.
- oil/svcs FK 불일치 로그파일의 보존 기간과 운영 알림 임계치를 정한다.
