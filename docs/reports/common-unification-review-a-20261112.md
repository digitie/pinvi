# Pinvi 독립 적대 리뷰 A — 고정 후보 검토

- 실제 reviewer thread ID: 01a1cb51-e757-7ee0-82e1-7cb7bcf9eeae
- 구현 소유자 태그: Harvey. reviewer 닉네임을 의미하지 않는다.
- 원본 보고서 SHA256: c77bfa731a34f6dd8b8d3083ff6014b710d5d533c39f278b53f73834aca95b22
- 이 보고서의 원후보/00bd 수정재확인 범위를 넘어 최종 통합 승인으로 사용하지 않는다.

- 검토일: 2026-11-12 (Asia/Seoul)
- 기준 커밋: `d42ac95300749df955ce9e2bb63ea62eba36da09`
- 검토 후보: `3626a624173e1fe4cef61ac33fa325d4f5299ff7`
- 읽기 대상: `/home/digitie/dev/common-unification-20261111/pinvi`
- 판정: **추가 P2 회귀 4건. 알려진 initial-panel Shift+Tab 문제 외에도 수정·검증이 필요하다.** P0/P1로 확정할 추가 문제는 찾지 못했다.
- 다른 리뷰어와 정보 교환 없이 검토했다. 소스·설치·빌드·브라우저·프로세스·커밋·푸시는 변경/실행하지 않았다. 이 보고서와 저장소 밖 작은 프로브만 작성했다. 부모 소유 `.github/workflows/common-frontend-policy.yml`은 제외·보존했다.

## 1. [P2] 404 및 삭제 성공 후 목록 이동이 error 조건 안에 갇힌다

**주요 위치**

- `apps/web/app/(admin)/admin/trips/[trip_id]/page.tsx:796-798`
- 같은 결함: `apps/web/app/(admin)/admin/pois/[poi_id]/page.tsx:324-326`, `apps/web/app/(admin)/admin/users/[user_id]/page.tsx:516-518`
- 상태 설정: trips `:625`, `:784`; pois `:186`, `:312`; users `:206`

**트리거와 영향**

1. 존재하지 않거나 삭제된 사용자·여행·POI 상세를 연다. 404 catch는 `setMissing(true)` 후 반환하며 `error`를 설정하지 않는다. 그러나 `redirect()`는 `if (error)` 또는 `if (error && !user)` 내부에만 있으므로 실행되지 않는다. 세 페이지 모두 목록 이동 대신 무기한 “불러오는 중…”에 남는다.
2. 정상 여행·POI 상세에서 삭제에 성공한다. 이 성공 분기도 `setMissing(true)`만 호출한다. 오류는 없고 기존 엔터티 상태는 남아 있어 삭제된 상세와 운영 모달을 계속 렌더한다. `acting=false`로 돌아가 삭제 버튼도 다시 활성화된다. 기존 구현은 즉시 목록으로 `router.replace()`했다.

**확정 근거**

후보에서 원본 `useAdmin*DetailPageModel` 함수 본문을 읽어 TypeScript로 메모리 변환하고 React `renderHook`으로 실행했다. API·라우터 경계만 대체했다.

- 404 세 경로: 모두 `renderBranch=render1`, `redirects=[]`.
- 삭제 성공 두 경로: 실제 해당 hook의 `deleteTrip`/`deletePoi` 호출 1회, 이후 모두 `renderBranch=render2`, `showOperationDialog=true`, `acting=false`, `redirects=[]`.

이는 네트워크·브라우저 추정이 아니라 원본 hook 제어 흐름을 실행한 결과다. 반복 삭제의 서버 부작용까지 주장하지 않는다.

**수정 방향**

`if (missing) redirect(...)`를 오류/로딩/정상 분기 앞의 독립 조건으로 둔다. 404 세 경로와 삭제 성공 두 경로를 각각 회귀 검증한다.

## 2. [P2] Trigger 없는 관리자 Dialog를 닫으면 포커스가 BODY로 떨어진다

**위치**

- `apps/web/components/admin/ui/dialog.tsx:56-61`
- 실제 호출 예: `apps/web/app/(admin)/admin/pois/page.tsx:306-316` — 외부 버튼으로 조건부 생성하며 `DialogTrigger`/`finalFocus` 없음.
- 복원 다이얼로그·여행 운영 다이얼로그 등에도 같은 사용 형태가 있다.

**트리거와 영향**

