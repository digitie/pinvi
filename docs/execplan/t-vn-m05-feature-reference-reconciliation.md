# T-VN-M05 — Feature 참조 재결합 paired consumer

## 목표

Map의 `manual-provider` 판단이 만든 immutable `rebind|detach` event를 PinVi가
자기 `app` schema에서 안전하게 적용하고, **local final receipt가 commit된 뒤에만**
Map에 ACK한다. 이 문서는 Map ADR-095와
`docs/reports/t-vn-m05-manual-provider-dedup-design-2026-08-21.md`를 PinVi 소비자
경계로 구체화한다.

기본 활성화는 `false`다. production에서 켜려면 현재 Map service contract와 PinVi image
revision에 맞는 activation receipt가 필요하다. Map subscription activation receipt,
production flag 또는 일반 운영 stack의 mutation만으로는 이 작업의 완료 증거가 아니다.

## 기준 계약

- Map service contract source: PR #1051 merge `db319a4798229098d04e68e3ac64338183ad547f`.
  Full/admin 표면은 PR #1054 merge `fadc029ce2b0cd730c604697e04d1fccdff02ce9` 기준이며, user
  표면은 #1029 계열 pin을 유지한다.
- M05가 결박하는 admin/full/service/user OpenAPI SHA-256과 source revision의 exact 쌍은
  [`contracts/kor-travel-map-m05-pair-provenance-v1.json`](../../contracts/kor-travel-map-m05-pair-provenance-v1.json)에
  고정한다. service 항목은 일반 service provenance와 반드시 일치해야 한다.
- read token은 `feature-reference-reconciliation:read`, ACK token은
  `feature-reference-reconciliation:ack` 한 scope만 가진 별도 server-only credential이다.
  M04 요청 큐·cache-target·admin·일반 service token과 값 재사용을 거부한다.
- service route는 `GET /v1/service/feature-reference-reconciliations`와
  `POST /v1/service/feature-reference-reconciliations/{event_id}/acks`만 쓴다.
  Map admin/API DB 또는 Map 내부 procedure를 직접 호출하지 않는다.

## local evidence 모델

새 relation은 모두 `app` schema, append-only이며 database trigger가 runtime의 raw
update/delete/truncate를 거부한다. trigger는 `ENABLE ALWAYS`라서
`session_replication_role = replica`에서도 우회되지 않는다. 같은 blocked 관측은
한 immutable attempt로만 보존하고, blocker material이 달라질 때에만 다음 attempt를 append한다.

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
   이전 final receipt가 같은 event material을 증명한 경우에만 그 receipt를 재사용해 ACK한다.
   단지 replacement tuple이 보인다는 사실만으로는 인과를 추론하지 않으며, 별도의
   `already_reconciled` impact도 만들지 않는다.
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

## production activation receipt

`PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ENABLED=true`를 production에서
사용하려면 `PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ACTIVATION_RECEIPT`에
서명된 v1 envelope를 주입하고, `PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ACTIVATION_RECEIPT_PUBLIC_KEY`로
Ed25519 서명을 검증한다. 이 public key는 같은 설정 채널의 receipt와 함께 임의로 바꿀 수 없으며,
tracked `contracts/pinvi-m05-activation-receipt-trust-v1.json`의 raw public-key SHA-256 fingerprint와
일치해야 한다. API는 기동 시 중복 JSON key·서명·닫힌 payload schema·현재 vendored
Map pair·세 Pinvi runtime image digest·`PINVI_SOURCE_REVISION`을 모두 대조하며, 하나라도 다르면
fail-close한다.

```json
{
  "payload": {
    "version": 1,
    "scope": "production",
    "adversarial_reviews": [
      {"commit": "<reviewed commit>", "p0_p1": 0, "review_id": "<review id>", "reviewer_id": "<reviewer id>"},
      {"commit": "<reviewed commit>", "p0_p1": 0, "review_id": "<review id>", "reviewer_id": "<reviewer id>"}
    ],
    "live_ui_e2e": "passed",
    "restore_drill": "passed",
    "map_pair_evidence_sha256": "<evidence hash>",
    "pinvi_image_evidence_sha256": "<evidence hash>"
  },
  "signature": "<Ed25519 signature, base64url>"
}
```

전체 payload는 구현된 닫힌 계약에 따라 Map admin/full/service/user artifact hash와 source
revision, Map API/admin/frontend image digest, Pinvi API/Web/Dagster image digest, Pinvi source
revision, live UI event·Map ACK·restore·review evidence hash를 포함한다. receipt는 증거 원문이나
token·private key를 담지 않는다. 두 전문 적대 리뷰, isolated live UI E2E, server-side Map ACK
대조, no-owner restore drill이 실제로 끝난 뒤에만 생성한다.

증거 봉인은 다음 도구가 수행한다. 입력 디렉터리는 `0700`, JSON 증거와 private key는 각각
`0600`이어야 하며, 운영 실행에서는 `--require-root-owned`를 사용한다.

```bash
python scripts/m05_activation_receipt.py create \
  --evidence-dir "$M05_EVIDENCE_DIR" \
  --private-key "$M05_ACTIVATION_PRIVATE_KEY" \
  --output "$M05_ACTIVATION_RECEIPT" \
  --pinvi-source-revision "$PINVI_SOURCE_REVISION" \
  --require-root-owned
```

입력 파일은 `reviews.json`, `live-ui.json`, `restore.json`, `map-pair.json`,
`pinvi-images.json`의 다섯 개이며, 도구가 schema·현재 tracked pair·immutable `sha256:` digest와
source revision을 확인한 후 payload를 서명한다. `--require-root-owned` 실행에서는 private key도
tracked trust anchor와 대조한다. 출력된 public key와 receipt는 운영 secret 저장소에
등록하고, 원문 증거는 root-owned 보관 위치에만 남긴다.

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
