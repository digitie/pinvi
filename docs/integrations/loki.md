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
      - "3002:3000"     # Next.js는 9022 고정 → grafana는 3002 권장
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PW}
    volumes:
      - /mnt/nvme/grafana:/var/lib/grafana
```

스택 합계 ~1.1GB — Odroid 8GB RAM에 들어감. vworld 임포트 같은 무거운 작업 시
일시적으로 promtail 비활성 옵션.

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
        structlog.processors.dict_tracebacks,
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

## 4. Sentry vs Loki

| 용도 | Sentry | Loki |
|------|--------|------|
| 에러/예외 | ✓ | ✗ |
| 성능 추적 | ✓ Transactions | ✗ |
| INFO 로그 | ✗ (event 한도) | ✓ |
| DB query 로그 | ✗ | ✓ slow query |
| 외부 API 호출 | △ 실패만 | ✓ 전체 |
| 사용자 행동 추적 | △ Breadcrumbs | ✓ 시계열 |
| ETL 진행 | ✗ | ✓ Dagster stream |
| 알림 | ✓ 즉시 | ✗ (Grafana alerting v2) |

## 5. Grafana 대시보드 (핵심 패널)

- API request rate / p50 / p95 / error rate (시계열)
- 외부 API 호출 모니터 (provider별 응답 시간 + 실패율)
- ETL 자산 진행 (Dagster materialization 로그)
- DB slow query top 10 (1초+)
- Loki 검색바: `{trip_id="abc-123"}` → 해당 trip 관련 모든 로그
- 위치 access log count (CPO 권한)

## 6. Admin 페이지 연계 (`/admin/debug/logs`)

`docs/api/admin.md` §10. WebSocket으로 Loki LogQL stream:

```
LogQL 예시:
  {service="fastapi", level="error"} |= "trip_id=abc"
  {service="postgres"} |~ "duration: [1-9]\\d{3,}ms"
```

서버는 백엔드에서 LogQL 호출 → WebSocket으로 push.

## 7. Retention

- Loki 7일 (Odroid 디스크 용량 고려)
- PostgreSQL slow query 로그는 별도 30일 (vacuum)
- Grafana 대시보드 export는 git에 (`infra/grafana/dashboards/*.json`)

## 8. AI agent 구현 체크리스트

- [ ] `infra/docker-compose.yml`에 loki / promtail / grafana 추가 (Sprint 5)
- [ ] `infra/loki/local-config.yaml`, `infra/promtail/config.yml`, `infra/grafana/`
- [ ] `apps/api/app/core/logging.py` structlog 설정
- [ ] `apps/api/app/middleware/request_id.py` (request_id 미들웨어)
- [ ] `apps/api/app/middleware/api_call_logging.py` (httpx 외부 호출 로그)
- [ ] `/admin/debug/logs` WebSocket LogQL stream
- [ ] PostgreSQL slow query log 활성화 (`postgresql.conf`)
- [ ] Grafana 대시보드 5종 import
- [ ] 위치 access log는 별도 (CPO 권한)
