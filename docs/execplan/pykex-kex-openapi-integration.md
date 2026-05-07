# pykex 기반 한국도로공사 OpenAPI 연동 실행 계획

## 배경

TripMate의 한국도로공사 휴게소/고속도로 데이터 연동은 아직 주로 문서 계획 상태다. 기존 계획은 데이터셋별 raw/serving 저장 정책을 정의하지만, 실제 API 호출 계층은 정해지지 않았다.

사용자 지시에 따라 TripMate 내부에 별도 한국도로공사 adapter나 wrapper를 만들지 않고, 범용 라이브러리인 `pykex`의 `kex_openapi.KexClient`를 직접 사용한다. TripMate에 필요한 호출 표면이 `pykex`에 부족하면 먼저 `pykex`를 개선한다.

## 변경 범위

- `F:/dev/pykex`
  - 휴게소 master 후보 API, 휴게소 주유소 가격 API, 휴게소 편의시설 API를 `KexClient.restarea` 네임스페이스에 추가한다.
  - 안정 필드는 Pydantic 모델로 노출하고, 응답 필드가 불확실한 편의시설 현황은 `Page[dict]`로 노출한다.
  - fake session 기반 unit test와 문서를 갱신한다.
- `F:/dev/mapplan`
  - `kex-openapi` 의존성을 추가한다.
  - `TRIPMATE_KEX_*` 설정을 추가한다.
  - 별도 adapter 없이 `KexClient`를 직접 생성하고 사용하는 계약 테스트를 추가한다.
  - 테스트 통과 후 `docs/data-sources.md`, README류 문서를 `pykex` 기준으로 갱신한다.

## 테스트 계획

1. `pykex`에서 `compileall`과 `pytest`를 실행한다.
2. TripMate API WSL2 가상환경에 로컬 `pykex`를 editable로 설치해 개선 내용을 반영한다.
3. TripMate의 신규 `pykex` 계약 테스트를 먼저 실행한다.
4. 관련 외부 API 클라이언트 계약 테스트를 함께 실행한다.
5. 가능하면 전체 API 테스트로 확장한다.

## 결정 사항

- TripMate는 한국도로공사 응답 정규화 adapter를 만들지 않는다.
- raw/serving DB 적재는 추후 구현하되, ETL 호출 표면은 `KexClient.restarea.*`를 직접 사용한다.
- `data.ex.co.kr`의 실서버 경로는 문서에 출처와 검증 상태를 분리해 기록한다.
