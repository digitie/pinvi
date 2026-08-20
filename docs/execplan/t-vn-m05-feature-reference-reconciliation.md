# T-VN-M05 — Feature 참조 재결합 paired consumer

## 목표

Map의 `manual-provider` 판단이 만든 immutable `rebind|detach` event를 PinVi가
자기 `app` schema에서 안전하게 적용하고, **local final receipt가 commit된 뒤에만**
Map에 ACK한다. 이 문서는 Map ADR-095와
`docs/reports/t-vn-m05-manual-provider-dedup-design-2026-08-21.md`를 PinVi 소비자
경계로 구체화한다.

기본 활성화는 `false`다. Map subscription activation receipt, production flag 또는
일반 운영 stack의 mutation은 이 작업의 완료 증거가 아니다.

## 기준 계약

- Map draft PR #1029 source: `037e24698f74e2067ea7c8572b044076dc0ac89c`.
- vendored full/service/user OpenAPI SHA-256:
  `697a08c475fc28ba730af1dd14da89998a3a56cafbfb7676bfb3fa4a0b9ef6fd` /
  `e1152a058e176f4f3aaeb4bb0965434f657601639786463f873ac82c6f3018eb` /
  `489b05d3e62e3531233e3e7eb8c97f9ddf92aa1ecf1573b7557a5951e7f6a61b`.
- read token은 `feature-reference-reconciliation:read`, ACK token은
  `feature-reference-reconciliation:ack` 한 scope만 가진 별도 server-only credential이다.
  M04 요청 큐·cache-target·admin·일반 service token과 값 재사용을 거부한다.
- service route는 `GET /v1/service/feature-reference-reconciliations`와
  `POST /v1/service/feature-reference-reconciliations/{event_id}/acks`만 쓴다.
  Map admin/API DB 또는 Map 내부 procedure를 직접 호출하지 않는다.

## local evidence 모델

새 relation은 모두 `app` schema, append-only이며 raw update/delete/truncate 권한을
PinVi runtime에서 주지 않는다.

| relation | 정본 | 핵심 제약 |
| --- | --- | --- |
| `ktm_feature_reference_reconciliation_delivery_attempts` | 매 delivery 검사 | `(event_id, attempt_sequence)` PK, `blocked|applied`, event sequence/hash, block fingerprint, deterministic row root와 관측 시각 |
| `ktm_feature_reference_reconciliation_applied_receipts` | Map ACK이 참조할 유일한 final receipt | event id/sequence/payload hash unique, `receipt_sha256` unique, action·impact root·적용 시각 불변 |
| `ktm_feature_reference_reconciliation_impacts` | final receipt의 row 단위 영향 | receipt/index PK, local relation/key, old/new feature pair, `rebind|detach|already_reconciled` outcome |

처리 transaction은 event UUID advisory lock을 먼저 얻고 final receipt를 잠근다.
이미 receipt가 있으면 event sequence/hash/action이 동일한지 대조하고 기존 final receipt만
ACK한다. 달라지면 fail-close한다.

1. `trip_day_pois`의 old `feature_id`와 `feature_uuid`가 모두 같은 행, 그리고 one-column만
   같은 partial 행을 `FOR UPDATE`로 읽는다.
2. `curated_plan_pois`도 같은 방식으로 읽는다. curation receipt six-column proof가 있는
   행은 바꾸지 않고 blocked evidence를 남긴다. receipt가 없는 행만 rebind/detach 가능하며,
   snapshot은 변경하지 않는다.
3. `feature_suggestions`의 correction/closure target pair를 잠근다. `pending|approved`는
   blocked이고, `rejected|added|duplicate` target은 절대 고치지 않는다.
4. partial pair, source mismatch, receipt-bound curation POI 또는 nonterminal suggestion가 하나라도
   있으면 mutation 없이 `blocked` attempt만 commit하고 Map ACK을 호출하지 않는다.
5. block이 없을 때 `rebind`는 두 pair column을 replacement pair로 같은 flush 안에 바꾸고,
   `detach`는 두 column을 `NULL`로 만들며 Trip POI에는 `feature_link_broken_at`을 기록한다.
   이미 action 결과가 증명된 행은 `already_reconciled` impact로 보존한다.
6. canonical JSON UTF-8 SHA-256 final receipt와 sorted impact root, attempt, impact rows를 commit한
   뒤에만 network ACK을 한다. commit 뒤 ACK 전 crash는 재lease 뒤 기존 receipt hash로 재-ACK한다.

## runtime·UI

- lifespan worker는 별도 process-local UUID를 worker header로 사용하며 local apply는 하나씩만
  수행한다. `PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ENABLED=false`가 기본이다.
- enable 시 read/ack 두 credential, exact Map source/hash pin, 서로 다른 token, poll bounds를
  fail-close 검증한다. Map activation subscription이 없으면 worker는 503을 retry하지 않고
  readiness failure로 남긴다.
- PinVi admin은 blocked/applied attempt와 final receipt·impact를 읽기 전용으로 표시한다.
  Map decision·subscription activation을 이 UI가 만들지 않는다.

## 검증과 activation gate

- strict client: 204/409/503, exact envelopes/meta/request ID, lease/action/event SHA와
  ACK replay header를 검증한다.
- integration: rebind/detach, existing receipt response-loss retry, partial pair,
  receipt-bound curation POI, nonterminal correction/closure, terminal suggestion nonmutation,
  local lock race, ordered ACK을 검증한다.
- admin UI mock E2E는 blocked/applied evidence를 표시한다.
- activation 전 반드시 exact Map/PinVi draft pair의 N150 격리 stack에서 M04 manual request →
  provider candidate → Map admin decision → PinVi rebind/detach → Map ACK을 실제 브라우저로
  실행하고, `pg_dump` → `pg_restore --no-owner --no-privileges` 복원 드릴과 두 전문 적대
  리뷰를 통과한다. shared/prod stack 또는 mock은 이 증거를 대체하지 않는다.

