# tasks-done.md — 완료·아카이브

완료된 task와 머지 이력을 보관한다. 열린 작업은 `docs/tasks.md`, 현재 진척과
"다음 한 작업"은 `docs/resume.md`가 정본이다. 작성 규약은 `docs/tasks-rule.md`를
따른다.

## 2026-09-02

- [x] **T-357** — T-356 후속 3건을 마무리했다(claude, PR #516, squash `301aafe4`).
      **모달 경계를 eslint로 강제**했다: T-356이 문서로만 두고 온 "admin은 base-ui / 사용자
      표면은 `lib/useModalDialog`" 분리를 `no-restricted-imports` 양방향 가드로 옮겼다.
      개별 파일(`components/ui/Dialog`) 하나만 막으면 `trips/ConflictDialog` 경유로 우회되고
      디렉터리를 통째로 막으면 모달과 무관한 `Button`·`FormField`까지 걸리므로,
      `lib/useModalDialog`에서 역방향 BFS로 **전이 도달 집합 17개**를 뽑아 그것만 막았다.
      포커스 복원 대상 판별은 `lib/focusTarget`으로 스택 밖에 분리해 admin이 가드를 넘지 않고
      쓰게 했다. 그 밖에 `features` 표 헤더 정렬을 서버 정렬과 연동했고(헤더가 현재 페이지만
      정렬해 화면이 사실과 달랐다), 수요 없는 모듈 3개를 지웠다
      (`multi-filter-combobox` 277줄, `ui/tabs` + `tabs-variants` 155줄).

      **적대적 리뷰 2회차가 NO-GO와 함께 P0 1건**을 냈다: `serverSort` 헤더가 두 번째 클릭부터
      죽었다. TanStack Table은 `sortDescFirst:false` + `enableSortingRemoval` 기본값(true)에서
      desc 다음 상태로 "정렬 제거"(빈 배열)를 돌려주는데 어댑터가 `if (!first) return;`으로
      그것을 삼켰다. 서버 정렬 모드에서 `enableSortingRemoval={false}`로 3-state 순환을 끈다.
      회귀 테스트는 **수정을 되돌려 실제로 실패하는 것을 확인한 뒤** 넣었다 — 첫 시도에서
      되돌리기 스크립트의 문자열이 안 맞아 "수정 없이도 통과"하는 가짜 초록을 봤고 `assert`로
      되돌리기 자체를 검증하게 고쳤다.

      P1 6건도 반영했다. flat config가 같은 규칙의 옵션을 **병합하지 않고 교체**해 kakao 가드가
      조용히 사라져 있던 것을 복원했고, `.ts`를 가드 대상에 넣었다(`lib/admin/*.ts`로 우회
      가능했다). `Section` → `SectionCard` 위임이 남긴 시각 델타도 걷었다: `CardContent`의
      `space-y-4`(16px) 위에 자식의 `mb-3`/`mt-3`(12px)이 더해져 28px가 되던 4곳을 정리하고,
      헤더에 버튼이 필요해 `Section`을 못 쓰던 패널을 위해 `actions` 슬롯을 열어
      (`SectionCard`는 원래 갖고 있었고 어댑터만 막고 있었다) 손수 패널 7개를 흡수했다.
      높이를 제한한 표가 카드 안에서 프레임을 잃어 스크롤 경계가 안 보이던 것도 고쳤다.

      **`Section` 렌더 계약 테스트가 0건이었다** — 소비처 60곳이 한 번에 움직이는 지점인데 위
      시각 델타를 로컬 4개 게이트가 전부 놓쳤다. `tests/AdminSectionContract.test.tsx`로
      제목 heading·카드 위임·표 flush(일반)/프레임 유지(높이 제한)를 잠갔다.

      검증: CI 블로킹 4종 pass, 로컬 4종(tsc / lint 0 error / **vitest 165** / build 57쪽),
      **N150 격리 e2e 169 passed / 0 failed**(rc=0, 체크아웃 SHA 가드 통과). 운영 스택 무영향 —
      박스에서 가장 최근 생성된 컨테이너가 e2e 실행 시각보다 8시간 앞서 e2e가 만든 잔여물이
      없다.

- [x] **T-356** — pinvi admin 화면을 kor-travel-map(KTM) admin과 색상톤만 제외하고 look and
      feel·기능까지 일치시켰다(claude, PR #515). `apps/web`을 Tailwind v4로 올리고(모바일은
      NativeWind 4 + v3 유지 — npm이 v3를 root에, v4를 `apps/web`에 중첩시키는 것을 최소 재현
      워크스페이스 실측으로 확인), KTM 프리미티브 28종 + `DataTable` 799줄을 이식했다.
      `AdminTable`을 어댑터로 재작성해 소비 페이지 36곳을 무수정으로 전환했고, 필터 툴바 23쪽에
      `FilterField` 66개를 배선했다. KTM 7단 타이포는 `[data-pv-surface='admin']` scope로만 넣어
      사용자 표면 활자를 보호했다. 사용자 지시로 "모든 모달은 `lib/useModalDialog`" 단일화 규칙을
      해제하고 admin 모달을 base-ui로 전환했다(수제 `role="dialog"` 5쪽 7개 수렴).

      게이트가 못 잡는 회귀를 여러 건 잡았다. 런타임 조립 Tailwind 클래스가 CSS를 아예 만들지
      않던 것, `admin-table-scroll`을 래퍼에 달아 e2e의 `scrollTo`가 no-op이 되던 것, sticky
      헤더가 행수 게이트에 묶인 것, v4가 없앤 `button{cursor:pointer}`, `outline-none`의
      forced-colors 폴백 소실, `control-line` 대비가 실제 admin 배경(#f7f7f7)에서 2.83으로 미달,
      brand/danger tint 픽셀 충돌.

      **N150 격리 e2e가 로컬 4개 게이트를 전부 통과한 회귀를 두 번 잡았다.** (1) v4가 `@layer`를
      네이티브 캐스케이드 레이어로 발행하면서 레이어 순서가 specificity를 이기게 돼
      `[data-mobile-layout] .app-shell-tabbar`(0,2,0)가 `.lg\:hidden`(0,1,0)에게 진 것 —
      globals.css 주석이 "레이어 순서와 무관하게 이긴다"고 못박아 둔 전제가 무효화됐다.
      (2) 미저장 폼 입력 보호를 "폼이면 보호"로 잡았다가 전에도 Escape로 닫히던 모달까지 막아
      새 회귀를 만든 것 — 올바른 기준은 "전환으로 없던 경로가 새로 생긴 곳"이었다.

      전문 리뷰어 2명 적대적 리뷰 + 교차검증을 두 차례 돌렸다(2차 판정 NO-GO → P0/P1 수정 후
      해소). 검증: CI 블로킹 체크 13종 pass, 로컬 tsc/lint 0 error/vitest 152/build 57쪽,
      API pytest unit 1333, 모바일 tsc clean, **N150 격리 컨테이너 e2e 169 passed / 0 failed**
      (운영 스택 무영향 — 운영 repo 브랜치 전환 없음, 운영 컨테이너 9개 그대로).

      부수: Playwright runner의 `test-results` tmpfs가 64m 고정이라 trace 기록 중 ENOSPC를 내던
      것을 1g 기본 + `PINVI_PLAYWRIGHT_RUNNER_TMPFS_SIZE`로 고쳤다. 그 크기를 리터럴로 잠그던
      API 가드도 격리 속성 검사로 바꿨다.

## 2026-08-27

- [x] **T-355** — `scripts/deploy-node.sh`/`scripts/docker-app.sh`의 bare-call errexit 무력화
      P0 3건을 `|| return $?`로 고쳤다(claude, #498). `if ! FUNC` 형태로 호출되는 함수는 그
      동적 호출 트리 전체에서 errexit이 꺼지는데, 그 안에서 하위 체크를 bare statement로 호출하면
      실패해도 무시되고 마지막 statement의 종료코드만 함수 반환값이 되던 문제다.
      `require_fresh_stack_identity()`의 하위 체크 3개(`require_n150_execution_host`,
      `require_canonical_compose_file`, `require_isolated_database_endpoint`),
      `fresh_stack_runtime_image_proof()`의 `pinvi_verify_runtime_image_provenance` 호출,
      `require_direct_compose_mutation_environment()`의 `require_docker`/
      `validate_configured_ports` 호출을 고쳤다. PR #487(`codex/pr477-followup`, 같은 날
      merge)이 같은 파일을 대폭 재작성했지만 이 3건은 고치지 않은 채 main에 살아있었음을
      merge 직후 재확인해 별도 PR로 분리했다. 검증: sed로 추출한 실제 함수 본문을 stub
      하위 함수로 재현해 수정 전/후 동작 확인(3건 모두), `bash -n` 통과, 관련 unit 테스트
      139건 통과.

## 2026-08-26 (3)

- [x] **T-351** — `pytest tests/integration`이 계속 자라(684건+, 91개 파일) job timeout을
      올려도(T-348, 15→35분) 구조적으로 재발하는 문제를 job 샤딩으로 해결했다(claude).
      `pytest-split`을 도입해 `lint-typecheck-test`의 `pytest (integration)` 스텝을 떼어내고
      독립된 `integration-test` matrix job(`group: [1, 2, 3, 4]`)으로 병렬 실행한다. 각 shard가
      자체 PostGIS testcontainer를 띄우므로(`conftest.py` session-scope fixture) 공유 상태 없이
      안전하게 나뉜다. `.test_durations` 캐시가 아직 없어 테스트 개수 기준 균등 분할이다(그룹당
      171개). `aggregate-ci.yml`의 `requiredChecks`에 `integration-test (1)`~`(4)`를 추가해
      게이트가 4개 shard를 모두 기다리게 했다 — 안 하면 이 파일이 이미 여러 번 겪은 "게이트가
      실제로 안 기다려서 항상 green"이 재발한다. `lint-typecheck-test`의 기존 timeout(35분)은
      재측정 근거 없이 낮추지 않고 그대로 뒀다.

      검증: 로컬에서 4그룹 분할이 정확히 684개를 중복 없이 커버함을 확인, shard 1(171건)을
      로컬 실제 실행해 통과 확인. PR #495 CI에서 실제로 4개 shard와 `lint-typecheck-test`가
      병렬로 green(각 2m5s~5m28s)이고 Aggregate CI gate가 가장 느린 shard까지 정확히
      기다렸다가 통과(5m50s)함을 확인 — 이전 단일 job 순차 실행(최대 관측 20분6초) 대비
      critical path가 크게 줄었다.

## 2026-08-26 (2)

- [x] **T-354** — Next.js 15 → 16 업그레이드. 사용자 요청으로 착수(npm audit
      union range 오독으로 미루기로 했던 과거 결정을 뒤집음, PR #489, claude).
      `@next/codemod upgrade latest` + `next-lint-to-eslint-cli`로 기계적 마이그레이션을
      먼저 돌리고, 실제로 깨진 지점을 하나씩 고쳤다.

      **의존성 버전 스큐 3건**: (1) `next-intl@3.26.5`가 Next 16을 지원 안 해 워크스페이스에
      `next`가 두 버전 공존 → npm arborist가 혼란스러워하며 vendored `file:` 패키지
      (`vworld-map-*`)를 레지스트리에서 찾으려다 404로 전체 install이 깨졌다(재현 3회 확인,
      순정 origin/main은 재현 안 됨 — bisect로 확정). `next-intl`이 실제로는 코드 어디서도
      import되지 않는 미사용 의존성임을 확인하고 4.13.7(Next 16 공식 지원)로 올려 단일
      `next` 버전으로 정리했다. (2) `eslint-config-next@16.3.3`이 `eslint-plugin-react-hooks
      @^7.0.0`을 원하는데 T-311이 걸어둔 `5.2.0` 루트 override와 충돌 — 이번엔 의도적
      업그레이드이니 override를 제거하고 실제로 v7 규칙을 채택했다. (3) `eslint@10.9.1`(codemod가
      자동 승격)은 `eslint-plugin-react`가 아직 지원 안 해(`context.getFilename is not a
      function`, 최신 7.37.5도 peer가 `<=9.7`) 9.x대로 유지했다 — `eslint-config-next`의 peer는
      `>=9.0.0`이라 10 강제가 아니었다.

      **`react-hooks/set-state-in-effect`(eslint-plugin-react-hooks v7의 새 React Compiler
      시대 규칙) 위반 44건**을 Workflow(10개 배치, 파일별 실제 구조 리팩터)로 고쳤다 — 순수
      파생값은 useEffect를 없애고 렌더 중 계산으로, prop 변경 시 여러 state를 리셋하는 곳은
      React 공식 문서의 "adjusting state when a prop changes" 렌더 중 패턴으로, 마운트 시
      fetch 패턴은 초기 state 값과 중복되는 동기 setState를 제거하는 방식으로. 이 과정에서
      `app/(auth)/profile/page.tsx`의 실제 버그(마운트 URL의 OAuth 에러가 나중에 조용히
      지워지던 문제)도 함께 발견해 고쳤다. `useModalDialog.ts`(포커스 관리가 타이밍에 민감해
      직접 처리)는 `dialogProps` 구성을 spread로 바꿔 "렌더 중 ref 접근" 오탐을 없앴고,
      `portalNode`(useState lazy init, setter 미사용) 뮤테이션은 useRef 전환을 시도했다가
      오히려 새 위반(렌더 중 ref 읽기)을 만들어 되돌리고 그 한 줄만 국소 eslint-disable +
      사유 주석으로 처리했다(React 공식 문서가 인정하는 lazy-ref-init 패턴을 이 lint 규칙이
      막는 경우라 구조를 바꾸는 게 더 위험하다고 판단).

      `@next/codemod`의 `cache-components-instant-false` 변환이 15개 라우트에
      `export const instant = false`를 추가했는데, 이 프로젝트는 `cacheComponents`를
      켜지 않아(Cache Components 아키텍처 미채택) 그 설정 자체가 빌드를 깼다 — 15곳 전부
      제거해 원본과 byte-identical하게 되돌렸다(Cache Components 도입은 별도 결정 필요).

      검증: `apps/web` typecheck·lint(에러 0, 경고 4건은 기존/무관)·build·vitest(18
      files/113 tests, `useModalDialog.test.tsx` 14건 포함) 전부 통과.

      **PR #489 최초 push 후 CI e2e에서 49개 실패 발견** — 실패한 스펙은 예외 없이
      `vworld-map-web`(지도)을 렌더링하는 페이지·다이얼로그·폼이었고, 지도가 없는 페이지는
      전부 통과했다. 로컬에서 같은 production build로 재현하니 `/map` 콘솔에
      `Module ... was instantiated ... but the module factory is not available`가 떴고
      앱 에러 바운더리까지 전파돼 지도가 fallback UI조차 그리지 못했다 — Next 16 Turbopack
      프로덕션 번들러가 `vworld-map-web`의 모듈 그래프를 청크로 나누는 과정에서 생기는
      런타임 버그로 확인, 이번 리팩터와는 무관. `next build --webpack`으로 재빌드하니
      콘솔 에러 없이 정상 렌더링됐고 실패했던 19개 대표 e2e(map-*, dialog-focus, form-a11y,
      trips-dashboard)를 재실행해 전부 통과 확인. `apps/web/package.json`의 `build`
      스크립트를 `next build --webpack`으로 고정해 CI·`apps/web/Dockerfile` 둘 다 이
      경로를 타게 했다(**ADR-066**). `dev` 스크립트는 범위 밖 — 로컬 dev에서 같은 증상이
      보고되면 그때 맞춘다.

## 2026-08-26

- [x] **T-350** — retention 관리자 페이지의 `executing` 배지 옆 경과시간이 실시간으로 갱신되게
      한다. `formatElapsed`는 렌더 시점의 `Date.now()`를 쓰는데 재렌더를 유발할 틱이 없어서
      새로고침 전까지 스냅샷처럼 보였다(T-345 적대적 리뷰, PR #480). `executing` run이 있을
      때만 1초 간격 `setInterval`로 재렌더를 유발하고, 없으면 타이머를 아예 안 돌게(불필요한
      리렌더/배터리 소모 방지) 했다. `apps/web` typecheck/lint/build 전부 통과.

## 2026-08-22

- [x] **T-VN-M04 follow-up — Feature request consumer 중립 식별자** — 범용 queue의
      service token 설정을 `KOR_TRAVEL_MAP_FEATURE_REQUEST_TOKEN`으로 정리하고 공용
      HTTP 요청 correlation extension을 `request_id`로 통일했다. 기존 `PINVI_*` 설정을
      그대로 읽는 호환 alias는 두지 않아 배포 환경도 새 이름으로 함께 바꿔야 한다.
- [x] **T-VN-40** — PinVi canonical curation consumer와 paired API acceptance를 완료했다.
      Pinvi PR #445·#459, Docker Manager PR #174, Map PR #1048을 반영하고, 격리 DB에서 canonical
      snapshot/import/replay/refresh와 legacy plan 부재를 확인했다. (완료: 2026-08-21)
- [x] **T-VN-M04** — 범용 Feature 요청 큐 consumer를 완료했다. Pinvi PR #458에서 신규 장소 승인
      요청의 UUID·idempotency·pending/exact-conflict 경계와 correction/closure 분리를 반영했고,
      Map 승인부터 PinVi receipt·Map ACK까지의 격리 paired browser evidence를 기록했다.
      (완료: 2026-08-21)

## 2026-08-25

- [x] **T-341/342/343/344/345/346/347** — retention 실행이 매달리지 않고, 감사가 정직하고,
      운영자가 진단할 수 있게 한다. (완료: 2026-08-25, PR #480, claude)
      전문 6인 병렬 조사가 각 task의 정확한 개입 지점을 도출했고, 그중 T-341은 이미 구현·검증까지
      끝난 상태로 조사에 잡혀 교차검증됐다. **T-324가 codex에 의해 이미 완료된 것도 이 조사에서
      재확인해 tasks-done.md 정리 누락을 함께 바로잡았다**(별도 PR #479).

      **T-341** — `lock_timeout=30s`/`idle_in_transaction_session_timeout=60s`/
      `statement_timeout=600s`를 세션 GUC로 건다. 요청 경로·백그라운드 워커·retention이 단일 엔진을
      공유해 하나라도 너무 짧으면 무관한 기능이 동시에 깨지므로, 배치 작업을 죽이지 않는 선에서
      "무기한 대기만 막는" 값을 골랐다. `lock_timeout`이 실제로 30초 만에 fail-fast하는 것을 실측
      확인했다 — 이것이 T-339의 hang이 탐지되지 않은 근본 원인이었다.

      **T-343** — 동시 execute를 advisory lock(`pg_try_advisory_xact_lock`, non-blocking)으로
      막는다. "조회 후 없으면 진행"은 그 자체로 경합 조건이라, 실제 두 개의 독립 DB 세션으로
      `asyncio.gather` 동시 호출을 만들어 정확히 하나만 통과함을 실측했다. 되돌려서 두 테스트 모두
      red가 되는 것도 확인했다.

      **T-342** — 실패한 execute도 `admin_audit_log`에 `retention.execute_failed`로 남는다.
      `docs/compliance/lbs-act.md` §3.4가 이미 그렇게 규정하고 있었는데 코드는 성공 경로에서만
      적재했다 — 문서가 옳았다. kill-switch/precheck에 막혀 run조차 안 만들어져도 남기되
      `resource_id`는 없다. 구현 중 `db.rollback()`이 세션의 모든 ORM 인스턴스를 만료시켜
      `admin.user_id` 접근이 `MissingGreenlet`으로 죽는 버그를 실측으로 잡았다 — rollback **전에**
      필요한 값을 미리 뽑아 두는 것으로 고쳤다.

      **T-346** — PII 익명화가 avatar `avatar_bucket`/`avatar_storage_key` **포인터만** NULL로
      만들고 RustFS의 실제 이미지 파일은 남기던 것을 고쳤다. `deleted_users` CTE가 UPDATE 이전
      시점에 원래 키를 함께 잡아(UPDATE 후 RETURNING으로는 이미 NULL이 된 값만 보인다) best-effort로
      삭제한다. 삭제 실패는 `result.pii.avatar_delete_failures`에 남기고 익명화 자체는 롤백하지
      않는다 — PII 익명화가 avatar 파일 하나 때문에 전부 실패하는 것이 더 큰 손상이다.
      **머지 전 27인 규모 적대적 리뷰가 major 결함을 잡았다**: 최초 구현은 이 avatar 삭제를
      아직 커밋되지 않은 파괴 트랜잭션 안에서 수행해, RustFS I/O 대기 중 T-341의
      `idle_in_transaction_session_timeout`(60초)에 걸리면 이미 끝난 PII 익명화까지 롤백될
      위험이 있었다 — 방금 위에서 설명한 설계 의도와 정반대 결과. `_execute_pii_retention`은
      이제 지울 키만 반환하고, 새 `finalize_avatar_purge()`가 라우트 커밋 **이후** 실제 삭제를
      수행하도록 분리했다.

      **T-347** — `GET /admin/retention/runs`·`/summary` 응답의 `error_message`를 고정 문구로
      가린다. `/execute`의 503은 T-339에서 이미 가렸는데, 같은 원문이 더 넓은 role(operator 포함)
      에게 이 두 endpoint로는 그대로 나가고 있었다. DB 컬럼 원문은 그대로 둬 runbook §5.2의 직접
      SQL 진단 경로가 계속 동작한다.

      **T-344** — `execute_retention()`이 트랜잭션 진입 직후 `application_name`에 run_id를 싣는다
      (`'pinvi-retention-execute:' || run_id`). runbook §5.2가 "살아 있는지 확인한다"고만 적고
      확인할 수단이 없었는데, 이제 `pg_stat_activity`로 실제 조회 가능하다 — 실행 중인 트랜잭션을
      멈춰 둔 상태에서 그 세션을 실제로 찾아내는 것까지 실측 확인했다. `state='idle in transaction'`
      이 T-341의 60초 타임아웃을 넘겨도 지속되면 그 자체가 이상 신호임을 §5.2에 명시했다.

      **T-345** — Admin 콘솔에 `executing` 상태를 `approved`(더 이상 안 쓰는 값)와 구분해 표시하고
      (pulse 애니메이션 — 프로젝트에 warning류 색상 토큰이 없어 새로 만들지 않았다), §5.2의 15분
      stale 기준과 맞물리는 경과 시간, 실패 사유(`error_message`, T-347 마스킹 적용된 값)를
      노출한다. Playwright e2e는 이번 세션에서 실행하지 못했다(N150/Windows 러너 미접근) —
      변경이 순수 조건부 렌더 추가라 기존 e2e의 assertion과 겹치지 않음을 코드로 확인했다.

- [x] **T-348** — CI 타임아웃이 통합 스위트 성장 속도를 못 따라간다. (완료: 2026-08-25, PR #481, claude)
      `api.yml`의 `lint-typecheck-test` job timeout을 15→35분, `aggregate-ci.yml`의 게이트
      timeout을 12→45분으로 올렸다. 적대적 리뷰(2인 병렬)에서 첫 커밋이 불완전함을 발견했다 —
      게이트의 폴링 스크립트 안에 job-level timeout과 완전히 독립된 하드코딩
      `deadline`(`Date.now() + 10분`)이 있어, job timeout만 올려서는 PR이 고치려던 정확한 증상
      (job은 성공했는데 게이트만 포기)이 그대로 재현됐다 — 두 번째 커밋에서 이 deadline을 40분으로
      올려 실제로 해결했다. 실제 merged CI에서 `lint-typecheck-test` 12분13초·`Aggregate CI gate`
      12분57초로 정상 통과를 확인했다. 남은 후속 과제(경험적으로 불확실한 "20:06" 관측치 근거,
      통합 스위트 근본 샤딩)는 T-351로 분리했다.

- [x] **T-319** — 모바일/웹 mutation 실패 시 원문 예외 노출을 막는다. (완료: 2026-08-25, PR #483, claude)
      `friendlyErrorText()`의 일반 `Error` fallback이 `error.message`를 무조건 그대로 보여줘,
      재정렬 실패 시 `fetch failed: java.net.ConnectException…`류 네트워크 원문이 그대로 노출됐다.
      저장소 전체의 의도적 사용자 안내 `throw new Error(...)`(admin 검증 흐름 30여 곳,
      `packages/domain/upload.ts` 등)는 전부 한글임을 확인하고, 한글이 없는 메시지만 기본 문구로
      가리도록 고쳤다 — 기존 한글 메시지 호출부는 회귀 없이 그대로 동작한다.

- [x] **T-323** — Web `e2e` job을 aggregate required check에 결박한다. (완료: 2026-08-24, codex)
      `aggregate-ci.yml`이 Web/packages 변경 시 `lint-typecheck-build`만 기다리고 `e2e`는 기다리지
      않아, `Aggregate CI gate`가 유일한 required check인 이 저장소에서 Playwright 실패가 머지를
      막지 못했다. Web 변경 조건에 `requiredChecks.push("e2e")`를 추가했다(주석에 T-323 인용,
      `.github/workflows/aggregate-ci.yml:88-91`). **tasks.md 정리 누락으로 열린 채 남아 있던 것을
      T-324와 함께 발견해 이동한다** — 코드는 이미 완료 상태였다(codex).

- [x] **T-324** — Google OAuth 런타임 배선 복원 + 라이브 검증. (완료: 2026-08-24, PR #467, codex)
      `infra/docker-compose.app.yml`이 `PINVI_GOOGLE_OAUTH_CLIENT_ID`/`_SECRET`을 API 컨테이너에
      전달하지 않아 `/auth/oauth/providers`가 Google을 disabled로 판정하고 있었다. compose 전달과
      `infra/.env.prod.example` 항목을 복원하고 계약 고정 단위 테스트(`test_oauth_runtime_config.py`)를
      추가했다. 2026-08-24 라이브 검증에서 API provider 응답의 Google 항목이 `enabled: true`이고,
      실브라우저가 `/login`에서 Google 버튼을 표시한 뒤 authorize 요청을 시작함을 확인
      (`LIVE_OAUTH_UI=passed provider=google button=visible authorize=started`). client secret과
      authorize URL 값은 기록하지 않았다. **tasks.md 정리 누락으로 열린 채 남아 있던 것을 이번에
      발견해 이동한다** — 코드·테스트·라이브 검증은 이미 완료 상태였다(codex PR #467).

- [x] **T-311·T-318** — 워크스페이스 전체 react 정렬로 `apps/mobile`의 react 중복과
      `expo-router` nest 문제를 함께 해소한다. (완료: 2026-08-25, PR #484, claude — 머지 대기)
      루트 `overrides`에 `react`/`react-dom`을 `19.2.6`(웹과 동일본) 단일 버전으로 고정하고
      `apps/mobile`의 `react`/`react-dom` 선언을 정확 버전(`19.2.3`)에서 caret(`^19.2.3`)로 풀어
      override가 실제로 먹히게 했다. **기존 `package-lock.json`을 남긴 채 `npm install`만 다시
      돌리면 override 값이 바뀌어도 이미 lock에 박힌 하위 트리는 재해석되지 않는다** — 이 사실을
      react가 여전히 `apps/mobile/node_modules`에 `19.2.3`로 남아 있는 것으로 실측했다.
      `package-lock.json`을 지우고 완전 재해석해야 실제로 단일본(`19.2.6`)이 된다.
      완전 재해석은 다른 transitive 패키지도 latest-satisfying으로 끌어올려
      `eslint-plugin-react-hooks`가 `5.2.0`→`7.1.1`로 건너뛰었고, 그 메이저에서 새로 추가된
      React Compiler류 규칙(`react-hooks/set-state-in-effect`, `react-hooks/refs`,
      `react-hooks/immutability`)이 web 전역 36개 파일에서 새로 실패해 lint를 깨뜨렸다 —
      `eslint-config-next`가 실제로 요구하는 범위는 `^5.0.0`뿐이라 관련 없는 회귀임을 확인하고
      루트 `overrides`에 `eslint-plugin-react-hooks: 5.2.0`을 추가로 고정해 원래 버전으로
      되돌렸다. 검증: `expo-doctor`가 react/react-dom 중복 신호를 더 이상 내지 않음(잔여 2건은
      SDK-56 patch 드리프트·Hermes V1 회귀로 T-352로 분리), `expo-router/_ctx-shared` 모듈
      해석이 root 배치만으로 성공(T-318의 심링크 우회 불필요), mobile
      `typecheck`/`lint`/web `typecheck`/`lint`/`build` 모두 통과. 개발 환경 메모: 이 worktree의
      `npm install`이 WSL2 DrvFs(`/mnt/f`) 위에서 대량 파일 삭제·교체 시 `ENOTEMPTY`/`EACCES`
      rename 경합을 반복적으로 냈다 — `node_modules` 삭제는 Windows 네이티브
      `Remove-Item -Recurse -Force`로 재시도해 우회했고, 남은 npm 임시
      rename 디렉터리(`.<pkg>-<hash>`)를 정리한 뒤에야 install이 안정됐다.

## 2026-08-24

- [x] **T-339 / T-340** — 실패한 retention이 매달리지 않고, 영수증이 진실을 말하게 한다.
      (완료: 2026-08-25, PR #476, claude)
      **티켓의 교착 서술은 틀렸다.** "최종 UPDATE가 실패하면 원래 트랜잭션이 락을 쥔 채…"는 성립하지
      않는다 — PostgreSQL은 ROLLBACK 수신이 아니라 **오류 발생 시점에** 행 락을 푼다(조사가 실측:
      abort된 백엔드의 락이 0으로 떨어지고 다른 세션의 UPDATE가 0.02초에 성공).
      **그러나 hang은 실재하고 창이 다르다**: `completed` UPDATE가 **성공한 뒤** 파이썬 예외가 나면
      트랜잭션이 살아서 `FOR NO KEY UPDATE`를 쥐고 있고, T-338이 넣은 별도 세션이 같은 행을 UPDATE하며
      영구히 블록된다. 대기 그래프에 간선이 하나뿐이라 PostgreSQL이 deadlock으로 탐지하지 못하고,
      이 프로세스에는 `lock_timeout`도 `statement_timeout`도 없다(확인). 지금은 도달 트리거가 없지만,
      T-339(b)를 고치는 순간 — 라우트 후단을 복구 대상에 넣는 순간 — 즉시 도달 가능해진다.
      해법은 별도 세션을 없애는 것이다. `record_retention_run_failure`가 **호출부 세션에서 먼저
      rollback**하고 기록한 뒤 commit한다. rollback 하나가 두 문제를 동시에 푼다 — abort 상태를 풀고,
      락을 놓아 hang 창을 없앤다. 두 번째 커넥션도 사라진다.
      `except`를 `BaseException`으로 넓혀 취소에도 영수증을 시도하되, 취소·인터럽트는 **래핑하지
      않는다**(중단 신호를 실패로 바꾸면 안 된다). 다만 이것을 성과로 과장하지 않는다 — 조사 결과
      현 배포에서 `CancelledError`는 클라이언트 끊김으로도 SIGTERM으로도 발생하지 않는다.
      라우트 후단(`append_admin_audit` + 최종 commit)을 try로 감싸 실제로 존재하는 유일한 `executing`
      잔존 경로를 닫았다. 자동 reaper는 **두지 않는다** — heartbeat가 없어 살아 있는 장기 run과 죽은
      run을 구분할 수 없고, 순진한 reaper는 감사 기록을 오염시킨다. 대신 runbook §5.1에 상태 어휘표를,
      §5.2에 stale 판정·수동 종결 절차를 넣었다.
      **T-340**: 기존 테스트는 실패를 순수 파이썬 예외로 만들어 세션이 abort가 아니었고, 그래서
      "같은 세션 + rollback 없이 commit"으로 퇴화해도 green이었다. 이름을 정직하게 바꾸고(견디는 것은
      호출부 rollback뿐), (a) DB CHECK 위반으로 **진짜 abort**를 만들어 영수증과 **데이터 폐기**를 함께
      검증하는 테스트와 (b) `completed` UPDATE 직후 실패에서 **20초 타임아웃**으로 hang을 잡는 테스트를
      추가했다. 두 되돌림으로 각각 red가 되는 것을 실증했다.
      적대적 리뷰는 **주간 한도로 중단됐다** — 제기 40건 중 반증 검증을 마친 것은 1건뿐이다. 그
      1건(라우트 후단 복구 경로 무테스트)을 반영했고, 미검증 지적 중 직접 실증 가능한 넷을 함께
      고쳤다: `BaseException` 확대 **되돌림**(취소를 잡고 `await`하면 원래 예외를 가리거나 셧다운을
      지연시키는데, 이 배포에서 `CancelledError`는 발생하지 않아 얻는 것이 없다) · `finally`의 GUC
      리셋이 커밋 뒤 새 트랜잭션을 열어 세션을 `idle in transaction`으로 반환하던 것 · 실패 영수증이
      status 가드 없이 **커밋된 `completed`를 덮을 수 있던 것**(ack 유실 시 "아무것도 안 지웠다"를
      정반대로 새긴다) · 503 본문에 SQLAlchemy 예외 전문(SQL + 바인드 파라미터)이 실리던 것.
      나머지 미검증 지적은 T-342~T-346으로 등록했다.

- [x] **T-333 / T-335 / T-336 / T-337** — 확인자료가 실패·아카이브·스키마 변화를 견디게 한다.
      (완료: 2026-08-25, PR TBD, claude)
      **T-333**: 미들웨어가 `status_code >= 400`이면 감사를 통째로 건너뛰었다. 그 가드는 좌표를 query에서
      **추측**하던 시절의 대리 지표였고(T-330이 추측을 없앴다) 전제가 사라진 뒤에도 남아 있었다.
      "일어나지 않은 위치 사용을 적지 않는다"는 보증은 상태 코드가 아니라 **호출 순서**가 지킨다 —
      모든 선언 지점이 인증·입력검증·동의 게이트 뒤에 있다. 그리고 가드만 지우는 것으로는 부족했다:
      실측 결과 미처리 예외는 `call_next`에서 **raise되어** 와서 가드에 도달조차 하지 않는다. 상류에
      좌표를 보낸 뒤 터진 요청을 잡으려면 except/re-raise가 필요하다. 도달 불가였던
      `response.headers` request_id 폴백도 함께 제거했다(그 헤더는 바깥 미들웨어가 나중에 붙인다).
      **T-335**: 체인의 직전 행 조회가 active 테이블만 봐서, 아카이브 실행 후 (a) 확인자료 열람이
      **상시 `X-Chain-Broken`**을 보고하고 (b) 새 행이 `GENESIS_HASH`로 체인을 조용히 재시작했다.
      읽기 측만 고치면 오탐이 자리만 옮기므로 쓰기·검증을 `previous_content_hash` 하나로 합쳐
      아카이브까지 UNION으로 본다. 수정을 되돌려 테스트가 실제로 red가 되는 것을 확인했다.
      **T-336**: 아카이브에 append-only 트리거가 없어, 원본 삭제 후 **유일한 사본**이 되는 테이블이
      UPDATE/DELETE에 열려 있었다. 기존 가드 함수를 재사용하면 retention 예외 절이 원본으로 좁혀져
      있어 아카이브는 자동으로 완전 차단된다. `ENABLE ALWAYS`라 replica mode로도 우회되지 않는다.
      **T-337**: PII 익명화가 컬럼을 손으로 나열해 새 컬럼이 조용히 빠질 수 있었다. **지금 빠진 것은
      없다** — 21개 익명화 + 5개 보존 근거로 `app.users` 전 컬럼이 판단된다. 가드는 다음 컬럼이
      생겼을 때 사람이 반드시 한 번 판단하게 만든다.
      **T-338**(작업 중 발견, 함께 완주): 실패한 retention execute가 영수증을 남기지 않았다. 서비스가
      `failed` 행을 쓰긴 하지만 그것이 파괴적 작업과 **같은 트랜잭션**에 있어 라우트의 `rollback()`이
      함께 지웠다. 영수증 행을 먼저 독립 커밋하고, 실패 기록은 별도 세션에서 남긴다 — 원인이 DB
      오류면 원래 트랜잭션은 이미 abort라 같은 세션으로는 아무것도 못 쓴다. 세션 factory는 모듈
      속성으로 참조한다(이름 import는 테스트가 교체한 factory를 못 따라가고, 소비자마다 conftest를
      손봐야 하는 구조가 된다).
      적대적 리뷰(제기 27건/생존 8건)가 **이 PR이 새로 만든 성능 회귀**를 잡았다 — `IS NULL OR
      log_id < ...` 형태가 generic plan에서 Index Cond를 잃어 확인자료 열람이 체인 전체를 스캔한다
      (실측 0.26ms → ~100ms @1M행). `COALESCE`로 단일 부등식을 유지해 고쳤다. 또 선재 결함 하나를
      함께 닫았다: `X-Request-Id`가 UUID가 아니면 감사 행을 조용히 버려, **사용자가 헤더 한 줄로
      자기 위치 기록을 지울 수 있었다**. 서버가 새 id를 발급하고 로그를 남긴다. 잔여는 T-339·T-340.

- [x] **T-334** — 고칠 수 있는 403을 고칠 수 없는 것처럼 보이지 않게 한다.
      (완료: 2026-08-25, PR TBD, claude)
      **티켓 전제의 절반이 사실과 달랐다.** "프런트가 동의 재요청 흐름으로 연결하지 않는다"고 적혀
      있었지만, 웹(`FeatureMapView`의 "내 위치" → 동의 다이얼로그)과 모바일(`map.tsx`의 안내 카드 +
      Alert → `consent.grant()`)은 **이미 완전한 복구 흐름을 갖고 있다**. 그리고 서버 403을 트리거할
      수 있는 프런트 경로는 오늘 **하나도 없다** — 전수 확인 결과 `featureApi.nearby`는 UI 호출자
      0건, `MapSearchBox`는 좌표를 보내지 않아 near-me가 아니며, `/geo/reverse`·`POST /features/requests`는
      항상 `map_pick`을 선언한다.
      실재한 결함은 다른 곳이었다: 공용 `friendlyErrorText`가 **모든 403을 "이 작업을 수행할 권한이
      없습니다"로 덮어** 서버가 보낸 "위치정보 이용 동의가 필요합니다. 설정에서 동의한 뒤 다시
      시도해 주세요"를 버리고 있었다. 동의만 하면 되는 상태가 고칠 수 없는 권한 문제로 읽히는 것이며,
      이건 403이 도달하는 **모든** 화면에 지금도 해당한다. 사용자가 스스로 해소할 수 있는 403 코드는
      서버 문구를 그대로 쓰게 하고, 코드가 붙지 않은 403만 일반 문구로 떨어뜨린다. 판별은 공용
      `isLocationConsentRequired`가 맡는다.
      **호출부 배선은 일부러 하지 않았다** — 부를 수 있는 지점이 없어 죽은 코드가 되기 때문이다.
      near-me 검색이나 `/features/nearby`를 UI에 붙이는 작업이 그 배선의 임자이고, 그때 쓸 판별
      함수는 준비돼 있다.

- [x] **T-332** — 보존 아카이브가 확인자료의 무손실 사본임을 테스트가 지킨다.
      (완료: 2026-08-25, PR TBD, claude)
      `_ARCHIVE_LOCATION_SQL`이 컬럼을 명시 나열해서, T-329가 추가한 `coord_source`가 **오류 없이
      조용히** 빠진 채 아카이브되고 곧바로 원본이 삭제되는 구조였다. 손실은 두 겹이다 — 확인자료
      내용이 줄고, 아카이브 행의 `content_hash`가 그 값을 커밋하고 있어 **사본만으로는 재검증이
      불가능**해진다(아카이브는 원본 삭제 후 유일한 사본이다). 컬럼을 추가하고 INSERT/SELECT 나열을
      고쳤다. 핵심은 그다음인데, 같은 일이 반복되지 않게 `test_retention_archive_fidelity.py`가
      (a) 두 테이블의 컬럼 집합 일치, (b) INSERT 나열이 원본 컬럼을 모두 담는지, (c) 실제 한 행을
      아카이브해 사본만으로 원래 해시가 재현되는지를 강제한다. (a)만으로는 부족하다 — 컬럼이 있어도
      나열에서 빠지면 값은 복사되지 않고, 그게 실제 결함이 있던 자리다. (a)는 이름뿐 아니라 **타입**도
      비교한다 — 원본 `text`를 아카이브가 `varchar(n)`로 받으면 컬럼은 있는데 값이 조용히 잘린다.
      마이그레이션 0066은 0065와 같은 이유로 forward-only fail-close다. 조사가 선재 결함 3건을 더
      찾아 T-335(아카이브 후 `X-Chain-Broken` 상시 참) · T-336(아카이브에 append-only 트리거 없음) ·
      T-337(PII 익명화도 컬럼 명시 나열)로 등록했다.

- [x] **T-331** — 좌표 범위 두 개에 이름을 붙이고, 폴리곤을 도입하지 않기로 결정했다.
      (완료: 2026-08-24, PR TBD, claude, ADR-064)
      티켓은 "대마도가 bbox에 포함되니 폴리곤 판정이 필요하다"였는데, 조사 결과 **전제가 더 나빴다**:
      저장소에 lat 범위가 두 개(`33~43`, `33~39.5`) 있는데 어느 쪽도 무엇인지 적혀 있지 않았고,
      T-325의 지도 자동 센터링이 그중 **입력 유효 범위**로 "국내인가"를 판정해 한반도 북단
      (온성 42.95)까지 통과시키고 있었다. 두 범위에 이름을 붙여 정본화하고(`app/core/coord_range.py`,
      `@pinvi/schemas`의 `COORD_INPUT_BOUNDS`/`SERVICE_AREA_BOUNDS`), 센터링 판정을 서비스 범위로
      옮겼다. 폴리곤은 도입하지 않는다 — **어떤 위도선도 남북한을 가르지 못하기 때문이다
      (개성 37.97°N이 강원 고성 38.38°N보다 남쪽)**. 대마도는 이 성질의 한 사례일 뿐 상한 조정으로
      고쳐지는 문제가 아니다. 그래서 이 판정은 "국내인가"를 답한다고 주장하지 않게 바꿨고, 답하는
      것은 "지도를 여기로 옮길 만한가"다(틀리면 빈 지도를 볼 뿐이다). 정확한 판정의 소비자가
      생기면 경로는 폴리곤 파일이 아니라 kor-travel-geo 행정구역 조회다. 한계는 문서가 아니라
      테스트로 고정했다 — 대마도·평양·개성이 통과함과 개성 < 고성을 단언해, 폴리곤이 도입되면
      그 테스트가 red가 되어 결정을 다시 보게 만든다.

- [x] **T-329** — 확인자료가 좌표의 **출처**를 기록하고, 동의 게이트는 `device`에만 걸린다.
      (완료: 2026-08-24, PR TBD, claude, ADR-063)
      T-327이 `/regions/*`·`POST /features/requests`·`/geo/reverse`를 미게이트로 남긴 이유가
      "좌표 출처가 계약상 구분되지 않는다"였다. 구분이 없으면 선택지가 둘뿐인데 **둘 다 틀렸다** —
      전부 막으면 지도에서 POI를 고르는 기능이 깨지고, 전부 열면 철회한 사용자의 실제 위치가
      통과한다. `coord_source`(`device`/`map_pick`)를 계약에 넣어 그 갈림을 없앴다.
      `/regions/*`·`/geo/reverse`는 query로, `POST /features/requests`는 body로 출처를 받고
      기본값은 `map_pick`이다(현재 실사용 호출자가 전부 지도 클릭이라 기본값이 `device`면 기존
      흐름이 403으로 깨진다). `/features/nearby`와 `/search` near-me는 endpoint의 의미상 좌표가
      사용자 위치일 수밖에 없어 선언을 받지 않고 서버가 `device`로 고정한다 — 클라이언트가
      `map_pick`이라 우겨도 무시된다. `/geo/reverse`를 `reverse_geocode`로 실제 감사에 넣었다
      (문서 3곳이 오래 규정했지만 구현된 적이 없던 것 — T-330에서 문서를 정정했고, 출처를 적을 수
      있게 된 지금은 `map_pick`으로 정직하게 남길 수 있다). 해시 체인은 출처가 없을 때 payload
      **키 자체를 생략**해 과거 행의 재계산 바이트를 보존한다(`"coord_source": null`을 넣으면 이
      컬럼이 없던 시절 행 전체의 content_hash가 어긋난다). 한계는 ADR-063에 명시했다 — 출처는
      클라이언트의 선언이라 거짓말할 수 있고, 그럼에도 이 설계인 이유는 게이트가 막으려는 것이
      적대적 클라이언트가 아니라 **자사 클라이언트가 철회를 존중하지 않는 것**이기 때문이다.
      적대적 리뷰(전문 2인 × 3각도, 제기 39건)가 **차단 1건**을 잡았다 — 해시 payload를 쓰기 측에만
      추가하고 admin 체인 검증기를 놓쳐, 새 확인자료 행이 전부 `X-Chain-Broken`으로 보고될 뻔했다.
      위변조 탐지가 상시 켜지면 실제 변조와 구분할 수 없어진다. payload 구성이 두 곳에 복제돼 있던
      것이 근본 원인이라 `location_log_payload` 하나로 합쳐 재발을 구조적으로 막았다. 잔여는
      T-332(보존 아카이브가 컬럼을 버림)·T-333·T-334로 승계했다.

- [x] **T-330** — 위치 감사가 **핸들러가 선언한 좌표만** 기록한다. (완료: 2026-08-24, PR TBD, claude)
      미들웨어가 query string(`lat`/`lng`/`lon`/`latitude`/`longitude`)을 추측해 읽던 것을 없애고
      `request.state.location_audit_coord`를 유일 정본으로 삼았다. 추측은 확인자료를 세 방향으로
      오염시켰다 — (a) 핸들러가 무시한 파라미터를 "썼다"고 적었고(`/search?q=&lat=`의 거짓 Kakao
      제공 기록, `/features/in-bounds`의 뷰포트를 사용자 위치로 기록), (b) 별칭 우선순위가
      `lng`→`lon`이라 `?lon=127&lng=999`가 **핸들러와 다른 좌표**를 기록했으며, (c) `?lng=abc`의
      `InvalidOperation`이 `except ValueError`를 통과해 정상 200을 500으로 바꿨다. 대신
      `/features/nearby`·`/regions/*` 핸들러가 좌표를 명시 선언하게 하고 경로별 감사 여부를 통합
      테스트 8건으로 고정했다 — 기존에는 이 경로들의 감사를 단언하는 테스트가 하나도 없어, fallback을
      지우면 법정 기록이 green인 채 사라질 수 있었다. 비유한 좌표(NaN/Infinity)는 enqueue 전에
      차단하고 drain 격리를 `Exception`으로 넓혀, 이미 적재된 poison 행이 T-328이 고친 "감사 전면
      정지"를 재현하지 못하게 했다. `viewport_query`/`weather_at_coord`는 발행을 중단했다(뷰포트와
      feature 좌표는 개인위치정보가 아니다). 과거 거짓 행은 append-only 보증을 깨지 않기 위해
      삭제하지 않고 `lbs-act.md` §3.2에 정오표로 해석 규칙을 고정했다. 문서 정정: `/geo/reverse`의
      `reverse_geocode` 적재는 문서 3곳이 규정했지만 **구현된 적이 없다**.

- [x] **T-327** — 서버측 위치 동의 게이트와 약관 버전 정본. (완료: 2026-08-24, PR TBD, claude)
      `user-location.md` §2 "서버는 다음 요청부터 위치 추론·기록 거부"와 `api/users.md` §3.3
      "철회 → 사용자 좌표 응답 차단"이 미구현이라 게이트가 전적으로 클라이언트 책임이었다 —
      클라이언트를 우회하면 철회한 사용자의 좌표도 서버가 받았다. `ACCEPTED_CONSENT_VERSIONS`로
      서버가 약관 버전 정본을 갖고(기록 시점에만 대조 — 읽기에서 걸면 과거 버전 동의가 소급 무효),
      `assert_location_consent`/`require_location_consent()`가 T-326의 `has_valid_consents`
      하나만 호출한다. `/features/nearby`는 dependency, `/search`는 near-me 분기 안에서만 검사한다
      (dependency로 걸면 좌표 없는 키워드 검색까지 막힌다). `lbs_tos`+`location_collection` 둘 다
      요구해 프런트 `hasLocationConsent`와 판정을 일치시킨다.
      적대적 리뷰에서 미게이트 경로 3종과 미들웨어의 부분 좌표 감사, 국내 판정 bbox 잔여를
      T-329·T-330·T-331로 승계했다.

- [x] **T-326** — 동의/철회 이벤트 이력을 남겨 재동의가 철회 사실을 지우지 않게 한다.
      (완료: 2026-08-24, PR #471, claude)
      `app.user_consents`는 `(user_id, consent_type, version)` PK의 현재 상태 테이블이라 재동의가
      같은 row를 in-place로 되살려(`withdrawn_at → None`) 철회 사실이 사라졌고, 이용약관 제4조의
      "동의 이력 기록" 고지가 거짓이었다. 현재 상태 테이블은 그대로 두고 append 전용
      `app.user_consent_events`를 신설했다(다행 전환은 설정 화면의 첫 행 선택과 마케팅 게이트를
      반전시킨다 — ADR-062). 마이그레이션 `0063`(DDL)·`0064`(백필, 복원 가능한 것만).
      곁들여 `record_consents`가 매 PUT마다 `agreed_at`을 덮어쓰던 것과 `list_user_consents`
      정렬이 버전 상승 시 옛 행을 표시하던 잠복 버그를 고쳤고, T-327이 쓸 `has_valid_consents`
      읽기 choke point를 만들었다. 적대적 리뷰가 downgrade의 증빙 삭제와 모델 주석의 **사실과
      다른 근거 2건**을 잡아 함께 정정했다.

- [x] **T-328** — `/search` 감사 purpose를 DB 계약에 맞추고 drain을 행 단위로 격리한다.
      (완료: 2026-08-24, PR #470, claude)
      미들웨어가 `third_party_place_search`를 발행하는데 `ck_location_access_log_purpose`는 6종만
      허용해 체인 적재가 거부됐고(라이브 DB에서 재현), drain이 배치를 한 트랜잭션으로 커밋해
      위반 1건이 배치를 abort → `_drain_loop`가 같은 head 행을 무한 재시도 → **`/search` 좌표 요청
      한 번이 이후 모든 위치 감사 기록을 영구 정지**시켰다(위치정보법 §16 확인자료).
      마이그레이션 `20260824_0062`로 제약을 7종으로 넓히고(downgrade는 append-only trigger 때문에
      `NOT VALID`), drain을 SAVEPOINT로 행 격리했다. 새 purpose 추가 시 마이그레이션 누락을 잡는
      정적 계약 테스트와, 체인 테이블까지 확인하는 통합 테스트 2건을 추가했다(기존 테스트는 outbox만
      봐서 이 결함에도 green이었다). 적대적 리뷰가 head pin 재결박 누락과 `ruff format` red를 잡아
      함께 고쳤다 — 후자는 fail-fast 때문에 이 PR의 테스트가 CI에서 한 번도 돌지 않게 만들고 있었다.

- [x] **T-325** — 웹·앱 지도의 최초 중심점을 단말기 위치로 잡는다. (완료: 2026-08-24, PR #469, claude)
      `docs/architecture/user-location.md` §1이 "지도 초기 중심점(앱 진입 시), 시군구 수준(~1km),
      세션당 1회"를 사양으로 두고 §5에 폴백 체인까지 규정했으나 미구현이었다.
      게이트 순서를 계약으로 삼았다(`packages/domain/src/mapCenter.ts`): 권한(프롬프트 없는 조회) →
      동의 → 취득 → 국내 범위. 권한이 granted가 아니면 네트워크도 취득도 하지 않고, 자동 경로는
      어떤 모달도 띄우지 않는다. 국외 좌표는 센터링도 마커도 하지 않는다.
      **선행 블로커**: api-client가 서버에 없는 `/users/consents`를 호출해 동의 조회/기록/철회가
      전부 404였다(e2e mock이 옛 경로를 가로채 가려 왔다) — `/users/me/consents`로 정정.
      적대적 리뷰(전문 2인 × 3각도, 제기 30건)가 잡은 차단 3건(세션 캐시의 게이트 우회, 철회 후
      stale 동의로 좌표 취득, 모바일 타임아웃이 측위 결과 파괴)과 minor 지적을 모두 반영했다.
      검증: domain 24건 · 워크스페이스 typecheck/lint/test 45파일 · 웹 e2e 5건(프로덕션 빌드).
      파생: T-326(철회 이력 소실) · T-327(서버측 동의 강제).

## 2026-08-21

- [x] **T-321** — vitest 워커 기동 실패 시의 "조용한 누락" 조사와 CI 실행 범위 교정.
      (완료: 2026-08-21, PR #461, claude)
      **등록 당시 전제가 틀렸다**: 워커 기동 실패가 exit 0으로 끝난다고 봤으나, vitest는 그 오류를
      unhandled error로 모아 `Unhandled Errors` 블록에 파일명과 함께 출력하고 `process.exitCode = 1`을
      설정한다. 실제 문제는 **요약 줄(`Test Files 12 passed (12)`)이 실행된 것만 세어 과소 집계**하는
      것이며 CI가 거짓 green을 내지는 않는다(CI 이력 132 run 전수 조사에서도 누락 0건).
      전제 오인의 원인은 검증 하네스였다 — `wsl -- bash -lc "...; echo $?"` 형태가 바깥 셸의 `$?`를
      먼저 치환해 항상 0을 보고했다. 종료 코드는 스크립트 파일로 측정해야 한다.
      따라서 리포터 가드는 vitest의 기존 실패 신호를 중복하고 `reporters` 명시라는 유지 부담만 남겨
      **철회**했고, 조사 중 드러난 진짜 구멍만 고쳤다: CI가 `npm test --workspace @pinvi/web`만 돌려서
      `packages/{domain,schemas}`의 24파일 104테스트가 한 번도 실행된 적이 없었다. 루트 `npm test`로
      교체해 CI 보호 범위에 넣었고 세 워크스페이스 43파일 224테스트가 통과한다.
      요약 줄 과소 집계와 대응은 `docs/conventions/testing.md` §6.1에 남겼다.

- [x] **T-VN-42 — Map user OpenAPI 재vendor(`95d2c128`) 소비 정렬** —
  1차 묶음 **PR #451 머지 완료**(2026-08-19 KST). 스냅샷 SHA-256 `6a2ee0f9…`(Map `95d2c128`·`origin/main`
  284fd10c와 바이트 동일). consumer drift 2건을 흡수한다: ① 3축 feature state cutover(`1f2bdc3a`)로
  user 표면에서 사라진 `status` 소비 절단, ② bitemporal cutover(`6650aa71`)로 옮겨간 시점 조회
  (`…/weather/snapshot`, `target_at`/`known_at`)와 `WeatherCardData.asof` → `selected_at` 개명.
  곁들여 transport 시간대 정책을 하나로 통일했다(aware만 수용 + 라우터에서 KST 보정).
  - [x] user 표면 `status` 소비 절단 + **누출 방지 회귀 테스트**(단위/통합, 되돌리면 red).
  - [x] 시점 조회 snapshot 경로 복구 + query 계약 exact 핀(`/weather`는 빈 집합).
  - [x] 공개 문서 정정(`docs/api/features.md` §1.1·§2.3, `docs/integrations/kor-travel-map-rest-api.md`).
  - [x] **admin 표면 3축 정렬(PR #451)** — Map admin `AdminFeatureRecord`/
        `AdminFeatureDetailFeatureRecord`에도 `status`가 없다. `schemas/admin.py`가 이를 required로
        두고 있어 PinVi admin의 feature 목록/상세가 502 `FEATURE_SERVICE_BAD_GATEWAY`였고,
        `lifecycle_state`/`publication_state`/`quality_state` 3축 + admin client query 이름
        (`status`/`provider`/`dataset_key` → 3축/`provider_dataset_id`)으로 재배선했다.
  - [x] **user client query 폐쇄 게이트** — `_CLIENT_QUERY_PARAMETERS`가 `_CLIENT_PATHS` 전체를
        덮도록 폐쇄 단언을 걸고(면제 없음), "client가 스냅샷에 없는 query를 보내는지"를 MockTransport로
        보는 반대 방향 게이트를 신설했다. 그 구멍으로 살아 있던 `/v1/categories?active_only=` 전송을
        제거하고, Pinvi 표면의 `active_only`는 응답 `is_active`로 **로컬 필터**로 구현했다
        (공개/admin 두 라우터 + 문서 + 테스트). `_CLIENT_PATHS` 목록 자체도 client 소스의 `/v1/...`
        리터럴과 양방향 정확 일치를 강제해(정적 스캔) "목록에 안 적어서 검사도 안 되는" 구멍을 닫았다.
  - [x] **admin weather-values 경로 전환** — Map admin 전용
        `GET /v1/admin/features/{id}/weather`로 옮겨 비공개 feature도 조회한다. Admin upstream에는
        `asof` 계약이 없으므로 기존 query는 조용히 최신값으로 가장하지 않고 422로 거부한다. 각 metric의
        `provider_dataset_id`/`dataset_key`/`dataset_display_name`/`known_at` provenance도 보존한다.
  - [x] **admin 상세 `state_transitions`/`curations` 투영** — Map admin 상세가 주는 list는
        sources/issues/overrides/files/**state_transitions**/**curations**이고 Pinvi가 남겨 둔
        `versions`/`change_requests`는 늘 빈 배열이다. Web 상세의 거짓 0 카운트 칩은 제거했고, 두 list를
        표시용 안정 subset으로 투영하고 Web 상세에서 실제 개수를 표시한다. upstream 내부 lineage/link/
        audit 전체를 투명 proxy하는 계약은 아니다.
  - [x] **admin OpenAPI 스냅샷 vendoring** — PR #443이 Map `da2c740a`의 전체 Admin 스냅샷
        (SHA-256 `22e3f2f…`) byte pin과 ops dataset/pipeline 소비 게이트를 소유한다. T-VN-42는 같은
        스냅샷의 feature 경로·AdminBFF security·query exact 집합·응답 schema 연결·3축/state
        transition/curation/weather 소비 shape를 계약 테스트로 고정했다.
  - [x] **공개 `status` 필드 제거(breaking cutover)** — `FeatureSummary`/`FeatureDetail`/
        `DetailCardBase`(`app/schemas/feature.py`)와 Zod 미러(`packages/schemas/src/feature.ts`)에서
        항상 None이던 `status`를 제거했다. 저장소 안 소비처는 `FeatureMapView`의 `data-feature-status`
        DOM 속성 1곳뿐이었고 그 속성을 읽는 코드는 0건이라 표시 동작 변화가 없다. 재도입 방지는
        선언 등호 + OpenAPI 노출 부재(`tests/unit/test_feature_schemas.py`), 값 재주입 차단
        (`test_feature_detail.py`·`test_feature_mapping.py`·wire 레벨 integration), Zod 필드 집합
        (`apps/web/tests/featureContract.test.ts`) 3중으로 건다.
      (완료: 2026-08-21, PR #460, claude)

## 2026-08-19

- [x] **T-310** — issue #215 잔여 후속: POI mutation 낙관적 override + 롤백, 여행 생성/편집 날짜 검증,
      POI 예산 검증, 위치 동의 gate, `apps/mobile` lint/typecheck CI. (완료: 2026-08-19, PR #446, claude)
      Android 에뮬레이터(AVD `pinvi_api35`, API 35) + EAS `development` 빌드 `5a90f90c`로 Dev Client
      smoke를 실행해 완료 조건을 소진했다. 날짜 검증(범위·형식, 필드 귀속·편집 시 해제) · POI 재정렬
      (낙관적 반영이 서버 `sort_order`에 반영, API 다운 시 롤백 + 실패 표면화) · 파괴적 삭제
      (`confirmDestructive` 대상 이름 확인, 취소 무변경) · 예산 검증(`-100` 차단, `25000` 저장) 통과.
      위치 동의 gate는 로컬 VWorld 키 부재로 지도 표면에 도달하지 못해 코드 경로만 확인하고 T-320으로 분리.
      smoke가 드러낸 결함 1건을 같은 PR에서 고쳤다: RN 0.85.3 렌더러가 react 19.2.3 정확 일치를 요구하는데
      저장소가 19.2.6을 핀했고 `expo.install.exclude`가 그 드리프트를 가려 dev client가 부팅 즉시 죽었다
      (핀 19.2.3 + 예외 제거). WSL Metro ↔ Windows 에뮬레이터 절차는 `apps/mobile/README.md`에 고정했다.
      파생 task: T-311(expo-doctor 3신호) · T-318(`expo start` hoisting) · T-319(실패 문구) · T-320.

- [x] **T-316** — Hallmark 마지막 조각: 요청 수명 계약 + 모달 격리·확인 정책 + 여행 상세·설정·법무·
      지도·파일 표면. (완료: 2026-08-19, PR #455, claude)
      범위는 `apps/web` + `packages/api-client`. 조사 3인 매핑(48항목) 기준으로 5조각을 한 PR에 담았다.
  - [x] **(1/5) 요청 수명 계약 + 모달 오류 소유권** — api-client 5요구사항(타이머가 body 소비
        완료까지 유지·abort가 전 생애주기 전파·`status 0`으로 타임아웃과 서버 확정 4xx 구분·장시간
        admin 호출 9종 `timeoutMs: 0`·`Dialog.onCancelBusy` 취소 탈출구)과 6차 적대적 리뷰가 main에서
        잡은 잔여 결함 4건(일자 409 재시도 막다른 길·포커스 폴백 no-op·전역 오류 누수·날짜 오류 잔존).
  - [x] **(2/5) 모달 격리·확인 정책** — `useModalDialog` body portal + 스택 인지형 배경 inert
        (+ `focusable`이 inert 상속을 보게 수정), `RestoreHotswapDialog` 프리미티브 수렴(407→265줄,
        마지막 손복사 셸 제거), `window.confirm` 6곳·`window.prompt` 1곳 제거 → `ConfirmDialog`/
        사유 입력 Dialog(저장소 전역 native dialog 0건), e2e의 `page.on('dialog')` 5곳 재작성.
  - [x] **(3/5) TripDetail** — 4겹 컨테인먼트(패널→일자 카드→POI 카드→tinted 첨부/날씨, 320px에서
        유효 폭 −35.3% 실측) 해체와 중복 컨트롤(일자 추가 4곳·개수 배지 5곳·공유 2곳) 정리.
  - [x] **(4/5) 나머지 표면** — `FeatureMapView` 상시 오류 dl 삭제(모바일에서 지도의 33% 점유) +
        조건부 오류/로딩/빈 상태, `MapView` 디버그 dl 삭제, nav '지도'를 데모 셸 대신 실제 탐색
        지도(`/map`)로 교정, DSR/신고 raw JSON textarea → 일반 폼 필드(서버 자유형 record 위에 프런트
        계약을 세우고 전송 리터럴은 보존), 법무 measure 65ch·본문 16px·초안 배너 중립화·공개 chrome
        (`app/legal/layout.tsx`, 문서 간 이동 링크 0개 해소), 설정 4쪽의 admin chrome 분리
        (`components/app/SettingsSurface`: uppercase eyebrow h2·12px 표 헤더·카드 안 카드 제거,
        표 → hairline row 리스트, skeleton/빈 상태 CTA), 파일 화면 상태 UI(skeleton·회복 행동·44px·
        100건 절단 표시).
  - [x] **(5/5) Hallmark 잔여 이탈 종결** — 사용자 표면의 44px 미달 컨트롤 53곳을 `min-h-11`/`size-11`로
        올리고 컨트롤 라벨 12px → 14px, 입력 14px → 16px(iOS 자동 확대 방지). 재발 방지는 새 lint 가드가
        맡는다(T-317 흡수): `eslint.config.mjs`의 `no-restricted-syntax`가 토큰 우회(`bg-white`/`text-white`/
        `bg-black/`), 그림자 티어 이탈(`shadow-sm|md|lg|xl|2xl`), 임의 z-index(`z-[`), 임의 타이포(`text-[Npx]`),
        44px 미달 컨트롤을 **사용자 표면에서** 차단한다(밀도가 다른 `(admin)`은 제외). 마커 팔레트 인라인 색
        위 텍스트 3곳만 사유 주석과 함께 예외로 남겼다.
        ※ `eslint-plugin-tailwindcss` 대신 자체 규칙을 썼다 — 필요한 것은 클래스 정렬이 아니라 **토큰 정책
        집행**이고, 새 의존성 없이 DESIGN.md 규칙을 그대로 표현할 수 있다.

    적대적 리뷰 3인(모달·요청 수명 / 여행 상세·표면 / 회귀·문서)이 P1 2건을 실측으로 잡아
    반영했다: `/map` 지도 높이가 362px로 붕괴(flex 사슬 미연결 — nav '지도'를 이 페이지로
    승격시킨 직후라 더 뼈아팠다), 비멱등 POST 취소가 서버 처리를 되돌리지 못하는데 조용히
    닫혀 재시도 시 중복 생성. P2로 admin 익명화의 `timeoutMs: 0` + busy 잠금 조합 영구 잠금,
    `dayUpdateAbortRef` 도달 불가 분기, 지도 빈 상태 조기 표시, 신고 evidence field 잔존,
    파일 삭제 후 포커스 body 낙하, DESIGN.md 모달 계약 미갱신도 함께 해소했다.

- [x] **T-315** — Hallmark PR-4(모달 셸 수렴). (완료: 2026-08-19, PR #452, claude)
      `components/ui/Dialog.tsx` 프리미티브 신설
      (scrim/overlay/z-modal 토큰 + `useModalDialog` 내장 + 헤더/본문/푸터 슬롯 + busy 잠금),
      손복사 모달 8종 이관(`LocationConsentDialog`(focus trap 없던 것)·`NoticePlanCopyDialog`·
      `TripEditDialog`·`TripManualPoiDialog`·`FeatureRequestDialog`·`DaySettingsDialog`·`ConflictDialog`·
      `FeatureDetailModal`(sheet)), 임의 z-index
      (`z-[50]/[60]/[70]`) 전면 토큰화, 마커 팔레트 UI 오용(TripDayHeader 일출/일몰)·`bg-primary/10`
      accent tint 제거, 죽은 훅(`useEscapeKey`/`useDialogAutoFocus`) 삭제. `RestoreHotswapDialog`(admin
      파괴적 흐름)는 portal + 배경 `inert`까지 쓰는 더 강한 격리라 토큰만 맞추고 이관은 보류 — 훅에
      inert/portal을 추가하는 T-316에서 수렴. 적대적 리뷰 5라운드(10인): 중첩 모달 키보드 도달(ConflictDialog
      이관), 포커스 격납(focusout 기반 — focusin만으로는 body 낙하를 못 잡음), 닫힐 때 포커스 복원 폴백
      (남은 최상단 모달 → `returnFocusRef`), 모달 스택을 마운트 생명주기에만 연동, `FeatureDetailModal` sheet
      이관, 일자 설정 저장을 await해 성공에만 닫기(busy가 죽은 prop이던 문제) + 그에 따라 오류를 **모달 안**
      에 표시·저장 중 입력 잠금·409 reload가 열린 폼을 덮지 않게 리셋 effect 축소, 일자 삭제 확인은 요청 완료
      후 닫아 busy/포커스 복원을 살림, 충돌 다이얼로그 필드 토글도 저장 중 잠금(+disabled 시각 상태).
      5차: **일자 설정 lost update**(열려 있는 동안 들어온 서버 version으로 저장해 409 없이 남의 변경을
      덮던 문제) → 연 시점 version 스냅샷으로 If-Match 고정, 오류를 전역 `mutationError`에서 떼어 각
      다이얼로그 세션 소유로(열 때/닫을 때 초기화, 날짜 검증 오류는 해당 FormField에 연결), `ConflictDialog`
      에도 모달 안 오류 슬롯 추가, 삭제 성공 시 사라진 트리거 대신 일자 목록으로 포커스 복원, 색 팔레트
      disabled 시각 상태. **api-client 요청 타임아웃은 이 PR에서 뺐다** — 3차 리뷰가 헤더까지만 덮는 범위, 헤더 이후
      호출부 abort 미전파, 408(4xx)이 Idempotency-Key 폐기 로직을 오작동시켜 큐레이션 import를 중복 실행,
      admin 예산(restore 30분 < 서버 60분) 불일치를 실측했다. 설계를 갖춘 뒤 T-316에서 다시 넣는다.

## 2026-08-18

- [x] **T-314** — Hallmark PR-3: 앱 셸·대시보드·탐색 지도 재설계. (완료: 2026-08-18, PR #450, claude)
      `AppShell`: ground를 `bg-surface-soft`→`bg-canvas`, 모바일(<lg) 하단 탭바 신설(주요 4 + `더보기` 시트,
      `min-h-14`·safe-area, 320px 가로 스크롤 nav 폐기)·데스크톱은 ink 밑줄 탭 유지, main 하단 패딩으로 탭바 회피.
      `useMobileWebLayout`: UA 정규식(SamsungBrowser|Android|…) 제거 → `(max-width:1023px), (pointer:coarse) and
(hover:none)` 단일 미디어쿼리(SSR/클라이언트 판정 분기 해소, Mj9). eyebrow 5곳(`Trips`·`Notice Plans`·
      `Pinvi`(map)·`Pinvi`(map-shell)·`Settings`) 삭제, 탐색 지도/맵 셸의 장식 칩 6개 삭제(C13), 추천 shelf에 설명 1줄 추가.
      TripDashboard: 필터를 `role=tab/aria-selected`→`role=group`+`aria-pressed`(44px, Mj10), 목록 로딩은
      skeleton 3행, 오류는 목록 자리를 대체하는 패널(원인 + `다시 시도`), 빈 상태는 버킷별 문구 + `새 여행 만들기`
      CTA로 분리(Mj5~Mj7). e2e 셀렉터 동기(trips-dashboard).
      **적대적 리뷰 2인 반영**: (P1) main 하단 패딩이 `md:py-8`에 덮여 768~1023px에서 탭바가 콘텐츠를 가리던 문제 →
      하단 패딩을 `.app-shell-main`(+`--app-tabbar-h`)으로 분리; (P1) 저장 실패가 정상 로드된 목록을 지우던 문제 →
      `listError`/`formError` 분리(배너=쓰기, 목록 자리 패널=로드, 패널에 `role=alert`); (P2) `더보기` 시트를
      `<details>`→제어 `button aria-expanded/aria-controls`(라우팅·바깥 클릭·Escape로 닫힘, Blink disclosure
      시맨틱 상실 해소); (P2) 셸 모바일 판정을 `data-mobile-layout`으로 `useMobileWebLayout`과 일치(넓은 layout
      viewport 폰); (P2) 빈 상태 CTA의 죽은 `scrollIntoView` → 폼 노출 후 effect에서 스크롤+포커스, variant는
      secondary(채운 primary 1개 규칙); (P3) `/`·`/profile`을 탭바 1순위에서 더보기로 내림(셸 밖 dead-end),
      `/settings/*` 활성 매칭, 지도 페이지 `min-h-[calc(100dvh-120px)]` 상수 제거(셸이 높이 전달),
      NoticePlanShelf 필터·로딩·빈 상태를 `/trips`와 동일 계약으로 통일, DESIGN.md 잔여 이탈 갱신.
      회귀 e2e 신설 `app-shell-mobile.e2e.ts` 5건(768px 가림·시트 닫힘·1180px 모바일 셸·저장 실패·로드 실패).
      검증: typecheck 0, next lint 0, vitest 100, 관련 Playwright 27 passed/1 skipped, 375px 실렌더.

- [x] **T-313** — Hallmark PR-1b 토큰 우회 코드모드(apps/web 89파일, +328/−320, 로직·testid·문구 의미 변경 0).
      (완료: 2026-08-18, PR #448, claude)
      `bg-white→bg-canvas`(131), `text-white`(92)→색 채움 위 `text-on-primary`/ink·scrim 위 `text-canvas`(마커 팔레트
      인라인 색 위 3곳은 유지), 텍스트 있는 채운 `bg-primary` CTA→`bg-cta text-on-primary hover:bg-cta-hover`(DESIGN.md
      대비 결정), `bg-black/35~60`→`bg-scrim/50`, 모달·시트 `shadow-lg/xl`→`shadow-overlay`·드롭다운/카드→`shadow-card`,
      미정의 `bg-surface`(4)→`bg-surface-soft`, 사용자 문구 `...`→`…`(e2e/vitest 어서션 동기), `min-h-screen/h-screen/
vh`→`dvh`(풀스크린 지도 표면 `100svh`는 유지), `text-[10~24px]`→스케일, 본문 `text-muted-soft→text-muted`, 일부
      버튼은 `buttonClassName`으로. 검증 에이전트가 잡은 4건(지도 svh 회귀·컨텍스트 메뉴 shadow 티어·업로드 label
      cta·admin 다이얼로그 표면·설정 인라인 버튼 크기) 반영. typecheck/lint 0, vitest 100, next build 통과.

- [x] **T-312** — Hallmark 감사(웹 7표면 13C/26M/19m) → 디자인 시스템 잠금 + 공개 표면 재설계(PR-1+PR-2).
      (완료: 2026-08-18, PR #447, claude)
      `DESIGN.md` "Hallmark 잠금 시스템"(modern-minimal · Narrative Workflow/Workbench/Long Document · N1/Ft2 · OKLCH
      토큰 · 대비 결정 `cta`=#e00b41 4.9:1 · 모션/상태/CTA voice/허용 범위/exports) 추가; `@pinvi/design-tokens`에
      `cta`/`cta-hover`/`focus`/`shadow-overlay`/`zIndex` + `spring` 삭제 + Pretendard Variable; globals에 self-host
      폰트·`overflow-x: clip`·keep-all·outline `.focus-ring`·`.checkbox`; `components/ui/Button.tsx`(8상태·44px) +
      `FormField/Select/TextArea` `inputClassName`; `PublicMasthead/PublicColophon/Wordmark`; 랜딩 Narrative Workflow
      재구성(3카드·내부 문구 삭제), (auth) 레이아웃·로그인·회원가입(전문 링크·20px 체크박스·disabled 사유)·
      verify-pending 재발송·verify-email, 공유 뷰 chrome/오류 상태, `FullPageMessage`/404 flat + chrome, `AppShell`
      워드마크·밑줄 탭, favicon/앱 아이콘/themeColor Rausch·canvas. 검증: typecheck/lint 0, vitest 100, build,
      e2e 9, 375/1280 실렌더. 적대적 리뷰 2인. 후속 T-313~T-316.

## 2026-08-06

- [x] **T-VN-41-F1D-C1b** — PinVi seven-image provenance. (완료: 2026-08-06, PR #442, codex)
      n150 F1D candidate가 `pinvi-web image source revision label is invalid`로 fail-close한 원인은
      API만 OCI provenance label을 갖고 Web·Dagster build가 revision/environment argument를 받지 않은
      데 있었다. 세 final Docker image가 하나의 validator로 exact commit을 검증하고
      `org.opencontainers.image.revision`·`io.pinvi.build.environment` label을 기록하게 했다. tag
      TOCTOU 지적을 반영해 검증된 image ID를 `PINVI_*_IMAGE` override에 고정하고 기동 뒤 container
      `.Image`를 재대조한다.

- [x] **T-VN-41-F1D-C1a** — PinVi 후보 migration head 정적 검사. (완료: 2026-08-06, PR #441, codex)
      `pinvi-admin-bootstrap head`가 revision module을 실행하지 않는 AST literal graph로 exact 단일
      head를 JSON으로 반환하고, dynamic·0개·복수·CWD decoy·설정 오류는 raw 경로나 credential을
      반사하지 않는 typed fail-closed error로 종료한다. DB session/DSN/credential file에 진입하지 않는다.

## 2026-08-04

- [x] **T-VN-41-P** — n150 격리 generation 7 cache-target paired live 증명.
      (완료: 2026-08-04, PR #427, codex) Map `96efac2494694bd504fb1f52b5d79388a2585db1`와
      PinVi `20b225131de990fd907dbf6148ddcb875bf36ca7`, generation `7`, service OpenAPI SHA-256
      `622ea54c98e9b0c09592cf84aced36227992c6bdf256742a3532b892f0efccf2`의 full-ancestry preflight를
      통과했다. command/consumer token 교차 호출은 각각 `403`이었다. fixture를 initial cutover 전에
      durable outbox에 넣어 `published=1`, count `1` fixed snapshot을 만들었고, causal canary는
      PUT→event→ACK→cache generation→DELETE 및 cursor/count/Merkle 수렴, command pending/leased/dead `0`을
      secret-free receipt로 확인했다. n150 Playwright Docker runner의 실제 admin 로그인·BFF-only recovery
      UI는 `1 passed (53.9s)`였으며 dead-letter replay와 reconciliation 뒤 backlog/dead `0`, ready checksum에
      도달했다. 같은 실제 claim을 local commit 뒤 한 번 더 적용해 cache generation이 `3→4→4`로 유지되는
      duplicate inbox 불변식도 확인했다. restore fence는 epoch `1→2`, active claim 1건 무효화, old ACK `409`
      거부 후 새 fixed snapshot·cursor의 ready 수렴까지 통과했다. 모든 실행은 별도 Docker network/DB와
      loopback-only UI binding에서 했고, 운영 consumer enable·final boundary·docker-manager manifest는
      변경하지 않았다. 종료 뒤 테스트 container/volume/image/임시 credential·browser 상태를 폐기했다.

- [x] **T-VN-SEC-03** — `npm audit` high 7→0 (next-전파 transitive + build-tooling transitive 정리).
      (완료: 2026-08-04, PR #426, claude)
      (1) in-range 표적 update 4종: brace-expansion 1.1.14→1.1.18(+nested 5.0.9), form-data 4.0.5→4.0.6,
      js-yaml 4.1.1→4.3.1, shell-quote 1.8.4→1.10.0 — 전부 DoS/CRLF-injection high. `npm audit fix`는
      Expo peer graph ERESOLVE로 불가라 `npm update <pkg>` 표적 실행. (2) next-전파분: next 15.5.22가
      exact-pin한 build-time postcss@8.4.31(fixed >8.5.22)은 nested lock 항목 제거로 root postcss@8.5.23에
      dedupe, 미사용 optional sharp@0.34.5(fixed ≥0.35.0, 앱 `next/image` 미사용)는 sharp/@img 27항목
      lock 제거로 미설치화. **npm 버전-키 overrides는 stale lock 항목 재해석에는 미반영이라 수술이
      필요했지만, lockfile 재생성 시에는 정상 적용됨을 리뷰에서 재현** — package.json overrides가
      재생성 경로의 실질 가드이므로 삭제 금지. 최종 상태는 npm 10/11 재해석-안정(up to date). lockfile
      의미 diff 검증(리뷰 수치 정정): 제거 55(sharp 계열 27 + nested postcss 1 + esbuild optional-peer
      27), 버전변경 8(표적 4 + transitive 4), 추가 0, 순서 동일 + 리뷰가 잡은 fsevents `dev:true` 유실
      1건 복원. 검증: fresh `npm ci` exit 0 → web build(Compiled
      successfully, 57 static pages)/lint 무경고/vitest 100 + domain 79 + schemas 13 + web·domain·mobile
      typecheck 0. 잔여 13 moderate는 전부 Expo SDK-56/maplibre major graph(Sprint M-1 이관), next-intl
      moderate는 별도 major. 적대적 리뷰 2명.

- [x] **TDR-mobile** — TDR day 표시(day-color/공휴일/일출·일몰)를 `apps/mobile`에 mirror.
      (완료: 2026-08-04, PR #425, claude)
      웹 전용이던 `apps/web/lib/tripDateLabels.ts`의 순수 포맷터 6종(formatTripDate/formatKstTime/
      holidayLabel/holidaysByDate/formatTripDateWithHoliday/formatTripDateRange)을 `@pinvi/domain`
      `tripDateLabels.ts`로 이관(ADR-011 §2.1 platform-agnostic)하고 웹은 re-export로 호환 유지(호출부
      5곳 무변경). 신규 `apps/mobile/components/TripDayHeader.tsx`가 웹 `TripDayHeader`(ADR-055 §6, F8)를
      RN으로 미러: 일자 팔레트 색 swatch(`paletteHex(marker_color)`) + `effective_date` 라벨 + 기간 벗어남
      뱃지 + 공휴일 뱃지(dedup) + 일출/일몰(success시 KST HH:MM + 기준 라벨, `pending_*`시 "준비 중",
      failed/null 미표시). 여행 상세 + 익명 공유 화면 양쪽 소비. domain vitest 7종 신설(KST +9h 변환 포함).
      검증: domain typecheck+vitest, web typecheck+lint+vitest 97(re-export 경유), mobile typecheck,
      전체 prettier clean. `formatKstTime`의 `Intl.DateTimeFormat(timeZone: 'Asia/Seoul')`은 Expo SDK 56
      Hermes ICU 지원 전제(문서화된 가정). 적대적 리뷰 2인이 P1/P2를 잡아 반영: (P1) `marker_color`는
      override 전용(null=기본)이라 회색 fallback이 렌더되던 것을 신규 `resolveDayMarkerColor`(서버
      `resolve_day_marker_color` 미러, 인덱스 기본색 16 순환)로 해석; (P2) `formatTripDate`가 date-only를
      기기 timezone으로 포맷해 UTC 서쪽에서 하루 밀리던 것을 `timeZone:'UTC'` 고정으로 수정(웹 latent
      버그 동시 해소). 반영 후 승인.

## 2026-07-31

- [x] **T-VN-20 / issue #394** — kor-travel-map 공개 API key의 header-only 소비 전환.
      (완료: 2026-07-20, PR #395, codex)
      URL의 `key` query를 제거하고 public read allowlist에서만
      `X-Kor-Travel-Map-Api-Key`를 전송한다. service token 우선순위와 batch의
      ServiceToken-only 경계를 고정했으며, Map PR #794 merge commit의 전체 user OpenAPI를
      SHA-256 및 byte equality로 vendor했다. focused **32 passed, 4 skipped**, API unit
      **616 passed, 1 skipped**, Ruff·strict mypy·Compose·CI가 통과했고 단일 적대적 리뷰가
      P0~P2 없음으로 승인했다. PR #395 merge commit은 `e60d1711…`이며 issue #394는 병합 뒤
      닫혔다. 후속 n150 production 경계 검증에서도 public key의
      valid **200** / wrong **401** / revoke **200** / revoked **401** lifecycle을 확인했다.

- [x] **T-VN-03-P / issue #392** — 잔여 관측 read caller의 `ops:read` principal 결선.
      (완료: 2026-07-27, PR #393·#408, codex)
      `consistency/{issues,reports}`, `system-logs`, `api-call-logs` 네 caller를 닫힌
      `ops:read` registry로 전환하고 Admin BFF/service/actor fallback 부재와
      `/ops/metrics`·`health-deep` direct caller 부재를 계약으로 고정했다. PR #393
      merge commit `61820f0a…`와 cancel 음성 계약을 보강한 PR #408 merge commit
      `6a035695…`가 main에 반영됐다. n150 production exact pair
      (Map `c8ed6164…` / PinVi `6a035695…`)에서 PinVi container-origin
      `GET /v1/ops/consistency/reports`가 `ops:read`로 **200**, token 없이 **401**을
      반환해 운영 활성화를 실증했고 issue #392를 닫았다.

- [x] **T-ADM-C6c** — canonical dataset/pipeline caller와 production compatible-pair 활성화.
      (완료: 2026-07-27, PR #387·#393·#408, codex)
      삭제된 Dagster/provider/import-job 호출을 `/v1/ops/datasets`와
      `/v1/ops/pipeline/{overview,executions}` 및 canonical cancellation으로 clean-cut하고,
      read/cancel principal 분리, 취소 reconciliation, schedule source degraded projection을
      완결했다. PR #387 merge commit `1b833ce8…` 뒤 #393/#408의 잔여 principal 계약까지
      반영했으며 API unit/integration·Ruff·strict mypy·Web lint/typecheck/Vitest/build와 CI가
      통과했다. n150 production에서 exact Map/PinVi source pair와 healthy runtime을 확인하고
      public/ops/debug principal 경계 **14/14**를 통과했다. 삭제 route 복원·shim·route policy
      예외는 모두 0건이며, 이 운영 증거로 canonical caller와 production activation 완료 조건을
      닫았다.

## 2026-07-30

- [x] **T-VN-16C** — PinVi 다중 날짜 weather batch 소비 전환.
      (완료: 2026-07-30, PR #421, codex)
      Map PR #902의 sparse `targets[{target_at, feature_ids}]`와 target-local
      `cards[]`/`card_key` 계약을 한 Trip view당 `POST /v1/features/weather/batch` 1회로
      소비한다. target 366개·target당 ID 200개·전체 pair 2,000개·
      `pair + 5 × unique feature` planning work 2,500·ID 256자 상한을 전송 전에
      검증하고, target/card/item 순서·정확한 참조 집합·metric 타입과 aware datetime을
      fail-closed한다. 성공 응답을 전부 decode한 뒤에만 투영하며 transport·timeout·계약
      실패는 미결 weather 전체를 `unavailable`로 둔다. 날짜별 worker fanout과 31일 상한,
      `not_requested` 상태를 제거했으며 10초 view budget과 부모 cancellation 전파는 유지한다.
      Trip 응답은 일자별 `weather_cards`와 feature별 `found(card_key)`로 정규화해 같은
      기상 격자의 metric payload를 feature 수만큼 반복하지 않으며, 누락·고아 참조를 거부한다.
      DST 전환일의 1일 horizon은 응답의 고정 offset을 기준으로 검증한다.
      소유자와 공유 여행 화면이 같은 정규화 계약을 렌더하며, producer OpenAPI의 제약 없는
      `card_key`를 임의로 좁히지 않는다. 적대 리뷰 2인의 최종 재검토는 P0~P3 0건이다.
      vendored OpenAPI는 Map main `94ace1a9…`, SHA-256 `0a7cabb3…`에 고정했다.
      n150 재사용 `ktm-tvn45-db`의 40일·45 POI 파괴적 Live UI에서 한 view당 weather POST
      1회, 다섯 parent 상태, weather found/no_data, weather-only 503→복구, 단건 weather
      0회, 40일차 API 상태와 UI arm 일치, 활성 Trip 잔존 0건을 최종 **1 passed (11.9s)**로
      확인했다. schema migration·새 clone·checkpoint·downgrade는 만들지 않았다.

- [x] **T-VN-16B** — PinVi weather batch 소비 cutover. (완료: 2026-07-30, PR #420, codex)
      Trip view가 unique `effective_date`별로 `POST /v1/features/weather/batch`를 호출하고
      날짜 안의 feature를 200개씩 dedupe한다. 브라우저 단건 N+1은 제거했으며
      `found|no_data|retired|suppressed|missing|unavailable|not_requested`을 day-scoped
      discriminated union으로 전달한다. 고유 날짜 31개·worker 4개·전체 10초 상한과 부모
      요청 취소 전파로 outbound를 제한하고, 상한 초과와 실제 장애를 구분한다.
      strict transport decoder와 vendored Map OpenAPI field contract, query-count integration,
      pure UI 상태 test, 단건 요청 0회 mocked Playwright를 고정했다. 적대 리뷰 2인이 날짜
      fanout·경계값 500·거대 JSON 정수·KST metric 선택·lifecycle 의미 소실·Live false-green·
      부모 취소 orphan을 찾아 회귀와 함께 수정했다. 최종 실데이터 Live와 CI·merge evidence는
      재사용 `ktm-tvn45-db`에서 여섯 parent 상태, weather found/no_data/retired,
      weather-only 503→복구, 단건 weather 0회를 UI로 통과했으며 활성 Trip 잔존은 0건이다.
      CI·merge evidence는 PR landing 뒤 journal에 보강한다.

- [x] **T-VN-11-P** — kor-travel-map 5상태 batch typed consumer 전환.
      (완료: 2026-07-30, PR #419, codex)
      `found|retired|suppressed|missing|unchanged`와 PostgreSQL `bigint` revision을 strict
      decode하고, `1..200` chunk·bounded LRU·generation/revision fence로 최신 상태의
      out-of-order rollback을 막았다. transport 실패만 stale snapshot을 `unverified`로
      재사용한다. Web·Map·Mobile 공용 resolver와 canonical `coord` snapshot을 적용했다.
      독립 적대 리뷰가 지도 마커 소실·cache rollback·동일 revision 복구를 막는 negative
      fence·chunk 상한·생산자 DB 장애 500 누출·실패한 planner gate·문서 drift를 찾아 모두
      보강했다. n150 재사용 실데이터 DB의 다섯 상태·503·복구와 지도 포인트 4곳을 파괴적
      Live UI로 통과하고 fixture·격리 자원을 정리했다. Map 생산자와 저장소별 호환 PR 쌍으로
      Map → PinVi 순서에 따라 landing한다.

- [x] **T-VN-08** — kor-travel-map batch 실패 false-broken 방지. (완료: 2026-07-26, PR #409, codex)
      `feature_resolution_state=not_linked|found|missing|unverified`를 도입하고 transport·인증·계약
      실패는 저장 snapshot을 유지한 `unverified`로 분리했다. 불투명 `feature_id` exact 왕복,
      중복 JSON member·비유한 수 fail-closed, n150 실데이터 정상→503→복구 Live UI를 검증했다.

## 2026-07-28

- [x] **T-VN-SEC-02** — `next` 15.5.18→15.5.22 보안 패치(web CVE 8건 제거). (완료: 2026-07-28, PR #414, claude)
      App Router Server Actions DoS(GHSA-m99w-x7hq-7vfj)·custom server SSRF(89xv-2m56-2m9x)·cache
      confusion(68g3-v927-f742, 4633-3j49-mh5q)·Edge unbounded payload(4c39-4ccg-62r3)·rewrite SSRF
      (p9j2-gv94-2wf4)·Image SVG DoS(q8wf-6r8g-63ch)·Server Function endpoint 노출(955p-x3mx-jcvp) —
      전부 `<15.5.21` fixed라 in-range 15.x 패치로 제거했다(`^15.5.21`). **SEC-01의 "Next 16 major" 전제
      정정**: npm audit union range(…-16.3.0-preview.7)를 오독한 것이고 실제 fix는 15.5.21. next
      typecheck/lint/build(57 static pages)/vitest(97) 통과, lock diff는 next+`@next/*` subtree 한정.
      npm audit `next high` 잔존은 next가 exact-pin한 build-time postcss@8.4.31 + 미사용 optional
      sharp@0.34.5 전파분(앱은 `next/image` 미사용·자체 postcss 8.5.23, exploit 불가). **global** override는
      next exact pin과 충돌해 "invalid overridden"으로 미적용됐고(scoped nested override는 미시도), 전파분은
      T-VN-SEC-03로 이관. 적대적 리뷰 2명 승인(추가로 리뷰어가 GHSA-6gpp-xcg3-4w24 middleware-bypass는
      16.x 전용이라 Next 16行이 오히려 더 취약했을 것임을 확인).

- [x] **T-VN-STYLE-01** — Prettier baseline 일괄 포맷(포맷 207개). (완료: 2026-07-28, PR #413, claude)
      `npm run format:check`가 실패하던 baseline 중 포맷 전용 207개(TS/TSX 108·MD 92·JSON/JS 7)를 정리했다.
      TS/TSX는 AST 보존(typecheck+lint+vitest 통과), JSON/JS는 값 바이트 동일, MD는 따옴표/표 패딩/코드펜스
      JS/빈 줄 정규화(산문 손실 0). **Vendored 파일은 byte-fidelity 위해 `.prettierignore`로 제외**(12개):
      (1) **P0 자체 차단** — `apps/api/tests/contract/`는 `test_kor_travel_map_contract.py`가 SHA-256
      (`91b30f40…`)으로 핀 고정한 upstream 스냅샷이라 재포맷이 핀 해시를 깼다 → 원본 복원 + ignore.
      (2) `.agents/skills/`·`.claude/skills/` — timescale/pg-aiguide vendored skill 세트(`> 원본:` 프로버넌스)
      11개를 원본 바이트로 복원 + ignore(재-vendoring diff noise 방지). `.claude/agents/*.md`는 마커 없는
      repo-owned이라 포맷 유지. 적대적 리뷰 2명(byte-sensitive-consumers·scope-ignore-completeness) 승인.
      `git diff --check`/format:check clean.

- [x] **T-VN-SEC-01** — `npm audit` critical 제거(vitest v2→v4 일괄 전환). (완료: 2026-07-28, PR #412, claude)
      critical은 dev direct dependency `vitest<=3.2.5`. apps/web·packages/domain·packages/schemas 3개
      workspace를 `vitest@^4.1.10`로 올렸다. vitest 4는 rolldown-vite/oxc를 쓰는데 esbuild 기반
      `@vitejs/plugin-react`가 주입한 JSX 옵션이 무시돼 `.tsx` 7개 suite가 import-analysis parse에서 깨졌다.
      plugin-react를 제거하고 `oxc.jsx`(automatic runtime, importSource react)로 대체했다. v3에서 삭제된
      `environmentMatchGlobs`도 jsdom 단일 환경으로 정리했다. audit 25→20(critical 0). 잔여 20(high 7/
      moderate 13)은 `next` 15→16 major와 Expo SDK-56 build-tooling transitive뿐이라 breaking →
      T-VN-SEC-02/T-VN-SEC-03로 분리했다. 검증: web 97 / domain 65 / schemas 8 vitest pass, web
      typecheck+lint pass, lockfile에 sub-v4 vitest 잔존 0. 적대적 리뷰 2명(correctness·security-scope)
      승인, P3 stale comment 1건 반영.

- [x] **T-WS-C7** — trip WebSocket reject close code가 프록시 edge를 넘게 settle. (완료: 2026-07-28, PR #410, claude)
      reject(`accept→close`)에 env-tunable settle(기본 0.25s)을 넣어 101 handshake를 flush → close
      code(4401/4403/4408/4429)가 리버스 프록시 edge를 건너 살아남는다. 미적용 시 브라우저 1006 오분류.
      kor-travel-map C7 #809/#820 동일 계층 포팅. 미인증 reject flood 동시 settle cap(기본 64)으로 FD 증폭
      차단. 적대적 리뷰 2명(P2 DoS cap·P3 test-order) 반영. edge-특정 검증은 prod(map #868 해제 후).

- [x] **T-307(후속)** — 색/이름만 바꾸는 일자 업데이트에 날짜 강제 제거. (완료: 2026-07-28, PR #411, claude)
      `TripDetail.handleUpdateDay`가 `date` 미변경 시 날짜 검증·PATCH를 건너뛰게 해, 기간 있는 여행 +
      날짜 없는 일자에서 색만 저장할 때 "일자 날짜 필요" 오류가 뜨던 friction을 제거했다. e2e 회귀 추가.

## 2026-07-21

- [x] **T-309a/T-309b** — 통합 검색 autocomplete + 외부 pick add-POI. (완료: 2026-07-21, PR #407, claude)
      T-309a: `MapSearchBox` `onSelect` union + address + source 아이콘 + 정렬 + debounce +
      attribution + back-link(F3-UI). T-309b: 외부 pick add-POI + best-effort auto-request UX +
      snapshot POI 렌더(F4-UI) + provider 파생 콘텐츠 미저장(§5.1). 두 task를 1 PR로 진행했다. ADR-054.

- [x] **T-308** — `TripDayHeader` — effective date + 공휴일 + 일출/일몰. (완료: 2026-07-21, PR #406, claude)
      신규 `TripDayHeader.tsx`와 SharedTripView 렌더(F8-UI, F1 empty-date). ADR-055.

- [x] **T-307** — 일자 색 picker + `display_marker_color` 지도/리스트 parity.
      (완료: 2026-07-21, PR #405, claude)
      `TripDayControls` per-day color picker + 지도 마커/리스트 뱃지 색 parity + PoiEditor F7 polish +
      fit-bounds 확인(F6/F7). ADR-055. 날짜 강제 friction 후속은 PR #411.

- [x] **T-306** — 일자 삭제 확인(F2) + 기간 벗어남 표시(F1). (완료: 2026-07-21, PR #404, claude)
      day-delete confirm은 T-306a의 `ConfirmDialog`를 소비하고, 기간을 벗어난 일자는 actionable
      배너/아이콘으로 표시한다. ADR-055/056.

- [x] **T-309c** — FeatureDetailModal 본문 + 마커→상세 모달. (완료: 2026-07-21, PR #402, claude)
      #396 shell 위 kind별 detail-card 본문(place/event/notice/price/generic) + 양 지도 마커→상세 모달
      (모바일 bottom-sheet, weather 제외) + 옵트인 Kakao/Naver enrichment UI(attribution+back-link,
      matched=false 처리). T-305와 병행(fork worktree agent) 후 cherry-pick verify + 링크 보안 검토 후 머지. ADR-056.

- [x] **T-305** — 일자 단위 일출/일몰 — `app.trip_day_rise_sets` + ETL asset.
      (완료: 2026-07-21, PR #401, claude)
      전용 table + Dagster asset + day-level rise/set read + batched re-seed + 완료 시그널. ADR-055.

- [x] **T-304** — feature detail-card kind별 투영 + 옵트인 외부 enrichment. (완료: 2026-07-21, PR #400, claude)
      `GET /features/{id}/detail-card` discriminated union(place/event/notice/price + generic) + 서버 투영
      (원본 detail/urls 미노출) + match-confidence 가드(정규화 포함/bigram + haversine ≤300m) + opt-in
      enrichment(place만, display-only) + in-bounds price. 단일 적대적 리뷰 오귀속 2건 반영. ADR-056.

- [x] **T-303** — 외부 pick feature-request 파이프라인. (완료: 2026-07-21, PR #399, claude)
      `source`/`external_ref`(POI+suggestion, 마이그레이션 0039), 전역 dedup(partial unique index),
      best-effort decoupled auto-fire(분리 세션·예외 미전파), post-approval reconciliation(external_ref→
      feature_id), 이미 added면 즉시 연결. 단일 적대적 리뷰 P2/P2/P3(교차사용자 note 미노출·auto-fire
      한도·require_review 문서화) 반영. ADR-054.

- [x] **T-302** — Kakao/Naver Local + 통합 `GET /search` source-tagged. (완료: 2026-07-21, PR #398, claude)
      표시 전용 provider client 2종(kor_travel_geo 미러, 부재/키 미설정=degrade), `GET /search`
      `{results: PlaceSearchResult[], degraded_sources}` 재작성(internal-first short-circuit +
      internal→kakao→naver + 소스별 degrade), "내 주변" 좌표 Kakao-only + location_audit
      third_party_place_search, `/features/search` 삭제, 순수 매핑(HTML strip·mapx/mapy /1e7). 단일
      적대적 리뷰 P1/P2(위치 감사 오기록) 반영. ADR-054.

- [x] **T-301** — TDR day 표시 모델 backend. (완료: 2026-07-21, PR #397, claude)
      `trip_days.date`를 override-only로 전환, effective_date 파생(materialize 3경로 폐지 + 마이그레이션
      0038), `core/markers.py`(일자 기본색+display 색), 일자 `marker_color` + POI `display_marker_color`,
      공휴일 effective_date 기준, DELETE day 409 `DAY_HAS_POIS`+`?force`, 공용 `trip_day_effective_locdate`
      (admin 경로 포함), copy 색 보존, py+zod 계약. 단일 적대적 리뷰 P3 3건 반영. ADR-055.

## 2026-07-20

- [x] **T-306a** — TDR 웹 모달 기반. (완료: 2026-07-20, PR #396, claude)
      공용 `useModalDialog` 훅(focus in/restore·Escape·body scroll-lock 참조카운트·Tab focus-trap·
      backdrop pointer-safe close·중첩 모달 topmost 가드·aria 배선) + 제네릭 `ConfirmDialog`(danger
      tone) + `FeatureDetailModal` shell(모바일 bottom-sheet 반응형, loading/error/children/footer).
      단일 적대적 리뷰 2라운드(2인)로 중첩 모달/focus-trap 누수/busy 포커스 3건 반영. 웹 unit 76 passed.

## 2026-07-19

- [x] **T-ADM-C7P** — PinVi API image provenance. (완료: 2026-07-19, PR #389, codex)
      exact source commit의 `git archive`만 immutable build context로 사용하고 Dockerfile·Compose·검증
      helper를 archive 내부 regular file로 제한했다. clean `HEAD`, build arg, OCI revision/environment
      label을 fail-closed로 결박하고, 검증한 image ID를 pin해 실행 container와 재대조하며 불일치한
      API/Web을 제거한다. 운영 node mutation은 명시적 `staging|production`에서만 허용한다. 단일
      적대적 리뷰 승인, focused unit 39개, 전체 unit 605개(1 skipped), Ruff/format/mypy/Bash/Compose와
      실제 production Docker 양·음성 검증 및 CI를 통과해 `1c5c89c`로 squash merge했다. 외부
      docker-manager의 동일 계약 연동과 N150 운영 실증은 cross-repo C6c/C7 gate에서 계속한다.

## 2026-07-11

- [x] **T-300** — Admin 메뉴 정렬 + 여행 날짜 공휴일 표시. (완료: 2026-07-11, PR #383, codex)
      Admin 좌측 메뉴 선택 항목의 세로 정렬 보정 + TripView day에 KASI 공휴일 metadata를 포함해
      여행 상세/공유/목록 날짜 UI에서 공휴일명을 표시한다. TDR(T-301~T-309c) 선행 작업.

## 2026-07-01

- [x] T-122 — Naver/Kakao OAuth provider 구현. (완료: 2026-07-01, PR #370, codex)
      기존 Google OAuth 흐름을 provider 공통 service/router로 일반화하고 Google 호환 wrapper를
      유지했다. Naver/Kakao start/callback/link/unlink를 `/auth/oauth/{provider}` 패턴으로 추가하고,
      Naver 신규 user는 `pending_verification` + Pinvi 인증 메일, Kakao 신규 user는 provider verified
      email 신호가 있을 때만 active 생성 정책으로 고정했다. Web 로그인/프로필 UI와
      `@pinvi/api-client`, `.env.example`, OAuth API/integration 문서를 함께 갱신했다. CI는
      api/web/mobile/e2e aggregate gate 통과, N150 Docker runner로 OAuth account-match target spec을
      별도 확인했다.

## 2026-06-30

- [x] T-259 — Release candidate gate / `v0.2.0`. (완료: 2026-06-30, codex)
      N150 배포 smoke, backup snapshot, 최신 main API/Web evidence, N150 Playwright Docker runner,
      Admin live 200/2000, restore staging drill, Admin live full catalog를 모두 닫았다. full catalog는
      `6343 tests in 5 files` 기준이며 N150 우선 실행 후 N150 runtime 한계 구간만 Windows fallback으로
      검증했다. `CHANGELOG.md`를 `v0.2.0` release 상태로 전환하고 tag/GitHub Release를 생성했다.

## 2026-06-29

- [x] T-270 — 성능 / 부하 / 보안 점검. (완료: 2026-06-29, codex)
      API에 `SecurityHeadersMiddleware`를 추가해 기본 보안 헤더와 API CSP를 적용했다. HSTS는
      production/HTTPS 요청에서만 붙이고, `/docs`/`/redoc`/`/openapi.json`은 CSP 예외로 둔다.
      반복 실행 가능한 gate로 `tests/load/api_p95_latency.py`와
      `tests/security/csp_cors_rate_limit.py`를 추가했으며, N150/Odroid 결과는
      `docs/runbooks/performance-security-gate.md` 기준으로 분리 기록한다.

- [x] T-266 — MCP 외부 인터페이스 운영 실증. (완료: 2026-06-29, PR #326, claude)
      MCP 서버(T-112)는 구현 완료였고, 기존 테스트는 토큰 lifecycle + list_trips만 다뤘다.
      `test_mcp_read_only_tool_scenario`로 read-only tool 5종(list_trips/get_trip/list_pois/
      get_user_profile/search_features) + 미존재 tool 404 + 잘못된 인자 422 + 회수 후 401을 자동
      실증(search_features는 KorTravelMapClient stub 주입). `scripts/verify-mcp.sh` 라이브 스모크 +
      runbook §8 운영 실증 체크리스트(클라이언트 등록/회수/감사) 추가.

- [x] T-286 — Cross-track review gap closure. (완료: 2026-06-29, claude)
      `docs/execplan/legal-ops-review-gap-crosswalk.md` §6에 closure 재감사를 추가. G-001~G-044 +
      R-001~R-009의 대응 Task가 모두 머지됨을 tasks-done.md와 교차 확인(legal/ops T-275~282, 보안
      T-283, RBAC/lifecycle/DSR/retention/moderation/email, integrity T-292, WS/conflict T-289/290,
      ETL sensor T-291, ETL SQL/audit split T-291-etl-sql-tests 등). 잔여 확인은 T-259 release gate와
      G-044 AI companion scope 제거 후속뿐이다. 미추적 gap 없음 → closed.

- [x] T-291-etl-sql-tests — app-owned ETL SQL 실행 테스트 + audit retention 정책 분리.
      (완료: 2026-06-29, codex)
      ETL 원시 SQL 상수를 Dagster asset 밖의 `pinvi.etl.sql` 모듈로 분리하고, ETL PostgreSQL dialect
      compile smoke와 API 통합 테스트의 Alembic schema 실행 smoke를 추가했다. PII retention summary는
      삭제 계정/OAuth/verification/session/OAuth transient 후보만 소유하게 줄였고,
      `location_access_log` 후보는 location archive summary 단독 책임으로 유지했다. `admin_audit_log`
      PII 후보는 90일 `append_only_cold_storage` 정책의 `audit_retention` summary로 분리하고, execute
      result에는 기존처럼 skip count evidence만 남긴다. Pydantic/zod/Web Admin/문서를 함께 갱신했다.

- [x] PR #227 — Web 지도 마커 튜닝 + viewport 캐싱. (완료: 2026-06-29, codex 작성 / claude 마무리)
      `featureBounds`에 zoom별 bbox precision(floor/ceil 바깥 확장)으로 낮은 줌 pan refetch churn 감소,
      `FeatureMapView`에 LRU(32)+TTL(60s) viewport 캐시, weather kind feature를 `WeatherMarker`로 렌더
      (icon→condition 매핑, 선택 시 기온). 98커밋 뒤처진 PR을 main에 동기화(resolveMarkerStyle와
      featureKind 병합, isSelected 추출)하고 typecheck/lint/vitest/CI 통과 후 머지.

- [x] T-268 — 한국 전용 geofencing 3중 안전망. (완료: 2026-06-29, PR #323, claude)
      middleware(3차 fallback)는 구현/배선/테스트 완료였고, runbook이 inline으로만 기술하던 Cloudflare
      WAF(1차)·nginx GeoIP2(선택 edge)·GeoIP 갱신을 실제 아티팩트로 구체화. `infra/cloudflare/
waf-korea-only.md`, `infra/nginx/{Dockerfile,conf.d/geo-kr*.conf,README}`, `scripts/update-geoip.sh`,
      `scripts/verify-geofence.sh`(T-273 게이트용) 추가 + korea-only 문서 DRY 정리.

- [x] T-269 — LBS / 법무 4문서 + 동의 UX. (완료: 2026-06-29, PR #324, claude)
      `docs/legal/{terms-of-service,privacy-policy,lbs-terms,location-consent}.md` 초안(변호사 검토 전,
      시행일/사업자정보 미정) + README, `apps/web/lib/legalDocs.ts` + 공개 `/legal/[slug]` 뷰어(초안 배너),
      동의 UX(settings/consents, profile-complete) 필수 4항목 "전문 보기" 링크, lbs-act 참조. 운영표면
      (동의 기록/철회, DSR, retention)은 T-275~282로 기구현.

- [x] T-265 — Admin notice plan 작성기. (완료: 2026-06-29, codex)
      `/admin/notice-plans` Admin CRUD를 목록/생성/상세/수정/삭제로 확장하고, `If-Match` 기반
      version conflict, POI 생성/수정/삭제/reorder, plan/POI 첨부 관리 흐름을 구현했다. Web Admin에는
      `/admin/notice-plans` 목록/필터, 신규 생성, 편집, `NoticePoiEditor`, 첨부 업로드 패널을 추가했다.
      `packages/schemas`/`packages/api-client` 계약과 query key를 갱신했고 API 통합 테스트 및 N150
      Playwright e2e로 검증했다.

- [x] T-287 — Trip Day optimistic lock API / conflict UX. (완료: 2026-06-29, claude)
      day rename/delete 동시성을 trip/POI와 동일한 정수 version optimistic lock(`If-Match` 헤더)으로
      도입. migration 0036으로 `app.trip_days.version` 추가(server_default 1), `PATCH/DELETE
/trips/{id}/days/{day_index}`가 If-Match version을 검증해 불일치 시 409 `VERSION_CONFLICT`.
      TripDay/TripView/CRUD 응답 + zod/api-client에 version 노출, TripDetail rename/delete가 version
      전달 + 충돌 시 reload+안내, mobile deleteDay도 version 전달. 통합 테스트(stale If-Match 409 +
      정상 204/version bump) 추가. live e2e는 T-259 게이트에서.
- [x] T-113 / T-271 / T-272 / T-285 — backlog scope 제거. (제거: 2026-06-29, 사용자 지시)
      구현하지 않고 열린 backlog에서 제거했다. T-113(`kor-travel-concierge` 별 repo 신설),
      T-271(Odroid+N150 병행 운영), T-272(AI companion 별도 서비스 분리),
      T-285(AI companion v1.0 scope gate)는 더 이상 열린 task로 추적하지 않는다.
      향후 AI companion 연동은 신규 repo 신설 대신 이미 존재하는 `kor-travel-concierge` API를
      활용하는 consumer/client 통합 task로 정의한다.

- [x] T-267 — Backup/Restore UI hot-swap 완성. (완료: 2026-06-29, PR #319, codex)
      Web Admin restore dialog에 snapshot 파일명 직접 입력 확인, Escape/backdrop/focus trap,
      실행 중 닫기 잠금, 성공 후 재제출 방지, 요청 중 pending phase와 완료 후 API phase/schema
      result 표시를 추가했다. 기본 restore 잠금 e2e와
      `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=1` enabled e2e를 N150 Playwright Docker runner로
      검증했고, Admin API 계약은 변경하지 않았다. 완료 후 `tasks.md`에서 T-267 선점/열린 항목을
      제거했다.

- [x] T-260 — Sprint 6 상세 실행 계획 / ADR 정리. (완료: 2026-06-29, claude)
      `docs/execplan/sprint6-v1.0-plan.md`(남은 task 그룹·의존성·DoD 매핑·병행 회피)를 작성하고,
      #315(T-261~263)에서 보류했던 경로 최적화 정책을 **ADR-053**(nearest-neighbor + 2-opt,
      haversine, OR-Tools/실도로 거리 보류)으로 박았다. SPRINT-6.md의 OR-Tools/category-mapping
      ADR 후보 노트를 확정 ADR-053/ADR-052 + execplan 참조로 정정하고, optimize DoD/산출물 항목을
      실제 구현(`services/trip.py`, `api/v1/trips.py`)에 맞췄다. 다음 신규 ADR = ADR-054.

- [x] T-264 — Admin category mapping DB override. (완료: 2026-06-29, PR #316, codex)
      ADR-052로 Pinvi category mapping 범위를 taxonomy가 아닌 presentation override로 고정하고,
      `app.category_mappings` migration/model, `/admin/category-mappings` 조회/PATCH/DELETE rollback,
      `admin_audit_log` 기록, Web Admin editor, schema/api-client, API integration, N150 Playwright
      e2e를 추가했다. `tasks.md`도 완료/머지/검증 이력을 제거하고 열린 항목만 남기도록 정리했다.

- [x] T-261 / T-262 / T-263 — 스마트 정렬 (경로 최적화). (완료: 2026-06-29, PR #315, claude)
      사용자 결정으로 OR-Tools 대신 순수 Python **2-opt** local search 채택(거리 haversine 유지,
      신규 의존성 0, Odroid ARM/N150 안전, trip day POI 수에 충분). `services/trip.py`에
      nearest-neighbor seed → 2-opt(`_optimize_day_order`/`_two_opt_improve`, 시작 POI 고정·
      `_TWO_OPT_MAX_POIS=60` 상한) + 기존 순서 거리(previous) 반환. 계약(strategy `two_opt` 기본 +
      `previous_distance_meters`)을 pydantic/zod/api-client에 반영하고 `TripDayOptimize.tsx`에
      "기존 → 최적 (N% 단축)" 표시. 2-opt 단위 테스트 추가. 최적화 정책 ADR과 카카오 실도로
      거리는 후속(보류).

- [x] T-291 — ETL compliance SQL / failure notification follow-up. (완료: 2026-06-29, PR #312, claude)
      PR #271/#273(+#276) 사후 리뷰의 ADR-050 conformance gap을 닫았다. `pinvi_run_failure_sensor`
      (retry 소진 실패를 Sentry + `app.telegram_system_notification_outbox`로 PII-free 통지)를 추가하고
      `Definitions(sensors=[...])`에 등록(monitored_jobs + asset job 명시 등록으로 get_job_def 충돌 해소).
      dagster-etl-bridge/etl 런북 doc drift 정정. 잔여(SQL 실행 테스트 + audit retention 분리)는
      `T-291-etl-sql-tests`로 분리.

- [x] T-292 — App integrity pagination / producer follow-up.
      PR #283 사후 리뷰의 `/admin/integrity/issues?source=all` pagination starvation을 composite
      cursor로 닫고, Pinvi app integrity producer/upsert helper와 active partial unique 회귀 테스트를
      추가했다. Web Admin integrity issue pagination UI와 action modal Escape/backdrop/focus trap도
      보강했다.

- [x] T-288-legacy-task-archive — `tasks.md` legacy 완료 이력 이관.
      `docs/tasks.md`에서 완료/폐기/머지 이력/운영 규칙이 섞인 legacy 섹션을 제거하고,
      열린 backlog만 남겼다. 완료·아카이브 요약과 머지 히스토리는 본 파일로, 병행 작업
      기록·충돌 회피 규칙은 `docs/tasks-rule.md` §8로 이동했다. T-285는 사용자 지시에 따라
      현재 진행하지 않는 열린 보류 항목으로 유지했다.

- [x] T-290 — Trip conflict UX follow-up. (완료: 2026-06-29, PR #310, claude)
      PR #266 사후 리뷰의 Trip conflict field whitelist drift, 409 envelope current row,
      `ConflictDialog` Esc/focus 접근성 gap을 닫았다. Day rename/delete 409는 T-287로 유지한다.

- [x] T-289 — WebSocket reconnect / invalidation follow-up. (완료: 2026-06-29, PR #310, claude)
      PR #265 사후 리뷰의 `4401` refresh tight loop, retry jitter, 수동 재연결 UX,
      TanStack Query invalidation 실제 배선 gap을 T-290과 같은 PR에서 닫았다.

- [x] T-284 — Mobile v1.0 scope gate.
      `apps/mobile`을 활성 Expo SDK 56 / Dev Client Sprint M-1 track으로 유지하되, `v1.0.0`
      Web/API/Admin 운영 출시의 필수 release blocker에서는 제외하는 scope gate를 문서화했다.
      EAS build, 실기기 smoke, store 제출, mobile live e2e는 모바일 release train에서 검증하며,
      `apps/mobile/**` 또는 공용 `packages/**` 변경 시 `mobile-typecheck` CI gate는 유지한다.

- [x] T-283 — Security review / threat model / penetration pass.
      auth/session/MCP/share token/rate-limit/storage/admin RBAC/incident 권한 threat model과
      1차 security review를 정리했다. v1.0 user-facing AI companion 범위는 별도 scope gate로
      분리했다가, 이후 사용자 지시에 따라 T-285는 현재 진행하지 않는다.

- [x] T-282 — Rate-limit / abuse admin surface.
      ADR-038 bucket 상태, fail-closed 503, block/allow override, suspicious activity 조회를
      Admin/API/UI로 노출했다.

- [x] T-281 — User lifecycle admin actions.
      force-resend-verify, sessions list/forced logout, force-password-reset, disable/reactivate,
      anonymize/delete account와 사용자 `DELETE /users/me` 흐름을 구현했다.

- [x] T-280 — RBAC role grant/revoke / permission matrix.
      ADR-033의 DB-backed role 모델을 운영 가능한 Admin API/UI로 확장했다.
      `/admin/rbac/permission-matrix`는 role 설명과 endpoint 권한 matrix를 제공하고,
      사용자 상세의 역할 관리 섹션은 `admin` / `operator` / `cpo` role 부여·회수를 수행한다.
      role mutation은 `admin` 전용, 운영 사유 필수, `admin_audit_log` 기록 대상이며 중복 부여,
      미보유 role 회수, 자기 admin 회수, 마지막 admin 회수를 차단한다. API integration,
      Admin mock Playwright, Admin API/runbook/RBAC architecture 문서를 함께 갱신했다.

- [x] T-279 — Content moderation / takedown workflow.
      `app.content_reports`와 `app.content_moderation_actions`를 추가해 trip/comment/attachment/share link
      신고, target snapshot, 증거 metadata, review/hide/takedown/restore/reject/appeal 상태와 조치
      history를 저장한다. `/users/me/content-reports`와 `/settings/moderation`은 사용자 신고
      접수/조회/이의제기를 제공하고, `/admin/moderation`은 운영자 검토/숨김/게시중단/복원/반려
      workflow와 `admin_audit_log` 기록을 제공한다. hide/takedown/restore는 여행 visibility/archive,
      댓글/첨부 soft-delete, 공유 링크 revoke 상태에 실제 반영된다. API integration, Admin/user mock
      Playwright, API/Admin/users/PIPA/schema/runbook 문서를 함께 갱신했다.

## 2026-06-28

- [x] T-278 — DSR intake workflow.
      `app.dsr_requests`를 추가해 개인정보 열람/정정/삭제/처리정지 요청의 접수, 10일 due,
      본인 확인, 처리 시작, 완료/거절/철회 상태, result notice hash, export manifest, partial
      response evidence를 저장한다. `/users/me/dsr-requests`와 `/settings/dsr`는 사용자
      self-service 접수/조회/철회를 제공하고, `/admin/dsr`는 CPO 전용 본인 확인/처리/완료/거절
      workflow와 `admin_audit_log` 기록을 제공한다. 완료/거절은 `dsr_result_notice` email queue
      row를 만들며 DSR 행은 원문 이메일 대신 hash/masked 값만 보존한다. API integration,
      Admin/user mock Playwright, API/Admin/users/PIPA/schema/runbook 문서를 함께 갱신했다.

- [x] T-277 — Email deliverability / suppression enforcement.
      `app.email_suppressions`와 `app.resend_webhook_events`를 추가해 Resend hard bounce,
      complaint, provider suppression을 발송 차단 source로 저장한다. `email_queue.status`는
      `delivery_delayed`와 `suppressed`를 포함하며, worker는 발송 전 `users.email_status`,
      active suppression, `marketing` consent를 검사해 provider 호출 없이 terminal 상태로 멈춘다.
      Resend 발송은 SDK 직접 호출에서 REST `ResendClient`로 전환되어 `api_call_log.provider='resend'`
      기록을 남긴다. `/webhooks/resend`는 event id/`svix-id` dedupe와 terminal precedence를 적용하고,
      `/admin/emails/deliverability` 및 Web Admin 이메일 큐 상태판은 domain/webhook/queue/suppression
      health를 raw secret 없이 표시한다. API integration, provider tracking test, mock Playwright,
      Resend/Admin/schema/compliance 문서를 함께 갱신했다.

- [x] T-276 — Retention execution / dashboard.
      `app.retention_runs`와 `app.location_access_log_archive`를 추가해 PII/위치 로그 보존기간
      dry-run/execute evidence를 저장한다. `/admin/retention` API는 summary, runs, dry-run,
      execute를 제공하며, execute는 기본 비활성 kill-switch와 confirm phrase, cutoff 이전
      pending outbox 및 hash-chain bridge precheck를 통과해야 한다. 실행은 삭제 계정 PII anonymize,
      OAuth identity/token/session/OAuth transient row 삭제, 위치 로그 archive 후 active row 삭제를
      수행하고 `admin_audit_log`에 사유를 남긴다. Web Admin `/admin/retention`, API client/schema,
      mock Playwright, API integration, Admin/LBS/schema/runbook 문서를 함께 갱신했다.

- [x] T-275 — PIPA security incident console.
      `app.security_incidents`를 `detected` → `triage` → `notification_decision` → `reported` →
      `closed` workflow로 확장하고, CPO 30분 review due, 72시간 외부 신고 due, 통지 payload hash,
      신고 접수번호, evidence attachment id를 migration/model/schema에 추가했다. `/admin/incidents`
      API는 incident 생성 시 Admin Telegram outbox를 만들고 CPO 전용 triage/decision/notify/report/close
      전이를 `admin_audit_log`에 남긴다. 정보주체 통지는 `security_incident_notice` email queue와
      deterministic payload hash를 기록한다. Web Admin `/admin/incidents`는 목록 필터, 신규 등록,
      상태별 조치 패널을 제공하며, admin API 문서, PIPA compliance, schema/data-model/runbook,
      mock Playwright와 API integration 테스트를 함께 갱신했다.

- [x] T-258 — Sprint 6 legal/ops implementation prep gate.
      `docs/execplan/legal-ops-implementation-prep-gate.md`를 추가해 T-275~T-286의 API/UI,
      상태 모델, due date, evidence/audit, runbook, test gate, sign-off 기준을 Sprint 6 진입
      계약으로 고정했다. 기존 `KISA 60일 report` 표현은 개인정보보호위원회/KISA 72시간 신고
      기준으로 정정했고, CPO 30분 review는 내부 SLA로 분리했다. v1.0 mobile 제외와
      user-facing AI companion 제외도 release checklist에 명시했다.

- [x] T-257 — Email deliverability / provider tracking preflight.
      `docs/execplan/email-deliverability-provider-preflight.md`를 추가해 Resend domain
      verification, SPF/DKIM/DMARC, webhook event dedupe/precedence, hard-bounce/complaint
      suppression, provider tracking gap을 T-277 구현 계약으로 고정했다. 현재 구현은 queue
      worker, Svix 서명 검증, queue 상태 갱신, `/admin/emails` queue 화면까지 닫혀 있고,
      suppression enforcement, deliverability 상태판, `api_call_log.provider='resend'`는
      T-277 잔여임을 `docs/integrations/resend.md`에 반영했다.

- [x] T-256 — Review gap crosswalk / legal-ops preflight.
      `docs/execplan/legal-ops-review-gap-crosswalk.md`를 추가해 PR #238/#264 legal-ops 리뷰 gap
      44개를 T-257/T-258/T-275~~T-286 등 대응 Task로 매핑했다. 최근 2일 PR #265~~#289
      리뷰 코멘트도 확인해 WebSocket, conflict, ETL compliance SQL, app integrity 후속을
      T-289~T-292로 남겼다. Sprint 5/6, tasks, resume, journal이 같은 crosswalk 정본을
      참조하도록 정리했다.

- [x] T-255 — 지도 마커 / 색상 적용 parity.
      `@pinvi/domain`에 marker resolver를 추가해 custom/resolved/upstream/snapshot/category/kind/fallback
      우선순위를 한 곳에서 계산한다. 사용자 Trip 지도, 탐색 지도, Admin Trip POI preview는 같은
      marker style metadata를 노출하고, Trip 지도는 selected/broken 상태를 DOM/e2e에서 확인한다.
      mock e2e는 Trip detail/Admin trip dialog marker parity를 검증하고, live read-only spec은
      `PINVI_ADMIN_LIVE_E2E=1` gate에서 `/map` marker metadata를 데이터 유무에 독립적으로 확인한다.
      N150 SSH alias는 현재 Linux 환경에서 해석되지 않아 Windows fallback Playwright로 검증했다.

- [x] T-254 — Admin live e2e matrix v0.2.0 확장.
      `admin-live-matrix.live.ts` catalog를 exact count로 고정해 drift를 감지하고,
      read-only matrix에 `/admin/debug/request/{id}` captured request timeline,
      feature detail subpage tabs, backup restore-lock/mutation guard, ETL app-owned job rows,
      Grafana dashboard selector/WebSocket dashboard, raw secret pattern 미노출 검사를 추가했다.
      runbook은 N150 우선 실행과 `PINVI_ADMIN_LIVE_CASE_LIMIT=200`, `2000`, full catalog gate를
      명시한다. N150 SSH alias는 현재 Linux 환경에서 해석되지 않아 실제 N150 live run은
      수행하지 못했고, catalog/typecheck 중심으로 검증했다.

- [x] T-253 — Prometheus/Grafana 운영 가시화 게이트.
      observability profile에 blackbox exporter를 추가해 Web/Dagster HTTP health를
      Prometheus target으로 확인하고, API `/metrics`에 SQLAlchemy DB pool gauge를 추가했다.
      Grafana provisioning은 기존 Overview에 API p95/error, DB pool, WebSocket, ETL/backup
      4종 dashboard를 더한다. `/admin/grafana`는 dashboard selector와
      `GET /admin/grafana/health` 기반 `ok`/`degraded` 표시를 제공하고, mock/live e2e가
      iframe, dashboard path, secret 미노출, degraded 상태를 검증한다. production httpx client는
      `kor_travel_map`, `kor_travel_map_admin`, `kor_travel_geo`, `telegram`, `google_oauth`
      provider tag를 `ApiCallTracker`에 연결하며 query secret과 Telegram bot token path를 mask한다.
      Resend SDK 경로는 T-257 감사에서 provider tracking 누락으로 확인됐고, T-277에서
      `provider='resend'` 기록을 구현한다. N150 SSH alias는 현재 Linux 환경에서 해석되지 않아
      실제 N150 live run은 수행하지 못했다.

- [x] T-252 — Backup/restore live UI e2e.
      `/admin/backup`에 snapshot 검색/status filter와 visible count를 추가하고,
      production 기본 restore 버튼을 `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=0`으로
      잠갔다. `admin-live-backup.live.ts`는 read-only 목록/sort/filter/empty/masking과
      backup mutation 미발생을 검증하고, `admin-backup-live-mutating.live.ts`는
      `PINVI_BACKUP_LIVE_MUTATING_E2E=1` + `PINVI_BACKUP_LIVE_STAGING=1`에서 staging
      snapshot 생성, `backup.snapshot` audit, `backup://<filename>` masking, 목록 limit cap을
      확인한다. N150 SSH alias는 현재 Linux 환경에서 해석되지 않아 실제 N150 live run은
      수행하지 못했다.

- [x] T-251 — Restore staging drill.
      `scripts/restore-staging-drill.sh`를 추가해 staging URL 없이는 restore를 시작하지 않도록
      가드하고, snapshot checksum, `pg_restore --list`, `restore-db.sh`, DB health row count,
      admin audit chain link, rollback rehearsal(precheck/drain)을 한 번에 수행한다.
      backup sidecar는 dump basename 기준으로 생성하고, restore 검증은 sidecar checksum 값을
      실제 dump hash와 비교하도록 정리해 staging 경로로 dump와 sidecar를 함께 옮겨도 검증이
      가능하다. N150 SSH alias는 현재 Linux 환경에서
      해석되지 않아 실제 N150 drill은 실행하지 못했고, fake DB tool 기반 스크립트 회귀로
      가드와 path masking을 검증했다.

- [x] T-250 — Backup script / snapshot endpoint hardening.
      `scripts/backup-db.sh`에 schema name guard, disk free guard, tmp dump 생성, sha256 생성/검증을
      추가했고 `scripts/restore-db.sh`는 sidecar checksum을 restore 전에 검증한다. Admin backup
      API는 snapshot/restore path를 `backup://<filename>`으로 mask하고, snapshot 생성 실패도
      `backup.snapshot_failed` audit으로 남긴다.

- [x] T-249 — App-owned integrity source / known orphan fix.
      `app.data_integrity_violations` migration/model과 Pinvi app-owned integrity service를
      추가했다. `/admin/integrity/issues`는 `source=all|kor_travel_map|pinvi_app` filter를
      받고, persisted row와 broken POI feature link, marker color drift, curated import source
      drift, active attachment deleted target 같은 known app issue를 `source="pinvi_app"`로
      반환한다. Web `/admin/integrity`는 source filter/column을 표시하고 Pinvi app issue는
      read-only로 둔다.

- [x] T-248 — Feature detail subpages.
      `GET /admin/features/{id}/sources`, `/overrides`, `/weather-values`를 추가했다.
      sources/overrides는 `kor-travel-map` admin detail payload에서 read-only projection으로
      반환하고, weather-values는 기존 feature weather card의 metrics를 Admin tab용 list로 투영한다.
      Web은 `/admin/features/{id}/{sources,overrides,weather-values}` deep link tab과 기존 feature
      inspector의 tab link를 제공한다. override mutation은 별도 ADR 전까지 추가하지 않는다.

- [x] T-247 — Provider sync 운영 mutation 계약 정리.
      upstream `kor-travel-map` 운영 mutation을 확인해 import job cancel만 Pinvi에 relay했다.
      `POST /admin/provider-sync/import-jobs/{job_id}/cancel`은 `admin` 전용, `access_reason`
      필수, upstream reason fallback, `provider_import_job.cancel` audit을 적용한다. Web
      `/admin/provider-sync`는 queued/running job에 취소 사유 패널을 제공하고 실패 시 row를 유지한다.
      provider run-now/pause/resume/reset cursor는 upstream provider mutation 또는 별도 ADR 전까지
      추가하지 않는다.

- [x] T-246 — Debug live UI e2e 확장.
      `apps/web/e2e/admin-debug-live.live.ts`를 추가해 `/admin/debug/logs` route render,
      sanitized polling fallback status, filter query 유지, live toggle/pause, request timeline 이동,
      raw secret pattern 미노출을 read-only로 검증한다. Pinvi admin client는 현재 `X-Request-Id`를
      `kor-travel-map` admin/ops 호출에 전달하며, debug live test는 UI credential 대신
      `PINVI_ADMIN_LIVE_STORAGE_STATE`도 지원한다. N150에서는 API/Web 재빌드·health 확인 후
      Playwright Chromium이 Ubuntu 26.04 미지원으로 실패했고, Windows fallback runner에서 N150
      Web/API 대상 live test 1건이 통과했다.

- [x] T-245 — Loki/Promtail 또는 대체 log stream.
      v0.2.0에서는 Loki/Promtail LogQL WebSocket을 필수 운영 구성으로 올리지 않고,
      `kor-travel-map` sanitized system/API logs polling fallback을 선택했다.
      `GET /admin/debug/logs/stream/status`는 `mode="polling"`, 5초 polling interval,
      source 목록, `loki_enabled=false`, `sse_enabled=false`를 반환한다.
      Web `/admin/debug/logs`에는 live toggle과 pause/resume을 추가했고, live 상태에서는 기존
      sanitized system/API endpoint를 같은 filter로 재조회한다. N150 live read-only 검증은 T-246에서
      request timeline masking 검증과 함께 수행한다.

- [x] T-244 — Request timeline API.
      `GET /admin/debug/request/{request_id}`를 추가해 Pinvi request id 중심 timeline을 반환한다.
      API call log, admin audit log, location access log/outbox, `payload.request_id`가 있는
      email queue와 upstream sanitized system/API logs를 시간순 event로 조합하되,
      `kor-travel-map` log는 보조 source로만 붙인다. upstream 보조 source 실패는
      `status="partial"`/source `degraded`로 접고, all-source not found는 404로 반환한다.
      Web `/admin/debug/logs`에는 request id 검색을, `/admin/debug/request/{request_id}`에는
      source/event table을 추가했다. N150 live read-only는 PR merge 후 배포 환경 검증으로 남겼다.

- [x] T-243 — ETL live / Dagster 운영 게이트.
      `/admin/etl/summary`가 Pinvi Dagster `/server_info`와 `/graphql`을 읽어
      code location repository/job/asset/schedule, 최근 run 상태를 live snapshot으로 반환한다.
      Web `/admin/etl`은 app-owned job row에 live/registry 상태, schedule timezone, 최신 run
      status를 표시한다. GraphQL 실패 시 `pinvi.status=degraded`로 강등하고 static registry와
      app-owned outbox/retention summary는 유지한다. run tag 값은 Admin 응답에 노출하지 않는다.
      N150 API smoke / Playwright live는 PR merge 후 배포 환경 검증으로 남겼다.

- [x] T-242 — Telegram system summary/outbox ETL.
      `pinvi_telegram_system_outbox` asset/job/schedule을 추가해 15분마다
      `app.telegram_system_notification_outbox`의 pending due/backoff/stuck, sent, skipped,
      failed, retry exhausted, category별 retry exhausted 비율을 집계한다.
      `/admin/etl/summary`와 Web `/admin/etl`은 같은 bounded Telegram outbox summary를
      노출하고, payload·message text·user id·chat id·token·last_error 원문은 노출하지 않는다.
      weekly/daily 사용자 브리프 생성은 후속 `pinvi_telegram_weekly` 범위로 남겼다.

- [x] T-289 — Linux-only 개발 환경 / ADR-051 문서화.
      ADR-051로 개발·git·CodeGraph는 Linux 기준, Playwright는 N150 우선 실행으로 고정했다.
      ADR-024의 NTFS source / WSL 테스트 미러 모델과 ADR-017의 Windows `git.exe` amendment를
      supersede하고, AGENTS/CLAUDE/SKILL, 개발 환경 런북, CodeGraph worktree 런북,
      실패 패턴 문서, README/Sprint 문서를 같은 기준으로 동기화했다.

- [x] T-241 — `pinvi_location_log_archive` Dagster job.
      `pinvi_location_log_archive` asset/job/schedule을 추가해 매일 KST 04:30
      `app.location_access_log`의 6개월 초과 archive 후보, active head/tail hash-chain bridge,
      미처리 `location_audit_outbox` blocker, purpose별 후보 수를 dry-run으로 집계한다.
      `/admin/etl/summary`와 Web `/admin/etl`은 후보 수와 bridge/pending 상태만 노출하고,
      raw 좌표·사용자 식별자는 노출하지 않는다. 실제 archive/delete/anonymize 실행은
      T-276 kill-switch/dashboard/evidence log 범위로 남겼다.

- [x] T-240 — `pinvi_pii_retention` Dagster job.
      `pinvi_pii_retention` asset/job/schedule을 추가해 매일 KST 04:15 삭제 계정 PII,
      OAuth identity, 만료 verification/reset token, 오래된 session, 만료 OAuth transient row,
      location/admin audit PII 보존 기간 만료 후보를 dry-run으로 집계한다. `/admin/etl/summary`와
      Web `/admin/etl`은 후보 수, cutoff, 권한 계정 제외 수를 PII 없이 노출한다. 실제
      delete/anonymize/archive 실행은 T-276 kill-switch/dashboard/evidence log 범위로 남겼다.

- [x] T-239 — `pinvi_email_outbox` Dagster job.
      `pinvi_email_outbox` asset/job/schedule을 추가해 15분마다 `app.email_queue`의 pending
      due/backoff/stuck, failed/bounced/complained, retry exhausted, template별 실패율을 PII 없이
      집계한다. `/admin/etl/summary`와 Web `/admin/etl`은 같은 bounded email outbox summary를
      노출한다. 실제 발송 source of truth는 FastAPI lifespan worker로 유지하고,
      deliverability/suppression 집행은 T-257/T-277로 남겼다.

- [x] T-238 — Pinvi app-owned ETL 표준 / ADR.
      ADR-050으로 Pinvi `apps/etl` app-owned Dagster job 표준을 고정했다. 신규 job은
      `app` schema 소유 범위, import-time side effect 금지, KST schedule, retry/backoff,
      idempotency key, bounded metadata, `run_failure_sensor` 기반 Sentry/Telegram outbox 알림,
      destructive dry-run gate를 따른다. ETL runbook, Dagster architecture 문서, Sprint 5 DoD,
      AGENTS/CLAUDE 진입 요약을 같은 기준으로 동기화했다.

- [x] T-237 — WebSocket backend hardening / metrics.
      Trip WebSocket backend에 bounded-label Prometheus gauge/counter와 `pinvi.websocket.close`
      구조화 로그를 추가했다. connection accept/reject, close code/reason, client message,
      broadcast result, send timeout/error를 계측하고, permission/rate-limit/connection-cap/
      heartbeat-timeout 회귀 테스트와 broker stale-removal metric 테스트를 보강했다. 기존 문서의
      rate-limit grace slot 반환 설명도 실제 구현처럼 "close까지 유지"로 정정했다.

- [x] T-236a — WebSocket multi-client N150 live e2e drill.
      N150 live mutating Playwright에서 실제 WebSocket broadcast/reconnect 뒤 Trip snapshot reload를
      검증했다. 첫 실패로 `pinvi-api` worker 2개와 process-local realtime broker 충돌을 확인해
      Pinvi compose 기본 worker를 1로 낮추고, `kor-travel-docker-manager` PR #44에서 운영 compose도
      `PINVI_API_WORKERS=1` 기본값으로 맞췄다. 두 번째 실패로 public Web/API CORS 주입 drift를 확인해
      docker-manager PR #45에서 `PINVI_PUBLIC_API_URL`/`PINVI_CORS_ALLOWED_ORIGINS`를 gitignore `.env`
      주입값으로 분리했다. 최종 Windows Playwright live mutating e2e 1건이 통과했다.

- [x] T-236 — WebSocket multi-client collaboration e2e.
      Trip 상세 mock Playwright e2e에 2개 브라우저 컨텍스트 presence/broadcast reload,
      재연결 후 최신 snapshot 반영, 5개 컨텍스트 presence fan-out와 offline cleanup 검증을
      추가했다. Fake WebSocket은 React Strict Mode 재마운트와 재연결에서 마지막 active socket을
      기준으로 서버 이벤트를 주입하도록 정리했다. N150 staging live 검증은 작업 크기를 분리해
      T-236a로 남겼다.

- [x] T-288 — Task 문서 분리 정책 반영.
      `kor-travel-map`의 `tasks.md`/`tasks-done.md`/`resume.md` 분리 정책을 확인하고,
      Pinvi에 `docs/tasks-rule.md`와 본 파일을 추가했다. 신규 task 진입 전 최근 2일 PR
      리뷰 코멘트 확인, task 분리 기준, 완료 후 `tasks-done.md` 아카이브 규칙을 고정했다.
      기존 `tasks.md`의 legacy 완료 이력 전체 이관은 `T-288-legacy-task-archive`로 분리했고,
      2026-06-29 해당 이관을 완료했다.

- [x] T-235 — Optimistic lock / conflict dialog.
      Trip/POI 409 conflict UX, LWW/수동 병합, server/my value 선택과 API/Vitest/Windows
      Playwright 회귀 테스트를 구현했다. Day API는 현재 `If-Match` 계약이 없어 T-287로
      분리했다.

- [x] T-234 — WebSocket client invalidation / auth close handling.
      WebSocket close code/reason 분류, 4401 refresh 재연결, 4403 권한 상실 안내,
      4408/4429 backoff 안내, realtime invalidation key와 duplicate reload 방지를 구현했다.

- [x] T-233 — Sprint 5/6 상세 Task 계획.
      `docs/execplan/sprint5-v020-release-plan.md`에 Sprint 5 `v0.2.0` 잔여 구현
      Task와 Sprint 6 `v1.0.0` 후속 Task 초안을 정리하고, PR 리뷰에서 지적된 법무/운영
      gap을 T-256~T-286으로 보강했다.

- [x] T-232 — Trip WebSocket frontend client / presence 첫 연결.
      `@pinvi/api-client`에 `TripRealtimeClient`와 `tripWebSocketUrl`을 추가하고,
      사용자 Trip 상세 화면을 `WS /ws/trips/{trip_id}` presence/reload 흐름에 연결했다.

## Legacy Archive (2026-06-29, T-288-legacy-task-archive)

이번 정리에서 `docs/tasks.md`에서 제거한 완료/폐기/머지 이력이다. 상세 구현 내역은 각 PR,
`docs/journal.md`, 관련 실행 계획 문서가 정본이며, 이 섹션은 task 추적과 ID 검색용 archive다.

### Admin 콘솔 기능 보강 프로그램

- [x] T-207~~T-229 — Admin 콘솔 보강 프로그램.
      실행 계획(`docs/execplan/admin-console-gap-plan.md`) 작성, Admin IA/메뉴/대시보드,
      `kor-travel-map` Admin proxy, feature/change request/dedup/integrity/debug logs,
      ETL/provider sync, category mapping, seed/reset dev-only guard, Grafana URL,
      dashboard 상세, system detail, trip/POI/user/avatar/file/operation 운영 기능,
      N150 Admin live e2e 묶음 게이트, sidebar 토글 정정, 완료 감사까지 닫았다.
- [x] T-230 — v0.1.0 릴리즈 상태 정합화.
      GitHub의 기존 `v0.1.0` tag/Release 상태를 문서와 추적 파일에 반영했다.
- [x] T-231 — v0.2.0 후보 범위 정리.
      `CHANGELOG.md`와 Sprint 5 문서에서 post-v0.1.0 반영분과 남은 release gate를 분리했다.

### 완료 legacy 묶음

- [x] T-000~~T-023 — v2 재시작 초기 문서/ADR/API/runbook/compliance/convention/agent 절차
      정리와 Sprint 4까지 PR 운영 runbook.
- [x] T-030~~T-035 — Sprint 1 monorepo/API/Web/ETL/infra/CI skeleton과 진입 PR.
- [x] T-050~~T-074 — Sprint 3/4 Admin, CI, 지도 shell, OAuth, KASI, 이메일 worker,
      kor-travel-map 계약 동기화, production URL/CORS/OAuth 문서화.
- [x] T-075, T-100~~T-105, T-109~~T-121 — Trip/notice shell, Resend/OAuth/Notice/RustFS/Admin
      v2 이식, geofence, Grafana, Backup snapshot, OAuth Google-only, consent, account matching,
      Admin user/trip/POI 관리, 첨부 도메인과 RustFS presigned 실서명.
- [x] T-123~~T-151 — 2026-06-06 감사 후속 문서/계약/schema/API/ADR 정합화.
- [x] T-152~~T-153 — Telegram 완료 알림 MCP와 PR 리뷰 모니터 MCP 알림 보강.
- [x] T-154~~T-169 — Codex PR 사후 리뷰 1~2라운드 보안/무결성/가용성 후속.
- [x] T-170~~T-182, T-210b~~T-210e, T-211 — `kor-travel-map` OpenAPI HTTP client,
      feature/trip/public/admin 연동, drift gate, curated import 연결.
- [x] T-183~~T-200 — backup hotswap hardening, 첨부/WS/cursor/geofence/rate-limit 후속,
      runtime 계약 hard cutover, 프로젝트명 `pinvi` 변경, docker-manager 포트 대역 정렬.
- [x] T-201~~T-206 — Web 지도 클라이언트 전환, geo v2 key 계약, Admin live matrix,
      이메일 outbox worker 연결, 로컬 env 키 반영, N150 bootstrap admin 생성/복구.
- [x] T-111, T-112, T-114, T-132 — Sprint 5~6 backlog 중 완료된 Backup/Restore UI,
      MCP 외부 인터페이스, GitHub Actions CI/CD 복원, trip 하위 리소스 구현.
- [x] T-066 — kor-travel-map OpenAPI HTTP client 구현 완료. drift gate는 이후 T-210e로 완료했다.
- [x] T-107 — Gemini 통합은 ADR-020에 따라 본 저장소 직접 구현 대상에서 제외했다.
      후속 T-113(`kor-travel-concierge` 별도 repo 신설)은 2026-06-29 사용자 지시로 backlog에서 제거했다.
      향후 필요 시 이미 존재하는 `kor-travel-concierge` API를 활용한다.
- [x] T-108 — 운영 배포 자동화 foundation.
      Odroid M1S + N150 deploy/smoke script, doctor, 노드별 배포 runbook을 추가했다.
      실제 노드 smoke와 backup/restore 복구 훈련은 Sprint 6 운영 게이트로 유지한다.

### Claude Sprint 4 PR-C 프론트

- [x] PR #126~~#139 — 지도 실 feature 로딩, trip 지도/POI 패널, 검색/내 위치/우클릭,
      POI 추가/재정렬/편집/삭제, 위치 동의, notice-plan copy, 공유 링크, 첨부 업로드,
      feature 제안, 댓글, 동반자, 동선 최적화, POI 상세 편집을 완료했다.

### 머지 히스토리

| PR            | 제목                                                                             | merge 일   | 비고                         |
| ------------- | -------------------------------------------------------------------------------- | ---------- | ---------------------------- |
| PR #9         | Sprint 1 진입 PR                                                                 | 2026-05-26 | T-030 ~ T-035                |
| PR #10        | Sprint 2 진입 PR                                                                 | 2026-05-26 | 사용자/Trip/POI/동의/Storage |
| PR #11        | Sprint 3 진입 PR                                                                 | 2026-05-26 | Admin + RBAC + audit chain   |
| PR #14        | docs: Sprint 4~~6 plan + ADR-018~~023                                            | 2026-05-27 | 릴리즈 마일스톤 정리         |
| PR #15        | ci: GitHub Actions workflow 복원 (Sprint 4 PR-A)                                 | 2026-06-05 | T-114/T-065                  |
| PR #16        | feat: 백엔드 features API + kor-travel-map Protocol + cluster + trip view (PR-B) | 2026-06-05 | T-060 일부                   |
| PR #52        | feat: add admin trip management                                                  | 2026-06-06 | T-120                        |
| PR #53        | feat: add admin POI management                                                   | 2026-06-06 | T-121                        |
| PR #54        | docs: fix T-123 consistency gaps                                                 | 2026-06-06 | T-123                        |
| PR #55        | docs: align Gemini responsibility boundary                                       | 2026-06-06 | T-149                        |
| PR #56        | docs: align tracking docs with merged work                                       | 2026-06-06 | T-150                        |
| PR #57        | docs: backfill auth rbac audit ADRs                                              | 2026-06-06 | T-151                        |
| PR #58        | docs: align map social kor-travel-geo docs                                       | 2026-06-06 | T-143                        |
| PR #59        | docs: fix rise set and gemini SQL docs                                           | 2026-06-06 | T-147                        |
| PR #60        | fix: use db roles for geofence admin bypass                                      | 2026-06-06 | T-142                        |
| PR #61        | docs: define trip search and export UX                                           | 2026-06-06 | T-144                        |
| PR #62        | docs: finalize backup schema-swap restore                                        | 2026-06-06 | T-145                        |
| PR #63        | feat: add trip realtime websocket broker                                         | 2026-06-06 | T-128                        |
| PR #64        | feat: add security incidents schema                                              | 2026-06-06 | T-138                        |
| PR #65        | feat: add trip companion comments flow                                           | 2026-06-06 | T-139                        |
| PR #67        | feat: add trip budget constraints                                                | 2026-06-06 | T-140                        |
| PR #69        | feat: add trip primary region                                                    | 2026-06-07 | T-141                        |
| PR #70        | feat: verify resend webhook signatures                                           | 2026-06-07 | T-136                        |
| PR #71        | feat: persist refresh sessions                                                   | 2026-06-07 | T-134                        |
| PR #120~~#123 | feat: T-105 첨부 도메인                                                          | 2026-06-10 | T-105                        |
| PR #125       | feat: RustFS presigned 실서명 활성화                                             | 2026-06-10 | storage                      |
| PR #126~~#131 | feat: Sprint 4 PR-C 지도 프론트 1차                                              | 2026-06-10 | T-060                        |
| PR #132~~#135 | feat: notice copy / 공유 링크 / 첨부 업로드 / feature 제안                       | 2026-06-10 | T-060                        |
| PR #136~~#139 | feat: 댓글 / 동반자 / 동선 최적화 / POI 상세 편집                                | 2026-06-10 | T-060                        |
