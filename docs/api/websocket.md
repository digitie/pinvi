# WebSocket API (`WS /ws/*`)

실시간 동기화 — Trip 채널, presence, broadcast. SPEC V8 J장 + `docs/spec/v8/03-frontend.md` §9.

## 1. 채널

### 1.1 `WS /ws/trips/{trip_id}`

여행 단위 채널. JWT 인증 (cookie 또는 query `?token=`).

```
ws://localhost:12501/ws/trips/<trip_id>?token=<jwt>
wss://pinviapi.digitie.mywire.org/ws/trips/<trip_id>?token=<jwt>
```

권한 없으면 즉시 `close 4403` (`{ "code": 4403, "reason": "permission_denied" }`).

## 2. 이벤트 (서버 → 클라이언트)

모두 JSON. `type`은 디스크리미네이터.

```jsonc
{
  "type": "poi.updated",
  "trip_id": "uuid",
  "actor_user_id": "uuid",        // 변경 발생자 (자기 자신 이벤트는 클라이언트가 무시)
  "ts": "2026-05-25T14:30:00+09:00",
  "version": 42,                   // 단조 증가
  "payload": { /* 도메인별 */ }
}
```

### 2.1 POI 이벤트

| type | payload |
|------|---------|
| `poi.created` | `{ "poi": { /* 새 POI 전체 */ } }` |
| `poi.updated` | `{ "poi_id": "uuid", "changes": { /* 변경된 필드 */ }, "version": 5 }` |
| `poi.deleted` | `{ "poi_id": "uuid" }` |
| `poi.reordered` | `{ "moves": [{ "poi_id": "uuid", "new_sort_order": "..." }] }` |

### 2.2 Day 이벤트

| type | payload |
|------|---------|
| `day.created` | `{ "day_index": 4, "date": "...", "title": "..." }` |
| `day.updated` | `{ "day_index": 2, "changes": {...} }` |
| `day.deleted` | `{ "day_index": 2 }` |

### 2.3 Trip 이벤트

| type | payload |
|------|---------|
| `trip.updated` | `{ "changes": {...}, "version": 12 }` |
| `trip.member_changed` | `{ "action": "added" \| "removed" \| "role_changed", "companion": {...} }` |

### 2.4 Presence

| type | payload |
|------|---------|
| `presence.update` | `{ "user_id": "uuid", "viewing_day": 2, "is_online": true }` |
| `presence.cursor` | `{ "user_id": "uuid", "lon": 127.0, "lat": 37.5 }` (옵션, 비활성 기본) |

### 2.5 시스템

| type | payload |
|------|---------|
| `ping` | `{ "ts": "..." }` (서버가 30초 주기 발송) |
| `error` | `{ "code": "RATE_LIMITED", "message": "..." }` |

## 3. 이벤트 (클라이언트 → 서버)

| type | payload | 비고 |
|------|---------|------|
| `presence.heartbeat` | `{ "viewing_day": 2 }` | 5초 주기 |
| `presence.cursor` | `{ "lon": ..., "lat": ... }` | 옵션 (v2). 서버는 legacy `lng`/`lat` 입력도 받지만 canonical broadcast는 `longitude`/`latitude`다. |
| `pong` | `{}` | 서버 `ping`에 응답 |

30초 무응답 → 서버가 offline 처리 + 다른 클라이언트에 `presence.update is_online=false`.

## 4. 충돌 해결

`docs/spec/v8/03-frontend.md` §9.2 + ADR-019 (Sprint 5 작성 예정).

| 전략 | 적용 |
|------|------|
| LWW (Last-Write-Wins) 필드 단위 | POI memo / budget / marker_color 등 |
| Optimistic Lock (POI 단위) | `version` + `If-Match`. 409 → 클라이언트 다이얼로그 |
| Fractional Indexing | sort_order — D&D 충돌 안 남 (E-6 COLLATE C) |
| Presence | 5초 heartbeat / 30초 offline |

## 5. broker 구현

- v1.0 단일 프로세스 in-memory broker (FastAPI WebSocket + asyncio queue)
- 수평 확장 (v2): Redis Streams 또는 PostgreSQL LISTEN/NOTIFY
- broker는 trip별 connection set 관리 + 메시지 broadcast

자세히는 `docs/architecture/websocket-broker.md` (ADR-035).

## 6. 인증 / 권한

- 연결 시 JWT 검증 → `current_user_id` 추출
- `trip_id` 권한 검사 (owner / companion editor or viewer) → 미권한이면 close
- 권한 변경 (`trip.member_changed`) 시 해당 사용자 connection 강제 종료
- Admin은 별도 디버그 채널 (`WS /admin/debug/logs` — `docs/api/admin.md` §10.1)

## 7. Rate limit

- 클라이언트 → 서버 메시지: 초당 5개 / 분당 60개
- 초과 시 `error` 이벤트 + broker slot 즉시 반환 + 30초 grace 후 close `4429`
  (`rate_limited`)
- Reconnect: 클라이언트 측 exponential backoff (1s, 2s, 4s, ... max 30s)
- `presence.cursor`는 좌표 숫자/range를 검증하고 서버가 `user_id`를 채워 broadcast한다.
- process-local cap: trip당 10 connections, process 전체 200 connections. 초과 시
  `{ "code": 4408, "reason": "trip_connection_limit_exceeded" }` 또는
  `process_connection_limit_exceeded` 후 close `4408`.
- HTTP mutation broadcast는 background task로 예약한다. 응답 경로는 fan-out 완료를 기다리지
  않는다.
- broadcast send timeout 기본 2초. 느린 peer는 stale connection으로 제거해 같은 trip fan-out을
  막지 않게 한다.

운영 조절 환경변수:

| 환경변수 | 기본 |
|----------|------|
| `PINVI_WS_CLIENT_RATE_PER_SECOND` | `5` |
| `PINVI_WS_CLIENT_RATE_PER_MINUTE` | `60` |
| `PINVI_WS_RATE_LIMIT_CLOSE_GRACE_SECONDS` | `30` |
| `PINVI_WS_MAX_CONNECTIONS_PER_TRIP` | `10` |
| `PINVI_WS_MAX_CONNECTIONS_TOTAL` | `200` |
| `PINVI_WS_SEND_TIMEOUT_SECONDS` | `2` |

## 8. AI agent 구현 체크리스트

### 백엔드

- [x] `apps/api/app/api/v1/ws.py` (FastAPI WebSocket)
- [x] `apps/api/app/services/realtime_broker.py` (단일 프로세스 in-memory)
- [ ] `apps/api/app/services/optimistic_lock.py` (`If-Match` 검증)
- [x] POI / Trip CRUD route에서 broker.publish() 호출
- [x] 연결 시 권한 검사 + heartbeat timeout
- [x] 통합 테스트 (FastAPI TestClient WebSocket)

### 프론트 (`packages/api-client/src/websocket.ts`)

- [ ] WebSocket wrapper — exponential backoff + 자동 재연결
- [ ] 메시지 디스크리미네이터별 핸들러 등록
- [ ] TanStack Query invalidation 트리거 (poi/day/trip 이벤트별 query key)
- [ ] presence store (zustand) — 동반자 온라인 / viewing_day
- [ ] 401 close 시 토큰 refresh 후 재연결
- [ ] 충돌 다이얼로그 컴포넌트 (`apps/web/components/poi/ConflictDialog.tsx`)
