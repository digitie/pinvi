# WebSocket broker 아키텍처 (ADR-035)

Pinvi 실시간 협업은 Sprint 5/T-128에서 **단일 FastAPI process 안의 in-memory
broker**로 시작한다. 지도 feature read와 무관하게 여행 계획(`app.trips`)과 POI
첨부(`app.trip_day_pois`) 변경을 같은 trip 채널에 broadcast한다.

## 1. 범위

- 채널: `WS /ws/trips/{trip_id}`
- 인증: `pinvi_access` httpOnly cookie 또는 query `?token=`의 access JWT
- 권한: 연결 시 `app.trips.owner_user_id` 또는 `app.trip_companions.user_id`
- 서버 이벤트:
  - `presence.update`
  - `presence.cursor`
  - `trip.updated`
  - `poi.created`
  - `poi.updated`
  - `poi.deleted`
  - `poi.reordered`
- 클라이언트 이벤트:
  - `presence.heartbeat`
  - `presence.cursor`
  - `pong`

## 2. 구현 모델

`apps/api/app/services/realtime_broker.py`가 process-local registry를 가진다.

```
trip_id -> set(RealtimeConnection)
RealtimeConnection = websocket + user_id + viewing_day + last_seen_at
```

HTTP mutating route는 DB commit 이후 `realtime_broker.publish_event_nowait(...)`로
broadcast task를 예약하고 응답 경로에서는 fan-out 완료를 기다리지 않는다. broker는 현재
process에 연결된 같은 trip WebSocket에만 JSON message를 보낸다.

이 구조는 다음을 의도적으로 감수한다:

- Uvicorn worker가 2개 이상이면 worker 간 broadcast가 전달되지 않는다.
- process restart 시 presence는 모두 사라진다.
- durable event log가 아니므로 offline replay는 없다.

Sprint 5의 가족 베타/단일 노드 운영에서는 이 제약을 수용한다. 운영에서는 WebSocket
worker를 1개로 고정하거나 sticky session을 적용한다.

## 2.1 안전장치

단일 process broker는 작은 범위에서 시작하지만, 직접 연결이 가능한 실시간 채널이므로
다음 guard를 기본 적용한다.

| guard | 기본값 | 목적 |
|-------|--------|------|
| client message rate | 초당 5 / 분당 60 | heartbeat/cursor flood 차단 |
| trip connection cap | 10 | 한 trip fan-out 폭증 차단 |
| process connection cap | 200 | process 메모리/FD 예산 보호 |
| send timeout | 2초 | 느린 peer 하나가 `_broadcast` 전체를 막는 backpressure 차단 |

초과 처리는 `docs/api/websocket.md` §7의 close code를 따른다. `presence.cursor`는
서버가 좌표 범위를 검증하고 canonical `longitude`/`latitude` payload로 broadcast한다.
client message rate 초과 connection은 close grace 전에 broker에서 제거해 cap slot을 즉시
반환한다.

## 3. 메시지 envelope

모든 서버 이벤트는 같은 envelope를 쓴다.

```json
{
  "type": "poi.created",
  "trip_id": "uuid",
  "actor_user_id": "uuid",
  "ts": "2026-06-06T12:34:56+09:00",
  "version": 1,
  "payload": {}
}
```

`actor_user_id`는 변경을 만든 사용자다. 클라이언트는 자기 자신이 만든 이벤트를
낙관적 UI 중복 적용 방지를 위해 무시할 수 있다.

## 4. 인증 / close code

| 상황 | 처리 |
|------|------|
| token 없음/서명 실패/sub 오류 | accept 후 `{code: 4401, reason: ...}` 전송, close `4401` |
| trip 없음 또는 권한 없음 | accept 후 `{code: 4403, reason: "permission_denied"}` 전송, close `4403` |
| heartbeat timeout | close `4400` |
| connection cap 초과 | accept 후 `{code: 4408, reason: ...}` 전송, close `4408` |
| client message rate 초과 | `error RATE_LIMITED` 전송, grace 후 close `4429` |
| 알 수 없는 client event | 연결 유지 + `error` 이벤트 |

권한 판단은 JWT role claim이 아니라 access JWT `sub`로 DB를 조회한다.

## 5. 충돌 해결 경계

- `If-Match` 기반 optimistic lock은 기존 Trip/POI HTTP API의 `version`으로 처리한다.
- WebSocket은 충돌을 직접 해결하지 않고, 성공한 mutation 결과를 broadcast한다.
- `poi.reordered`는 현재 `sort_order` 변경 결과를 broadcast한다. Fractional indexing
  / COLLATE "C" unique 정책은 POI HTTP 서비스와 DB 제약이 담당한다.

## 6. v2 확장

다음 조건 중 하나가 생기면 broker를 Redis Streams 또는 PostgreSQL LISTEN/NOTIFY로
교체하는 ADR을 새로 쓴다.

- API worker 2개 이상에서 같은 trip broadcast가 필요
- offline replay 또는 durable event log가 필요
- presence 정확도를 process restart 이후에도 유지해야 함
- WebSocket fan-out 규모가 단일 process 메모리/CPU 예산을 넘음
