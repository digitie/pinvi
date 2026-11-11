# PinVi Admin 공통 셸 독립 UI 수정 후 리뷰

- 실행 ID: pinvi-ui-post-20261111T042712Z
- 시작 시각: 2026-11-11T04:27:12Z. 종료 확인: 2026-11-11T04:27:29Z.
- 저장소: /home/digitie/pinvi-codex (WSL Ubuntu-26.04)
- 이전 후보: 7b874bbae02c102aff6420e00fe3b1c36e727d98
- 수정 후 immutable candidate: 74f894baec561c78474348f450d6ccdb1f9467d0
- candidate tree: 3e400f3a67e0725299a917efb98100637c77fef6
- 시작·종료 HEAD는 candidate와 동일하며 status는 모두 clean이다.
- 원본 공통 manifest8파일의 수정 후 delta 및 새 리뷰 보존 파일을 확인했다. git show/diff object-only로 검토했고 소스 수정·상대 리뷰 원본 열람은 하지 않았다.

## 수정 및 회귀 검토

- UI-01: RESOLVED(코드). layout.tsx의 로그아웃 버튼이 min-h-11 lg:min-h-9로 바뀌어 1024px 미만44px, PC36px 의도와 일치한다. mobile min-height44px e2e assertion도 추가되었다.
- CSS는 설명 주석만 좁혔다. 런타임 스타일 delta는 없으며 기존 PinVi 색상 매핑과 메뉴 접힘 범위는 보존된다.
- e2e는 뒤에서 두 번째 메뉴에 포커스를 둔 뒤 Tab으로 마지막 메뉴와 viewport 포함을 확인하고, skip link Enter 후 main의 실제 포커스를 확인하도록 보강했다.
- e2e는 로그아웃 첫 요청500·재시도204를 mock하여 오류 표시·현재 페이지 유지·재시도 로그인 이동을 검사한다. query cache clear와 공통 LoginForm으로의 이동을 경유한다.
- 새 테스트 선언·locator·변수 범위에서 정적 오류를 발견하지 않았다. 실제 브라우저 결과는 별도 gate다.
- 기존30개 메뉴·document navigation·RBAC·공통 AppMenu/LoginForm 계약에 대한 추가 소스 변경은 없다.
- 실행 계획은 최초 후보·리뷰·수정 내역을 구분하고 재검토와 N150 실측 전 완료로 표시하지 않는다.
- 자신의 원본 UI 리뷰 보존 파일은 /tmp 원본과 마지막 줄의 CRLF→LF 차이만 있고 내용은 동일하다. 상대 원본은 존재만 확인하고 본문은 열지 않았다.

## 검증과 판정

- PASS: git diff --check(이전 후보→수정 후보), immutable tree 확인, 시작·종료 HEAD/status 확인, UI-01 코드 수정·테스트 보강 정적 검토.
- NOT_RUN(본 리뷰어가 재실행하지 않음): Linux typecheck/lint/build/단위 테스트.
- NOT_RUN(N150 최종 후보 rebuild/test는 작성자가 진행 예정): 실제 높이·반응형·접힘·skip focus·메뉴 끝 키보드 스크롤·로그아웃 실패/재시도·시각 QA. 실행 결과를 받기 전 PASS로 집계하지 않는다.
- NOT_RUN(map 기준 object 부재 유지): map32668d003와 직접 시각·소스 대조.
- 새 finding: 없음. 기존 UI-01은 코드상 해소. 미해결 P0/P1/P2/P3 없음.
- 코드 리뷰 판정: PASS.
- 실행 gate 판정: OPEN. candidate74f894baec561c78474348f450d6ccdb1f9467d0에 대한 필수 Linux·N150 결과 확인 전 작업 전체 완료 판정은 유보한다.
