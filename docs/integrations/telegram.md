# Telegram Bot (알림)

Pinvi는 여행별 최대 3개 Telegram 대상을 연결한다. 수동 전체·일자 일정 발송과
사용자가 동의한 KST 전날·당일 일간 브리프, 주간 여행 목록을 지원한다(#636/#638).

## 1. 정책

- bot token **원본 절대 DB 저장 X** — `telegram_bot_token_ref` (env 변수 이름 또는 vault ref)
- target = (`telegram_chat_id`, `telegram_chat_type`, `telegram_message_thread_id`, ...) tuple
- trip은 user-owned target을 **참조**만 — 복사 X
- 같은 시군구 데이터는 중복 메시지 안 보냄
- 일반 user 알림에는 stack trace / dataset key / API key / 토큰 / 로그 경로 **포함 X**
- Admin 알림에는 dataset key / Dagster job/run id / 재시도 횟수 / 실패 stage / stale serving 사용 flag / 로그 reference 포함
- Admin role은 DB tool (pgAdmin)로 부여 — UI에서 부여하지 않음
- 활성 Admin target 없으면 Admin 페이지 안내만 (이메일 발송 X)

## 2. DB 모델 (app schema)

### 2.1 `app.telegram_targets`

```sql
CREATE TABLE app.telegram_targets (
  id                                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                           uuid NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
  telegram_bot_token_ref            varchar(128) NOT NULL,        -- env var name or vault ref
  telegram_chat_id                  varchar(64) NOT NULL,
  telegram_chat_type                varchar(16) NOT NULL,         -- private|group|supergroup|channel
  telegram_message_thread_id        varchar(64),                 -- forum topic
  telegram_direct_messages_topic_id varchar(64),
  telegram_label                    varchar(80),                  -- 사용자 별칭
  is_default                        boolean NOT NULL DEFAULT false,
  is_enabled                        boolean NOT NULL DEFAULT true,
  last_verified_at                  timestamptz,
  last_send_status                  varchar(32),                 -- ok | failed | rate_limited
  created_at                        timestamptz NOT NULL DEFAULT now(),
  updated_at                        timestamptz NOT NULL DEFAULT now(),
  deleted_at                        timestamptz
);

CREATE INDEX telegram_targets_user_idx ON app.telegram_targets (user_id) WHERE deleted_at IS NULL;
```

### 2.2 `app.trip_telegram_targets`

```sql
CREATE TABLE app.trip_telegram_targets (
  trip_id              uuid NOT NULL REFERENCES app.trips(trip_id) ON DELETE CASCADE,
  telegram_target_id   uuid NOT NULL REFERENCES app.telegram_targets(id) ON DELETE CASCADE,
  created_at           timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (trip_id, telegram_target_id)
);
```

trip별 target 수 제한 (`<= 3`) — 응용 레이어 CHECK 또는 trigger.

### 2.3 `app.telegram_system_notification_outbox`

Admin / system 알림 (ETL retry 소진 등).

```sql
CREATE TABLE app.telegram_system_notification_outbox (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  category            varchar(64) NOT NULL,             -- 'etl_failure' | 'security_incident' | ...
  payload             jsonb NOT NULL,                    -- dataset_key, run_id, etc
  status              varchar(16) NOT NULL DEFAULT 'pending',
  attempts            int NOT NULL DEFAULT 0,
  last_error          text,
  scheduled_at        timestamptz NOT NULL DEFAULT now(),
  sent_at             timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now()
);
```

### 2.4 일정·예약 알림 (0104, #636/#638)

- telegram_notification_preferences: 사용자 기본 off 동의, KST 시각·요일·주간 대상과 동의 generation.
- telegram_notifications: 사용자별 고유 발생키, 최초 메시지 snapshot, 예약 기준 날짜·만료와 안전한 부모 오류.
- telegram_notification_deliveries: 대상·연결 generation, chunk 진행, 시도·재시도 시각과 정제 오류.
- 대상 검증·재연결은 generation으로 구분한다. 기존 system outbox와 분리해 기존 batch의 잠금을 중간에 풀지 않는다.
- 0106: planner 순환 cursor(`last_planned_at`), Telegram 호출 중 lease(`claim_token`), 본문 보존 기한 정리 시각(`body_purged_at`). 동작은 `docs/runbooks/telegram-notifications.md` §0106.

## 3. 환경변수

| 환경변수                           | 비고                           |
| ---------------------------------- | ------------------------------ |
| `PINVI_TELEGRAM_BOT_TOKEN_DEFAULT` | Pinvi 시스템 봇 (Admin 채널용) |
| `PINVI_TELEGRAM_ADMIN_CHAT_ID`     | 운영자 채널 ID                 |
| `PINVI_TELEGRAM_API_BASE`          | `https://api.telegram.org`     |
| `PINVI_TELEGRAM_TIMEOUT_SECONDS`   | `5`                            |
| `PINVI_TELEGRAM_PLANNER_BUDGET_SECONDS` | `60` — planner 한 tick의 사용자 처리 예산(Dagster 호출 timeout 120초보다 짧게) |
| `PINVI_TELEGRAM_NOTIFICATION_RETENTION_DAYS` | `30` — 발송이 끝난 알림 본문 보존 기간 |

사용자 봇 토큰은 vault 또는 사용자별 env 변수에 (`telegram_bot_token_ref`).

예약 planner는 API와 Dagster에 같은 PINVI_TELEGRAM_PLANNER_KEY를 별도 주입하고 PINVI_NOTIFICATION_PLANNER_API_URL로 API를 찾는다. 키는 32바이트 이상의 무작위 값을 사용한다. 미설정은 no-op이며 사용자 JWT로 내부 planner를 호출할 수 없다. PINVI_TELEGRAM_API_BASE는 운영에서 Telegram을 사용하고 WSL 검증에서는 소유 HTTP fixture로 지정한다.

## 4. Verification

target 등록 시 (`POST /users/me/telegram-targets`):

```python
# apps/api/app/services/telegram_client.py
async def verify_target(token: str, chat_id: str) -> dict:
    # 1) getChat — chat 존재/타입/봇 접근권 확인
    r = await httpx.get(
        f"https://api.telegram.org/bot{token}/getChat",
        params={"chat_id": chat_id},
        timeout=5,
    )
    if r.status_code != 200:
        raise TelegramVerifyError(_classify(r))
    chat = r.json()["result"]
    return {
        "telegram_chat_type": chat["type"],          # private|group|supergroup|channel
        "title_snapshot": chat.get("title") or chat.get("first_name"),
    }
```

또는 `sendMessage`로 권한 검증 + topic 유효성 (forum 채널).

## 5. 실패 분류

| 코드              | 의미                  | 응답                           |
| ----------------- | --------------------- | ------------------------------ |
| `missing_chat_id` | chat_id 빈값          | 422                            |
| `bot_forbidden`   | bot이 chat에서 차단됨 | 403, target `is_enabled=false` |
| `invalid_chat`    | chat_id 잘못됨        | 422                            |
| `invalid_topic`   | thread_id 잘못됨      | 422                            |
| `rate_limited`    | Telegram 429          | 429 + Retry-After              |
| `network_error`   | timeout / connection  | 503                            |
| `unknown_error`   | 그 외                 | 500                            |

## 6. API endpoint

### 6.1 `POST /users/me/telegram-targets`

```jsonc
{
  "telegram_bot_token": "...", // body로만, 즉시 vault에 저장
  "telegram_chat_id": "123456789",
  "telegram_label": "가족 단톡",
  "telegram_message_thread_id": null,
  "is_default": true,
}
```

응답 201: target 정보 (bot_token 응답에 X).

### 6.2 `GET /users/me/telegram-targets`

목록.

### 6.3 `POST /users/me/telegram-targets/{id}/verify`

verify 재실행.

### 6.4 `DELETE /users/me/telegram-targets/{id}`

soft delete. trip 연결도 함께 끊음.

### 6.5 `POST /trips/{trip_id}/telegram-targets`

```jsonc
{ "telegram_target_id": "uuid" }
```

이미 3개면 `422` + `details.reason: "max_targets_reached"`.

### 6.6 `DELETE /trips/{trip_id}/telegram-targets/{target_id}`

### 6.7 일정·예약과 발송 결과

- POST /trips/{trip_id}/telegram/send: 소유자만 사용한다. request_id(UUID), scope(trip/day), day 범위의 day_index를 받아202와 발송 식별자를 반환한다. 같은 요청 ID는 최초 snapshot을 유지하며 다른 의미로 재사용하면422다. 사용자당 대기 중인 수동 전송이 3건이면 새 요청은 429 `TELEGRAM_SEND_BACKLOG`다(같은 요청 ID 재시도는 상한과 무관).
- GET/PUT /users/me/telegram-notification-preferences: 기본 off 일간·주간 설정과 KST 시각·요일·본인 주간 대상을 조회·저장한다. 무효화된 대상이 수신 해제를 막지 않는다.
- GET /users/me/telegram-notifications: 최근 발송의 대상별 진행·실패/skip 원인·다음 시도를 조회한다. trip_id로 현재 소유 여행만 좁힐 수 있다.
- POST /internal/telegram/plan: 전용 X-Pinvi-Notification-Planner-Key만 받는다. Dagster의 pinvi_telegram_notification_planner_job이 매분 호출한다.

## 7. 메시지 생성

### 7.1 주간 여행 목록 (weekly_summary)

최신 #638에 따라 선택한 KST 요일·시각에 앞으로7일 안에 시작하는 본인 여행 목록을 선택한 검증 대상으로 보낸다. 과거 문서의 단일 여행7일 전 템플릿은 이 범위에서 사용하지 않는다.

### 7.2 전날·당일 일간 브리프 (daily_brief)

선택한 KST 시각에 오늘·내일 여행 일자의 장소·도착/출발·메모 요약을 여행에 연결한 검증 대상으로 보낸다. 날씨는 기존 투영을 사용하고, 일출은 해당 날짜의 성공·비stale 캐시만 포함한다. 미확인 정보는 미확인으로 표시한다.

같은 KST 회차를 중복 생성하지 않는다. 각 chunk 전에 현재 날짜·계정·소유권·동의·대상/연결을 확인한다. 날짜 변경·KST 자정 경과·설정 변경으로 무효가 된 기존 회차는 재생성하지 않는다. 수동 일정 요청은 최초 snapshot을 유지한다.

### 7.3 Admin 알림 예시

```
🚨 ETL retry 소진 — `python-visitkorea-api_festivals`

dataset_key: search_festival
run_id: dagster_run_abc123
attempts: 3/3
failure_stage: provider_call
last_error: TourApiAuthError (HTTP 401)
log: https://grafana.example/d/.../etl?from=now-1h

stale_serving_used: false
```

raw_log_excerpt 같은 민감 정보는 별도 endpoint (`/admin/debug/request/{id}`) 링크로만.

## 8. 발송 / Outbox 패턴

기존 telegram_system_notification_outbox는 기존 batch transaction을 유지한다. 새 일정·예약은 telegram_notifications와 대상별 deliveries를 사용하며 한 transaction에서 한 chunk만 보낸다. SKIP LOCKED claim 뒤 동의→Trip→User→Target 순서로 현재 상태를 확인한다. 정책 잠금을 기다린 시간까지 반영하여 HTTP 직전에 예약 만료를 다시 검사한다.

성공 ACK는 literal ok=true와 양의 message_id가 필요하다. HTTP 요청·response hook 전체에 timeout을 적용하고 오류를 받은 시각부터 양의 retry_after와 backoff를 존중한다. 확인한 chunk는 재발송하지 않지만 Telegram 수락 후 DB ACK가 유실되면 해당 chunk가 중복될 수 있다.

너무 긴 일정은 사용자별 실패로 기록하고 뒤 사용자를 계속 처리한다. 부모 오류도 UI·운영 SQL·Prometheus에 표시한다. 자세한 설정과 검증 범위는 [운영 안내](../runbooks/telegram-notifications.md)를 따른다.

## 9. 보안

- bot token 정규식 마스킹 (`\d+:[A-Za-z0-9_-]+`)
- 로그에 token / chat_id 일부만 (mask)
- HTTP 호출은 Telegram public API만 (다른 호스트로 redirect 차단)
- 사용자 메시지에 PII 포함 시 사용자 책임 (UI에 "다른 사람도 볼 수 있는 채널이면
  주의" 경고)

## 10. AI agent 구현 체크리스트

T-106 **Sprint 4 스코프(신규 trip / 동반자 초대 알림 채널)** 완료. PR #160~#168.

- [x] `app.telegram_targets`(0018) + `trip_telegram_targets`(0020) + `telegram_system_notification_outbox`(0019) Alembic — #161/#165/#166
- [x] Telegram client (verify, send) — `apps/api/app/clients/telegram.py`(§5 실패분류 + §9 token 마스킹), #160
- [x] 즉시 알림은 telegram_messages.py, 일정·예약은 telegram_itinerary.py/telegram_planner.py에서 생성한다(#636/#638).
- [x] `apps/api/app/api/v1/telegram_targets.py` + `trip_telegram_targets.py` 라우터(user CRUD + trip 링킹 §6.5/6.6) — #161/#166
- [x] pinvi_telegram_notification_planner_job의 KST 일간·주간 발생키와 전용 API 경계, 사용자 설정·진행/오류 UI를 구현했다(#636/#638).
- [x] **(Sprint 5 ETL)** `pinvi_telegram_system_outbox` 운영 요약 — `app.telegram_system_notification_outbox`의 due/backoff/stuck/retry exhausted/category 통계를 payload·user id·chat id·token 없이 Dagster metadata와 `/admin/etl/summary`로 노출
- [x] outbox worker (retry + exponential backoff) — `services/telegram_outbox.py`(SKIP LOCKED + lifespan drain), #165
- [x] PII/secret 마스킹 — client `mask_token`(§9, 에러/로그 token 비노출). 메시지 본문은 PII 미포함(이메일 등). #160/#163
- [x] UI: `/settings/telegram` target 관리(#164) + trip 상세 target 연결(#168)
- [x] `docs/compliance/pipa.md` Telegram 위탁자 명시 — §4.3에 위탁 내용/수령 정보/토큰 미저장 명시

**남은 후속 (별 스코프)**: per-user 봇 토큰 vault(현재 단일
시스템 봇만 — §1 준수), Sentry/Loki 로그 파이프라인 마스킹 정규식.

## 11. 여행 중 공식 기상특보 발표 (#637)

Weather201 병합 d8534ae의 GET /v1/weather/alert-events 공개 계약만 소비한다. 원천을 직접 파싱하거나 활성 특보 카드의 빈 목록에서 해제를 만들지 않는다. 여행 대표 BJD·현재 KST 여행 기간·검증된 연결 대상으로 한정한다. POI 좌표를 대표 BJD로 추정하지 않는다. 일부 구역만 확인되므로 전 지역 안전·활성 상태·경보 회차 연결을 보장하지 않는다.

weather_enabled는 기본 off이며 서버가 Pref 잠금 아래 전환할 때 weather_enabled_at을 기록한다. 과거 발표의 소급 전송을 피하고, 구형 PUT에서 필드를 생략하면 기존 동의를 보존한다. 특보는 일간/주간의 시각·요일과 독립적으로 매분 planner 대상에 포함된다. 모든 지역 HTTP는 DB 읽기 세션 종료 후 사용자당8초 예산으로 조회한다.

최근1시간 관측을 겹쳐 조회하고 공식 발표가 동의 이후·최근30분 안인 경우만 새 알림을 만든다. 생성15분·발표30분·여행 종료 KST 자정 중 가장 이른 시각에 만료된다. 여행 기간 안의 자정 경과 자체는 무효화 이유가 아니다. 메시지에는 발령/해제/변경/연장/정정/취소의 발표 의미와 KST 시각을 적고 현재 활성 상태를 단정하지 않는다.

0105의 telegram_weather_observations는 여행·공식 announcement별 취소와 모호성을 영속 보존한다. first_seen_at이나 hash로 수정 순서를 추정하지 않는다. 취소는 되돌리지 않으며 여러 비취소 관측은 미확정으로 보내지 않는다. 이 상태를 각 chunk 전에 확인하므로 새 취소/상충 확인은 이전 대기 알림을 무효화한다. 발생키는 여행·공식 발표·action으로 고정하고 최초 대상 snapshot을 늘리지 않는다.

전송 직전 현재 계정·동의 generation·Trip version/대표 지역/기간·소유권·대상/연결 generation을 확인한다. Trip version이 바뀐 대기 특보는 날짜·지역을 원복해도 생략하며 무관한 여행 편집도 보수적으로 이전 대기를 무효화할 수 있다.

최신성·전체 조회 완료·지역이 미확인인 경우 새 발송을 만들지 않는다. 오류는 고정 한국어 원인/코드의 별도 부모 이력으로 보이고, 원문 응답·URL·credential은 저장하지 않는다. 같은 여행/원인/시간대는 중복을 제한하며 이후 정상 발표 발생키를 막지 않는다. planning failures와 weather_alert 전송은 기존 Prometheus 표면의 고정 차원으로 수집한다.
