# python-krtour-map 통합 기준

`python-krtour-map`은 TripMate의 하부 feature 라이브러리다. 여러 provider 라이브러리의 응답을 공통 feature, source trace, weather/price value로 정리하고, 그 저장 schema와 helper 함수를 함께 제공한다.

## 책임 분리

`python-krtour-map` 책임:

- `Feature`, `SourceRecord`, `SourceLink`, `WeatherValue`, `PricePoint`, `ProviderSyncState` DTO
- feature/source/weather/price DB schema와 row 변환 함수
- provider canonical name과 legacy alias 정규화
- deterministic `feature_id`, `source_record_key` 생성
- debug fixture 저장, masking, pytest replay helper
- provider 응답을 feature 계약으로 바꾸는 순수 parser/processor 경계

TripMate 책임:

- FastAPI endpoint와 권한 검증
- 사용자, 여행 일정, 알림, API serving에 필요한 제품 DB
- Dagster schedule, ETL orchestration, 운영 알림
- Admin UI, 검수, dedup, source override workflow
- 사용자 여행/POI snapshot 정책

TripMate는 별도 feature DB를 만들지 않는다. feature 저장과 weather/price/source 상태는 `krtour_map.db`의 schema와 함수를 사용한다.

## Provider 사용 원칙

TripMate는 `KmaGateway`, `OpiNetAdapter`, `KrexWrapper` 같은 새 중간 계층을 만들지 않는다. ETL loader는 각 `python-*-api` 라이브러리의 public client와 typed model을 직접 사용한다.

부족한 endpoint, typed model, pagination, cursor, exception 분류는 TripMate 안에 우회 wrapper를 만들지 않고 해당 provider 라이브러리에 먼저 반영한다.

## 현재 코드 경계

TripMate API는 `apps/api/pyproject.toml`에서 `python-krtour-map` 커밋을 직접 의존성으로 고정한다.

- `app.services.krtour_map_feature_store`: `krtour_map.db` metadata/table/row helper를 import하는 TripMate 경계
- `app.core.krtour_map_contract`: enum/check 값 공유. feature DB를 새로 정의하기 위한 곳이 아니다.
- `tests/test_krtour_map_contract.py`: TripMate가 library-owned feature DB 계약을 import하는지 확인한다.

## Weather feature

날씨성 데이터는 KMA 시간축을 기준으로 `python-krtour-map`의 `WeatherValue`와 feature DB에 저장한다.

- `forecast_style`: 관측/예보/지수/특보 성격
- `timeline_bucket`: KMA식 초단기/단기/중기 조회 축

같은 feature에 여러 provider 값이 들어와도 TripMate API는 사용자 화면에서 하나의 weather card로 조립하고, Admin/debug 화면에서는 provider별 source row를 확인할 수 있게 한다.

## 문서 정리 기준

TripMate 문서에는 TripMate 제품 DB, API, Admin, 운영 runbook만 남긴다. feature DTO, source role, provider canonical name, fixture replay, feature DB schema는 `python-krtour-map` 문서를 canonical로 둔다.

제거 또는 축소할 내용:

- TripMate 전용 provider adapter/wrapper 생성 지침
- `pykma`, `pyopinet`, `pykrex` 같은 legacy alias를 DB/provider 표기명으로 쓰는 예시
- feature DB table/column을 TripMate 문서에서 중복 정의하는 내용
- fixture마다 pytest 코드를 생성하는 방식 설명
- feature DTO 상세 중복 정의
