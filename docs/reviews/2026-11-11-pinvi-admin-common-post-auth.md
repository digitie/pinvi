# PinVi Admin 후속 독립 리뷰 — 인증·상태·계약

- 실행 ID: pinvi-auth-post-review-20261111T042721Z
- 시작: 2026-11-11T04:27:21Z
- 종료 점검: 2026-11-11T04:27:35Z
- 이전 candidate/base: 7b874bbae02c102aff6420e00fe3b1c36e727d98
- 후속 immutable candidate: 74f894baec561c78474348f450d6ccdb1f9467d0
- tree: 3e400f3a67e0725299a917efb98100637c77fef6
- 시작/종료 HEAD와 tree가 위 값에 일치하고 git status --short 출력 없음.
- 소스 변경 없음. 고정 Git object-only 검토. 상대 리뷰 원본 파일은 열람하지 않았다.

## 범위

이전 공통 manifest 8파일에 대한 후속 delta 중 layout.tsx, globals.css, admin-common-shell.e2e.ts, 실행 계획 변경 전체를 독립 검토했다. 신규 두 raw review 보존 파일은 diff 이름만 확인하고 상대 원본 내용은 열람하지 않았다. 실행 계획에는 리뷰 이력 요약이 포함되어 있으나 본 판정은 내 원 finding과 수정 코드/검증 계약에 근거한다.

## finding disposition

AUTH-01 / P2 / FIXED: layout.tsx:289가 min-h-11 lg:min-h-9로 바뀌어 1024px 미만에서44px, PC에서36px 최소 높이를 분리한다. admin-common-shell.e2e.ts:75~79에서320/375/414/768px마다 로그아웃 버튼 min-height44px를 검사한다. 기존 scope나 로그인 가드·비동기 상태 처리는 바꾸지 않는다. 실제 computed style 통과 여부는 N150 실행 gate로 분리한다.

새 P0/P1/P2/P3 finding 없음.

## 회귀 검토

- 로그아웃 성공/실패 분기와 await → cache clear → login replace 순서는 변경하지 않았다.
- e2e의 최초500 오류 응답과 두 번째204 응답이 기존 ApiClient requestNoContent 경로와 호환된다. 실패 뒤 현재 trips 경로 유지, 성공 뒤 login 폼 노출을 검증한다. 이 테스트는 모킹 기반 셸 동작 검증이며 실제 서버 쿠키 종료 증거는 아니다.
- 메뉴28번째 인덱스에서 실제 Tab으로 마지막 메뉴에 도달한 뒤 viewport 포함을 검사하고, skip link Enter 뒤 main focus를 검사한다. 메뉴 스크롤과 skip 동작의 정적 테스트 계약은 적절하다.
- 기존30개 메뉴, RBAC, document anchor, 접힘 저장, 관리자 전용 색상 scope의 실행 코드는 높이 클래스 외에 변경하지 않았다.
- CSS 변경은 주석의 범위를 실제 로그인·메뉴 색상 매핑으로 좁히며 런타임 동작을 바꾸지 않는다.
- 실행 계획은 후속 재검토와 N150 실측 전 완료로 표시하지 않는다고 명시한다.

## 검증

- PASS: git diff --check 이전candidate 후속candidate (exit0).
- PASS: 시작/종료 SHA/tree/clean status.
- CODE_REVIEW_PASS: AUTH-01 수정과 변경된 코드/테스트 계약에 재현 가능한 신규 결함을 발견하지 않았다.
- NOT_RUN(본 리뷰는 독립object-only): typecheck/lint/build/Vitest/Playwright 실행. 작성자의 실행 보고를 독립 실행PASS로 집계하지 않는다.
- PENDING_EXTERNAL_GATE: 이 후속candidate의 N150 rebuild 및 브라우저 검증. 해당 immutable 소스가 실제 빌드/실행된 증거와 통과 결과를 별도로 확인해야 한다.

## 판정

코드 검토 APPROVE. AUTH-01은 코드에서 해결되었다. 최종 실행 gate는 PENDING이며 N150 검증 통과나 작업 전체 완료를 선언하지 않는다.
