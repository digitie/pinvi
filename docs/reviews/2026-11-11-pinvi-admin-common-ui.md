# PinVi Admin 공통 셸 독립 적대적 UI 리뷰

- 실행 ID: pinvi-ui-20261111T042539Z
- 리뷰어: 독립 UI·CSS·반응형·접근성 담당 서브에이전트
- 종료 관측 시각: 2026-11-11T04:25:39Z. 시작 관측의 별도 시각은 수집하지 않았다.
- 저장소: /home/digitie/pinvi-codex (WSL Ubuntu-26.04)
- 기준선: cc3489a0bb33c184a36fa38a65fa59f937bbedc0
- immutable candidate: 7b874bbae02c102aff6420e00fe3b1c36e727d98
- candidate tree: 4259b5b475ef5ba336bba07b0b2f7889672f5ee3
- 시작 HEAD: candidate와 동일, 시작 status: clean.
- 종료 HEAD: candidate와 동일. 종료 status: 작성자가 수정 중인 layout.tsx·admin-common-shell.e2e.ts 두 파일 dirty. 리뷰어는 변경 파일을 직접 읽거나 수정하지 않고 git show/diff로 candidate object만 읽었다.
- 다른 리뷰어 결과를 열람하지 않았다. 소스·테스트·추적 문서를 수정하지 않았다.

## 검토 범위

동일 manifest 8파일 전체: apps/web/app/(admin)/admin/layout.tsx, apps/web/app/globals.css, apps/web/e2e/admin-common-shell.e2e.ts, apps/web/tests/adminCommonShell.test.tsx, docs/execplan/pinvi-admin-common-map-shell.md, docs/journal.md, docs/resume.md, docs/tasks.md.

공통 AppMenu·LoginForm 계약은 candidate에 고정된 vendored tgz를 git show→tar -xO로 읽어 대조했다. 실행 계획을 요청·수용 기준으로 사용했다. map 기준 32668d003은 접근한 map worktree에 object가 없어 직접 대조하지 못했다.

## 공격 시나리오와 관찰

1. 30개 메뉴를 잘못 줄이거나 경로·순서·RBAC 가드를 변경할 가능성: NAV_GROUPS와 ADMIN_ROLES는 변경하지 않았고 CommonDocumentLink는 기존 plain anchor를 유지한다.
2. 접힌 상태를 저장한 뒤 모바일로 전환했을 때 라벨이 사라질 가능성: 신규 숨김·정렬 CSS를 1024px 이상으로 제한했고 모바일 라벨을 유지한다.
3. 30개 링크가 작은 PC 높이에서 사용자/로그아웃을 밀어내는 가능성: aside h-dvh, 메뉴 min-h-0·flex-1·overflow-y-auto, footer shrink-0 구조는 합리적이다. 실제 키보드 자동 스크롤은 브라우저 미검증이다.
4. common 기본 녹색이 로그인·활성 메뉴에 남을 가능성: brand·brand-tint·focus·표면·테두리 매핑과 @theme inline 계약을 대조했다. 주요 화면에서 참조되는 값은 PinVi로 연결된다. 실제 계산 색상은 미측정이다.
5. 접힌 메뉴에서 이름이 사라질 가능성: AppMenu 자체 aria-label이 유지되어 CSS로 숨긴 텍스트와 무관하게 링크 이름을 제공한다.
6. 로그아웃 실패·재시도·중복 클릭: 실패 시 원문을 숨기고 alert 표시·버튼 재활성화, 성공 시 query cache clear·로그인 이동을 확인했다. RTL에 실패→성공 시나리오가 있으나 이 리뷰에서는 재실행하지 않았다.
7. 모바일 신규 로그아웃 터치 높이: 아래 UI-01 발견.
8. 본문 건너뛰기: 앵커 대상 id와 main tabindex=-1 계약은 보존한다. 실제 브라우저 포커스 이동은 기존 e2e에서 검사하지 않는다.

## Finding

### UI-01 · P2 · 모바일 로그아웃 버튼이 36px에 머문다

- 위치: apps/web/app/(admin)/admin/layout.tsx:289
- 조건: 320/375/414/768px 모바일에서 신규 footer 로그아웃 버튼 사용.
- 근거: className에 min-h-9만 있어 최소 높이가 36px이며 mobile 별도 높이 지정이 없다. 13.5px 텍스트와 16px 아이콘도 44px로 높이를 늘리지 않는다.
- 영향: 실행 계획의 모바일44px 터치 타깃 유지 수용 기준에 어긋난다. 메뉴 링크만44px로 검사하는 현재 e2e는 이를 놓친다. WCAG의24px 최소 기준 위반을 주장하는 finding은 아니다.
- 권고: min-h-11 lg:min-h-9로 모바일44px·PC36px를 분리하고 mobile logout 실제 높이를 브라우저에서 단언한다.
- disposition: 원본 candidate에서는 OPEN. 작성자가 후속 수정 중임을 통지했으나 새 immutable commit 확인 전 RESOLVED로 처리하지 않는다.

## 미검증과 판정

- NOT_RUN(본 리뷰어는 테스트를 실행하지 않음): Linux typecheck/lint/build/단위 테스트. 작성자 보고와 독립 실행 증거를 구분한다.
- NOT_RUN(N150 브라우저 실행은 작성자가 진행 중): 320/375/414/768px·PC overflow, screenshot, 실제 색상, 로그인 오류, 로그아웃 실패/재시도, 실제 skip-link 포커스, 키보드 메뉴 끝 스크롤.
- NOT_RUN(map 기준 object 부재): map baseline 32668d003와 직접 시각·소스 대조.
- P0/P1: 없음. P2: UI-01 한 건. P3: 없음.
- 판정: CHANGES_REQUESTED. UI-01 수정과 브라우저 gate 결과를 새 immutable commit으로 재검토해야 한다.
