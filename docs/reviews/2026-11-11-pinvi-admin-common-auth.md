# PinVi Admin 독립 적대적 리뷰 — 인증·상태·계약

- 실행 ID: pinvi-auth-review-20261111T0422Z
- 리뷰어 역할: 인증 가드, 로그아웃 비동기 상태, Query 캐시, 라우팅, 단위 테스트 계약
- 시작 시각: 2026-11-11T04:22Z 부근(첫 도구 실행, 정확한 초 미수집)
- 종료 시각: 2026-11-11T04:25:52Z
- 기준 base: cc3489a0bb33c184a36fa38a65fa59f937bbedc0
- immutable candidate: 7b874bbae02c102aff6420e00fe3b1c36e727d98
- candidate tree: 4259b5b475ef5ba336bba07b0b2f7889672f5ee3
- 시작 HEAD: candidate와 일치. git status --short 출력 없음.
- 중간 종료 점검(04:24:42Z): HEAD/tree 일치, git status --short 출력 없음.
- 다른 리뷰어 결과는 열람하지 않았다. 저장소 파일을 수정하지 않았다.
- 소스는 git show/git diff/git grep의 고정 object에서만 열람했다.

## 범위

manifest 8파일 전체 diff를 읽었다: apps/web/app/(admin)/admin/layout.tsx, apps/web/app/globals.css, apps/web/tests/adminCommonShell.test.tsx, apps/web/e2e/admin-common-shell.e2e.ts, docs/execplan/pinvi-admin-common-map-shell.md, docs/journal.md, docs/resume.md, docs/tasks.md.

관련 고정 object의 AdminQueryProvider, DocumentNavLink, 기존 LogoutButton, admin login, api-client auth endpoint와 client, route-group admin scope도 확인했다.

## finding

### AUTH-01 / P2 / OPEN — 모바일 로그아웃 타깃이 수용 기준 44px보다 작다

- 위치: apps/web/app/(admin)/admin/layout.tsx:289, apps/web/e2e/admin-common-shell.e2e.ts:67.
- 증거: 새 로그아웃 버튼은 min-h-9(36px)이며 모바일에서도 더 큰 높이 또는 세로 padding을 주지 않는다. 자체 텍스트/아이콘 높이는 36px보다 작아서 일반 루트 글꼴 크기에서 36px 타깃이 된다.
- 공격/실패 시나리오: 320/375/414/768px 화면에서 로그아웃하려는 사용자는 44px보다 작은 버튼을 눌러야 한다. 실행 계획은 모바일 44px 터치 타깃 유지를 수용 기준으로 둔다. 테스트는 여행 nav 링크 높이만 검사하므로 새 footer 버튼 회귀를 포착하지 못한다.
- 영향: 실행 계획의 모바일 조작 계약 미달. 인증 우회/비밀 노출 결함은 아니다.
- 최소 수정: 모바일 min-h-11, 필요하면 lg:min-h-9로 PC 밀도 유지. 각 모바일 폭에서 실제 logout button bounding box 높이가 44px 이상인지 단언한다.
- 주의: globals.css의 기존 주석은 관리자 일반 컨트롤 36px 예외를 설명한다. 본 finding은 이번 실행 계획에 별도로 명시한 모바일 44px 기준을 새 셸 logout 동작에도 적용하는 해석이다. 작성자가 해당 기준을 메뉴 링크에만 한정하려면 계획에 범위를 명시하고 UI 책임자가 이를 판단해야 한다.

## 점검한 실패 시나리오

1. 로그인 경로에서 /auth/me 무한 redirect: isLoginPage와 enabled false가 보존되고 메타 상태 전 return으로 메뉴/가드를 노출하지 않는다.
2. 비관리자/권한 조회 실패 상태에서 자식 노출: 기존 ADMIN_ROLES와 렌더 분기가 보존됐다. user 역할만 가진 경우 null과 forbidden redirect다. 401/404는 login, 기타 오류는 재시도 UI다.
3. 메뉴 경로 누락/활성 경로 변화/client navigation 전환: NAV_GROUPS 30개 데이터와 exact 정책은 diff에서 변하지 않았다. CommonDocumentLink는 실제 anchor이며 기존 document navigation을 유지한다.
4. 로그아웃 응답 전 이동 또는 캐시 삭제: await logout 뒤 clear와 replace 순서다. 실패 시 clear/replace가 호출되지 않고 일반화된 오류와 재시도 상태로 돌아간다.
5. 반복 클릭: pending state와 disabled button, loggingOut early return이 있다. 실제 지연 응답 중 연속 클릭 실행은 이번 리뷰에서 미실행이다.
6. 캐시 잔류: QueryClient는 AdminQueryProvider 소유이며 성공 시 해당 client.clear를 호출한다. 로그인 폼도 기존에 동일 client.clear를 사용한다. 신규 테스트는 clear 호출이나 캐시 비움을 직접 단언하지 않는다(보강 후보이며 추가 기능 결함으로 판정하지 않음).
7. 내부 오류 원문 누출: catch는 상수 한국어 문자열을 노출하고 테스트도 내부 오류 원문 비노출을 단언한다.
8. 사용자 표면 전파: 추가 의미 토큰은 기존 data-pv-surface=admin scope 안에 있다. 공통 메뉴 CSS는 pinvi-common-menu scope다.
9. evidence 과장: 추적 문서와 실행 계획은 검증 중이라고 표시하므로 미실행 N150 검증을 PASS로 선언하지 않았다.

## 직접 수행한 검증과 미검증

- PASS: git diff --check base candidate (exit 0).
- PASS: 시작과 중간 점검 HEAD/tree 일치 및 clean status 확인. 종료에는 HEAD/tree가 그대로이고 작성자의 layout.tsx와 e2e 수정 두 건이 있었다. 이 dirty 파일은 열람하지 않았고 본 리뷰는 고정 candidate만 대상으로 한다.
- STATIC_REVIEW: 위 실패 시나리오 1~9. 실제 브라우저 재현과 구분한다.
- NOT_RUN(독립 리뷰는 object-only 정적 검토): typecheck/lint/build/Vitest. 작성자의 통과 보고를 독립 실행 PASS로 집계하지 않았다.
- NOT_RUN(N150 browser gate는 작성자 진행 중): Playwright/axe/모바일 치수 실측/실제 로그아웃/쿠키 제거/후속 관리자 접근. 실행 계획 완료 전 외부 gate가 남아 있다.

## 판정

REQUEST_CHANGES — P0/P1 신규 결함은 발견하지 않았다. AUTH-01을 수정하거나 명시적 계약 해석으로 disposition하고, N150 gate를 완료해야 최종 수용할 수 있다. 인증·캐시·라우팅 영역에서는 그 밖의 재현 가능한 신규 기능 결함을 발견하지 않았다.