외부 버튼으로 관리자 폼을 열고 내부 “닫기/취소”를 누른다. 새 어댑터는 `finalFocus.current`가 있을 때만 포커스를 복원한다. 실제 설치된 Radix modal Dialog의 기본 `onCloseAutoFocus`는 기본 복원을 막은 뒤 `context.triggerRef.current?.focus()`만 호출한다. 이 호출 형태에는 등록된 Trigger가 없으므로 아무 대상도 복원하지 않는다. 키보드 사용자는 원래 열기 버튼 대신 문서 시작 쪽으로 이동하게 된다.

**확정 근거**

실제 c8 패키지와 후보 관리자 어댑터를 가져온 DOM 프로브에서 외부 버튼 → 조건부 Dialog → 내부 닫기 → 150ms 후 결과:

`active=BODY`, `openerFocused=false`.

초기/닫기 정책은 모킹하지 않았다. 이 프로브는 실제 POI 페이지 전체가 아니라 동일한 호출 구조의 최소 하네스다. 구 Base UI 경로의 실제 실행은 하지 않았고, 기본 opener 복원 계약과 변경된 Radix 동작을 대조했다.

**수정 방향**

Trigger 없는 controlled 사용에도 실제 opener를 기록·복원하는 대상 선택 어댑터를 연결하거나 실제 호출부에 Trigger/finalFocus를 연결한다. 자체 trap/전역 dismiss 엔진을 복제할 필요는 없다. 취소·성공 후 disabled/제거된 opener의 폴백도 검증한다.

## 3. [P2] 첨부 영구 정리 AlertDialog의 초기 포커스가 모달 밖에 남는다

**위치**

- `apps/web/components/admin/StorageRetentionPanel.tsx:188`, `:195-201`
- 관련 어댑터: `apps/web/components/admin/ui/alert-dialog.tsx:34-40`

**트리거와 영향**

정리 사유와 확인 문구를 입력한 뒤 “기한 지난 여행·파일 정리”를 눌러 확인창을 연다. 이 호출부는 `initialFocus`를 전달하지 않으며 “취소”도 일반 `button`이다. Radix AlertDialog는 기본 open auto-focus를 막고 등록된 `AlertDialogCancel`로 포커스를 옮긴다. 여기서는 cancelRef가 등록되지 않으므로 포커스가 옮겨지지 않는다.

결과적으로 포커스가 배경의 열기 버튼에 남고, 해당 버튼의 조상에는 모달 격리의 `aria-hidden=true`가 걸린다. 영구 삭제 확인창을 열었는데 키보드/보조기술의 현재 위치가 확인창 안으로 이동하지 않는 접근성 회귀다.

**확정 근거**

후보 관리자 AlertDialog 어댑터와 실제 공통/Radix 패키지에 위 호출부와 같은 일반 취소/실행 버튼 구조를 렌더한 프로브:

`activeText="open cleanup"`, `activeInsideDialog=false`, `openerHiddenForAT=true`.

StorageRetentionPanel 전체의 API 흐름이나 실제 파일 삭제는 실행하지 않았다.

**수정 방향**

취소 버튼을 공통 `AlertDialogCancel`로 연결하거나 취소 ref를 `initialFocus`로 명시한다. 비동기 영구 정리 실행 버튼은 기존의 성공/실패·busy 제어를 유지한다.

## 4. [P2] 공개 Dialog의 설명 문단과 aria-describedby ID가 다르다

**위치**

- `apps/web/components/ui/Dialog.tsx:136`
- 관련 Content 설정: `:110`

**트리거와 영향**

`description`을 가진 공개 Dialog를 연다. Content는 Radix context가 만든 description ID를 참조하지만 `DialogDescription`에는 별도의 `titleId + '-desc'`를 덮어쓴다. Content에 일치하는 ID를 명시하지 않아 설명 참조가 존재하지 않는 요소를 가리킨다. 지도 상세/제안, 여행 복사·내보내기, 충돌 설명 등이 모달 설명으로 연결되지 않는다.

**확정 근거**

후보 커밋의 실제 공개 Dialog를 렌더했다.

- Content `aria-describedby="radix-_r_3_"`
- 해당 ID 요소 존재: `false`
- 실제 설명 요소 ID: `_r_0_-desc`

구현은 기존 모달에서 동일 descriptionId로 Content와 문단을 연결했다. Radix context ID 생성은 비결정적이지만 두 요소의 불일치는 결정적이다.

**수정 방향**

