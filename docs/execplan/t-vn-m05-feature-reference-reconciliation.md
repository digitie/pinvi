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
  Full/admin 표면은 Map `main` merge `2845e14243ae7f342a7dc840e834ddffd3220436`의
  `openapi.json`(SHA-256 `6419c1332ba95ab03b8ec794d9d2e7c2a6f2e6da012d23118708e4e4bc5343bb`) 기준이며,
  user 표면은 #1029 계열 pin을 유지한다.
- M05가 결박하는 admin/full/service/user OpenAPI SHA-256과 source revision의 exact 쌍은
  [`contracts/kor-travel-map-m05-pair-provenance-v1.json`](../../contracts/kor-travel-map-m05-pair-provenance-v1.json)에
  고정한다. service 항목은 일반 service provenance와 반드시 일치해야 한다.
- M04 approval을 M05 old Feature에 결박할 때는 provenance의 opaque `feature_id`를 approved request의
  resolved reference와 대조하고, 별도 `feature_uuid`를 manual/old Feature UUID에 각각 대조한다.
  receipt에는 manual case의 복사본이 아니라 검증된 provenance UUID만 기록한다.
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

1. `trip_day_pois`에서 old reference를 가리키는 행을 `FOR UPDATE`로 읽는다. canonical
   축은 UUID다(Map ADR-068): `feature_uuid`가 같으면 텍스트 축이 무엇이든 같은 feature다.
   `feature_uuid`가 NULL이면(= 검증된 alias map 이관 전 정상 상태) legacy 축으로 판정한다.
   **one-column만 같으면 partial**이라는 종전 규칙은 폐기했다 — 그 규칙 아래에서는 평범한
   행 하나가 피드를 영구히 세웠고, cutover가 만드는 `(legacy alias, canonical UUID)` 전체가
   Map의 값 전환 이후 통째로 blocked가 됐다.
2. `curated_plan_pois`도 같은 방식으로 읽는다. curation receipt six-column proof가 있는
   행은 바꾸지 않고 blocked evidence를 남긴다. receipt가 없는 행만 rebind/detach 가능하며,
   snapshot은 변경하지 않는다.
3. `feature_suggestions`의 correction/closure target pair를 잠근다. `pending|approved`는
   blocked이고, `rejected|added|duplicate` target은 절대 고치지 않는다.
4. **진짜 모순**(legacy 축은 old를 가리키는데 canonical 축이 *다른* feature를 가리킴),
   source mismatch, receipt-bound curation POI 또는 nonterminal suggestion가 하나라도
   있으면 mutation 없이 `blocked` attempt만 commit하고 Map ACK을 호출하지 않는다.
5. block이 없을 때 `rebind`는 legacy 축을 replacement로 바꾼다. canonical 축은
   **이미 채워져 있던 행에서만** replacement로 이동하고, 비어 있던 행에는 새로 새기지
   않는다 — 그 행이 old를 가리킨다는 유일한 근거가 길이만 검증되는 client 자유 문자열이라,
   미검증 값을 정본화하면 "검증된 alias map만 채운다"는 모델 불변식이 깨진다(적대 리뷰 F1,
   `feature_uuid_cutover`). 정본화 권한은 cutover에 남고, 다음 이관이 새 참조를 검증해 채운다.
   두 column 변경은 같은 flush 안에 이뤄지고,
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
사용하려면 `PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ACTIVATION_RECEIPT` 또는
root-owned `0600` bind-mounted `PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ACTIVATION_RECEIPT_PATH`에
서명된 v1 envelope를 주입하고, `PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ACTIVATION_RECEIPT_PUBLIC_KEY`로
Ed25519 서명을 검증한다. 이 public key는 같은 설정 채널의 receipt와 함께 임의로 바꿀 수 없으며,
tracked `contracts/pinvi-m05-activation-receipt-trust-v1.json`의 raw public-key SHA-256 fingerprint와
일치해야 한다. API는 기동 시 중복 JSON key·서명·닫힌 payload schema·현재 vendored
Map pair·세 Pinvi runtime image digest·`PINVI_SOURCE_REVISION`을 모두 대조하며, 하나라도 다르면
fail-close한다. receipt payload에는 실제 API container ID도 포함되므로 운영 배포는 inline 환경변수보다
파일 경로를 사용한다. 최종 container를 재생성하지 않은 상태에서 receipt 파일만 봉인·교체한 뒤 기동해야 한다.

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
revision, 실행 중 Map API의 HTTP OpenAPI 응답 hash, Map API/admin/frontend image digest, Pinvi
API/Web/Dagster image digest, Pinvi source revision, live UI event·Map ACK·restore·review evidence
hash를 포함한다. attestation 단계에서 실행 중 Map admin OpenAPI의 정규화된 JSON을 pinned Git
blob과 비교한다. receipt는 증거 원문이나 token·private key를 담지 않는다. 두 전문 적대 리뷰,
isolated live UI E2E, server-side Map ACK 대조, no-owner restore drill이 실제로 끝난 뒤에만
생성한다.

증거 봉인은 다음 도구가 수행한다. 입력 디렉터리는 `0700`, JSON 증거와 private key는 각각
`0600`이어야 하며, 운영 실행에서는 `--require-root-owned`를 사용한다.

