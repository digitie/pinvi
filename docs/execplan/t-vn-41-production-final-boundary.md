# T-VN-41-F — production final boundary 실행 계획

## 목적과 범위

generation 7 cache-target consumer를 production에서 처음 활성화하고, Map과 PinVi의 최종
증적을 append-only boundary audit으로 확정한다. 이 작업은 격리 paired proof(`T-VN-41-P`)를
반복하지 않는다. production의 실제 pair와 Docker-manager journal을 단일 정본으로 삼아
`ktdctl cache-target cutover` 한 명령으로만 전환한다.

직접 `docker compose`, `.env` 수정, Map/PinVi DB 직접 변경, 일반 API로의 fence·finalize 호출은
범위 밖이며 금지한다. 결과·receipt에는 credential, host, resolved Compose, raw payload를 기록하지
않는다.

## 현재 판정과 선행 task

- `T-VN-H42`는 완료되어 provider 수렴과 Map live 검증 선행 조건이 충족됐다.
- Map durable writer drain과 Docker-manager recovery hardening은 최신 Manager 기준 재검토에서
  P0/P1이 없고 관련 회귀가 통과했다.
- 그러나 Docker-manager의 tracked production manifest는 이전 generation 7 pair를 고정한다.
  현재 배포 pair의 cache-target contract는 Map functional owner
  `e12494bd5c4b5b2e1d51c72b6ddcf18eead0e53f`, Map release
  `c0afaa4e318a2e2e6d85f53bb889af3e6adec8c1`, PinVi release
  `3ff54b8b15965c6ecd5c55b1419208e65831c7fe`, service OpenAPI SHA-256
  `144b4335d98fc021368b3297f5b8ed7b1c560e9850ebbdd8af71e45623ba7b3d`다.

따라서 이 task는 다음 PR 단위로 직렬화한다.

1. **T-VN-41-F1 — Docker-manager pair re-pin**: production manifest, cutover runbook,
   release/contract regression을 위 exact pair로 함께 갱신한다. Manager를 production에 배포한 뒤
   read-only preflight가 같은 pair를 확인해야 한다.
2. **T-VN-41-F2 — production boundary**: F1 merged·deployed 뒤 n150에서 사전 진단을 실행하고,
   새 canonical UUID로 `ktdctl cache-target cutover --json`을 정확히 한 번 시작한다. 결과를 이
   문서·작업 기록 PR에 secret-free 요약으로 추가한다.

F1가 끝나기 전 F2 command를 실행하면 old manifest와 running pair가 달라 mutation 전에 중단돼야
한다. 그 fail-close를 우회하거나 manifest 값만 production에서 수동으로 바꾸지 않는다.

## F2 실행 gate

1. n150에서 canonical production checkout의 Manager release, Map release, PinVi release, migration
   head, pair manifest와 cache-target pin을 read-only로 대조한다. non-terminal window/enable/diagnostic
   journal, active writer, stale runner, partial sync setting 하나라도 있으면 중단한다.
2. `ktdctl cache-target diagnose --diagnostic-id <new-uuid> --json`으로 writer-drain, backup/archive,
   scratch restore, immutable pair와 authenticated smoke를 확인한다. 진단 receipt는 cutover backup으로
   재사용하지 않는다.
3. `sync=false`와 새 positive restore epoch을 확인하고 새 `cutover_id` 및 비밀 없는 사유를 정한다.
   operator는 exact Manager release의
   `ktdctl cache-target cutover --cutover-id <uuid> --expected-restore-epoch <n> --reason <reason> --json`
   만 호출한다. initial, enable, raw Compose를 나누어 호출하지 않는다.
4. Manager가 같은 global lock 안에서 `csv5 → Map H35 gc → final all-writer fence → stopped-Map typed
   evidence → Pin finalize`를 수행한다. `initial`/sync enable/causal canary, final Map evidence와
   Pin append-only audit은 각각 durable journal phase 및 typed digest로 결박돼야 한다.
5. 성공 후 PinVi cache-target readiness, Map/PinVi compatible-pair attestation, command backlog/DLQ 0,
   cursor/count/Merkle exact equality, final audit row 1건을 read-only로 재확인한다. n150 production UI
   smoke는 login과 sync 상태만 확인하며 credential·browser state는 즉시 폐기한다.

## 실패·복구 규칙

- 외부 event 이전의 failure/crash는 Manager의 same-journal resume 또는 coupled rollback만 허용한다.
  성공 여부가 불확실하면 새 ID를 만들지 않고 같은 ID로 재개한다.
- Manager가 terminal `rolled_back`을 기록하면 sync=false runtime과 pair attestation이 확인될 때까지
  다른 mutation을 시작하지 않는다.
- final boundary/audit이 성공한 뒤에는 old image-only rollback, audit 삭제, DB 직접 복원으로 되돌리지
  않는다. 후속 문제는 새 forward task와 append-only evidence로 다룬다.
- 진단·preflight 실패, stale pin, journal identity 불일치는 모두 F2 미시작으로 기록하고 원인을 F1
  또는 별도 task에서 수리한다.

## 완료 기준

- F1의 code/문서/test PR이 merge되고 production Manager가 해당 revision으로 재배포됐다.
- F2는 Manager의 terminal `runtime_activated`와 Pin final boundary audit의 fresh read-back까지
  도달했거나, fail-close/rollback receipt와 정확한 재개 조건을 남겼다.
- `docs/tasks.md`, `docs/tasks-done.md`, `docs/journal.md`, `docs/resume.md`와 PR에 secret-free
  result를 동기화한다. 성공 시에만 `T-VN-41-F`를 완료로 이관한다.
