# tasks.md — 활성 작업

이 문서는 완료되지 않은 작업만 의존 순서대로 한 줄씩 나열한다. lane, 담당자 구분,
계층형 하위 작업은 사용하지 않는다. 완료·퇴역 이력은
[`docs/tasks-done.md`](tasks-done.md), 현재 근거와 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

> **M05/T-VN-41 교차 저장소 감사(2026-09-18)**: 이 클러스터는 `kor-travel-map`·
> `kor-travel-docker-manager`(`ktdctl`)와 공유하는 task ID를 쓴다. 같은 "M05" 라벨이
> 저장소마다 다른 범위(ktdctl/PinVi = execution-identity v6 cross-repo activation
> 게이트, Map = 그 게이트에 대한 Map 측 attestation **+** 별도의 Map 전용
> provider-dedup 프로토콜 ADR-097)를 가리켜 혼선이 있다 — 아래 개별 항목에 정확한
> 근거를 남긴다. `kor-travel-map` 저장소 `docs/tasks-done.md`에도 별도로
> **line 577에 미해결 git merge conflict marker(`|||||||`, commit `ae547dead7`,
> 2026-08-31)가 그대로 커밋돼 있다** — Pinvi가 고칠 파일이 아니라 여기 기록만 남긴다.
- [/] T-VN-M05-EXECUTION-IDENTITY-V6 — 반복 terminal을 문서 revision/Map·PinVi source 변경으로 우회하지 않도록 Docker Manager `ktdctl`의 v5 source pinset(Map·PinVi materialization identity)은 보존하고, trusted Manager installer revision까지 포함한 v6 execution identity를 execution ledger·terminal block·public generation binding·PinVi isolated admission·activation attestation에 도입한다. Manager revision은 CLI/환경이 아니라 `.ktdm-source-revision`과 `.ktdm-release-manifest.json`의 root no-follow 대조 결과만 수용한다. v5 history/block과 v6/v8 evidence는 immutable legacy audit으로 남기고, 새 v6 execution history/block을 별도 namespace로 관리한다. 기계적 문서는 즉시 병합하며 runtime source tuple을 재결박하지 않는다. terminal raw E2E output은 M05 완주 전까지 gitignored `m05-e2e-analysis.local.md`에만 상세 forensic으로 기록하고 stage·commit·push하지 않는다.
  **⚠️ 미해소 교차 저장소 모순**: `kor-travel-map`은 `docs/tasks-done.md`에 이 정확한 ID를
  `[x]` 완료(2026-08-31, 근거: 2026-08-29~30 같은 pair `3916ebfd`/`b6af59f2` 위에서
  Map 커밋 0개로 9개 candidate 실행·phase 단조 전진 — A1~A4 전부 충족)로 기록했다.
  반면 `kor-travel-docker-manager`(실 구현 저장소)의 `docs/tasks.md`는 같은 ID를
  여전히 `[/]`로 남겨 두고("registry/ktdctl/ledger/terminal-block/public-binding 배선
  잔여") `tasks-done.md`에 종결 항목이 없다(2026-09-18 확인). Map의 "완료"는 Map
  자신이 관측 가능한 기준만 충족했다는 뜻일 수 있다 — **ktdctl 쪽 종결 없이는 이
  항목을 닫지 않는다.**
- [/] T-VN-M05-TEMPLATE0-PINSET — `68d99705…`·`285618c0…`·`37932169…`·`31fe73ad…`·`b22bfb8c…`·`89330403…`·`c6c73cdf…` n150 candidate는 terminal로 보존하며 재시도하지 않는다. `c6c73cdf…`은 `foreign_membership` terminal이며 원문 builder 출력·stderr·catalog row는 읽지 않았다. (교차 저장소 감사: Map·Manager 어느 쪽에도 이 ID는 없다 — PinVi 전용 잠긴 이력 기록.)
- [/] T-VN-M05-NEW-CANDIDATE — PinVi `69a5ac65…`·Map `9c64e862…`의 pinset `030b12fc…`은 `committed` generation(Map application `300`, Map Dagster `29b539ebc72a`, PinVi `20260824_0101`)으로 보존하며 재실행하지 않는다. committed Map runtime provenance를 반영한 PinVi `a90b1f06…`·Map `9c64e862…`의 pinset `87fe2abc…`만 다음 trusted release candidate다. 이 새 pinset에서만 `rebuild-pinned --confirm --json`을 정확히 한 번 실행한다. (교차 저장소 감사: Map·Manager 어느 쪽에도 이 ID는 없다 — PinVi 전용 잠긴 이력 기록.)
- [ ] T-VN-M05-ACTIVATION — provenance가 재결박된 committed candidate에서만 isolated M04/M05 live mutating E2E와 activation attestation을 통과한다.
  **⚠️ 미해소 교차 저장소 모순**: `kor-travel-map`은 같은 ID를 `[x]` 완료(2026-09-08,
  "M04/M05 live acceptance attestation 승격")로 기록했다. `kor-travel-docker-manager`는
  "M05 activation"을 여전히 `[ ]`(미착수)로 두고, 2026-09-03 측정 기록에 "**남은
  판정은 소유자 몫**"이라고 명시했다 — 그 직후 pair 계약이 v1→v2로 승격(9/7~9/8,
  PinVi PR #538/539)했으므로 9/3 측정은 "fresh candidate" 요건상 무효화됐을 가능성이
  높다. v2 계약 위에서 `pin rotate-pair → run-pinned-rebuild-once →
  run-m05-isolated-e2e-once → activation attestation`이 재실행된 기록이 세 저장소
  어디에도 없다 — **다음 단계는 여기서 막혀 있다.**
- [ ] T-VN-41C — relay, reconciliation, consumer enable paired acceptance를 완료한다.
  **교차 저장소 확인(2026-09-18)**: `kor-travel-map`은 이 ID를 `[ ]`로 유지하되
  "**보류**(오너 지시 2026-09-07)"로 명시한다 — relay/reconciliation 구현은 끝났고,
  남은 것은 런타임 결선·enable뿐인데 현재 lifecycle에서 enable과 pinned rebuild가
  **상호배타**라 실 production 전환 시점까지 의도적으로 미룬 것이다("실 production
  전환이 결정되면 이 절을 그대로 다시 세운다"). 기술적 blocker가 아니라 owner
  timing 결정이므로 여기서도 같은 상태로 둔다.
- [ ] T-VN-H49 — standalone backup의 주기 실행, bounded retention, off-box 증거를 완료한다.

## 모바일

- [ ] **T-320** — 모바일 위치 동의 gate 런타임 확인. VWorld 키가 있는 환경에서 지도 표면을
      띄우고 "현재 위치로"가 OS 권한 요청 전 동의를 받는지 확인한다(T-310 smoke에서 키 부재로
      미확인). T-353이 풀려 SDK 57 development APK가 나왔으므로(EAS `b3a52da4`, 2026-09-05) 이제 진행 가능하다. VWorld 키가 있는 환경에서 그 APK를 설치해 확인한다.
