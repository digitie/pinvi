# python-kma-api 기반 기상청 연동 반영 계획

## 목표

TripMate의 KMA 단기/중기/특보 수집과 DFS 격자 변환을 공용 라이브러리 `python-kma-api` 공개 API로 이동한다. TripMate에는 KMA 중간 계층을 새로 두지 않고, ETL 저장에 필요한 최소 row 변환만 남긴다.

## 확인한 python-kma-api 업데이트

- 기준 commit: `5dcf059e4ec8ea4cecc450d882e13a4f44074ecb`
- 공개 API: `KmaClient`, `DataGoKrClient`, `GridPoint`, `LatLon`, `wgs84_to_kma_grid`, `kma_grid_to_wgs84`
- 공통 helper: `ResponseMetadata`, `sanitize_request_params`, `make_cache_key`, pagination helper

## TripMate 반영 항목

- `apps/api/pyproject.toml`에 `python-kma-api` git commit pin을 추가한다.
- `apps/api/app/geospatial/kma_grid.py`를 제거하고, weather loader와 테스트는 `python-kma-api` 격자 변환 함수를 직접 import한다.
- `KmaWeatherApiClient`의 KMA data.go.kr 호출은 `kma.KmaClient`와 `kma.DataGoKrClient`로 위임한다.
- AirKorea와 해수욕장 전용 수집 로직은 이번 변경 범위 밖이므로 기존 구현을 유지한다.
- 문서와 ADR에 KMA 경계를 `python-kma-api` 기준으로 갱신한다.

## python-kma-api에 upstream할 추가 후보

아래는 TripMate에 래퍼를 늘리지 않기 위해 `python-kma-api` 쪽 Codex에 내릴 수 있는 후속 명령이다.

```text
python-kma-api의 DataGoKrClient에 모든 페이지의 response.body.items.item을 list[Mapping[str, Any]]로 반환하는 public helper를 추가해줘. service, operation, params, num_of_rows, max_pages를 받게 하고, resultCode 03/NO_DATA는 빈 list로 처리해줘. 기존 items()의 단일 페이지 동작은 깨지지 않게 유지하고 테스트를 추가해줘.
```

```text
python-kma-api에 KMA WthrWrnInfoService, MidFcstInfoService, TourStnInfoService1 endpoint별 typed model과 convenience method를 추가해줘. raw payload와 ResponseMetadata를 보존하고, TripMate가 DataGoKrClient.iter_pages를 직접 돌리지 않아도 되게 해줘.
```

```text
python-kma-api의 KmaError result_code 매핑에 data.go.kr resultCode 03/NO_DATA를 명시적인 no-data 예외 또는 빈 item helper 처리로 분리해줘. 인증, quota, 서버 오류와 구분되는 테스트를 추가해줘.
```

## 검증 계획

- WSL2 `apps/api` 가상환경에서 `python-kma-api`를 editable 또는 commit pin으로 설치한다.
- 좁은 범위부터 `pytest -q tests/test_kma_grid.py tests/test_weather_loader.py -k "kma or weather"`를 실행한다.
- 현재 저장소에 병합 충돌이 남아 있으면 import 단계에서 깨질 수 있으므로, 충돌 해소 후 `ruff`, `mypy`, 전체 `pytest`로 확장한다.