`DialogDescription`의 임의 id를 제거하여 Radix가 같은 context ID를 사용하게 한다. 설명이 있는/없는 경우 및 중첩 인스턴스에서 실제 ID 연결을 단언한다.

**후보 이후 작업 트리 관찰**

리뷰 도중 작업 트리에 이 id를 제거하는 수정과 관련 테스트 추가가 나타났다. 다른 작업자의 변경으로 보고 건드리지 않았다. 본 발견과 최종 프로브는 `git show 3626a624…:<path>`로 읽은 지정 후보 기준이다. 이 미커밋 수정의 통과 여부를 본 리뷰가 승인한 것은 아니다.

## 알려진 Shift+Tab 문제와 검증 범위

- 사용자가 전달한 full unit **509PASS/1FAIL** 및 초기 패널 Shift+Tab → 마지막 요소 실패는 이미 알려진 별도 잔여 gate로 유지한다. 이 리뷰에서 전체 unit이나 Chromium을 재실행하지 않았고, 전달받은 결과를 독립 실행 결과로 표현하지 않는다.
- 공개 Dialog/ConfirmDialog의 busy/onCancelBusy, Escape/outside, 양방향 drag, 중첩 우선순위, opener 복귀 및 SSR 경로와 AppShell 공통 nonmodal Popover를 소스·기존 계약 테스트와 대조했다.
- AdminTable/DataTable → 실제 common VirtualTable의 열 메타·row ID·초기/서버 정렬·정렬 해제·가상화 임계/스크롤 컨테이너를 비교했다. 직접 RHF/Zod collection 폼의 명령 키 보존·성공/오류 초기화와 common LoginForm 자동완성 동기화/중복 제출 제어를 확인했다. 이 범위에서 위 발견 외 별도 확정 회귀는 찾지 못했다.
- Doctor 분해의 대규모 view/model 추출과 실제 변경된 호출을 비교했고, 특히 404/삭제 이동 회귀를 실행으로 확인했다. 전체 페이지의 모든 조합을 실행한 검증은 아니다.
- 필수 지침과 관련 프론트엔드/관리자/ADR-079/검증 보고서를 확인했다. 전체 Doctor/full warning·lint·타입·clean ci·E2E는 소유자가 검증 중이므로 중복 실행하지 않았다. 이 리뷰를 최종 전체 gate PASS로 사용할 수 없다.

## 산출물 정합성과 실행 증거

- 후보 root/web/mobile의 세 common-artifacts 원장에서 6종 tgz 모두 실제 SHA512와 일치한다.
- 공통 source `670a753bc17f956f71bdc28385d6241a6e4ee017`, 지도 source `9a7a348b02d61969b394c681b024d5851eef836b`, CSS `1.33.0+nativecss.fix.4`를 확인했다. 새 pack은 만들지 않았다.
- 실제 설치된 common의 `dist/dialog.js`, `dist/alert-dialog.js`, `dist/virtual-table.js`, `dist/login-form.js`는 전달 UI tgz의 해당 파일과 바이트가 같다.
- 최종 프로브: `node /tmp/pinvi-review-a-final-probe.mjs` (WSL Linux, Node22.22.2, jsdom, 브라우저 없음).
- 결과: `/tmp/pinvi-review-a-evidence.jsonl`; stderr: `/tmp/pinvi-review-a-evidence.stderr.log` (0바이트).
- 프로브는 앱 TS/TSX를 후보 커밋에서 메모리로 읽는다. 설치 패키지·앱 소스·기존 테스트를 수정하지 않는다. 상세 404/삭제 증거는 원본 hook 본문에 API/라우터 경계만 대체한 것이며, API 서버/실제 삭제 검증을 뜻하지 않는다.

완료 직전 상태 확인에서도 HEAD는 지정 후보 그대로였으며 관리자 상세 3곳·Dialog 어댑터·모바일 일부 및 신규 테스트의 외부 미커밋 변경을 관찰했다. 모두 보존했다. 해당 작업 트리 전체를 새 후보로 재검토하거나 수정 완료로 판정하지 않았다.

## 후속 재확인 — 00bd8c8d7bf429d886d8885ae29d3a195a42d55c

