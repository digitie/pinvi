# PinVi Admin 공통 UI·map 셸 정렬

사용자 요청(2026-11-11): kor-travel-common 적용과 map 기준 look and feel 정렬, PinVi 색상 유지.

## 기준과 범위

PinVi 기준 cc3489a0, map 기준 32668d003. 이미 vendored common UI dev.9의 LoginForm·AppMenu와 tokens를 소비한다. 새 패키지 복사 대신 관리자 subtree에서 누락된 의미 토큰을 PinVi 팔레트에 연결한다. 기존 메뉴30개·경로·권한·document navigation은 유지한다. map처럼 256px/64px rail, wordmark, 메뉴 자체 스크롤·그룹 라벨·하단 사용자/로그아웃, 본문 헤더 계층을 사용한다. 모바일 메뉴는 공통 strip과44px 터치 타깃을 유지한다.

## 수용 기준

- 공통 LoginForm/AppMenu 사용, 기본 녹색 테마 누출 없음.
- PinVi Rausch/CTA·흰색 표면·회색 선/잉크 유지, 사용자 표면의 전역 색상 변경 없음.
  -30개 메뉴의 경로·순서·활성 항목 및 권한 가드 보존.
- 접힘은 PC에만 적용, 모바일320/375/414/768px 및 PC에서 overflow·키보드·접힘·로그아웃 실패/재시도 검증.
- Linux typecheck/lint/단위/build, N150 브라우저 검증. 미실행 검증은 명시한다.

## 검증 기록

진행 중. CodeGraph MCP는 WSL SQLite 잠금으로 실패하여 Linux native codegraph impact/context로 AdminGuard→AdminLayout 영향 범위를 확인했다. 원 trunk와 손상된 기존 Codex 폴더는 보존하고 /home/digitie/pinvi-codex 고정 worktree에서 작업한다.

## 독립 리뷰 기준선

공통 manifest: PinVi cc3489a0 → 후보7b874bbae02c102aff6420e00fe3b1c36e727d98(tree4259b5b475ef5ba336bba07b0b2f7889672f5ee3),8개 파일 전체, map32668d003 기준. 두 전문 reviewer는 Git object-only로 독립 검토했다. 원본은 [UI](../reviews/2026-11-11-pinvi-admin-common-ui.md)·[인증](../reviews/2026-11-11-pinvi-admin-common-auth.md)에 보존한다.

두 reviewer가 각각 UI-01/AUTH-01 P2로 모바일 로그아웃36px를 지적했다. 수정은 모바일44px·PC36px 분리이며, e2e의 버튼 높이·키보드 메뉴 끝 스크롤·skip focus·로그아웃 실패/재시도 검사도 보강했다. 후속 immutable commit의 독립 재검토와 N150 실측 전 완료로 표시하지 않는다.

## 최종 검증 결과

- 최종 코드 후보:8ee56763b66f261f18e1c2ebcfbed4cf605bbf7f(tree d274634a770c9ebe34480e33e30b8751f5e69cdc). 최초 기준선과 후속74f894ba의 제품 변경은 모바일 버튼44px 수정이며, 최종 delta는 Next route announcer와 겹친 테스트 alert 선택 범위 한정뿐이다.
- Linux Node22.22.2: web typecheck·전체 lint·production webpack build, 관련 단위3파일13개, 변경 소스 Prettier·diff 공백 검사 성공.
- N150 공식 Playwright Docker1.64.1: 최종 Chromium1개 시나리오 성공(6.1초, 웹 빌드 포함1.2분). 첫 실행은 새 의존 설치, 최종 실행은 동일 lock 의존 volume 재사용 후 fresh 앱 빌드다. 메뉴30개·활성 경로·색상매핑·axe WCAG A/AA(사이드바)·키보드 끝항목/스크롤·skip focus·접힘 저장/새로고침·320/375/414/768/1024/1440px overflow·모바일44px·로그아웃500후204재시도·공통 로그인 화면을 확인했다.
- N150 실제 검증 소스4파일 SHA256은 [원본](../reviews/2026-11-11-pinvi-admin-common-source.json)에 기록하며 로컬 immutable 후보와 일치한다.
- [후속UI](../reviews/2026-11-11-pinvi-admin-common-post-ui.md)·[후속인증](../reviews/2026-11-11-pinvi-admin-common-post-auth.md)와 [최종UI](../reviews/2026-11-11-pinvi-admin-common-final-ui.md)·[최종인증](../reviews/2026-11-11-pinvi-admin-common-final-auth.md)가 코드 PASS/APPROVE다. UI-01/AUTH-01은 FIXED, 신규/잔여 finding0. 원본의 실행 gate PENDING은 이후 위 실제 실행 성공으로 닫았다.
- 실패 이력: 생성된 public/maplibre worker의 root 소유권 때문에 첫 재동기화가 exit23, 해당 재생성 파일을 제외하고 재동기화했다. 브라우저 두 번째 실행은 Next route-announcer도 alert로 선택하는 테스트 strict-mode 오류였다. sidebar 안 오류 alert를 지정하고 세 번째 실행에서 통과했다. 제품 오류를 숨기거나 assertion을 제거하지 않았다.
- 로컬 스크린샷/로그: common 작업 폴더의 test-results/pinvi-admin-common/ 아래 PC·접힘·모바일·로그인4장과 실행 로그. 화면 데이터는 모의 API이며 운영 데이터/인증 검증으로 세지 않는다.
- NOT_RUN: 실제 운영 인증·세션 서버 연동/배포, 전체 서비스 E2E. 변경은 관리자 UI이며 제품 서버나 다른 저장소는 수정하지 않았다. GitHub CI는 PR 생성 뒤 확인한다.
