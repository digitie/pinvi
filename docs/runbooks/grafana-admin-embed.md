# Grafana Admin Embed 운영 (Sprint 5)

> `/admin/grafana`에서 Grafana 대시보드를 iframe으로 표시. anonymous viewer +
> frame-ancestors CSP.

## 1. Grafana 설정

`infra/grafana/grafana.ini`:

```ini
[security]
allow_embedding = true
cookie_samesite = none
cookie_secure = true

[auth.anonymous]
enabled = true
org_name = Pinvi
org_role = Viewer

[auth]
disable_login_form = false

[server]
domain = grafana.example.com
root_url = https://grafana.example.com/
```

`infra/grafana/provisioning/dashboards/default.yaml`:

```yaml
apiVersion: 1
providers:
  - name: pinvi
    folder: Pinvi
    type: file
    options:
      path: /etc/grafana/dashboards
```

Provisioning 대시보드:

- `infra/grafana/dashboards/api-performance.json` — Overview (`uid=pinvi`)
- `infra/grafana/dashboards/api-http.json` — API p95/error/in-flight (`uid=pinvi-api-http`)
- `infra/grafana/dashboards/db-pool.json` — SQLAlchemy DB pool (`uid=pinvi-db-pool`)
- `infra/grafana/dashboards/websocket.json` — Trip WebSocket metrics (`uid=pinvi-websocket`)
- `infra/grafana/dashboards/etl-backup.json` — Web/Dagster health + ETL/backup route
  (`uid=pinvi-etl-backup`)

Sprint 6에 추가:

- `mcp-server.json` — MCP 호출량 / 에러
- `geo-blocked.json` — 451 응답 (ADR-018)
- `backup-restore.json` — backup 성공 / 사이즈 / 핫스왑 이력

## 2. apps/web 라우터

`apps/web/app/(admin)/admin/grafana/page.tsx`:

현재 구현은 다음 env를 사용한다. `NEXT_PUBLIC_*` 값은 Web build time에 embed되므로
운영 도메인이나 기본 dashboard uid/slug를 바꾸면 Web 이미지를 다시 빌드한다.

```bash
NEXT_PUBLIC_GRAFANA_URL=http://localhost:12205
PINVI_GRAFANA_HEALTH_URL=http://localhost:12205
NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH=/d/pinvi/overview?orgId=1&kiosk=tv
```

운영에서는 gitignore된 `infra/.env.prod`에만 실제 origin을 둔다. 추적 파일에는
placeholder만 쓴다.

```bash
NEXT_PUBLIC_GRAFANA_URL=https://grafana.example.com
PINVI_GRAFANA_HEALTH_URL=http://grafana:3000
NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH=/d/pinvi/overview?orgId=1&kiosk=tv
```

`infra/docker-compose.app.yml`은 이 값을 Web build args와 Grafana
`GF_SERVER_ROOT_URL`에 함께 주입한다. 대시보드 slug/uid가 바뀌면
`NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH`만 바꾼다.

`/admin/grafana`는 위 기본 path를 iframe으로 띄우고, 화면의 dashboard selector로
API/DB pool/WebSocket/ETL·Backup 대시보드 path를 전환한다. `GET /admin/grafana/health`는
Next route handler가 서버 측에서 `PINVI_GRAFANA_HEALTH_URL`(없으면 `NEXT_PUBLIC_GRAFANA_URL`
origin)의 `/api/health`를 2.5초 timeout으로 probe한 뒤 `ok` 또는 `degraded`를 반환한다.
app compose 기본값은 컨테이너 내부 접근용 `http://grafana:3000`이다. 이 endpoint는
origin/status/message만 반환하고 credential, dashboard URL query secret을 노출하지 않는다.

## 3. CSP

`apps/web` 다음 헤더 박음:

```
Content-Security-Policy: frame-src 'self' <NEXT_PUBLIC_GRAFANA_URL origin>; frame-ancestors 'self';
```

Grafana 측:

```
X-Frame-Options: 제거 (allow_embedding=true가 처리)
Content-Security-Policy: frame-ancestors https://pinvi.example.com https://*.pinvi.example.com;
```

Compose는 `GF_SECURITY_ALLOW_EMBEDDING=true`, `GF_AUTH_ANONYMOUS_ENABLED=true`,
`GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer`, `GF_SERVER_ROOT_URL=${NEXT_PUBLIC_GRAFANA_URL}`를
환경변수로 주입한다.

## 4. RBAC

`/admin/grafana` 라우터는 layout의 `require_role("admin", "operator", "cpo")`로
보호 (기존 admin layout과 동일).

Grafana 자체는 anonymous viewer (read-only). 편집 / dashboard 추가는 Grafana
admin 로그인 (별 계정 — `/admin/grafana/login` 별 라우트, infra 운영자만).

## 5. 트러블슈팅

| 증상                                  | 원인                       | 해결                                                             |
| ------------------------------------- | -------------------------- | ---------------------------------------------------------------- |
| iframe 빈 화면                        | `frame-ancestors` CSP 누락 | grafana.ini + nginx 헤더 모두 점검                               |
| iframe 안에서 "embedding not allowed" | `allow_embedding=false`    | grafana.ini 갱신 + 재시작                                        |
| 401 / 로그인 폼                       | anonymous 비활성           | `[auth.anonymous] enabled=true`                                  |
| 데이터 없음                           | datasource 미연결          | Loki / Prometheus URL 확인                                       |
| Admin health 상태 `강등`              | Grafana `/api/health` 실패 | Grafana container, reverse proxy, `PINVI_GRAFANA_HEALTH_URL` 확인 |

## 6. 참조

- SPRINT-5.md
- ADR-022 (Backup 대시보드)
- ADR-019 (MCP 대시보드)
- `docs/integrations/loki.md` / `docs/integrations/sentry.md`
