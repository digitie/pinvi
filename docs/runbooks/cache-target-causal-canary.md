# cache target causal canary

## 1. 목적

`pinvi-cache-target-causal-canary`로 PinVi command outbox → Map target apply → pull event inbox → ACK →
cache generation의 실제 causal chain과 최종 snapshot 수렴을 한 번에 검증한다. docker-manager가 sync가
활성화되고 ready인 running PinVi API container 안에서 호출한다.

## 2. 안전 경계

- 운영자가 공급한 UUID는 매 실행별 durable `run_id`다.
- 모든 실행은 별도 deterministic synthetic target UUID 하나를 재사용해 tombstone을 누적하지 않는다.
- user trip, `trip_day_pois`, 실제 POI는 생성·수정·삭제하지 않는다.
- ordinary API의 command/consumer token만 사용한다. restore/recovery token을 주입하지 않는다.
- 같은 run ID는 crash 뒤 재개용이다. 이미 성공한 ID의 재호출도 current head/consumer/backlog/snapshot을
  새로 재검증하며, 저장 성공 관측치와 달라졌으면 receipt를 재출력하지 않는다. 새로운 liveness 증거에는
  새 UUID를 쓴다.
- 성공한 synthetic tombstone head와 audit row는 삭제하지 않는다.
- stdout은 secret-free 단일 JSON receipt다. token, URL, raw payload를 출력하지 않는다.

## 3. 실행

docker-manager의 paired lock과 frozen environment 안에서 PinVi API container를 지정해 실행한다.

```bash
docker exec <pinvi-api-container> \
  pinvi-cache-target-causal-canary \
  --run-id <uuid> \
  --timeout-seconds 180
```

성공은 exit code `0`과 단일 JSON object다. stderr의 실패 메시지는 error code와 phase만 포함하며
credential이나 원격 응답 body를 포함하지 않는다. 예상하지 못한 Pydantic/URL/token parsing 오류도
`{"error_code":"internal_error","phase":"runtime"}` 한 줄만 남기고 raw cause/traceback을 숨긴다.
잘못된 UUID/float/unknown option은 supplied argv와 usage를 출력하지 않고
`{"error_code":"invalid_arguments","phase":"startup"}` 한 줄과 exit code `2`로 끝난다. timeout은
NaN/±Inf/0/음수를 허용하지 않으며 advisory lock 전에 거부한다.
process cancellation과 `SystemExit`은 보존한다. 동일 run ID가 중단됐다면 같은 명령으로 재개한다.

## 4. 성공 조건

- PUT/DELETE command가 deterministic identity와 연속 source generation을 가진다.
- 각 command에 matching `cache_target.state_applied` event가 적용되고 claim item ACK가 완료된다.
- PUT과 DELETE 뒤 `feature_cache_generation`이 각각 증가한다.
- synthetic stable head가 exact DELETE generation/fingerprint와 remote deleted tuple을 유지한다.
- local desired head 전체 count/Merkle와 Map generic snapshot self-root/count/root가 exact 일치한다.
- consumer가 ready이고 remote stream control을 snapshot 전후로 읽은 두 결과가 동일하며 blocked/active
  reconciliation 상태가 아니다. local stream ETag와 restore epoch도 remote control/snapshot과 일치한다.
- 일반 snapshot 소비에서 high-watermark는 commit-safe replay lower-bound다. 다만 고립된 canary 성공에는
  미소비 event가 없어야 하므로 local applied cursor, local remote-ACK mirror, 실제 HTTP snapshot
  high-watermark cursor 세 값이 exact하게 같다.
- pending/leased/dead command가 모두 0이다.

성공 JSON은 `status=succeeded`, run/target/PUT·DELETE command/event ID, generation, relay order,
baseline/PUT/final cache generation을 포함한다. 또한 `pending_commands`, `leased_commands`,
`dead_letter_commands`가 각각 `0`이고,
`local_applied_cursor == local_remote_acked_cursor == remote_snapshot_high_watermark_cursor`,
`local_count == remote_count`, `local_merkle_root == remote_merkle_root`임을 서로 다른 필드로 증명한다.
이 값과 backlog 3종은 상수로 조립하지 않고 성공 transaction에서 각각 typed column에 관측·저장한 값을
그대로 출력한다. remote restore epoch/control version/ETag도 독립 필드로 남긴다. command source
fingerprint, event의 source command/generation/source·payload fingerprint, claim item ACK cursor/fingerprint/시각,
claim consumer/status/ACK cursor/완료 시각 결박도 성공 transaction과 동일-run 재검증에서 다시 확인한다.

bounded timeout, ACK 미완료, generic snapshot 일시 실패, final backlog/cursor/Merkle 미수렴은 nonzero로
fail-close하되 row를 `running`으로 보존한다. 원인을 해소한 뒤 반드시 같은 run ID로 재개한다. dead/halt,
foreign/mismatched durable material과 snapshot 자체 checksum 위반은 terminal `failed`이며 수동 개입 없이는
다른 run ID로 덮어쓰지 않는다.

