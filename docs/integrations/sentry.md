# Sentry — 에러 / 성능 / Replay

SPEC V8 #0 N-8 + `docs/spec/v8/00-infrastructure.md` §2.7. FastAPI + Next.js +
Dagster (apps/etl) 3 곳에 통합.

## 1. 티어

- **SaaS Free**: 월 5K events, 90일 보관, $0 — v1.0 시작 (SPEC V8 결정)
- **Team**: $26~$80, 월 50K~250K — DAU 100+ 시 검토
- **Self-hosted**: Sentry 자체가 RAM 8GB+ 필요 → Odroid 부적합. 클라우드 마이그레이션
  단계에 검토
- **GlitchTip**: Sentry 호환 API, 가볍고 ARM64 지원 — Odroid에 1GB 정도로 셀프호스팅 가능 (대안)

## 2. 환경변수

| 환경변수 | 비고 |
|----------|------|
| `PINVI_SENTRY_DSN` | 백엔드 / Dagster |
| `NEXT_PUBLIC_SENTRY_DSN` | 프론트 (빌드 타임 embed) |
| `PINVI_SENTRY_ENVIRONMENT` | `production` / `staging` / `development` |
| `PINVI_SENTRY_RELEASE` | git short sha (CI 주입) |
| `PINVI_SENTRY_TRACES_SAMPLE_RATE` | `0.1` (10%, Odroid 부하 고려) |
| `PINVI_SENTRY_PROFILES_SAMPLE_RATE` | `0.0` (ARM 프로파일링 제한) |
| `SENTRY_AUTH_TOKEN` | source map 업로드용 (CI) |

## 3. 백엔드 (FastAPI + SQLAlchemy + Dagster)

```python
# apps/api/app/core/sentry.py
import re
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.asyncpg import AsyncPGIntegration

from app.core.config import settings


def init_sentry():
    if not settings.pinvi_sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.pinvi_sentry_dsn,
        environment=settings.pinvi_sentry_environment,
        release=settings.pinvi_sentry_release,
        traces_sample_rate=settings.pinvi_sentry_traces_sample_rate,
        profiles_sample_rate=settings.pinvi_sentry_profiles_sample_rate,
        send_default_pii=False,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            AsyncPGIntegration(),
        ],
        before_send=_scrub_sensitive,
        before_send_transaction=_filter_noisy,
    )


_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_COORD_RE = re.compile(r"\b3[3-8]\.\d{2,}, ?12[4-9]\.\d{2,}\b")
_TOKEN_RE = re.compile(r"\b(re_|AIza|\d{8,}:[A-Za-z0-9_-]{20,})\S+")


def _scrub_sensitive(event, hint):
    if "request" in event and "data" in event["request"]:
        data = event["request"]["data"]
        for key in ["email", "password", "lat", "lng", "phone", "api_key",
                    "telegram_bot_token", "telegram_chat_id"]:
            if key in data:
                data[key] = "[FILTERED]"
    if "request" in event and "url" in event["request"]:
        event["request"]["url"] = (
            event["request"]["url"]
            .replace("lat=", "lat=[f]")
            .replace("lng=", "lng=[f]")
        )
    for exc in event.get("exception", {}).get("values", []):
        if "value" in exc:
            exc["value"] = _EMAIL_RE.sub("[email]", exc["value"])
            exc["value"] = _COORD_RE.sub("[coord]", exc["value"])
            exc["value"] = _TOKEN_RE.sub("[token]", exc["value"])
    return event


def _filter_noisy(event, hint):
    tx = event.get("transaction", "")
    if any(p in tx for p in ["/health", "/metrics", "/admin/debug"]):
        return None
    return event
```

`apps/api/app/main.py`에서 `init_sentry()` 호출 (FastAPI 생성 전).

### 3.1 Dagster 통합

