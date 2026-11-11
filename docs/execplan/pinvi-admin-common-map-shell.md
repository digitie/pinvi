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
