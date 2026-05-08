# Skill: Dagster ETL

주기 수집, 공공 API 수확, cache 갱신, freshness 동작, Dagster job/schedule 변경이 관련되면 이 skill을 사용한다.

## Job 설계 규칙

각 Dagster job은 아래를 정의해야 한다:

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
- raw 테이블과 normalized/serving 테이블 분리
- timeout / retry 명시
- 장애 시 `etl_run_logs`, 관리자 알림, Telegram outbox 기록 확보
- Dagster job import 시점에는 DB와 외부 네트워크에 접근하지 않기

## Dagster 기준

- job/schedule 정의는 `apps/api/app/dagster_etl/`에 둔다.
- schedule timezone은 KST(`Asia/Seoul`)로 고정한다.
- Dagster UI와 daemon은 Docker Compose의 `dagster` service에서 함께 실행한다.
- 실패 알림은 Dagster retry가 소진된 마지막 시도에서만 생성한다.
- 수동 backfill config는 op config로 받되, 검증 가능한 parser를 먼저 둔다.
- 인증키가 필요한 저쿼터 데이터셋은 키가 없을 때 schedule을 만들지 않고, 수동 실행은 skipped ETL log로 남긴다.

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
- Dagster job/schedule import
- retry 소진 전후 알림 차이
- skip 처리와 수동 config validation
- 실제 provider live smoke는 명시 opt-in으로 실행

## 문서화

Dagster job 동작이 바뀌면 schedule, 테이블 lineage, cache 로직, 운영 명령을 문서에 반영한다.
