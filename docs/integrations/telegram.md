# Telegram Bot (알림)

TripMate는 trip별 최대 3개 Telegram target을 연결해 1주일 전 / 1일 전 알림을
보낸다. v1 design + v2에서 Sprint 4~5 구현.

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

## 3. 환경변수

| 환경변수 | 비고 |
|----------|------|
| `TRIPMATE_TELEGRAM_BOT_TOKEN_DEFAULT` | TripMate 시스템 봇 (Admin 채널용) |
| `TRIPMATE_TELEGRAM_ADMIN_CHAT_ID` | 운영자 채널 ID |
| `TRIPMATE_TELEGRAM_API_BASE` | `https://api.telegram.org` |
| `TRIPMATE_TELEGRAM_TIMEOUT_SECONDS` | `5` |

사용자 봇 토큰은 vault 또는 사용자별 env 변수에 (`telegram_bot_token_ref`).

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

| 코드 | 의미 | 응답 |
|------|------|------|
| `missing_chat_id` | chat_id 빈값 | 422 |
| `bot_forbidden` | bot이 chat에서 차단됨 | 403, target `is_enabled=false` |
| `invalid_chat` | chat_id 잘못됨 | 422 |
| `invalid_topic` | thread_id 잘못됨 | 422 |
| `rate_limited` | Telegram 429 | 429 + Retry-After |
| `network_error` | timeout / connection | 503 |
| `unknown_error` | 그 외 | 500 |

## 6. API endpoint

### 6.1 `POST /users/me/telegram-targets`

```jsonc
{
  "telegram_bot_token": "...",       // body로만, 즉시 vault에 저장
  "telegram_chat_id": "123456789",
  "telegram_label": "가족 단톡",
  "telegram_message_thread_id": null,
  "is_default": true
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

## 7. 메시지 생성

### 7.1 일주일 전 (`weekly_summary`)

```
🏖 [부산 2박 3일] 7일 후 출발!

📅 6월 1일 (월) ~ 6월 3일 (수)

🌤 부산 날씨
  6/1 (월) ☀ 22~28°C
  6/2 (화) ☁ 21~26°C
  6/3 (수) 🌧 19~24°C

⛽ 휴게소 유가 (어제 기준)
  - 부산 → 마산 휴게소: 휘발유 1,624원
  - 부산 → 진주 휴게소: 휘발유 1,612원

🗺 일정
  Day 1: 광안리 해수욕장, 자갈치 시장, 부산타워 ...
  Day 2: ...
  Day 3: ...
```

### 7.2 1일 전 (`daily_brief`)

```
🌅 [부산 2박 3일] 내일 출발!

📅 6월 1일 (월)

🌤 광안리 시간별 (KMA)
  09시 ☀ 22°C
  12시 ☀ 26°C
  15시 ☀ 28°C
  18시 ☁ 25°C

🗺 Day 1
  - 광안리 해수욕장 (09:00 도착 예정)
  - 자갈치 시장 (점심)
  - 부산타워 (15:00)
  - 광안대교 야경 (19:00)

📦 챙겨갈 것
  - 자외선 차단제 (UV 8)
  - 우산 (오후 강수 30%)
```

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

```python
# apps/api/app/services/telegram_sender.py
async def send_to_target(target_id: UUID, message: str, parse_mode: str = "MarkdownV2"):
    target = await db.get(TelegramTarget, target_id)
    token = await secrets.get(target.telegram_bot_token_ref)
    try:
        r = await httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": target.telegram_chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "message_thread_id": target.telegram_message_thread_id,
            },
            timeout=5,
        )
        if r.status_code != 200:
            raise _classify(r)
        target.last_send_status = "ok"
    except TelegramError as e:
        target.last_send_status = f"failed:{e.code}"
        raise
```

trip 알림은 Dagster schedule이 weekly_summary / daily_brief job을 실행. 실패 시
재시도 outbox.

## 9. 보안

- bot token 정규식 마스킹 (`\d+:[A-Za-z0-9_-]+`)
- 로그에 token / chat_id 일부만 (mask)
- HTTP 호출은 Telegram public API만 (다른 호스트로 redirect 차단)
- 사용자 메시지에 PII 포함 시 사용자 책임 (UI에 "다른 사람도 볼 수 있는 채널이면
  주의" 경고)

## 10. AI agent 구현 체크리스트

- [ ] `app.telegram_targets` + `trip_telegram_targets` + `system_notification_outbox` Alembic
- [ ] `apps/api/app/services/telegram_client.py` (verify, send)
- [ ] `apps/api/app/services/telegram_messages.py` (weekly_summary, daily_brief 생성)
- [ ] `apps/api/app/api/v1/telegram_targets.py` 라우터
- [ ] Dagster schedule: `tripmate_telegram_weekly_summary` (일 1회), `tripmate_telegram_daily_brief` (시간 N)
- [ ] outbox worker (retry + exponential backoff)
- [ ] PII 마스킹 정규식 (Sentry / Loki)
- [ ] UI: 프로필에서 target 관리 + trip 화면에서 target 연결
- [ ] `docs/compliance/pipa.md` Telegram 위탁자 명시
