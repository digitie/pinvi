# tasks.md — 활성 작업

이 문서는 완료되지 않은 작업만 의존 순서대로 한 줄씩 나열한다. lane, 담당자 구분,
계층형 하위 작업은 사용하지 않는다. 완료·퇴역 이력은
[`docs/tasks-done.md`](tasks-done.md), 현재 근거와 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

- [/] T-VN-M05-TEMPLATE0-PINSET — `68d99705…`·`285618c0…`·`37932169…`·`31fe73ad…`·`b22bfb8c…`·`89330403…`·`c6c73cdf…` n150 candidate는 terminal로 보존하며 재시도하지 않는다. `c6c73cdf…`은 `foreign_membership` terminal이며 원문 builder 출력·stderr·catalog row는 읽지 않았다.
- [/] T-VN-M05-NEW-CANDIDATE — PinVi `69a5ac65…`·Map `9c64e862…`의 pinset `030b12fc…`은 `committed` generation(Map application `300`, Map Dagster `29b539ebc72a`, PinVi `20260824_0101`)으로 보존하며 재실행하지 않는다. committed Map runtime provenance를 반영한 PinVi `a90b1f06…`·Map `9c64e862…`의 pinset `87fe2abc…`만 다음 trusted release candidate다. 이 새 pinset에서만 `rebuild-pinned --confirm --json`을 정확히 한 번 실행한다.
- [ ] T-VN-M05-ACTIVATION — provenance가 재결박된 committed candidate에서만 isolated M04/M05 live mutating E2E와 activation attestation을 통과한다.
- [ ] T-VN-41F1D-D1 — 최종 격리 리허설과 provenance attestation을 기록한다.
- [ ] T-VN-41F1D-D2 — data-dependent Map/PinVi admin live E2E와 receipt 승격을 완료한다.
- [ ] T-VN-41C — relay, reconciliation, consumer enable paired acceptance를 완료한다.
- [ ] T-VN-41F1D-E — 이전 generation 퇴역과 v6/v8 attestation 전환을 완료한다.
- [ ] T-VN-H49 — standalone backup의 주기 실행, bounded retention, off-box 증거를 완료한다.
