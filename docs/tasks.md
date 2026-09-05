# tasks.md — 활성 작업

이 문서는 완료되지 않은 작업만 의존 순서대로 한 줄씩 나열한다. lane, 담당자 구분,
계층형 하위 작업은 사용하지 않는다. 완료·퇴역 이력은
[`docs/tasks-done.md`](tasks-done.md), 현재 근거와 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

- [/] T-VN-M05-EXECUTION-IDENTITY-V6 — 반복 terminal을 문서 revision/Map·PinVi source 변경으로 우회하지 않도록 Docker Manager `ktdctl`의 v5 source pinset(Map·PinVi materialization identity)은 보존하고, trusted Manager installer revision까지 포함한 v6 execution identity를 execution ledger·terminal block·public generation binding·PinVi isolated admission·activation attestation에 도입한다. Manager revision은 CLI/환경이 아니라 `.ktdm-source-revision`과 `.ktdm-release-manifest.json`의 root no-follow 대조 결과만 수용한다. v5 history/block과 v6/v8 evidence는 immutable legacy audit으로 남기고, 새 v6 execution history/block을 별도 namespace로 관리한다. 기계적 문서는 즉시 병합하며 runtime source tuple을 재결박하지 않는다. terminal raw E2E output은 M05 완주 전까지 gitignored `m05-e2e-analysis.local.md`에만 상세 forensic으로 기록하고 stage·commit·push하지 않는다.
- [/] T-VN-M05-TEMPLATE0-PINSET — `68d99705…`·`285618c0…`·`37932169…`·`31fe73ad…`·`b22bfb8c…`·`89330403…`·`c6c73cdf…` n150 candidate는 terminal로 보존하며 재시도하지 않는다. `c6c73cdf…`은 `foreign_membership` terminal이며 원문 builder 출력·stderr·catalog row는 읽지 않았다.
- [/] T-VN-M05-NEW-CANDIDATE — PinVi `69a5ac65…`·Map `9c64e862…`의 pinset `030b12fc…`은 `committed` generation(Map application `300`, Map Dagster `29b539ebc72a`, PinVi `20260824_0101`)으로 보존하며 재실행하지 않는다. committed Map runtime provenance를 반영한 PinVi `a90b1f06…`·Map `9c64e862…`의 pinset `87fe2abc…`만 다음 trusted release candidate다. 이 새 pinset에서만 `rebuild-pinned --confirm --json`을 정확히 한 번 실행한다.
- [/] T-VN-M05-MAP-HEALTH-TRANSPORT — `9b6eab1e…`과 `41be91fe…`·`5512ce12…`·`b46743ea…`은 PinVi runtime/M04/M05 전에 Map host-loopback health transport에서 terminal 처리됐으므로 재실행하지 않는다. Manager `bc99ce1…`의 bounded retry, exact-head CI·전문 적대 리뷰, frozen Map `86d38d46…`·PinVi `3b9d6026…` provenance가 모두 정합할 때만 새 `ktdctl pin rotate-pair` candidate를 만든다.
- [ ] T-VN-M05-ACTIVATION — provenance가 재결박된 committed candidate에서만 isolated M04/M05 live mutating E2E와 activation attestation을 통과한다.
- [ ] T-VN-41F1D-D1 — 최종 격리 리허설과 provenance attestation을 기록한다.
- [ ] T-VN-41F1D-D2 — data-dependent Map/PinVi admin live E2E와 receipt 승격을 완료한다.
- [ ] T-VN-41C — relay, reconciliation, consumer enable paired acceptance를 완료한다.
- [ ] T-VN-41F1D-E — 이전 generation 퇴역과 v6/v8 attestation 전환을 완료한다.
- [ ] T-VN-H49 — standalone backup의 주기 실행, bounded retention, off-box 증거를 완료한다.

## 도구·환경

- [/] **T-358** — npm 11을 상시 버전으로 고정하고, 그 과정에서 드러난 lockfile 무결성 회귀를
  고친다. 브랜치 `agent/claude-t358-npm11`.

  **원래 문제**: npm 10.9.7은 `package-lock.json` 없이 의존성을 처음부터 풀 때
  `TypeError: Cannot read properties of null (reading 'edgesOut')`
  (`@npmcli/arborist` `#loadPeerSet`)로 죽는다. 크래시 지점은 `apps/web`의 `vitest ^4.1.10`이
  끌어오는 optional peer 체인(`@vitest/browser-playwright`, `jsdom`→`canvas`)이고 모바일과
  무관하다. 기존 lockfile이 그 해석을 담고 있어 지금까지 드러나지 않았다.
  → **해결**: `engines.npm`을 `>=11`로 올리고, CI 5개 job(`web.yml` 2, `mobile.yml` 3)에
  `npm install -g npm@11.19.1` 스텝을 넣어 로컬과 CI를 같은 메이저에 맞췄다.
  로컬 전역 npm도 11.19.1로 올렸다(npm 자기 자신을 교체하다 `promise-retry`를 잃는 경합이
  있어 `npx npm@11 install -g npm@11`로 우회해야 했다).

  **그 과정에서 발견한 회귀 (더 중요)**: T-352(PR #528)에서 lockfile을 재생성하며
  **`integrity` 보유율이 100%(1143/1143) → 4.8%(53/1106)로 떨어진 채 머지됐다.**
  `npm ci`가 패키지 대부분을 무결성 검증 없이 설치하는 상태였다.
  원인은 `--package-lock-only` 플래그가 아니라 **`node_modules`가 존재하는 상태에서 해석한
  것**이다 — npm이 디스크에서 트리를 읽으면(loadActual) `resolved`/`integrity`를 적지 않는다.
  전체 `npm install`로도 `node_modules`가 있으면 똑같이 재현된다.
  → **해결**: `node_modules`를 치운 뒤 재생성해 **99.5%(1252/1258)** 로 복구했다. 남은 6건은
  `@tailwindcss/oxide-wasm32-wasi`의 번들 하위 의존으로 npm이 원래 `resolved`를 적지 않는 부류다.
  → **재발 방지**: `scripts/check-lockfile-integrity.mjs`(하한 99%)를 만들어 `web.yml`의
  `lint-typecheck-build`에 배선했다(lockfile만 읽으므로 `npm ci` **전에** 돈다).
  `npm run check:lockfile`로 로컬에서도 돌린다. 가드가 실제로 실패를 잡는 것을 확인했다
  (integrity 400개 제거 → `rc=1`, 복구 → `rc=0`).

  **lockfile을 다시 만들어야 할 때의 절차**:
  `node_modules`를 먼저 치우고(`/mnt/f`에서 `rm -rf`는 매우 느리니 같은 파일시스템 안에서
  rename으로 비켜 두고 삭제는 뒤로 돌린다) → `npm install --package-lock-only` →
  `npm run check:lockfile`로 확인 → `npm ci`.

## 모바일

- [ ] **T-320** — 모바일 위치 동의 gate 런타임 확인. VWorld 키가 있는 환경에서 지도 표면을
  띄우고 "현재 위치로"가 OS 권한 요청 전 동의를 받는지 확인한다(T-310 smoke에서 키 부재로
  미확인). T-353이 풀려 SDK 57 development APK가 나왔으므로(EAS `b3a52da4`, 2026-09-05) 이제 진행 가능하다. VWorld 키가 있는 환경에서 그 APK를 설치해 확인한다.
