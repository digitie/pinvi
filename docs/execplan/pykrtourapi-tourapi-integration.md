# pykrtourapi 기반 TourAPI 연동 실행 계획

## 목표

TripMate의 KTO TourAPI 연동은 `pykrtourapi`를 직접 사용한다. TripMate backend에는 adapter/gateway 래퍼를 만들지 않고, 설정과 DB 저장 경계만 둔다. TourAPI 호출, 파라미터 검증, 응답 파싱, 오류 분류, provider raw 보존에 필요한 공통 동작은 `pykrtourapi` 저장소에서 구현한다.

## 이번 변경 범위

- `apps/api/pyproject.toml`에 `pykrtourapi` git commit 의존성을 추가한다.
- `app.core.kto`에는 `KrTourApiClient`와 `TourApiHubClient`를 생성하는 설정 함수만 둔다.
- `tests/test_kto_pykrtourapi.py`에서 TripMate가 pykrtourapi client와 Pydantic 응답 모델을 직접 사용한다는 계약을 검증한다.
- `.env.example`, API README, 로컬 runbook, 데이터 소스 문서, ADR을 갱신한다.

현재 반영 commit:

- `pykrtourapi`: `dc855cb177c9a7842400957f5574760b85e71347`

최신 pykrtourapi는 TripMate가 요청했던 `Page.context`, typed `related_tour`, pagination helper, exception metadata, `cpyrhtDivCd`/HTML 표시 helper를 public API로 제공한다. TripMate 코드는 별도 KTO adapter 없이 이 API를 직접 사용한다.

## TripMate 쪽 원칙

- `KtoAdapter`, `KtoGateway`, `NormalizedKtoPlace` 같은 앱 전용 래퍼를 만들지 않는다.
- endpoint별 호출 코드는 `KrTourApiClient` 또는 `TourApiHubClient`를 직접 사용한다.
- KTO raw response 전체 저장 예외는 KTO raw/serving/snapshot 테이블에만 적용한다.
- `mapX`는 경도, `mapY`는 위도로 취급하고, 저장 시 `lng`, `lat`으로 분리한다.
- `areaCode`, `sigunguCode`, `lDongRegnCd`, `lDongSignguCd`를 TripMate `legal_dong_code`와 혼동하지 않는다.

## pykrtourapi 반영 완료 항목

- `Page.context`: `service_name`, `endpoint`, `request_params`, `collected_at` 제공. `request_params`에는 `serviceKey`가 포함되지 않는다.
- `RelatedTourItem`과 `hub.related_tour.area_based_list()`, `hub.related_tour.search_keyword()` typed helper 제공.
- `Page.has_next_page`, `Page.next_page_no`, `KrTourApiClient.iter_pages()`, `TourApiHubClient.iter_pages()`, `RelatedTourServiceClient.iter_*()` 제공.
- `TourApiError.metadata`: `result_code`, `status_code`, `endpoint`, `service_name`, `failure_kind` 제공.
- `copyright_display_info()`와 `clean_tourapi_html()` opt-in helper 제공.

## pykrtourapi 저장소에 줄 추가 Codex 지시문

현재 TripMate가 요청했던 KTO 경계 기능은 `dc855cb177c9a7842400957f5574760b85e71347`에서 모두 반영됐다. 추가로 새 TourAPI 서비스를 쓰게 될 때 typed model이 부족하면 아래 형식으로 upstream한다.

```text
pykrtourapi 저장소에서 작업해줘.

목표:
- TripMate가 <서비스명>/<operation명>을 adapter 없이 직접 사용할 수 있도록 typed model과 service helper를 추가해.

요구사항:
- 공식 TourAPI field를 보존하는 Pydantic frozen model을 추가하고 `raw`를 유지해.
- `TourApiHubClient`에서 `<service_key>` property 또는 service-specific helper로 `Page[<Model>]`을 반환하게 해.
- `Page.context`, `iter_*` pagination helper, typed exception metadata가 기존 서비스와 같은 방식으로 채워지게 해.
- serviceKey 원문은 request provenance, exception, test fixture에 남기지 마.
- offline fake response tests, docs, README 예시를 추가하고 `python -m pytest`, `ruff check .`, `mypy pykrtourapi`를 통과시켜.
```

## 검증 계획

- WSL2에서 `cd /mnt/f/dev/mapplan/apps/api && uv sync --group dev`
- WSL2에서 `uv run ruff check .`
- WSL2에서 `uv run ruff format --check .`
- WSL2에서 `uv run mypy .`
- WSL2에서 `uv run pytest tests/test_kto_pykrtourapi.py`

## 남은 위험

- `pykrtourapi`는 GPL-3.0-or-later이므로 TripMate 배포 라이선스와 양립성을 확인해야 한다.
- KTO 호출 한도와 `cpyrhtDivCd`별 UI 문구/출처 표기 정책은 실제 계정/최신 문서 기준 확인이 필요하다.
- `clean_tourapi_html()`은 표시용 텍스트 정리 helper이며 보안 sanitizer가 아니므로 화면 구현 시 별도 sanitizer 정책이 필요하다.
