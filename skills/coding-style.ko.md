---
name: coding-style
description: "TripMate 코드 작성·수정 시 적용하는 코딩 스타일 기준. 기능 구현, 리팩터링, 버그 수정, 테스트 보강, 마이그레이션, 프론트엔드/백엔드 코드 변경을 할 때 사용한다. 특히 lint, format check, typecheck 실행 여부를 완료 조건으로 점검해야 할 때 사용한다."
---

# Skill: 코딩 스타일

이 skill은 TripMate 코드 변경 시 기본 코딩 품질선을 맞추기 위해 사용한다.

## 핵심 원칙

- 코드 변경에는 lint와 타입체킹을 필수 검증으로 포함한다.
- 테스트가 필요한 변경은 관련 테스트를 추가하거나 갱신한다.
- 스타일을 맞추기 위해 의미 없는 대규모 포맷팅을 하지 않는다.
- 기존 코드베이스의 구조, 네이밍, 계층 분리를 우선한다.
- 숨은 전역 상태, 임의 문자열 파싱, 하드코딩된 secret, 불필요한 추상화를 피한다.
- 타입 안정성을 코드로 확보한다. 타입 선언만 믿고 동적 데이터나 외부 응답을 바로 캐스팅하지 않는다.

## 타입 안정성 기준

- API, DB row, 외부 provider 응답, JSONB처럼 런타임 shape가 흔들릴 수 있는 값은 경계에서 `unknown`/`object`로 받고 parser, schema, `TypedDict`, Pydantic model 등으로 좁힌다.
- `Any`는 SQLAlchemy/외부 라이브러리처럼 타입 표현이 불가피한 좁은 경계에만 둔다. 서비스 public return type, API response type, React state type에는 `Any`를 확산시키지 않는다.
- JSON 응답은 `JsonValue` 같은 닫힌 타입으로 표현하고, datetime/UUID/Decimal/bytes 등은 직렬화 정책을 한 곳에 둔다. Pydantic schema에 쓰는 재귀 타입 alias는 Python 3.12의 `type JsonValue = ...` 문법을 사용한다.
- 타입 에러를 숨기기 위한 `cast`, `as`, `type: ignore`는 마지막 수단이다. 사용하면 왜 안전한지 코드 구조나 주석으로 드러나야 한다.
- 새 endpoint/client helper를 만들 때는 요청 타입, 응답 타입, 오류 타입을 함께 정의한다.

## 언어별 기준

### Python / FastAPI

- 타입 힌트를 작성한다.
- 동적 dict를 반환하는 service는 가능하면 `TypedDict` 또는 Pydantic model로 public return shape를 고정한다.
- JSON 직렬화 함수는 반환 가능한 타입을 `Any`가 아니라 JSON value 타입으로 제한한다.
- FastAPI router는 얇게 유지하고, 규칙은 service/loader/source 계층으로 둔다.
- SQLAlchemy 모델, Alembic migration, 테스트 fixture의 제약 이름과 타입을 서로 맞춘다.
- 외부 API source에는 timeout, retry, quota, 에러 분류를 고려한다.
- DB datetime은 timezone-aware KST 기준을 지킨다.

필수 확인:

- `ruff check`
- `ruff format --check`
- `mypy` 또는 저장소가 정한 Python typecheck 명령

### TypeScript / React

- 정당한 이유 없이 `any`를 쓰지 않는다.
- API 응답은 `unknown`으로 받은 뒤 endpoint별 parser/type guard로 검증하고 React state에 넣는다.
- generic fetch helper에서 `return payload as T`처럼 응답을 무검증 캐스팅하는 패턴은 피한다.
- 비즈니스 규칙을 React component에 과도하게 넣지 않는다.
- 폼 검증, API schema, UI 상태 타입을 명시한다.
- 사용자 흐름이 바뀌면 component/integration/E2E 테스트 필요 여부를 판단한다.

필수 확인:

- `npm run lint`
- `npm run typecheck`

## 실행 기준

- 명령은 먼저 저장소에 실제 script가 있는지 확인한 뒤 실행한다.
- 저장소 명령은 WSL2 Ubuntu를 최우선으로 실행한다. Windows PowerShell에서는 `wsl.exe -e bash -lc "cd /mnt/f/dev/tripmate && ..."` 형태를 우선 사용한다.
- backend test, Docker, PostgreSQL/PostGIS, Alembic, Dagster 검증은 WSL2 Ubuntu 기준으로 실행한다.
- 실행하지 못한 검사가 있으면 성공했다고 쓰지 말고, 이유와 남은 위험을 최종 요약에 남긴다.
- lint/typecheck 실패는 구현 완료로 보지 않는다. 실패가 기존 문제라면 범위와 증거를 분리해서 기록한다.

## 완료 조건

코드 변경 완료 전 아래를 확인한다.

- 관련 lint 통과
- 관련 typecheck 통과
- 변경 범위에 맞는 테스트 통과
- DB schema 변경 시 Alembic migration과 upgrade 검증
- 외부 API/ETL 변경 시 data source 문서와 runbook 갱신
- 최종 요약에 실행한 명령과 결과 포함
