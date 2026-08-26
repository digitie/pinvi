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
2. 기존 aggregate predicate와 같은 catalog facts를 class별 boolean으로 분리해 JSON 한 줄로
   만든다. SQL은 `BEGIN READ ONLY`와 `SELECT` 외 문장을 쓰지 않는다.
3. disposable PostGIS 16 Compose test에서 canonical sealed result, stale membership의 typed
   noncanonical result, verifier 전후 catalog fingerprint 불변을 확인한다.
4. static test에서 verify-only가 mutation 경로·raw output을 갖지 않고 endpoint/input failure도
   typed JSON으로 닫히는지 확인한다.
5. PinVi PR merge 뒤 별도 Docker Manager PR이 exact revision/pinset과 root-only verifier
   command를 추가한다. 새 source는 old d9 journal의 authority가 아니며 새 candidate가 필요하다.

## 완료 조건

- 통합 test가 실제 PostGIS 16에서 canonical과 stale membership의 typed 결과를 증명한다.
- verify-only 전후 catalog fingerprint가 동일하다.
- verifier output과 오류 경로에 secret·DSN·catalog 값이 없다.
- 두 전문 적대 리뷰가 PinVi source PR을 승인한다.
- Manager wiring은 이 PR과 분리하고, 새 immutable pinset/candidate에서만 사용한다.
