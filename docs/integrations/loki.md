# Loki + Promtail + Grafana — 로그 집계

Sentry는 에러/예외/성능, Loki는 일반 INFO 로그 / 요청 추적 / slow query. SPEC V8
#0 N-9 + `docs/spec/v8/00-infrastructure.md` §2.7.

## 1. 컨테이너 구성 (Sprint 5)

```yaml
# infra/docker-compose.yml — Loki 스택 추가
services:
  loki:
    image: grafana/loki:3.x
    deploy:
      resources:
        limits: { memory: 512M }
    volumes:
      - /mnt/nvme/loki:/loki
    command: -config.file=/etc/loki/local-config.yaml

  promtail:
    image: grafana/promtail:3.x
    deploy:
      resources:
        limits: { memory: 256M }
    volumes:
      - /var/log:/var/log:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /etc/promtail:/etc/promtail
    command: -config.file=/etc/promtail/config.yml

  grafana:
    image: grafana/grafana:11.x
    deploy:
      resources:
        limits: { memory: 384M }
    ports:
      - '12205:3000' # observability 대역(Grafana)
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PW}
    volumes:
      - /mnt/nvme/grafana:/var/lib/grafana
```

스택 합계 ~1.1GB — N150 16GB 운영 자원 예산 안에서 관리한다. vworld 임포트 같은 무거운
작업 시 일시적으로 promtail 비활성 옵션을 사용할 수 있다.

## 2. Promtail config (`/etc/promtail/config.yml`)

```yaml
server:
  http_listen_port: 9080

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  # 1) Docker 컨테이너 stdout/stderr 자동 수집
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 30s
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        target_label: 'container'

  # 2) FastAPI structlog JSON
  - job_name: fastapi
    static_configs:
      - targets: [localhost]
        labels:
          service: fastapi
          __path__: /var/log/fastapi/*.log
    pipeline_stages:
      - json:
          expressions:
            level: level
            request_id: request_id
            user_id: user_id
      - labels:
          level:
          request_id:
          user_id:

  # 3) PostgreSQL slow query
  - job_name: postgres-slow
    static_configs:
      - targets: [localhost]
        labels:
          service: postgres
          __path__: /var/log/postgres/postgresql.log
```

## 3. structlog 설정 (FastAPI)

```python
# apps/api/app/core/logging.py
import logging
import structlog
from uuid import uuid4

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=False),  # KST aware
        # 프레임 지역 변수는 찍지 않는다(§3.1)
        structlog.processors.ExceptionRenderer(ExceptionDictTransformer(show_locals=False)),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)


# 미들웨어
@app.middleware("http")
async def add_request_id(request, call_next):
    request_id = request.headers.get("X-Request-Id") or str(uuid4())
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        user_id=getattr(request.state, "user_id", None),
        path=request.url.path,
        method=request.method,
    )
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


# 사용
log = structlog.get_logger()
log.info("trip.poi.added", trip_id=trip_id, poi_count=10)
log.warning("external_api.slow", api="vworld", duration_ms=1200)
```

JSON 출력 예시:

```json
{
  "timestamp": "2026-05-25T14:30:00+09:00",
  "level": "info",
  "event": "trip.poi.added",
  "request_id": "abc-123",
  "user_id": "uuid",
  "path": "/trips/.../pois",
  "method": "POST",
  "trip_id": "uuid",
  "poi_count": 10
}
```

### 3.1 비밀값 가리기 (2026-11-02)

prod 점검에서 httpx의 INFO 줄(`HTTP Request: POST http://…/v2/geocode?key=…`)이 kor-travel-geo 공개 API key를 컨테이너 stdout에 그대로 찍은 것을 확인했다. `api_call_log` 테이블은 이미 가리고 있었지만 stdout 로그는 가리지 않았다. 지금은 두 겹으로 막는다.

- `configure_logging()`이 `httpx`·`httpcore` 로거를 WARNING부터만 내게 둔다. 요청마다 전체 URL을 찍는 줄이 나오지 않는다.
- `app.core.redaction.SecretRedactingFilter`를 root·uvicorn handler와 `httpx`·`uvicorn.access` 로거에 단다. 가리는 대상:
  - query 비밀값: `key`, `serviceKey`, `apiKey`, `token`, `access_token`, `X-Amz-Signature` 등. 키 집합은 `SENSITIVE_QUERY_KEYS`가 정한다.
    - 이름이 정확히 일치할 때만 가린다. `sido_code`는 가리지 않는다.
    - 비밀 이름만 찾는다. 비밀이 아닌 쌍의 값이 뒤에 오는 비밀 쌍을 삼키지 않게 하려는 것이다(예: `redirect_uri=…?token=…`).
    - 이름 앞에 올 수 없는 것: 이름 문자, 점, 하이픈. 그래서 `obj.key=`, `Idempotency-Key=`는 가리지 않는다.
    - 이름 앞에 와도 되는 것: JSON escape(`\n`·`\t`·`\uXXXX`), percent-encoding(`%3F`·`%26`). 완전히 인코딩된 중첩 URL도 그래서 잡힌다.
    - 따옴표로 연 값(`api_key='…'`, `token=\"…\"`)은 닫는 따옴표까지 가린다. 쉼표·공백·괄호가 있어도 꼬리가 새지 않는다.
    - 따옴표 없는 값은 query 구분자·공백·따옴표·JSON escape까지 가린다. 닫는 괄호·쉼표도 비밀값의 일부일 수 있어 같이 가린다.
    - 값 안의 `\uXXXX`는 값의 일부로 본다. `%3D`로 인코딩된 `=`도 잡는다.
  - Telegram token: `/bot<id>:<token>/`, 그리고 접두가 없는 `<id>:<35자>` 꼴(대문자를 포함한 것만, uuid 제외).
  - path 자격 증명: `/trips/{id}/shared/{token}`, `/storage/{uploads,downloads}/{token}`.
  - OAuth callback의 `code`·`state`. callback path에서만 가린다.
  - URL userinfo의 password: `scheme://user:***@host`, 빈 사용자 `redis://:***@`.
  - `Authorization: Bearer|Basic|Token …`.
  - 가린 뒤에도 JSON 줄은 JSON이다. 값은 escape를 먹지 않는다.
