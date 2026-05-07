# ADR: MVP 범위 정리와 보류 항목

## 상태

Accepted

## 배경

초기 brief에는 일반 여행 앱, 협업, 공유, 국제 여행 가능성을 암시하는 내용이 있었다. 현재 제품 지침은 대한민국 전용, 로그인 필수, Kakao 지도, 지역 데이터 캐시, Telegram 알림을 우선한다.

## 결정

MVP에서 다음을 명확히 포함한다.

- 이메일 기반 인증
- 여행/날짜/장소 CRUD
- Kakao 지도 기반 장소 입력
- provider 원문과 내부 정규화 데이터 분리
- 지역 데이터 캐시 기반 날씨/유가 요약
- 여행별 Telegram 알림 대상 최대 3개

MVP에서 다음을 제외한다.

- 비회원 모드
- 해외 여행
- 항공권/숙박 예약 대행
- provider 원문 전체 장기 저장
- 화면 요청마다 외부 날씨/유가 API를 직접 호출하는 구조
- 자동 주기 실행되는 Gemini Deep Research

## 후속 결정으로 확정된 부분

- 인증 세션 방식은 httpOnly cookie 기반 서버 세션으로 시작한다.
- Telegram bot token은 환경변수에 실제 값을 두고 DB에는 secret reference만 저장한다.
- Kakao 지도는 JavaScript SDK 지도 UI와 지도 클릭 입력을 먼저 구현하고, Kakao Local API 검색 adapter는 API/cache 계약 이후 붙인다.
- 행정구역 원천 데이터는 V-WORLD `법정구역정보` SHP를 사용하고 raw EPSG:5179, serving EPSG:4326을 분리한다.
- Gemini API 키는 사용자 개인 키 입력 구조로 설계한다.

## 결과

불필요하게 큰 범위를 줄이고, Phase 1 이후 구현에서 제품 판단이 흔들릴 가능성을 줄인다.
