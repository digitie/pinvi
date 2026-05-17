---
name: database-architect
description: "TripMate의 PostgreSQL/PostGIS DB 설계, SQLAlchemy 2 모델, GeoAlchemy2 공간 컬럼, Alembic migration, 인덱스, 제약조건, DB 테스트를 작성·리뷰할 때 사용한다. DB 스키마 변경, 마이그레이션 추가, 주소/장소/날씨/유가/휴게소 ETL 저장 구조, 공간 쿼리, FK/unique/index 정합성, timezone 저장 정책 검토에 적용한다."
---

# Skill: 데이터베이스 아키텍트

TripMate의 DB 작업은 PostgreSQL + PostGIS + SQLAlchemy 2 + GeoAlchemy2 + Alembic 기준으로 설계하고 검증한다.

## 먼저 확인할 문서

- 전체 구조: `docs/architecture.md`
- 주소 기준: `docs/architecture/address-schema.md`
- 장소 기준: `docs/architecture/place-schema.md`
- 데이터 소스 정책: `docs/data-sources.md`
- ETL 운영: `docs/runbooks/etl.md`
- 공간 규칙: `skills/geospatial-postgis.ko.md`
- 테스트 기준: `skills/testing-and-qa.ko.md`

## 핵심 원칙

- ORM 모델, Alembic migration, 테스트 fixture가 같은 계약을 말해야 한다.
- DB 스키마 변경은 migration 없이 모델만 바꾸지 않는다.
- 대량 공공데이터는 raw와 serving 레이어를 분리한다.
- 외부 provider 원문 저장 정책은 `docs/data-sources.md`를 따른다.
- 모든 주소 코드, provider 코드, 카테고리 코드는 선행 0 보존을 위해 문자열로 저장한다.
- DB datetime은 timezone-aware `timestamptz`로 저장하고 KST 정책을 지킨다.
- app 시작 시점에 몰래 스키마를 변경하지 않는다.

## SQLAlchemy 모델 기준

- SQLAlchemy 2 스타일 `Mapped[]`, `mapped_column()`을 사용한다.
- 공통 생성/수정 시각은 기존 mixin 패턴을 따른다.
- FK는 이름을 명시하고, 삭제 동작(`CASCADE`, `SET NULL`, 제한)을 의도적으로 고른다.
- FK 컬럼에는 명시 인덱스 또는 FK 컬럼으로 시작하는 covering index를 둔다.
- nullable은 migration과 모델이 일치해야 한다.
- JSONB는 원천 재처리나 provider payload처럼 구조가 달라질 수 있는 데이터에만 제한적으로 사용한다.
- 상태값은 의미 있는 문자열 enum 후보를 문서화하고, 임의 문자열 확산을 피한다.

## PostGIS 기준

- 공간 컬럼은 SRID를 반드시 명시한다.
- 원천 경계 데이터는 원천 SRID를 보존하고, 앱/지도/API용 serving geometry는 EPSG:4326을 둔다.
- 공간 컬럼은 `spatial_index=False`로 선언하고 Alembic에서 GiST 인덱스를 명시 생성한다.
- 좌표는 DB/PostGIS에서 `lon`, `lat`, `ST_MakePoint(lon, lat)` 순서를 사용한다.
- 행정구역 point-in-polygon은 PostGIS를 기준으로 한다.
- 정확한 거리 검색이 아니라 행정구역 기반 근사면 문서와 UI에서 근사라고 쓴다.

## Alembic migration 기준

- revision ID, down_revision, upgrade/downgrade를 모두 확인한다.
- `CREATE EXTENSION IF NOT EXISTS postgis`는 초기 migration에 두고, downgrade에서 extension을 함부로 drop하지 않는다.
- geometry 컬럼, SRID, GiST 인덱스는 migration에서 명시한다.
- FK/unique/check/index 이름을 안정적으로 붙인다.
- nullable unique에 `NULL`을 같은 값처럼 취급해야 하면 PostgreSQL `NULLS NOT DISTINCT` 사용 여부를 테스트한다.
- 대형 테이블에 인덱스를 추가할 때 운영 lock 위험을 검토하고 문서화한다.
- destructive migration은 백업/복구/재처리 계획이 없으면 만들지 않는다.

## 리뷰 체크리스트

DB 작업 후 반드시 아래를 점검한다.

- 모델 테이블명과 migration 테이블명이 일치한다.
- 컬럼 타입, 길이, nullable, 기본값이 모델과 migration에서 일치한다.
- FK 대상 테이블과 컬럼이 존재한다.
- FK 컬럼에 인덱스가 있다.
- unique 제약이 ETL 멱등성 기준과 맞다.
- raw/serving 테이블의 목적이 섞이지 않았다.
- 공간 컬럼은 SRID와 GiST 인덱스를 가진다.
- timestamp 컬럼은 timezone-aware다.
- provider 원문 장기 저장 금지 정책을 위반하지 않는다.
- 기존 여행/주소 참조가 깨지는 delete/update를 하지 않는다.

## 테스트 기준

DB 관련 변경에는 최소한 다음 중 해당 항목을 추가하거나 갱신한다.

- migration contract test: migration 파일에 핵심 테이블/컬럼/제약/인덱스가 있는지 확인.
- model metadata test: `Base.metadata`에 모델이 등록되고, timezone/SRID/FK/index 계약이 맞는지 확인.
- loader idempotency test: 같은 원천 데이터를 두 번 적재해도 중복이 생기지 않는지 확인.
- FK mismatch test: skip/log 정책이 문서대로 동작하는지 확인.
- Alembic upgrade 검증: WSL2 Docker Postgres에서 `alembic upgrade head`.
- 필요한 경우 downgrade 후 upgrade 재검증.

권장 명령:

아래 명령은 Windows PowerShell에서 실행하더라도 WSL2를 감싸는 형태를 우선한다. 이미 WSL2 shell 안에 있다면 `wsl.exe -e bash -lc` 부분을 빼고 같은 작업 디렉터리에서 실행한다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/tripmate/apps/api && .venv-wsl/bin/ruff check ."
wsl.exe -e bash -lc "cd /mnt/f/dev/tripmate/apps/api && .venv-wsl/bin/ruff format --check ."
wsl.exe -e bash -lc "cd /mnt/f/dev/tripmate/apps/api && .venv-wsl/bin/mypy ."
wsl.exe -e bash -lc "cd /mnt/f/dev/tripmate/apps/api && .venv-wsl/bin/pytest"
wsl.exe -e bash -lc "cd /mnt/f/dev/tripmate/apps/api && .venv-wsl/bin/alembic upgrade head"
```

## 금지 사항

- SRID 없는 geometry 컬럼을 만들지 않는다.
- 공간 검색 대상 컬럼에 GiST 인덱스를 빼지 않는다.
- FK 컬럼을 인덱스 없이 방치하지 않는다.
- `lat`, `lng`만 저장하고 PostGIS geometry를 생략하지 않는다.
- provider 원문 전체를 정책 없이 장기 저장하지 않는다.
- 비밀값, API key, token 원문을 DB/로그/test fixture에 넣지 않는다.
