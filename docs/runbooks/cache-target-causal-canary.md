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
- 같은 run ID는 crash 뒤 재개용이다. 새로운 liveness 증거에는 새 UUID를 쓴다.
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
credential이나 원격 응답 body를 포함하지 않는다. 동일 run ID가 중단됐다면 같은 명령으로 재개한다.

## 4. 성공 조건

- PUT/DELETE command가 deterministic identity와 연속 source generation을 가진다.
- 각 command에 matching `cache_target.state_applied` event가 적용되고 claim item ACK가 완료된다.
- PUT과 DELETE 뒤 `feature_cache_generation`이 각각 증가한다.
- local desired head 전체 count/Merkle와 Map generic snapshot count/root가 exact 일치한다.
- consumer의 local applied cursor와 remote ACK cursor가 같다.
- pending/leased/dead command가 모두 0이다.

성공 JSON은 `status=succeeded`, run/target/PUT·DELETE command/event ID, generation, relay order,
baseline/PUT/final cache generation을 포함한다. 또한 `pending_commands`, `leased_commands`,
`dead_letter_commands`가 각각 `0`이고, `local_applied_cursor == remote_acked_cursor`,
`local_count == remote_count`, `local_merkle_root == remote_merkle_root`임을 서로 다른 필드로 증명한다.

bounded timeout, ACK 미완료, generic snapshot 일시 실패, final backlog/cursor/Merkle 미수렴은 nonzero로
fail-close하되 row를 `running`으로 보존한다. 원인을 해소한 뒤 반드시 같은 run ID로 재개한다. dead/halt,
foreign/mismatched durable material과 snapshot 자체 checksum 위반은 terminal `failed`이며 수동 개입 없이는
다른 run ID로 덮어쓰지 않는다.
