# Observability 운영 Runbook

Prometheus + cAdvisor + Grafana 기반 성능 측정/모니터링 절차. 포트는
`kor-travel-docker-manager`의 observability 대역을 따른다.

## 1. 포트

| 서비스            | Host 포트 | Container 포트 | URL                      |
| ----------------- | --------: | -------------: | ------------------------ |
| Prometheus        |   `12401` |         `9090` | `http://127.0.0.1:12401` |
| cAdvisor Exporter |   `12301` |         `8080` | `http://127.0.0.1:12301` |
| Grafana           |   `12205` |         `3000` | `http://127.0.0.1:12205` |

FastAPI는 `GET /metrics`로 Prometheus exposition format을 노출한다. 기본 metric:

- `pinvi_api_http_requests_total`
- `pinvi_api_http_request_duration_seconds`
- `pinvi_api_http_requests_in_progress`

`/health`, `/health/db`, `/metrics`는 요청 성능 metric에서 기본 제외한다.

Docker 이미지의 Uvicorn worker는 2개이므로 `apps/api/Dockerfile`은
`PROMETHEUS_MULTIPROC_DIR=/tmp/pinvi-prometheus`를 설정하고 container start 때 기존
multiprocess metric 파일을 비운다. 로컬 `uvicorn --reload` dev 실행은 단일 process
기준으로 동작한다.

## 2. 로컬 dev

API/Web은 기존 방식으로 띄운 뒤 observability profile만 추가로 올린다.

```bash
cd ~/pinvi-workspaces/pinvi-codex
scripts/dev-up.sh
docker compose -f infra/docker-compose.yml --profile observability up -d cadvisor prometheus grafana
```

dev compose의 Prometheus scrape target:

- `prometheus:9090`
- `cadvisor:8080`
- `host.docker.internal:12801/metrics` (WSL dev FastAPI)

## 3. App smoke compose

```bash
cd ~/pinvi-workspaces/pinvi-codex
scripts/docker-app.sh up
docker compose -p pinvi-app -f infra/docker-compose.app.yml --profile observability up -d cadvisor prometheus grafana
```

app compose의 Prometheus scrape target:

- `prometheus:9090`
- `cadvisor:8080`
- `app-api:8000/metrics`

## 4. Grafana

Grafana datasource와 기본 dashboard는 provisioning으로 자동 등록된다.

| 파일                                                    | 역할                                    |
| ------------------------------------------------------- | --------------------------------------- |
| `infra/grafana/provisioning/datasources/prometheus.yml` | Prometheus datasource                   |
| `infra/grafana/provisioning/dashboards/default.yml`     | dashboard file provider                 |
| `infra/grafana/dashboards/api-performance.json`         | API latency/request/container dashboard |

Admin 콘솔 `/admin/grafana` 기본 embed URL은
`http://localhost:12205/d/pinvi/overview?orgId=1&kiosk=tv`다. 운영에서는
`infra/.env.prod`의 `NEXT_PUBLIC_GRAFANA_URL=https://grafana.example.com` 및
`NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH` placeholder를 실제 값으로 바꾼 뒤 Web 이미지를
다시 빌드한다.

## 5. 검증

```bash
curl -fsS http://127.0.0.1:12801/metrics | grep pinvi_api_http_requests_total
curl -fsS http://127.0.0.1:12401/-/ready
curl -fsS http://127.0.0.1:12205/api/health
```

Prometheus UI의 **Status → Targets**에서 `pinvi-api-dev` 또는 `pinvi-api`가
`UP`인지 확인한다.

## 6. 운영 주의

- `/metrics`는 인증 없는 endpoint지만 PII를 노출하지 않는다. 운영에서는 reverse
  proxy/IP allowlist 또는 내부 네트워크에서만 접근시킨다.
- geofence strict 모드에서도 내부 Prometheus scrape가 막히지 않도록 `/metrics`는
  `PINVI_GEOFENCE_BYPASS_PATHS` 기본값에 포함한다.
- Grafana 기본 admin password는 운영 `.env`에서 반드시 교체한다.
