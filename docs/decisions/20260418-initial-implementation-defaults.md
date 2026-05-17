# ADR: 초기 인증, 지도, Telegram, Gemini 비밀값 구현 선택

## 상태

Accepted

## 배경

Phase 1 이후 구현을 시작하려면 인증 방식, Kakao 지도 도입 순서, Telegram bot token 보관 방식, Gemini API 키 소유 주체를 먼저 좁혀야 한다. 사용자 요청에 따라 보수적인 추천안을 기본값으로 확정하되, Gemini는 사용자 개인 키 입력 구조로 확정한다.

## 결정

- 인증은 httpOnly cookie 기반 서버 세션으로 시작한다.
- 세션 cookie에는 난수 기반 opaque token만 저장한다.
- 서버 DB에는 세션 토큰 원문이 아니라 해시, 사용자 ID, 만료 시각, 폐기 시각을 저장한다.
- Kakao 지도는 JavaScript SDK 기반 지도 UI와 지도 클릭 장소 초안을 먼저 구현한다.
- Kakao Local API 검색 client/source는 `docs/data-sources.md`의 캐시/저장 정책과 `docs/api/places.md` 계약을 먼저 확정한 뒤 구현한다.
- Telegram bot token 실제 값은 환경변수에 저장한다.
- DB의 `telegram_bot_token_ref`에는 환경변수 이름 또는 내부 참조값만 저장한다.
- Gemini Deep Research는 사용자 개인 API 키 입력 구조로 설계한다.
- Gemini API 키 원문은 일반 DB 테이블과 로그에 저장하지 않는다.
- 사용자/실행 결과 테이블에는 secret reference, masked fingerprint, 검증 상태만 저장한다.
- 실제 키는 secret store 또는 암호화된 비밀 저장 계층을 통해서만 읽는다.

## 대안

- access/refresh token 조합: 외부 API 클라이언트나 네이티브 앱에는 유리하지만, 현재 웹앱 MVP에는 저장/회전/탈취 대응 복잡도가 더 크다.
- Kakao 지도 UI와 Local API client/source 동시 구현: 사용자 흐름을 빨리 완성할 수 있지만, provider 저장 정책과 cache key가 흐려질 위험이 있다.
- 서버 운영 Gemini 키: 사용자별 비용/쿼터/철회 추적이 약해지고, 개인 유료 계정 사용 전제와 맞지 않는다.
- Telegram secret manager 즉시 도입: 운영 보안성은 좋지만 ODROID 초기 배포와 로컬 개발 복잡도가 커진다.

## 결과/영향

- 인증 구현은 same-origin 웹앱에 맞춰 단순하고 안전하게 시작한다.
- 장소 검색 구현 전에 데이터 소스 정책과 API 계약을 먼저 고정한다.
- Telegram 비밀값은 DB와 로그에 남기지 않는다.
- Gemini 비밀값은 사용자별로 입력, 검증, 교체, 삭제할 수 있어야 한다.
- Gemini 실행 기록은 추적성을 위해 남기되, API 키 원문은 남기지 않는다.

## 후속 작업

- `docs/api/auth.md`에 cookie 이름, 만료, 오류 응답, 로그아웃 동작을 문서화한다.
- `docs/api/places.md`에 지도 클릭 장소 초안과 검색 후보 스키마를 분리해 문서화한다.
- `docs/runbooks/telegram.md`에 필요한 환경변수와 검증 절차를 문서화한다.
- `docs/api/gemini-research.md`에 사용자 키 등록/검증/삭제와 실행 결과 schema를 문서화한다.
- 연동 상세가 바뀌면 `docs/integrations/telegram.md`와 `docs/integrations/gemini.md`를 함께 갱신한다.
