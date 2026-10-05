# PinVi/Common Dagster 최종 검증 (2026-10-05)

최종 제품 후보 PinVi `46305d44dab08ff73b3033443199501fb695eb80`, Common UI
`e28559803c1ec1134ef7ba7736b9acf4cadb9a32`(dev.6), Python
`73e3ff8b9398e533806d2d1a8435292570169de3`. 이후 커밋은 검증 기록·가이드만 갱신한다.
PR: [PinVi #575](https://github.com/digitie/pinvi/pull/575),
[Common #27](https://github.com/digitie/kor-travel-common/pull/27).

## 독립 적대 리뷰와 수정

복구/DB/메모리와 UI/인증/API 계약 두 관점에서 base→제품 전체를 독립 검토했다.
원본 BLOCK와 후속 PASS를 [manifest](manifest.json)에 연결한 JSON에 UTF-8 원문과 SHA256으로
보존한다. reviewer에게 peer 원문을 제공하지 않았다. 각 reviewer의 직접 실행 범위는 원문을 따른다.

- malformed run status가 list/dict일 때 TypeError 전파: 문자열 검사·음성 회귀로 FIXED.
- 압축 GraphQL 응답의 사전 대량 할당: identity 요청과 비identity encoding 거부로 FIXED.
- 활성 실행 누락·상한 결과의 거짓 정상: 별도 active query/1000건 degraded/nullable counts로 FIXED.
- 공통 runtime cap의 미확인·heuristic 혼동과 nullable schedule 타입 migration: Common dev.4와 가이드로 FIXED.
- live 메뉴·envelope·검색·필수 schedule 링크/URL 및 CI selector 불일치: 실제 공통 DOM/API 경로로 FIXED.
- Dagster gRPC 자동 탐색의 `_base_defs`/`defs` 중복(P1): 임시 객체 제거 후 실제 autodiscovery·CLI 회귀로 FIXED.
  두 reviewer가 이전 실패와 후보 1 defs/9 jobs/7 schedules/6 sensors를 독립 재현했다.
- dev.5의 공통 기본 `showRunDetails=false`에서 grid min-content로 페이지 전체가 넘치는 P2: dev.6의 root grid child min-width0와 내부 표 스크롤로 FIXED. 기본/상세 두 모드의 실제 Chromium/Firefox 24조합을 재검증했다.
미해결 신규 P0/P1/P2는 없다. 변경 전 BLOCK/조건부 보고서는 수정하지 않았다.

## 실제 N150 UI

별도 소유 컨테이너의 network namespace 안에 고정 5432/12801/12802/12803/12805 포트를 사용했다.
host port를 publish하지 않았고 운영 서비스·DB·daemon은 사용하지 않았다. PostgreSQL16/PostGIS의
빈 fixture에 공식 Alembic `upgrade head`(`20260917_0102`)를 적용하고 예시 역할 계정만 넣었다.
실제 후보 API와 code location, Common Python의 `__file__`이 마운트 후보 경로임을 검증했다.
Dagster1.13.24 실제 읽기 전용 outbox job 실행도 성공했다. daemon/provider 정기 실행은 하지 않았다.

N150에서 immutable Playwright image·Node22.22.2·npm11.19.1 `npm ci`·production Next build를
사용했다. dev.4의 test URL/ETL 로딩 수정 때만 동일 Web app/vendor/lock 객체의 build를 재사용했고,
dev.5/dev.6 artifact 변경에서는 각각 fresh npm ci와 production build를 다시 실행했다. 테스트는 `playwright.common-dagster-live.config.ts`의
Chromium·Firefox 각 2건, 최종 dev.6 전체 **4 PASS (1.0분)**다. dev.4/dev.5의 앞선 성공은 별도 로그로 보존한다. API/GraphQL mock은 사용하지 않았다.

- 잘못된 이메일 focus/password clearing, 실제 일반 사용자 logout→401, CPO→404, operator→200.
- 최신 종료 35건 밖의 오래된 활성 run이 포함되고 foreign location run은 제외됨.
- 실제 메뉴·실행 검색/상세·필수 스케줄 링크·repository@location encoding.
- 소유 Dagster webserver 실제 stop→중단 표시/마지막 정상 snapshot 유지→start→정상 회복.
- 390px 모바일 가로 overflow 없음. Chromium/Firefox desktop/mobile 캡처를 확인했다.

[live manifest](live-manifest.json), [최종 실제 결과](browser-dev6.log.json), [migration](migration.log.json),
[desktop](chromium-desktop-dev6.png), [mobile](chromium-mobile-dev6.png)에 공개 가능한 근거를 보존한다.
비밀 env/인증 trace는 커밋하지 않는다. 최초 fixture의 `.test` 이메일 거절, 잘못된 `/v1` URL,
누락 테이블, 이미지 cwd가 기존 코드를 import한 실패는 수정 후 재실행했으며 성공으로 집계하지 않는다.
활성 run은 persistent storage fixture로 만들었다. 실제 worker kill/monitor 및 tick 생성 검증은 아니다.

[추가 layout/keyboard 실증](mobile-readability-dev6.json)은 실제 설치된 공통 컴포넌트의 SSR 마크업과 CSS로
기본/상세 ×320/390/640/641/768/1280 ×Chromium/Firefox의 **24조합**을 검사했다. 이 fixture는 CSS layout 검증이며
React 이벤트/API live와 구분한다. 실제 PinVi React UI의 390px keyboard 검사 **2건**도 통과했다.
문서폭390/표영역322/표내용640, 작업명 button 약129~133px×45px로 읽기 가능하며 표 focus 후 ArrowRight로
scrollLeft가 증가했다. [실행 probe 원문](mobile-readability-probe-dev6.json)에 원문/SHA를 보존한다. JSON에는 후보·artifact·CSS SHA를 연결했다.

## 회귀와 한계

- ETL ruff/pytest **67 PASS**. 실제 자동 탐색 전 실패→수정 후 성공 회귀 포함.
- API 전체 **1508 PASS/1 FAIL**: 실패는 기존 Map snapshot을 현 로컬 Map checkout과 비교하는 freshness
  검사다. base와 후보 vendor bytes가 동일함을 확인했다. 필수 CI contract-pin-consistency는 PASS다.
- API focused probe/OpenAPI **28 PASS**, ruff/format·strict mypy **247 files PASS**.
- Web 전체 **172 PASS**, type-check·production build PASS, lint 오류0/기존 경고4.
- Common UI **50 PASS**·check/build/tarball smoke, 문서·도구 테스트 PASS.
- 합성 KASI5000행(행8KiB)의 tracemalloc peak **1,838,875 bytes**. Python allocation이며 운영 RSS가 아니다.

필수 CI는 최종 문서 커밋 후 ready 전환해 Aggregate gate까지 확인한다. mobile-doctor는 별도의
informational 실패로 남으며 필수 mobile lint/typecheck와 구분한다. 운영 shared daemon 설정/배포,
worker kill·실측 RSS·provider 외부 호출은 NOT_RUN이다. notification 전달 보장과 trip-day의 기존
부분 실패 metadata 의미는 변경하지 않았다. 소비자 YAML만으로 shared Manager 정책이 바뀌지는 않는다.

문서 증거의 원문 해시(`original_sha256`)와 JSON 파일 해시(`file_sha256`)를 구분한 최종 metadata 검토도 [별도 원문 manifest](metadata-manifest.json)에 보존했다. J-DOC-P2-01은 FIXED이며 제품 리뷰 건수에는 추가하지 않는다.