- 재확인일: 2026-11-12 (Asia/Seoul).
- 범위: 최초 후보 `3626a624173e1fe4cef61ac33fa325d4f5299ff7` 대비 후속 `00bd8c8d7bf429d886d8885ae29d3a195a42d55c`의 **본 리뷰 네 발견 관련 소스와 회귀 테스트만** 읽기 전용으로 재검토했다.
- 최초 보고 내용과 당시 실행 증거는 위에 그대로 보존한다. 다른 독립 리뷰와 합치거나 최초 후보 판정을 소급 변경하지 않는다.
- 판정: **본 리뷰의 추가 P2 네 건은 후속 소스에서 수정 확인. 해당 수정 범위의 새로운 P0/P1/P2 차단 발견 없음.** 아래 판정은 코드·테스트 정적 재확인이며, 새 전체 실행 또는 배포 승인 판정이 아니다.

| 최초 발견                                 | 후속 확인과 판정                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. 404/삭제 성공 후 이동 누락             | 사용자·여행·POI 상세 모두 `if (missing) redirect(...)`가 error/로딩/정상 반환 전에 독립 조건으로 이동했다. 404 catch와 여행/POI 삭제 성공에서 설정한 missing이 이제 반드시 목록 이동에 도달한다. `adminMissingDetail.test.tsx`는 실제 페이지 세 곳을 렌더해 각각 올바른 목록 redirect 호출을 단언한다. `adminDeletedDetail.test.tsx`는 실제 여행/POI 페이지에서 삭제 모달을 열고 사유를 입력·확정한 뒤 해당 delete 호출 1회 및 목록 redirect를 단언한다. **수정 확인.** |
| 2. 관리자 Dialog 닫기 후 포커스 소실      | Dialog와 AlertDialog 어댑터 모두 Radix onOpenAutoFocus에서 실제 opener를 기록한다. onCloseAutoFocus는 호출부 preventDefault를 존중하고, 기존 DOM 대상 판별로 명시적 finalFocus를 우선한 뒤 유효 opener로 복귀한다. 전역 이벤트·자체 trap/dismiss/portal 엔진은 추가하지 않았다. `adminDialogFocus.test.tsx`의 Trigger 없는 조건부 마운트 두 경우가 opener 복귀와 명시적 finalFocus 우선권을 각각 단언한다. **수정 확인.**                                               |
| 3. 영구 정리 AlertDialog 초기 포커스 누락 | StorageRetentionPanel의 취소 버튼에 ref를 연결하고 같은 ref를 AlertDialogContent initialFocus에 전달했다. 어댑터가 기본 autofocus를 막고 실제 취소 버튼에 포커스를 옮기므로 Radix의 미등록 cancelRef 경로를 피한다. `StorageRetentionPanel.test.tsx`는 실제 컴포넌트의 사유·문구 입력 후 취소 초기 포커스, 취소 후 opener 복귀, 영구 정리 미실행을 단언한다. 기존 비동기 execute/busy·오류 흐름의 정책 변경은 없다. **수정 확인.**                                      |
| 4. 공개 Dialog 설명 연결                  | DialogDescription의 임의 id가 제거되어 Radix context가 Content와 Description에 동일 ID를 공급한다. 추가 테스트는 `toHaveAccessibleDescription('작업 설명')`과 aria-describedby가 가리키는 실제 요소의 본문을 함께 확인한다. **수정 확인.**                                                                                                                                                                                                                              |

### 재확인 한계와 남은 gate

- 소유자가 알린 전체 unit **518PASS/1FAIL(519)**, Doctor **full486files 진단0**, TypeScript PASS, lint 오류0/기존 인증 경고1은 후속 커밋의 검증 보고서에도 기록돼 있음을 읽었다. 본 재확인에서는 이 명령이나 테스트·DOM 프로브·브라우저·대형 검증을 다시 실행하지 않았다. 따라서 이를 독립 재실행 결과로 표현하지 않는다.
- 공개 Dialog 초기 패널 Shift+Tab의 마지막 요소 기대값은 테스트에 그대로 남아 있다. 알려진 Radix reverse-entry 실패 **1건은 미해결 gate**로 유지하며, 이번 네 수정으로 해소됐다고 판정하지 않는다.
- 두 커밋 사이 vendor/세 common-artifacts 원장/package-lock에는 변경이 없음을 git diff로 확인했다. 이번 후속에서 별도 pack·패키지 엔진 복사·의존 변경은 없다.
- 재확인 당시 HEAD는 `00bd8c8d7bf429d886d8885ae29d3a195a42d55c`이고 작업 트리에는 부모 소유 미추적 workflow만 보였다. 앱 소스·기존 테스트·workflow는 변경하지 않았고 이 보고서에만 후속 절을 추가했다.
