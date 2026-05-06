# KTO TourAPI 연동 계약

## 현재 상태

TripMate API에는 아직 KTO 후보 조회용 공개 HTTP endpoint가 없다. 현재 제공하는 것은 backend 내부에서 사용할 KTO client 생성 경계다.

- 코드 위치: `apps/api/app/core/kto.py`
- 국문 관광정보 client: `build_kto_kor_client()`
- TourAPI Hub client: `build_kto_hub_client()`
- 사용 라이브러리: `pykrtourapi`
- 고정 commit: `6fd0601ad01d6cdef59ca3d46cb1df3b6b697e59`
- 최신 확인 내용: `8d8416d4..6fd0601a` 구간은 pykrtourapi 런타임 API 변경 없이 사용자 가이드, Pydantic 모델 문서, troubleshooting 문서를 확장한 업데이트다.

TripMate backend에는 KTO 전용 adapter 또는 gateway 래퍼를 만들지 않는다. `pykrtourapi`의 `KrTourApiClient`, `TourApiHubClient`, Pydantic 응답 모델, `raw` payload를 직접 사용한다.

## 설정

환경변수 prefix는 `TRIPMATE_`다.

| 설정 | 필수 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `TRIPMATE_KTO_SERVICE_KEY` | 예 | 없음 | 공공데이터포털 TourAPI decoding 인증키 |
| `TRIPMATE_KTO_MOBILE_APP` | 아니오 | `TripMate` | TourAPI 공통 `MobileApp` 값 |
| `TRIPMATE_KTO_MOBILE_OS` | 아니오 | `WEB` | TourAPI 공통 `MobileOS` 값 |
| `TRIPMATE_KTO_TIMEOUT_SECONDS` | 아니오 | `10.0` | 요청 timeout 초 |
| `TRIPMATE_KTO_MAX_RETRIES` | 아니오 | `2` | pykrtourapi HTTP retry 횟수 |

`TRIPMATE_KTO_SERVICE_KEY`가 없으면 `TourApiAuthError`를 발생시킨다. `pykrtourapi`의 일반 환경변수 fallback에 의존하지 않고, TripMate prefix 설정만 사용한다.

## 내부 사용 예시

```python
from app.core.kto import build_kto_kor_client, build_kto_hub_client
from pykrtourapi import ContentType, Wgs84Coordinate

kor_client = build_kto_kor_client()
page = kor_client.location_based_list(
    coordinate=Wgs84Coordinate(longitude=126.9769, latitude=37.5796),
    radius=15000,
    content_type_id=ContentType.TOURIST_ATTRACTION,
)

related_client = build_kto_hub_client().service("related_tour")
related_page = related_client.call(
    "areaBasedList1",
    params={"baseYm": "202604", "areaCd": "1", "signguCd": "23"},
)
```

## 응답 처리 기준

- `pykrtourapi` 응답 객체는 Pydantic model이다.
- serving 저장 후보 필드는 `model_dump()`로 얻을 수 있다.
- JSON API 응답이나 캐시 payload로 직렬화할 때는 날짜 처리를 위해 `model_dump(mode="json")` 또는 `model_dump_json()`을 우선 사용한다.
- provider 원문 보존은 `Page.raw`와 item별 `raw`를 사용한다.
- `mapX`는 경도, `mapY`는 위도다. TripMate 저장 시 `lng`, `lat`으로 분리한다.
- `areaCode`, `sigunguCode`, `lDongRegnCd`, `lDongSignguCd`는 TourAPI 조회용 코드다. TripMate `legal_dong_code`로 취급하지 않는다.

## 오류 처리 기준

`pykrtourapi`의 typed exception을 그대로 사용한다.

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