## 5. forward boundary helper

causal canary 성공 뒤 docker-manager의 writer fence를 유지한 채 다음 두 명령을 서로 다른 단계에서 실행한다.

```bash
pinvi-cache-target-final-boundary preflight < <strict-request.json>
pinvi-cache-target-final-boundary finalize < <strict-request.json>
```

`preflight`는 migration 전 schema `20260801_0047`, `finalize`는 migration/canary 후 schema
`20260802_0048`만 허용한다. request는 JSON object 한 개와 마지막 LF만 허용하며 extra/missing field,
비정규 UUID, 40/64자리 lowercase hex 위반, operation/subcommand 불일치, preflight의 non-null final fence/
prior/canary/Map evidence, finalize의 null final fence/prior/canary/Map evidence와 같은 initial/final fence를
모두 mutation 전에 거부한다. argv parsing과 JSON 오류는 raw argv/path/input을
출력하지 않는 typed JSON 한 줄로 닫는다.

manager는 고정 5-writer registry, 세 DB의 in-flight 0, Map Dagster queued/running 0을 먼저 직접 증명한다.
helper request에는 manager가 관측한 count를 전달하지 않고 initial/final writer-fence receipt digest를 전달한다.
따라서 helper가 외부 process/Map Dagster 의미를 재구현하거나 manager 제공 숫자 0을 신뢰하지 않는다.
writer registry digest canonical bytes는 ASCII
`pinvi-cache-target-writer-registry-v1\0` 뒤에 정렬된
`kor-travel-map-api\0kor-travel-map-dagster\0kor-travel-map-dagster-daemon\0pinvi-api\0pinvi-dagster\0`를
연결한 값이며 SHA-256은 `526240609e2919357699b90244eb8cc8b9505f37db6c60552a98c7a37ed22d7c`다.

Pin app queue는 같은 DB snapshot에서 `email_queue.status='pending'`,
`telegram_system_notification_outbox.status='pending'`, `location_audit_outbox.processed_at IS NULL`을 각각
직접 세어 receipt와 final audit에 저장한다. 이 backlog는 backup/restore 대상이므로 0을 요구하지 않는다.
세 worker는 durable `processing`/lease 상태 없이 pending row를 `FOR UPDATE SKIP LOCKED` transaction에서
처리한다. 따라서 active worker가 없다는 증명은 상수 count가 아니라 manager의 exact writer stop/fence와
helper가 자기 session을 제외해 관측한 Pin DB in-flight transaction 0의 결합이다.

Manager 실행 순서는 `csv5 → Map H35 gc → final all-writer fence → Map verify → Pin finalize`다. Map H35 `gc`는
기존 advisory lock과 deterministic observation idempotency를 사용하고 final backlog 0을 증명해야 한다.
Map verify는 writer가 멈춘 Map DB에서 `ktm-cache-target-final-evidence/v1` object를 만들며 consumer/epoch/control/
ETag/high-watermark/count/Merkle와 reconciliation/outbox/claim/delivery backlog 0을 포함한다. Pin finalize는
HTTP를 호출하지 않고 이 object의 canonical SHA-256부터 검증한다.

helper는 `pg_control_system()`/`current_database()`에서 현재 Pin DB identity를 독립 재계산하고 자기 helper
session을 제외한 Pin DB in-flight transaction이 0인지 확인한다. preflight는 cache-target material 전체가
0이어야 하므로 migration `0048`의 generated UUID cast 전제가 된다. finalize는 initial reconciliation receipt
1개와 canary PUT/DELETE 2개만 허용하고 각각의 terminal ACK 및 canary durable row FK/hash를 재검증한 뒤,
Map typed evidence와 local cursor/count/Merkle/epoch/control evidence를 hash-bind한다.

finalize 성공 row는 outer transaction/cutover에 unique하고 append-only다. 동일 request와 동일 fresh evidence만
동일 receipt로 replay할 수 있다. UPDATE/DELETE/TRUNCATE 및 다른 material 재사용은 DB/서비스 양쪽에서
fail-close한다. concurrent finalize는 audit table을 처음부터 `SHARE ROW EXCLUSIVE`로 직렬화해 SHARE→INSERT
lock upgrade deadlock을 만들지 않는다. receipt의 `audit_id`, canonical 13-field `audit_request_sha256`,
`audit_row_count=1`은 반환 직후 fresh DB 조회로 재증명한다. `app.ktm_cache_target_boundary_audits`에서
`transaction_id=audit_id`가 정확히 한 행이고 request/evidence/Map evidence/initial·final fence/prior receipt
SHA-256이 receipt와 같아야 한다. helper는 stop/start, backup/restore, migration, fence 설정·해제, audit 삭제를
하지 않는다.
pre-forward rollback은 docker-manager가 보유한 schema `0047` Pin DB 전체 backup restore로 수행한다.
