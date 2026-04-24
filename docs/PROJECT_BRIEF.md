# TripMate Project Brief

## 한 줄 설명

TripMate는 대한민국 국내 여행을 일정, 장소, 지도, 지역 데이터, Telegram 알림으로 관리하는 로그인 기반 여행 계획 웹앱이다.

## 1차 사용자

- 국내 주말/단기 여행을 계획하는 개인 또는 소규모 그룹
- 여러 후보 장소를 지도 위에서 비교하고 날짜별 동선으로 정리하려는 사용자
- 여행 전 날씨, 유가, 지역 정보를 캐시된 데이터 기반으로 확인하고 싶은 사용자
- Telegram으로 여행별 알림을 받고 싶은 사용자

## MVP 범위

1. 이메일 기반 회원가입과 httpOnly cookie 서버 세션 로그인
2. 여행 생성, 수정, 삭제
3. 날짜별 일정 관리
4. Kakao 지도 클릭으로 장소 초안 추가
5. Kakao Local API 검색 adapter 기반 장소 검색 추가
6. 여행별 Telegram 알림 대상 최대 3개 저장
7. 저장된 지역 데이터 기반 날씨/유가 요약의 기반 구조

## 명확히 제외하는 것

- 비회원 모드
- 해외 여행 데이터 모델링
- 항공권/숙박 예약 대행
- provider 원문 장소 데이터의 무제한 장기 저장
- 외부 날씨/유가 API를 화면 요청마다 직접 호출하는 구조
- Telegram bot token의 DB 평문 저장
- 자동 주기 실행되는 Gemini Deep Research

## 나중에 확장할 수 있는 것

- 예산/물품 관리
- 동행자 투표와 댓글
- 사용자 정의 마커
- Gemini 기반 장소 보강 조사
- read-only 공유 링크
- ODROID M1S 운영 배포 자동화

## 확정된 초기 구현 선택

- 인증은 httpOnly cookie 기반 서버 세션으로 시작한다.
- Kakao 지도는 JavaScript SDK 기반 지도 UI와 지도 클릭 장소 초안을 먼저 구현하고, Kakao Local API 검색 adapter는 API/cache 계약을 문서화한 뒤 붙인다.
- Telegram bot token 실제 값은 환경변수에 두고, DB에는 `telegram_bot_token_ref`만 저장한다.
- 행정구역 원천 데이터는 V-WORLD `법정구역정보` SHP를 사용한다.
- 행정구역 raw 레이어는 원본 EPSG:5186 geometry를 그대로 보존하고, serving 레이어는 지도/API 조회용 EPSG:4326 변환본을 둔다.
- 행정구역 point-in-polygon 판정은 PostGIS에서 수행하며, 웹 지도 출력과 API 응답은 EPSG:4326을 사용한다.
- Gemini Deep Research는 사용자 개인 API 키 입력 구조로 설계한다. API 키 원문은 일반 DB에 평문 저장하지 않고 secret reference와 masked fingerprint만 도메인 테이블에 남긴다.
