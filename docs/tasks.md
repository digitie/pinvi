# tasks.md — 열린 백로그

열린 진행/예정/보류 task만 둔다. 완료·머지·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 작성·유지 규칙과 반복 체크리스트는
[`docs/tasks-rule.md`](tasks-rule.md), 현재 진척과 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

## 현재 선점 / 충돌 회피

- 현재 선점: `T-VN-M05-ACTIVATION` — `codex/m05-activation`. M05 설정·compose·activation
  receipt 경계와 ADR-065 Alembic `0100/0101` rebaseline만 만지며, T-323·Google OAuth 파일과
  충돌을 피한다.
- 현재 선점: `T-VN-41-ABC`의 Manager pair 재핀 전제 —
  `fix/runtime-role-loopback-endpoint`. Manager host-network one-shot에 필요한 PinVi runtime-role
  script의 허용 endpoint만 수정하며, 진행 중인 `codex/pr477-followup`의 API·wrapper 변경은 건드리지 않는다.

## kor-travel-map compatible pair

- [/] **T-VN-41-ABC — cache target relay producer/consumer 결박** — Map queued refresh의 source event/outbox
  원자화, restore exact replay `200` OpenAPI 선언, PinVi service artifact exact re-vendor와 restore-fence
  one-shot command를 하나의 compatible pair로 고정한다. command는 sync disabled 상태에서 immutable
  pre-CAS receipt로 응답 유실 exact replay까지 검증할 뿐 writer를 열지 않는다. PinVi 쪽 relay는
  **PR #444 머지 완료**(2026-08-18), 계약 재핀은 **#453·#454까지 머지**됐다. 남은 완료 조건은 새
  exact pair의 적대적 재리뷰와 n150 isolated rehearsal이다.
  - [ ] **docker-manager pair 재핀(F1J-D 전제)** — Manager tracked v5 pinset은 아직 옛 pair를 고정한다.
        `MAP_PINNED_RUNTIME_SOURCE`=`4672aa96…`, `PINVI_PINNED_RUNTIME_SOURCE`=PinVi 재핀 머지 SHA,
        `pinset_sha256` 재계산 후 trusted Manager release를 배포해야 n150 격리 rehearsal이 fail-close를 통과한다.
  - Map PR #1051 merge `db319a4798229098d04e68e3ac64338183ad547f`가 service OpenAPI의
    admission 상한(500,000 item/56 MiB)과 compacted-material `410`을 갱신했다. 현재 service
    artifact SHA는 `99ba6c178bf55401d3e1bb638a01b96f66bbac38d604534aa126a70f4be53d3d`이며,
    이 PinVi branch에서 vendored bytes와 provenance를 재핀한다. 이전 #453·#454 pair의
    paired CI·n150 증거는 새 exact pair의 증거로 재사용하지 않는다. 새 pair 검증 전에는
    완료 receipt를 만들지 않는다.
    production `SYNC_ENABLED=true`는 final C7 root enable boundary 전까지 Settings validation이 거부하며,
    격리 n150 live proof는 `smoke` stack에서만 실행한다.
- [/] **T-VN-41-F — C6c 격리 compatible-pair 증명** — 서비스 전 단계이므로 production consumer enable,
  운영 데이터 보존·복원, 중간 DB 백업은 이 task의 범위가 아니다. 데이터가 필요하면 fixture 또는
  ETL 재실행으로 새로 만든다. 설계 정본은
  [`t-vn-41-f1j-contract-provenance.md`](execplan/t-vn-41-f1j-contract-provenance.md)다.
  - [x] **F1J-A Map fixture lifecycle** — Map PR #960에서 동적 cancel-probe fixture의 arm/consume/finalize
        lifecycle와 DB 불변식을 병합했다.
  - [x] **F1J-B Manager orchestration** — docker-manager PR #159에서 정적 job ID를 제거하고 dynamic
        fixture의 exact unsafe `409` 회수와 response-loss 복구를 병합했다.
  - [x] **F1J-C service provenance 재결박** — PinVi PR #435와 docker-manager PR #160이 Map `1df45b57`의
        service OpenAPI exact bytes/SHA-256와 `cache_target=7`, `c6c_cancel_probe=2` capability를 하나의 일반
        service provenance로 재vendor·preflight 결박했다. PinVi ordinary runtime에는 fixture scope/token/route를
        주입하지 않는다.
  - [/] **F1J-D n150 final isolated rehearsal/UI E2E** — F1J-C의 exact pinset만으로 별도 Compose
    project·DB·volume을 생성해 destructive rehearsal과 live UI E2E를 실행하고 즉시 폐기한다. 운영
    stack·DB·backup/restore는 금지한다. 첫 격리 build에서 wheel `force-include` source path가 Docker
    filesystem에 없음을 확인했고, canonical contract를 editable install 전에 같은 source-relative
    위치에 복사하는 PinVi Docker fix는 **PR #437 머지 완료**(2026-08-06)다. 남은 일은 동일 pinset
    rehearsal 재개다.