- structlog event-dict의 비밀 이름 키(`log.info("x", api_key=…)`)는 렌더 전에 가린다(`redact_event_dict`). JSON에서는 `"api_key": "…"` 꼴이라 문자열 필터가 못 보기 때문이다.
- 남는 한계:
  - `=`가 바로 붙지 않은 꼴은 가리지 못한다. 예: dict repr `{'password': …}`, SQLAlchemy 오류의 parameters, `x-api-key: …`, `key = …`.
  - 접미사가 붙은 이름도 가리지 못한다. 예: `db_password=`, `bot_token=`.
  - password에 인코딩 안 된 `/`·`'`·`@`가 든 userinfo도 가리지 못한다.
  - 비밀값을 그런 꼴로 로그에 남기지 않는다.
- uvicorn access 줄은 args 튜플 모양을 유지한 채 원소만 바꾼다. `AccessFormatter`가 그 튜플을 풀어 쓰기 때문이다.
- 필터는 예외를 밖으로 내지 않는다. logging은 filter 예외를 잡아 주지 않으므로, 가리기에 실패하면 메시지를 고정 문구로 바꾼다.
- structlog 예외 렌더러는 프레임 지역 변수를 찍지 않는다(`show_locals=False`). 지역 변수 repr에는 URL 모양이 아닌 비밀값이 들어갈 수 있고, 필터가 그것을 가리지 못한다. 예: `api_key`, DB 접속 인자의 password.
- `api_call_log.endpoint`(`sanitize_api_call_endpoint`)와 MCP 호출 기록도 같은 모듈의 `sanitize_url`을 쓴다. 규칙은 한 곳에서만 정한다.

새 외부 client가 다른 이름의 query 비밀값을 쓰면 `SENSITIVE_QUERY_KEYS`에 추가한다. 비밀값은 가능하면 header로 보낸다.

## 4. Sentry vs Loki

| 용도             | Sentry         | Loki                    |
| ---------------- | -------------- | ----------------------- |
| 에러/예외        | ✓              | ✗                       |
| 성능 추적        | ✓ Transactions | ✗                       |
| INFO 로그        | ✗ (event 한도) | ✓                       |
| DB query 로그    | ✗              | ✓ slow query            |
| 외부 API 호출    | △ 실패만       | ✓ 전체                  |
| 사용자 행동 추적 | △ Breadcrumbs  | ✓ 시계열                |
| ETL 진행         | ✗              | ✓ Dagster stream        |
| 알림             | ✓ 즉시         | ✗ (Grafana alerting v2) |

## 5. Grafana 대시보드 (핵심 패널)

- API request rate / p50 / p95 / error rate (시계열)
- 외부 API 호출 모니터 (provider별 응답 시간 + 실패율)
- ETL 자산 진행 (Dagster materialization 로그)
- DB slow query top 10 (1초+)
- Loki 검색바: `{trip_id="abc-123"}` → 해당 trip 관련 모든 로그
- 위치 access log count (CPO 권한)

## 6. Admin 페이지 연계 (`/admin/debug/logs`)

2026-06-28 T-245 기준 v0.2.0은 N150 운영 부담을 줄이기 위해 Loki/Promtail LogQL WebSocket을
필수 구성으로 올리지 않는다. Admin debug live mode는
`GET /admin/debug/logs/stream/status`의 `mode="polling"` 계약과 기존 sanitized system/API log
endpoint 재조회로 닫는다. 아래 LogQL stream은 Loki retention/용량 정책이 확정된 뒤의 후속 운영
선택이다.

`docs/api/admin.md` §14. WebSocket으로 Loki LogQL stream:

```
LogQL 예시:
  {service="fastapi", level="error"} |= "trip_id=abc"
  {service="postgres"} |~ "duration: [1-9]\\d{3,}ms"
```

서버는 백엔드에서 LogQL 호출 → WebSocket으로 push.

## 7. Retention

- Loki 7일 (N150 NVMe 보존 예산 기준)
- PostgreSQL slow query 로그는 별도 30일 (vacuum)
- Grafana 대시보드 export는 git에 (`infra/grafana/dashboards/*.json`)

## 8. AI agent 구현 체크리스트

- [ ] `infra/docker-compose.yml`에 loki / promtail / grafana 추가 (후속 운영 선택)
- [ ] `infra/loki/local-config.yaml`, `infra/promtail/config.yml`, `infra/grafana/`
- [ ] `apps/api/app/core/logging.py` structlog 설정
- [ ] `apps/api/app/middleware/request_id.py` (request_id 미들웨어)
- [ ] `apps/api/app/middleware/api_call_logging.py` (httpx 외부 호출 로그)
- [x] `/admin/debug/logs` sanitized polling fallback (T-245)
- [ ] `/admin/debug/logs` WebSocket LogQL stream (후속 운영 선택)
- [ ] PostgreSQL slow query log 활성화 (`postgresql.conf`)
- [ ] Grafana 대시보드 5종 import
- [ ] 위치 access log는 별도 (CPO 권한)
