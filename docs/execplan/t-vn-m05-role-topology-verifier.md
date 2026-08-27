# T-VN-M05 — sealed role topology 읽기 전용 진단

## 배경

Docker Manager의 고정 PinVi 후보 d9는 `map_runtime_ready` 뒤 role lifecycle의 open과
failure cleanup seal 양쪽에서 `role_topology_noncanonical`로 중단됐다. 현재 bootstrap
script는 role·membership·ACL·schema를 변경한 뒤 여러 불변식을 하나의 boolean으로
합친다. 따라서 기존 후보를 재실행하면 원인을 판별하지 못한 채 PostgreSQL cluster-global
catalog를 다시 변경하게 된다.

이 작업은 그 후보를 재개하거나 자동 수리하지 않는다. 기존 strict 정책을 낮추지 않고,
sealed 상태만 관찰하는 비밀 비노출 진단 계약을 PinVi source에 추가한다.

## 목표와 범위

- `PINVI_ROLE_TOPOLOGY_VERIFY_ONLY=1`일 때 기존의 승인 endpoint·role 입력 검증을 사용한다.
- verifier는 `PINVI_MIGRATOR_DISABLE_LOGIN=1` 및 non-legacy profile만 허용한다.
- `BEGIN READ ONLY` 안 `SELECT`로만 topology를 확인하고 정확히 한 줄의 고정 JSON만 출력한다.
- noncanonical 이유는 값이 아닌 고정 enum으로 분류한다. role/database 이름, OID, ACL 값,
  endpoint, 경로, password, psql raw stderr는 출력하지 않는다.
- normal bootstrap의 role reconciliation·open→admin→seal 규칙과 failure behavior는 바꾸지
  않는다. unexpected membership/ACL을 자동으로 제거하지 않는다.
- 단, 새 candidate가 target PinVi DB를 파기·재생성한 직후에만 `PINVI_ROLE_CATALOG_RESET_ONLY=1`
  one-shot을 허용한다. 이는 일반 reconciliation이 아니라 이전 terminal candidate가 남긴
  cluster-global role membership/setting을 제거하기 위한 fresh-target bootstrap 전용 경계다.
  정확히 네 generated non-root role만 대상으로 하며, target 밖 membership·database ownership·
  role setting·shared dependency가 하나라도 있으면 role을 변경하지 않고 실패한다.

## 진단 계약

성공 출력은 다음 schema를 사용한다.

```json
{"schema":"pinvi.role-topology-diagnostic.v1","status":"canonical","mode":"sealed","reasons":[]}
```

`status`는 `canonical`, `noncanonical`, `invalid`, `unavailable` 중 하나다. `reasons`는
정렬된 다음 고정 enum만 담는다.

- `principal_identity`
- `bootstrap_catalog`
- `fence_acl`
- `runtime_role`
- `schema_owner_membership`
- `migration_owner_policy`
- `migrator_sealed`
- `migrator_membership_setting`
- `app_ownership`
- `extension_ownership`
- `input_invalid`
- `endpoint_unavailable`
- `verification_unavailable`

## 구현 순서

1. bootstrap script의 input validation과 endpoint readiness 뒤에 verify-only early-return을 둔다.
2. normal final gate와 sealed verifier가 **하나의** catalog evaluator를 사용하게 한다. evaluator는
   normal에는 `t`/`f`, verifier에는 status와 ordered reason record만 내며, SQL은 `BEGIN READ ONLY`와
   catalog `SELECT`·`ROLLBACK` 외 문장을 쓰지 않는다.
3. verifier는 evaluator record를 fixed enum/strictly increasing order로 다시 검증한 뒤 JSON 한 줄을
   재구성한다. empty·unknown·duplicate·역순·multiple record는 `verification_unavailable`으로
   fail-close한다.
4. disposable PostGIS 16 Compose test에서 canonical sealed result와 fixed 10-enum 전체의
   typed noncanonical result를 확인한다. `principal_identity`는 database owner collision이
   함께 위반하는 `fence_acl`·`migrator_sealed`까지 ordered multi-reason으로 증명하며, verifier
   전후 확장 catalog fingerprint 불변도 확인한다.
5. static test에서 verify-only가 mutation 경로·raw output을 갖지 않고 endpoint/input failure 및
   malformed evaluator record도 typed JSON으로 닫히는지 확인한다.
6. fresh catalog reset은 target DB가 비어 있는지와 foreign dependency 부재를 한 transaction에서
   확인한 뒤 exact four-role `DROP ROLE`만 실행한다. `DROP OWNED`, `REASSIGN OWNED`, bootstrap
   root role 변경, legacy profile, 일반 runtime에서의 실행은 금지한다. 실패 출력에는 role·DSN·
   catalog raw 값을 남기지 않는다.
7. PinVi PR merge 뒤 별도 Docker Manager PR이 exact revision/pinset과 root-only reset·verifier
   command를 추가한다. sealed verifier는 폐기 대상인 기존 DB의 admission이 아니라 fresh target-state
   후조건이다. 따라서 Manager는 durable reset intent 뒤 DB reset → fresh catalog reset → role open →
   admin/migration bootstrap → seal 및 exact head 확인 뒤, PinVi runtime start/manifest commit 전에만
   이를 호출한다. noncanonical·unavailable/reset failure는 원문이나 reason enum 없이 owner-only terminal
   receipt로 같은 pinset을 봉인한다. 새 source는 old d9·cbb·52·06045 journal의 authority가 아니며
   새 candidate가 필요하다.

## 완료 조건

- 통합 test가 실제 PostGIS 16에서 canonical과 stale membership의 typed 결과를 증명한다.
- normal gate와 verifier가 common evaluator를 사용하며, verify-only 전후 확장 catalog fingerprint가
  동일하다.
- JSON은 exactly one record와 ordered fixed enum만 수용하고 malformed record는
  `verification_unavailable`으로 닫힌다.
- verifier output과 오류 경로에 secret·DSN·catalog 값이 없다.
- fresh catalog reset은 stale four-role residue를 제거한 뒤 canonical normal open을 통과하며,
  foreign dependency면 mutation 없이 fail-close한다.
- 두 전문 적대 리뷰가 PinVi source PR을 승인한다.
- Manager wiring은 이 PR과 분리하고, 새 immutable pinset/candidate에서만 사용한다.