- (역사·참조) **T-VN-41-F production final boundary 초안(2026-08-05, PR #429)** —
  [`t-vn-41-production-final-boundary.md`](execplan/t-vn-41-production-final-boundary.md). 당시 F1 re-pin은
  Manager PR #130으로 됐으나 그 pin(`c0afaa4e…`)은 F1F-A에서 old release로 판정돼 재핀됐고, F1A(default-off
  bootstrap)는 착수되지 않은 채 F1D-C one-shot·F1F-B canonical env replace로 대체됐으며, F2 cutover는 미착수다.
  문서 헤더에 역사 기록으로 표기했다. 현행 실행 정본은 위 F1J 항목이며 두 문서가 어긋나면 F1J(신규)를 따른다.

## 데이터 / 보존

- [ ] **T-VN-M05-ACTIVATION** — ADR-065 `0100/0101` rebaseline, paired live/restore/review evidence를
  요구하는 M05 production activation receipt gate와 실제 isolated activation 검증을 완료한다.
- [ ] **T-349** — `app.retention_runs`에 `status='executing'`이 최대 1개라는 불변식이 DB 제약이
  아니라 `_assert_no_concurrent_execution`의 advisory lock 규율에만 의존한다(T-343 적대적 리뷰,
  PR #480). 지금 유일한 호출 경로는 안전하지만, 향후 다른 코드 경로/수동 SQL이 이 함수를 거치지
  않고 INSERT하면 막을 DB 차원 방어선이 없다. 후속 마이그레이션으로
  `CREATE UNIQUE INDEX ... ON app.retention_runs (status) WHERE status = 'executing'` 추가
  (defense-in-depth, blocking 아님). **T-VN-M05-ACTIVATION이 끝날 때까지 진행 불가** —
  `tests/unit/test_tvn40_migration_immutability.py`의
  `test_active_migration_artifacts_are_complete_and_digest_guarded`(PR #466)가
  `alembic/versions/`에 `20260824_0100`/`20260824_0101` 두 파일만 있어야 한다고 고정해 둬서,
  이 activation이 끝나 그 가드가 풀리기 전에는 새 마이그레이션이 CI를 통과할 수 없다(claude,
  PR #491에서 실제로 막힘 확인, 마이그레이션·회귀 테스트 코드는
  `agent/claude-t349-retention-unique-index` 브랜치에 보존).

## 웹 / 테스트 인프라

- [ ] **T-351** — 통합 테스트 스위트가 계속 자라(662건+) T-348로 타임아웃을 올려도 구조적으로는
  같은 문제가 재발한다(T-348 적대적 리뷰에서 지적, PR #481 코드 주석에도 "스위트가 더 자라면
  다시 올려야 한다"고 명시). 근본 해법은 숫자 상향이 아니라 `pytest tests/integration`을 여러
  job으로 샤딩하거나 느린 테스트를 분리하는 것 — CI job 구조 변경이 필요해 별도 task로 뗀다.

## 모바일

- [ ] **T-320** — 모바일 위치 동의 gate 런타임 확인. VWorld 키가 있는 환경에서 지도 표면을 띄우고
  "현재 위치로"가 OS 권한 요청 전 동의를 받는지 확인한다(T-310 smoke에서 키 부재로 미확인).
- [ ] **T-352** — `expo-doctor` 잔여 2건(T-311의 react 중복 해소 후 재확인 — react/react-dom은
  이제 워크스페이스 전체 `19.2.6` 단일본이라 통과): SDK-56 patch 드리프트로 인한 Hermes V1 메모리
  회귀(Expo SDK 57 `expo@^57.0.9` + React Native 0.86.2+ 업그레이드 필요)와 `react-native-screens`
  중복(앱 직접 의존 `4.25.2` ↔ `expo-router` 내부 `4.27.0` — expo-doctor가 이제 이를 "duplicate
  dependencies"로 분류). `npx expo install --fix`류 SDK 정렬은 dev client 재빌드를 동반하므로
  별도 PR로 검증한다.

## 보류 / 미래 작업

- [ ] **T-273 — v1.0.0 E2E / Live Gate** — geofence 운영 설정과 전용 staging Web/API가 준비될 때까지
  보류한다.

## Sprint 6 / v1.0.0 후속 Task 초안

- [ ] T-274 — v1.0.0 릴리즈.
