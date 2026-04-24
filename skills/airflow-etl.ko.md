# Skill: Airflow ETL

주기 수집, 공공 API 수확, 캐시 갱신, freshness 동작이 관련되면 이 skill을 사용한다.

## DAG 설계 규칙
각 DAG는 아래를 정의해야 한다:
- source system
- schedule
- freshness target
- idempotency 전략
- retry 정책
- 목적 테이블
- 관측성 로그/지표

## 필수 패턴
- 가능하면 incremental fetch
- cache-key 기반 skip
- extract / normalize / load 단계 분리
- raw 테이블과 normalized 테이블 분리
- timeout / retry 명시
- 장애 시 로그 또는 알림 확보

## 소스별 지침
### 날씨
- region code와 forecast window 기준 정규화
- fresh 데이터가 있으면 반복 fetch 방지

### 유가
- update timestamp를 명확히 저장
- 상류 갱신 주기가 낮으면 full refresh를 남발하지 않는다.

### 시군구 shp
- 분기 단위 fetch
- source archive metadata 유지
- 재적재와 diff 지원

## 검증
아래를 검사한다:
- 중복 row
- key 필드 누락
- 잘못된 좌표
- freshness 만료
- 상류 스키마 drift

## 문서화
DAG 동작이 바뀌면 schedule, 테이블 lineage, cache 로직을 문서에 반영한다.
