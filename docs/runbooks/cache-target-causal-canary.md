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

timeout, dead/halt, ACK 미완료, foreign/mismatched durable row, Merkle/cursor 불일치는 nonzero로
fail-close한다. 실패 ID는 terminal audit row로 남으므로 원인을 수정한 뒤 새 UUID를 사용한다. process
crash처럼 terminal failure를 기록하지 못한 중단만 같은 ID로 재개한다.
