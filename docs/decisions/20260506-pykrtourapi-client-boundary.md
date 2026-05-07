# pykrtourapi 직접 사용 경계

- 상태: 승인
- 날짜: 2026-05-06

## 배경

TripMate는 KTO `KorService2`와 `TarRlteTarService1`를 사용할 계획이지만, 저장소 안에는 아직 TourAPI 호출 코드가 없고 정책 문서만 존재한다. 사용자는 `pykrtourapi`를 활용하되 TripMate backend에 adapter류 래퍼를 두지 않고, 가능한 구현 책임을 `pykrtourapi` 쪽에 두기를 원했다.

## 결정

- `apps/api`는 `pykrtourapi`를 git commit으로 고정 의존성에 추가한다.
- TripMate에는 `KrTourApiClient`와 `TourApiHubClient` 생성에 필요한 설정 경계만 둔다.
- TourAPI endpoint 호출, 파라미터 검증, pagination 응답 정규화, typed exception, 좌표 순서 검증은 `pykrtourapi`의 책임으로 둔다.
- TripMate 쪽에는 `KtoAdapter`, `TourApiGateway`, provider별 DTO 변환기 같은 중간 래퍼를 만들지 않는다.
- 저장소 내부 로직은 필요할 때 `pykrtourapi`의 Pydantic model과 `raw` payload를 직접 받아 raw/serving/snapshot 저장 단계에 넘긴다.
- `TarRlteTarService1`는 `pykrtourapi`의 typed `related_tour` helper를 직접 사용한다. 새 TourAPI 서비스에서 typed model이 부족하면 TripMate에서 별도 정규화 래퍼를 만들지 않고 필요한 model과 helper를 `pykrtourapi`에 upstream한다.

## 대안

- TripMate backend adapter를 새로 만들기: 기존 OpiNet adapter와 비슷한 구조를 재사용할 수 있지만, TourAPI 파라미터/응답 처리 책임이 앱 저장소로 다시 들어온다.
- raw HTTP 호출을 직접 구현하기: 가장 단순해 보이나 오류 처리, 좌표 순서, `items.item` 단건/list 차이, `resultCode` 처리 중복이 생긴다.

## 결과/영향

- `TRIPMATE_KTO_SERVICE_KEY`, `TRIPMATE_KTO_MOBILE_APP`, `TRIPMATE_KTO_MOBILE_OS`, `TRIPMATE_KTO_TIMEOUT_SECONDS`, `TRIPMATE_KTO_MAX_RETRIES` 설정이 추가됐다.
- 현재 `pykrtourapi` 고정 commit은 `dc855cb177c9a7842400957f5574760b85e71347`이다. 이 버전은 응답 객체를 Pydantic model로 제공하고 `Page.context`, typed `related_tour`, pagination helper, exception metadata, `cpyrhtDivCd`/HTML 표시 helper를 포함한다.
- KTO 관련 기능 구현 시 pykrtourapi에서 부족한 기능을 먼저 보강한다.
- pykrtourapi의 GPL-3.0-or-later 라이선스 영향은 배포 정책 확정 전에 별도 확인한다.

## 후속 작업

- TripMate 화면 구현 시 `copyright_display_info()`의 label/notice를 국내 서비스 문구로 어떻게 표시할지 확정한다.
- `clean_tourapi_html()`은 보안 sanitizer가 아니므로, HTML 렌더링 화면의 sanitizer 정책을 별도로 결정한다.
- KTO 실제 계정 기준 호출 한도와 retry/cache 정책을 운영 runbook에 반영한다.