```python
# apps/etl/pinvi/etl/sentry_hook.py
from dagster import RunFailureSensorContext, run_failure_sensor
import sentry_sdk

@run_failure_sensor
def report_dagster_failure(context: RunFailureSensorContext):
    sentry_sdk.capture_message(
        f"Dagster run failed: {context.failure_event.message}",
        level="error",
        contexts={
            "dagster": {
                "run_id": context.dagster_run.run_id,
                "job_name": context.dagster_run.job_name,
                "assets": [str(k) for k in (context.dagster_run.asset_selection or [])],
            }
        },
        tags={"component": "etl", "asset": context.dagster_run.job_name},
    )
```

## 4. 프론트 (Next.js)

```ts
// apps/web/sentry.client.config.ts
import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NEXT_PUBLIC_PINVI_ENV,
  release: process.env.NEXT_PUBLIC_PINVI_RELEASE,
  tracesSampleRate: 0.1,
  replaysSessionSampleRate: 0.0,
  replaysOnErrorSampleRate: 1.0,            // 에러 직전 30초 replay 캡처
  beforeSend(event) {
    if (event.request?.url) {
      event.request.url = event.request.url
        .replace(/lat=[\d.-]+/g, "lat=[filtered]")
        .replace(/lng=[\d.-]+/g, "lng=[filtered]");
    }
    return event;
  },
  ignoreErrors: [
    // (legacy) "kakao is not defined" — Kakao SDK 사용 시. ADR-015로 maplibre-vworld-js로 교체 후 불필요
    "ResizeObserver loop",
    /Network request failed/,
  ],
});
```

```ts
// apps/web/sentry.server.config.ts
import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NEXT_PUBLIC_PINVI_ENV,
  tracesSampleRate: 0.1,
});
```

```ts
// apps/web/instrumentation.ts
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
}
```

source map: `@sentry/nextjs` webpack 플러그인 자동 (`SENTRY_AUTH_TOKEN` 필요).

## 5. 알림 정책

| 트리거 | 알림 채널 | 즉시도 |
|--------|-----------|--------|
| New issue (새 종류) | Slack #alerts 또는 이메일 | 즉시 |
| Regression (해결된 issue 재발) | 즉시 | |
| Spike (평균 5배 이상) | 30분 후 | 잠깐 글리치 무시 |
| Critical 표시한 issue | 이메일 + Telegram bot | 즉시 + 반복 |
| 야간 (00:00 ~ 08:00 KST) | Critical만 즉시. 나머지는 morning digest | |

Telegram 봇 token은 `PINVI_TELEGRAM_BOT_TOKEN_DEFAULT` (위 [`telegram.md`](./telegram.md)).

## 6. Admin 페이지 연계 (`/admin/debug`)

- `/admin/debug/sentry` iframe 임베드 또는 API 호출로 issue 목록 표시
- `X-Request-Id` ↔ Sentry `trace_id` 자동 연결 → `/admin/debug/request/{id}`에서
  "Sentry에서 보기" 링크
- User feedback widget (`Sentry.captureUserFeedback`) — 사용자가 "문제 발생!"
  신고 시 event 와 자동 연결

## 7. AI agent 구현 체크리스트

- [ ] `apps/api/app/core/sentry.py` + `apps/api/app/main.py`에서 init 호출
- [ ] `apps/web/sentry.{client,server}.config.ts` + `instrumentation.ts`
- [ ] `apps/etl/pinvi/etl/sentry_hook.py` (Dagster `run_failure_sensor`)
- [ ] `before_send` PII 마스킹 정규식 (이메일/좌표/토큰)
- [ ] Sentry CI release tag (git short sha 주입)
- [ ] CI에 `SENTRY_AUTH_TOKEN` secret 설정 (source map 업로드)
- [ ] `/admin/debug/request/{id}` Sentry deep link
- [ ] DSN 관리: 단일 프로젝트 + environment 태그 (Free 5K 공유)
- [ ] `docs/compliance/pipa.md` Sentry 위탁자 명시