```bash
python scripts/m05_activation_receipt.py create \
  --evidence-dir "$M05_EVIDENCE_DIR" \
  --private-key "$M05_ACTIVATION_PRIVATE_KEY" \
  --output "$M05_ACTIVATION_RECEIPT" \
  --pinvi-source-revision "$PINVI_SOURCE_REVISION" \
  --review-response-nonce "$PINVI_M05_REVIEW_RESPONSE_NONCE" \
  --require-root-owned
```

`create`에는 challenge 파일(`--review-challenge`), 해당 실행에서만 전달한 review response nonce
(`--review-response-nonce`), external allowlist(`--review-allowlist`)를 함께 전달한다. ledger 기록 시에는
`--durable-history`와 `--durable-anchor`를 ledger/high-watermark/floor와
분리된 root-owned durable 경로에 append한다. anchor는 coordinated snapshot rollback을 막기 위해
별도 durable mount에 둔다. `PINVI_M05_ACTIVATION_ANCHOR_DATABASE_URL`을 ledger producer에만
전달하면 `ops.m05_activation_database_anchor`에도 같은 record hash를 append한다.

실제 복원 증거는 고정된 `scripts/backup-db.sh`와 `scripts/restore-staging-drill.sh`를 source→fresh
target으로 호출하는 `scripts/m05_restore_drill.py`가 만든다. source·target URL과 runtime URL은
환경변수로만 전달하며, 결과 JSON에는 URL·SQL 비밀값을 저장하지 않는다.

fresh target은 매 실행 `DROP DATABASE ... WITH (FORCE)` 뒤 target cluster의
`PINVI_RESTORE_TEMPLATE_DATABASE_URL`에서 재생성한다. 이 template은 `app` schema가 없어야
하고 `x_extension` schema에 `citext`, `pgcrypto`, `pg_trgm`이 설치되어 있어야 하며 runtime
login에 `x_extension` USAGE만, 별도 `PINVI_RESTORE_HOTSWAP_DATABASE_URL`의 executor에
database `CREATE`와 `x_extension` USAGE만 부여한다. extension 설치는 one-time privileged
bootstrap에서 수행하고 restore staging login에는 extension 생성 권한을 주지 않는다. staging
provisioner는 disposable database 재생성을 위해 `CREATEDB`를 가지지만 target owner가 아니다.
별도 `PINVI_RESTORE_FENCE_DATABASE_URL`/`PINVI_RESTORE_FENCE_ROLE`의 target owner는
`CREATEDB`와 role membership가 없어야 하며, target 생성 후 staging에는 `CONNECT`, hotswap에는
`CONNECT, CREATE`만 부여한다. hotswap executor는 `CREATEDB` 없이 `INHERIT`와 직접
`pg_signal_backend` membership만 가진다. restore는
hotswap executor로 수행해 복원된 `app` schema의 owner와 schema-swap executor를 동일하게
결박한다.

입력 파일은 `reviews.json`, `live-ui.json`, `restore.json`, `map-pair.json`,
`pinvi-images.json`과 live verifier가 생성한 서명 `attestation.json`이다. signer는 schema·현재
tracked pair·각 pinned Map commit의 Git blob·실제 Map HTTP OpenAPI·실제 runtime image ID/OCI
revision·immutable `sha256:` digest와 source revision을 확인한 후 payload를 서명한다.
`--require-root-owned` 실행에서는
private key와 증거 디렉터리도 tracked trust anchor/소유권과 대조한다. 출력된 public key와 receipt는
운영 secret 저장소에 등록하고, 원문 증거·append-only ledger는 root-owned 보관 위치에서 API에
read-only로만 mount한다.

리뷰 증적은 실행 전에 만든 root-owned challenge 파일에 commit, PR, 두 reviewer ID, 각 reviewer의
원문 응답 경로와 one-run nonce의 hash를 고정한다. nonce 원문은 challenge 파일에 저장하지 않고 두
리뷰어와 signer 프로세스에만 전달하며, 두 응답은 nonce·challenge ID와 원문 SHA-256을 함께 제출해야
한다. signer는 allowlist와 `reviews.json`이 challenge 파일의 실제 원문에 결박되지 않으면 거부한다.
복구 도구는
`PINVI_M05_RESTORE_TOOL_TRUST_MANIFEST`의 root-owned `0600` manifest에 고정된 `git`, `pg_dump`,
`pg_restore`, `psql` 경로·digest만 사용한다. live가 아닌 테스트 모드의 fake tool은 root-owned
운영 증적으로 승격할 수 없다.

복구 드릴의 target은 `pinvi_m05_restore_*` prefix 안에서 매 실행 `DROP DATABASE ... WITH (FORCE)`
후 extension template에서 새로 만들며, source/target/runtime의 database OID·system identifier·pinned `hostaddr`·port를
복구 직전과 직후에 대조한다. activation ledger·high-watermark와 별도로 DB snapshot에 포함하지 않는
durable history(`PINVI_M05_ACTIVATION_DURABLE_HISTORY_PATH`)와 외부 anchor
(`PINVI_M05_ACTIVATION_DURABLE_ANCHOR_PATH`)도 같은 generation과 receipt hash를 append-only hash
chain으로 보존한다. 여기에 `ops.m05_activation_database_anchor` append-only DB anchor도 같은
generation·receipt·ledger record hash를 보존한다. 네 파일과 두 anchor가 서로 어긋나거나 anchor보다
과거인 snapshot은 API startup에서 거부한다.

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
