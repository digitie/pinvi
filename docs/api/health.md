# Health API (`/health*`)

라이브니스 + DB 연결 + 외부 의존 헬스 체크. 공통 규약 [`common.md`](./common.md).

## 1. Endpoint

### 1.1 `GET /health`

```http
GET /health
```

응답 200:

```jsonc
{ "status": "ok", "service": "pinvi-api", "version": "v1.0.0", "git_sha": "abc123" }
```

- 인증 없음, rate limit 없음
- Loki / Promtail / Sentry transaction 노이즈 제외 대상 (이름이 `/health*`로 시작하면 필터)
- Docker `healthcheck:` 의 진입점

### 1.2 `GET /health/db`

```http
GET /health/db
```

응답 200:

```jsonc
{ "status": "ok", "database": "ok", "latency_ms": 4 }
```

- `SELECT 1` 1회 + 시간 측정
- 실패 → `503 SERVICE_UNAVAILABLE` + `{"error": {"code": "DB_UNAVAILABLE", "details": {"reason": "..."}}}`

### 1.3 `GET /health/external`

```http
GET /health/external
```

응답 200:

```jsonc
{
  "data": {
    "kor_travel_map": { "status": "ok", "latency_ms": 12 },
    "rustfs": { "status": "ok", "latency_ms": 8 },
    "resend": { "status": "ok", "rate_limit_remaining": 95 },
    "kakao_map": { "status": "ok" }
  }
}
```

- `kor_travel_map`: kor-travel-map API `/debug/health` 또는 OpenAPI health 경로 호출
- `rustfs`: HeadBucket 호출
- `resend`: `/domains` GET (선택, rate limit 보호 위해 5분 캐시)
- `kakao_map`: SDK 로드 가능 여부는 클라이언트 측 (서버는 X)
- 각 의존이 down이어도 본 endpoint 자체는 `200`. 개별 status에 `error` 명시

## 2. Uptime 모니터링

UptimeRobot 또는 Better Stack이 `/health`를 5분 주기로 외부에서 ping. 운영 환경
에서만 활성. SPEC V8 N-4 / `docs/spec/v8/00-infrastructure.md` §2.7.

## 3. Prometheus metrics

`GET /metrics`는 Prometheus scrape용 성능 metric endpoint다. 인증은 없지만 PII를
내보내지 않으며, 운영에서는 reverse proxy/IP allowlist 또는 내부 네트워크에서만
노출한다.

- `pinvi_api_http_requests_total`
- `pinvi_api_http_request_duration_seconds`
- `pinvi_api_http_requests_in_progress`

자세한 실행 절차는 [`observability.md`](../runbooks/observability.md).

## 4. AI agent 구현 체크리스트

- [ ] `apps/api/app/api/v1/healthz.py` (네이밍은 `health` 모듈)
- [ ] FastAPI Depends 없이 inline 함수 (DB 의존성 없는 `/health`)
- [ ] `apps/api/app/services/health.py` (외부 의존 헬스)
- [ ] Docker compose `healthcheck:` 설정 (`CMD curl -f http://localhost:8000/health`)
- [ ] Sentry / Loki에서 `/health*` transaction 필터
- [ ] (선택) `/health/external` 결과를 Admin 대시보드에 표시
