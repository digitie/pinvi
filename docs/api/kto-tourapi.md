# KTO TourAPI 연동 계약

## 현재 상태

TripMate API에는 아직 KTO 후보 조회용 공개 HTTP endpoint가 없다. 현재 제공하는 것은 backend 내부에서 사용할 KTO client 생성 경계다.

- 코드 위치: `apps/api/app/core/kto.py`
- 국문 관광정보 client: `build_kto_kor_client()`
- TourAPI Hub client: `build_kto_hub_client()`
- 사용 라이브러리: `visitkorea`
- 고정 commit: `dc855cb177c9a7842400957f5574760b85e71347`
- 최신 확인 내용: `6fd0601a..dc855cb1` 구간에서 TripMate가 요청했던 호출 provenance, typed related-tour model, pagination helper, exception metadata, 저작권/HTML 표시 helper가 visitkorea public API로 추가됐다.

TripMate backend에는 KTO 전용 adapter 또는 gateway 래퍼를 만들지 않는다. `visitkorea`의 `KrTourApiClient`, `TourApiHubClient`, Pydantic 응답 모델, `raw` payload를 직접 사용한다.

## 설정

환경변수 prefix는 `TRIPMATE_`다.

| 설정 | 필수 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `TRIPMATE_KTO_SERVICE_KEY` | 예 | 없음 | 공공데이터포털 TourAPI decoding 인증키 |
| `TRIPMATE_KTO_MOBILE_APP` | 아니오 | `TripMate` | TourAPI 공통 `MobileApp` 값 |
| `TRIPMATE_KTO_MOBILE_OS` | 아니오 | `WEB` | TourAPI 공통 `MobileOS` 값 |
| `TRIPMATE_KTO_TIMEOUT_SECONDS` | 아니오 | `10.0` | 요청 timeout 초 |
| `TRIPMATE_KTO_MAX_RETRIES` | 아니오 | `2` | visitkorea HTTP retry 횟수 |

`TRIPMATE_KTO_SERVICE_KEY`가 없으면 `TourApiAuthError`를 발생시킨다. `visitkorea`의 일반 환경변수 fallback에 의존하지 않고, TripMate prefix 설정만 사용한다.

## 내부 사용 예시

```python
from app.core.kto import build_kto_kor_client, build_kto_hub_client
from visitkorea import ContentType, Wgs84Coordinate, clean_tourapi_html, copyright_display_info

kor_client = build_kto_kor_client()
page = kor_client.location_based_list(
    coordinate=Wgs84Coordinate(longitude=126.9769, latitude=37.5796),
    radius=15000,
    content_type_id=ContentType.TOURIST_ATTRACTION,
)

related_page = build_kto_hub_client().related_tour.area_based_list(
    base_ym="202604",
    area_cd="1",
    signgu_cd="23",
)

for code_page in kor_client.iter_pages(kor_client.area_codes, num_of_rows=100):
    ...

display_text = clean_tourapi_html(page.items[0].raw.get("overview"))
copyright_info = copyright_display_info(page.items[0].copyright_division_code)
```

## 응답 처리 기준

- `visitkorea` 응답 객체는 Pydantic model이다.
- serving 저장 후보 필드는 `model_dump()`로 얻을 수 있다.
- JSON API 응답이나 캐시 payload로 직렬화할 때는 날짜 처리를 위해 `model_dump(mode="json")` 또는 `model_dump_json()`을 우선 사용한다.
- provider 원문 보존은 `Page.raw`와 item별 `raw`를 사용한다.
- 호출 provenance는 `Page.context` 또는 편의 속성 `service_name`, `endpoint`, `request_params`, `collected_at`을 사용한다. `request_params`에는 `serviceKey` 원문이 포함되지 않는다.
- 반복 조회는 `KrTourApiClient.iter_pages()`, `TourApiHubClient.iter_pages()`, `RelatedTourServiceClient.iter_*()` helper를 사용한다.
- `TarRlteTarService1`는 `build_kto_hub_client().related_tour`의 typed helper를 우선 사용하고, 기존 generic `call()`은 실험 또는 미지원 operation에만 사용한다.
- `mapX`는 경도, `mapY`는 위도다. TripMate 저장 시 `lng`, `lat`으로 분리한다.
- `areaCode`, `sigunguCode`, `lDongRegnCd`, `lDongSignguCd`는 TourAPI 조회용 코드다. TripMate `legal_dong_code`로 취급하지 않는다.
- `copyright_display_info()`는 `cpyrhtDivCd` 표시 label/notice를 얻기 위한 기본 helper다. 실제 UI 문구와 정책 검수는 TripMate 화면 구현 시 다시 확인한다.
- `clean_tourapi_html()`은 opt-in 표시용 텍스트 정리 helper이며 보안 sanitizer가 아니다. HTML을 렌더링하는 화면은 별도 sanitizer를 적용한다.

## 오류 처리 기준

`visitkorea`의 typed exception을 그대로 사용한다.
예외 객체의 `metadata`에는 `result_code`, `status_code`, `endpoint`, `service_name`, `failure_kind`가 들어갈 수 있으며, 관리자 로그와 사용자 표시 메시지를 나누는 기준으로 사용한다.

| 예외 | TripMate 처리 |
| --- | --- |
| `TourApiAuthError` | 서버 설정 오류로 기록하고 사용자에게는 KTO 조회를 사용할 수 없다고 표시 |
| `TourApiRateLimitError` | quota/traffic 제한으로 기록하고 재시도 또는 stale cache 사용 |
| `TourApiRequestError` | 요청 파라미터 오류로 기록하고 개발자 로그에 endpoint/params 요약 저장 |
| `TourApiServerError` | upstream 장애로 기록하고 사용자에게 일시 오류 표시 |
| `TourApiParseError` | schema drift 가능성으로 기록하고 raw payload 보존 |
| `TourApiNoDataError` | 상세 조회 대상 없음으로 처리 |

인증키 원문은 로그, 예외 메시지, 문서, 테스트 fixture에 남기지 않는다.

## 향후 공개 endpoint 후보

아래 endpoint는 아직 구현 전이다.

- `GET /places/{place_id}/kto-nearby`: 저장 장소 좌표 기반 `locationBasedList2`
- `GET /places/{place_id}/kto-area`: 저장 장소 행정구역 기반 `areaBasedList2`
- `GET /places/{place_id}/kto-related`: `TarRlteTarService1` 기반 연관 관광지 후보
- `POST /trips/{trip_id}/places/from-kto`: 사용자가 선택한 KTO 후보를 TripMate 여행지로 저장

구현 시 `docs/data-sources.md`의 KTO 저장 정책과 이 문서를 함께 갱신한다.
