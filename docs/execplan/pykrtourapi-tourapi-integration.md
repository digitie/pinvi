# pykrtourapi 기반 TourAPI 연동 실행 계획

## 목표

TripMate의 KTO TourAPI 연동은 `pykrtourapi`를 직접 사용한다. TripMate backend에는 adapter/gateway 래퍼를 만들지 않고, 설정과 DB 저장 경계만 둔다. TourAPI 호출, 파라미터 검증, 응답 파싱, 오류 분류, provider raw 보존에 필요한 공통 동작은 `pykrtourapi` 저장소에서 구현한다.

## 이번 변경 범위

- `apps/api/pyproject.toml`에 `pykrtourapi` git commit 의존성을 추가한다.
- `app.core.kto`에는 `KrTourApiClient`와 `TourApiHubClient`를 생성하는 설정 함수만 둔다.
- `tests/test_kto_pykrtourapi.py`에서 TripMate가 pykrtourapi client와 Pydantic 응답 모델을 직접 사용한다는 계약을 검증한다.
- `.env.example`, API README, 로컬 runbook, 데이터 소스 문서, ADR을 갱신한다.

현재 반영 commit:

- `pykrtourapi`: `8d8416d4ca865071f94060b5c07fa46ae3f46916`

## TripMate 쪽 원칙

- `KtoAdapter`, `KtoGateway`, `NormalizedKtoPlace` 같은 앱 전용 래퍼를 만들지 않는다.
- endpoint별 호출 코드는 `KrTourApiClient` 또는 `TourApiHubClient`를 직접 사용한다.
- KTO raw response 전체 저장 예외는 KTO raw/serving/snapshot 테이블에만 적용한다.
- `mapX`는 경도, `mapY`는 위도로 취급하고, 저장 시 `lng`, `lat`으로 분리한다.
- `areaCode`, `sigunguCode`, `lDongRegnCd`, `lDongSignguCd`를 TripMate `legal_dong_code`와 혼동하지 않는다.

## pykrtourapi 저장소에 줄 Codex 지시문

### 1. 요청/응답 provenance 추가

```text
pykrtourapi 저장소에서 작업해줘.

목표:
- TripMate 같은 소비자가 별도 adapter 없이 raw/serving 저장을 할 수 있도록 Page에 호출 provenance를 담아줘.

요구사항:
- Page에 service_name, endpoint, request_params, collected_at 같은 metadata를 추가하거나 하위 호환 가능한 context 객체를 추가해.
- request_params에는 serviceKey 원문을 절대 넣지 말고, MobileOS/MobileApp/_type과 endpoint별 params는 남겨.
- 기존 public API와 테스트가 깨지지 않게 기본값 또는 optional 구조로 설계해.
- KrTourApiClient의 areaBasedList2/locationBasedList2/searchKeyword2/detail* 계열과 TourApiHubClient의 generic call 모두 metadata를 채워.
- tests를 추가하고 `python -m pytest`, `ruff check .`, `mypy pykrtourapi`를 통과시켜.
```

### 2. `TarRlteTarService1` typed model 추가

```text
pykrtourapi 저장소에서 작업해줘.

목표:
- TripMate가 관광지별 연관 관광지 정보를 adapter 없이 사용할 수 있도록 TarRlteTarService1 typed client/model을 추가해.

요구사항:
- RelatedTourItem 같은 frozen dataclass를 추가하고 아래 필드를 typed 속성으로 노출해:
  baseYm, tAtsCd, tAtsNm, areaCd, areaNm, signguCd, signguNm,
  rlteTatsCd, rlteTatsNm, rlteRegnCd, rlteRegnNm, rlteSignguCd, rlteSignguNm,
  rlteCtgryLclsNm, rlteCtgryMclsNm, rlteCtgrySclsNm, rlteRank, raw
- TourApiHubClient에서 `hub.related_tour.area_based_list(...)`, `hub.related_tour.search_keyword(...)` 형태로 typed Page[RelatedTourItem]을 받을 수 있는 방법을 제공해. 기존 generic `call()`은 유지해.
- `areaCd`/`signguCd`는 TourAPI용 지역 코드일 뿐 법정동코드가 아니라는 docstring을 남겨.
- offline fake response tests를 추가해 단건 item/list item 모두 검증해.
```

### 3. pagination helper 추가

```text
pykrtourapi 저장소에서 작업해줘.

목표:
- TripMate가 코드 캐시와 후보 조회에서 페이지 반복 로직을 자체 구현하지 않도록 pagination helper를 추가해.

요구사항:
- Page.total_count, page_no, num_of_rows를 기준으로 다음 페이지가 있는지 판단하는 helper를 추가해.
- KrTourApiClient와 TourApiHubClient 양쪽에서 `iter_pages(...)` 또는 endpoint별 `iter_*` helper를 제공해.
- 무한 반복 방지를 위해 max_pages 또는 max_items guard를 제공해.
- NO_DATA 응답은 빈 iterator로 처리하고, 인증/쿼터/서버 오류는 기존 typed exception을 그대로 올려.
- tests에서 totalCount가 numOfRows보다 큰 경우 pageNo가 증가하는지 검증해.
```

### 4. 오류 객체에 분류 metadata 추가

```text
pykrtourapi 저장소에서 작업해줘.

목표:
- TripMate가 별도 exception mapping 래퍼를 만들지 않아도 관리자 로그와 사용자 오류 메시지를 분리할 수 있게 해줘.

요구사항:
- TourApiError 계층에 result_code, status_code, endpoint, service_name, failure_kind 같은 optional metadata를 담을 수 있게 해.
- 기존 `except TourApiAuthError` 같은 catch 동작은 유지해.
- HTTP 401/403, 429, 4xx, 5xx, XML service-key 오류, JSON resultCode 오류에서 metadata를 채워.
- serviceKey 원문은 exception 문자열, repr, metadata 어디에도 남기지 마.
- tests를 추가해 auth/rate_limit/no_data/server/request/parse 분류를 검증해.
```

### 5. `cpyrhtDivCd`와 HTML helper 보강

```text
pykrtourapi 저장소에서 작업해줘.

목표:
- TripMate가 KTO 이미지/텍스트 표시 정책을 앱 전용 문자열 매핑 없이 적용할 수 있도록 일반 helper를 제공해.

요구사항:
- cpyrhtDivCd 값을 안전하게 보존하면서, 표시 가능한 label/주의사항을 반환하는 helper를 추가해.
- detailCommon2 homepage/overview, detailInfo2 infotext 같은 HTML 문자열을 앱이 sanitize하기 전 미리 정리할 수 있는 opt-in helper를 제공해. 원문 raw는 반드시 보존 가능해야 해.
- helper는 기본 parsing 결과를 바꾸지 말고, 소비자가 명시적으로 호출할 때만 동작하게 해.
- README와 tests를 추가해.
```

## 검증 계획

- WSL2에서 `cd /mnt/f/dev/mapplan/apps/api && uv sync --group dev`
- WSL2에서 `uv run ruff check .`
- WSL2에서 `uv run ruff format --check .`
- WSL2에서 `uv run mypy .`
- WSL2에서 `uv run pytest tests/test_kto_pykrtourapi.py`

## 남은 위험

- `pykrtourapi`는 GPL-3.0-or-later이므로 TripMate 배포 라이선스와 양립성을 확인해야 한다.
- `TarRlteTarService1`는 현재 generic hub 호출로는 사용할 수 있지만 typed model이 부족하다.
- KTO 호출 한도와 `cpyrhtDivCd`별 표시 정책은 실제 계정/최신 문서 기준 확인이 필요하다.
