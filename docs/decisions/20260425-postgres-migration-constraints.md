# ADR: PostgreSQL 마이그레이션 식별자 길이와 Juso 적재 제약

## 상태

Accepted

## 배경

Juso 주소 적재 스키마를 추가하면서 실제 WSL2 Docker PostgreSQL/PostGIS에 `alembic upgrade head`를 수행하는 과정에서 PostgreSQL 식별자 길이 제약에 걸렸다.

문제가 된 자동 생성 이름은 아래와 같았다.

- FK: `fk_address_serving_juso_related_jibun_road_address_management_no_address_serving_juso_road_address`
- Index: `ix_address_serving_juso_related_jibun_road_address_management_no`

PostgreSQL 식별자는 최대 63바이트까지만 허용된다. 테이블명과 컬럼명이 긴 상태에서 SQLAlchemy/Alembic의 자동 이름 생성에만 의존하면, 실제 PostgreSQL 마이그레이션 시점에 `IdentifierError`가 나거나, DB 레벨에서 이름이 잘려 추적이 어려워질 수 있다.

이번 적재에서는 스키마 이름 제약 외에도 두 가지 운영 제약이 확인됐다.

- `address_serving_juso_related_jibun`은 `address_serving_juso_road_address`를 FK로 참조하므로 적재 순서가 고정된다.
- `legal_dong_code`, `road_name_code`, `administrative_dong_code`, `road_address_management_no` 같은 주소 식별자는 선행 0 보존이 필요하므로 숫자가 아니라 문자열로 저장해야 한다.

2026-04-26 날씨/관광코스 스키마를 추가하면서 nullable 컬럼이 포함된 unique 제약의 PostgreSQL 동작도 확인했다.

- PostgreSQL의 일반 unique 제약은 `NULL` 값을 서로 다른 값으로 취급한다.
- 따라서 `sido_code`, `sigungu_code`, `legal_dong_code_prefix`처럼 scope 컬럼 일부가 null일 수 있는 mapping table에서는 일반 unique만으로 중복 row를 막을 수 없다.
- 같은 이유로 관광코스 상세 날씨 cache처럼 `spot_id`, `base_date`, `forecast_date` 일부가 null일 수 있는 unique key도 DB 레벨 중복 방지에 구멍이 생길 수 있다.

## 결정

- 긴 테이블명/컬럼명을 사용하는 스키마에서는 FK, index, unique, check 제약 이름을 자동 생성에 맡기지 않는다.
- 제약 이름은 모델과 마이그레이션 모두에서 짧고 명시적인 ASCII 이름으로 고정한다.
- 실무 기준으로 새 제약 이름은 가능하면 40자 이하로 유지한다. 이번 사례에서는 아래 이름으로 확정했다.
  - FK: `fk_addr_serv_rel_jibun_ramno`
  - Index: `ix_asjrj_ramno`
- 스키마 변경은 모델 메타데이터 확인만으로 끝내지 않고, WSL2 Docker PostgreSQL/PostGIS에서 실제 `uv run alembic upgrade head`를 최소 1회 성공시켜야 완료로 본다.
- PostgreSQL 15 이상에서 nullable 컬럼이 포함된 unique key가 실제 중복 방지 역할을 해야 하면 `NULLS NOT DISTINCT`를 명시한다. SQLAlchemy 모델과 Alembic migration에는 `postgresql_nulls_not_distinct=True`를 함께 둔다.
- Juso serving 적재 순서는 아래 순서를 고정한다.
  1. `address_serving_juso_road_address` 재구성
  2. `address_serving_juso_related_jibun` 재구성
- 주소 식별자 컬럼은 PostgreSQL에서 `TEXT` 계열로 유지하고, ETL 파서/로더에서 정수 변환을 하지 않는다.

## 대안

- 자동 생성 이름을 그대로 사용한다:
  - 구현은 간단하지만 긴 이름에서 다시 실패하거나, PostgreSQL이 이름을 잘라서 운영 중 추적성이 떨어진다.
- SQLite나 메타데이터 테스트만 통과시키고 PostgreSQL DDL 검증을 생략한다:
  - PostgreSQL 전용 제약은 놓치기 쉽고, 실제 배포 직전에 마이그레이션이 깨질 수 있다.

## 결과/영향

- 모델과 마이그레이션에 짧은 명시적 이름을 적어야 하므로 작성량은 조금 늘어난다.
- 대신 제약 이름이 안정적으로 유지되고, Alembic diff와 장애 분석이 쉬워진다.
- Juso 적재 파이프라인은 FK 의존성을 고려한 적재 순서를 반드시 지켜야 한다.
- 주소 코드 계열을 문자열로 유지하므로 선행 0 손실을 막을 수 있다.
- nullable scope unique 제약은 `NULLS NOT DISTINCT`를 쓰면 일반 unique보다 의도가 더 분명해진다. 단, 이 기능은 PostgreSQL 15 이상이 필요하므로 로컬/운영 PostgreSQL 버전은 16 계열을 유지한다.

## 후속 작업

- `docs/runbooks/local-dev.md`에 PostgreSQL 마이그레이션 체크리스트를 유지한다.
- 이후 긴 테이블명/컬럼명을 추가하는 스키마 작업에서도 동일 규칙을 적용한다.
