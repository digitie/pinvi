# python-krtour-map 통합 기준

`python-krtour-map`은 TripMate의 하부 feature 계약 라이브러리다. TripMate가 직접 provider별 adapter/wrapper를 늘리지 않고도 여러 API 라이브러리에서 올라오는 여행 지도 정보를 공통 feature, source trace, weather/price value로 정리하기 위한 기준을 제공한다.

## 책임 분리

`python-krtour-map` 책임:

- `Feature`, `SourceRecord`, `SourceLink`, `WeatherValue`, `PricePoint`, `ProviderSyncState` Pydantic DTO
- `place`, `event`, `notice`, `price`, `weather`, `route`, `area` feature kind 계약
- provider canonical name과 legacy alias 정규화
- deterministic `feature_id`, `source_record_key` 생성
- debug fixture 저장, 민감정보 마스킹, pytest replay helper
- provider 응답을 저장 계약으로 바꾸는 순수 parser/processor 경계

TripMate 책임:

- FastAPI endpoint와 권한 검사
- SQLAlchemy/PostGIS model과 Alembic migration
- Dagster schedule, ETL orchestration, 운영 알림
- Admin UI, dedup review, source override workflow
- 사용자 여행/POI snapshot 정책

## Provider 사용 원칙

TripMate는 `KmaGateway`, `OpiNetAdapter`, `KrexWrapper` 같은 새 중간 계층을 만들지 않는다. ETL loader는 각 `python-*-api` 라이브러리의 public client와 typed model을 직접 사용한다.

부족한 endpoint, typed model, pagination, cursor, exception 분류는 TripMate 안에서 우회 wrapper를 만들지 않고 해당 provider 라이브러리에 먼저 반영한다.

## 현재 코드 경계

TripMate API는 `apps/api/pyproject.toml`에서 `python-krtour-map` 커밋을 직접 의존성으로 고정한다.

- `app.core.krtour_map_contract`: `FeatureKind`, `SourceRole`, `WeatherDomain`, `ForecastStyle` 값을 가져와 SQLAlchemy check constraint 값으로 사용한다.
- `app.services.krtour_map_contract`: `MapFeature`, `SourceRecord`, `MapFeatureWeatherValue`, `ProviderSyncState` ORM row를 `python-krtour-map` Pydantic DTO로 내보낸다.
- `tests/test_krtour_map_contract.py`: TripMate 모델 제약과 export 함수가 하부 라이브러리 계약을 따르는지 확인한다.

## Weather feature

날씨성 데이터는 KMA 시간축을 기준으로 `map_feature_weather_values`에 저장한다.

| provider library | domain | 기준 |
| --- | --- | --- |
| `python-kma-api` | `kma_ultra_short_nowcast`, `kma_ultra_short_forecast`, `kma_short_forecast`, `kma_mid_forecast` | 전체 weather timeline 기준 |
| `python-krex-api` | `rest_area_weather` | 휴게소 feature context |
| `python-krairport-api` | `airport_weather` | 공항 feature context |
| `python-visitkorea-api` | `tourist_spot_weather` | 관광지 상세 날씨 보강 |
| `python-airkorea-api` | `air_quality` | 주변 측정소/시도 대기질 |
| `python-khoa-api` | `beach_marine` | 해수욕장/해양 지수 |

같은 feature에 여러 provider 값이 들어와도 TripMate API는 사용자 화면에서는 하나의 weather card로 조립하고, Admin/debug 화면에서는 provider별 source row를 그대로 확인할 수 있어야 한다.

## 문서 정리 기준

TripMate 문서에는 앱 DB, API, Admin, 운영 runbook만 남긴다. feature DTO, source role, provider canonical name, fixture replay 포맷은 `python-krtour-map` 문서를 canonical로 삼는다.

삭제 또는 축소할 내용:

- TripMate 전용 provider adapter/wrapper 생성 지침
- `pykma`, `pyopinet`, `pykrex` 같은 짧은 alias를 DB/provider 표기명으로 사용하는 예시
- fixture마다 pytest 코드를 생성하는 방식의 설명
- feature DTO 상세 중복 정의

남길 내용:

- TripMate DB table name, migration revision, index, retention
- TripMate API endpoint와 응답 조립 정책
- Admin UI와 운영자 검수/override/dedup workflow
- Dagster job schedule과 실패 대응 절차
