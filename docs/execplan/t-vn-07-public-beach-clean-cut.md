# T-VN-07 공개 해수욕장 소비자 clean-cut 실행 계획

## 목표

kor-travel-map T-VN-07에서 제거한 `include_quality`·`include_forecast` no-op query를
PinVi의 공개 API와 Python/TypeScript client에서도 제거하고, 같은 query drift를 계약
테스트가 즉시 검출하게 한다.

## 변경 범위

- PinVi `/public/beaches` 목록·상세 route의 두 query 제거
- `KorTravelMapClient`와 `@pinvi/api-client`의 동일 옵션 제거
- vendored OpenAPI의 beach operation을 kor-travel-map `integration/t-vn`과 동기화
- 공개 API·HTTP client·OpenAPI query shape 회귀 테스트 보강
- 양 저장소의 공개 API 문서와 진행 기록 동기화

## 검증과 완료 조건

1. 전문 리뷰어 1명이 양 저장소 수정본을 승인한다.
2. 관련 API unit/integration, Ruff, mypy와 API client typecheck가 통과한다.
3. PinVi PR은 `main`, kor-travel-map 문서 PR은 `integration/t-vn`에 CI green으로
   머지한다.
4. 두 저장소에서 `include_quality`·`include_forecast`가 이력 문서와 응답 필드명을
   제외한 활성 계약·호출 코드에 남지 않는다.

## 결과

- 전문 리뷰어 1명 승인
- 관련 Python 테스트 31개 통과
- Ruff lint/format, mypy 188개 소스, API client typecheck, JSON 검증 통과
