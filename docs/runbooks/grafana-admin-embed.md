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
org_name = TripMate
org_role = Viewer

[auth]
disable_login_form = false

[server]
domain = grafana.tripmate.kr
root_url = https://grafana.tripmate.kr/
```

`infra/grafana/provisioning/dashboards/default.yaml`:

```yaml
apiVersion: 1
providers:
  - name: tripmate
    folder: TripMate
    type: file
    options:
      path: /etc/grafana/dashboards
```

기본 대시보드 (Sprint 5 1차):
- `infra/grafana/dashboards/api-latency.json` — API p95 latency by route
- `infra/grafana/dashboards/db-pool.json` — Postgres connection pool
- `infra/grafana/dashboards/ws-presence.json` — WebSocket 연결 수 / 메시지율
- `infra/grafana/dashboards/etl-assets.json` — Dagster asset 최근 상태

Sprint 6에 추가:
- `mcp-server.json` — MCP 호출량 / 에러
- `geo-blocked.json` — 451 응답 (ADR-018)
- `backup-restore.json` — backup 성공 / 사이즈 / 핫스왑 이력

## 2. apps/web 라우터

`apps/web/app/(admin)/admin/grafana/page.tsx`:

```tsx
'use client';

export default function GrafanaPage() {
  const grafanaUrl = process.env.NEXT_PUBLIC_GRAFANA_URL ?? 'https://grafana.tripmate.kr';
  return (
    <div className="h-screen w-full">
      <iframe
        src={`${grafanaUrl}/d/tripmate/overview?orgId=1&kiosk=tv`}
        className="h-full w-full border-0"
        sandbox="allow-same-origin allow-scripts allow-popups"
      />
    </div>
  );
}
```

현재 구현은 다음 env를 사용한다.

```bash
NEXT_PUBLIC_GRAFANA_URL=http://localhost:3002
NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH=/d/tripmate/overview?orgId=1&kiosk=tv
```

운영에서는 `NEXT_PUBLIC_GRAFANA_URL`을 실제 Grafana origin으로 교체한다. 대시보드
slug/uid가 바뀌면 `NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH`만 바꾼다.

## 3. CSP

`apps/web` 다음 헤더 박음:

```
Content-Security-Policy: frame-src 'self' <NEXT_PUBLIC_GRAFANA_URL origin>; frame-ancestors 'self';
```

Grafana 측:

```
X-Frame-Options: 제거 (allow_embedding=true가 처리)
Content-Security-Policy: frame-ancestors https://app.tripmate.kr https://*.tripmate.kr;
```

## 4. RBAC

`/admin/grafana` 라우터는 layout의 `require_role("admin", "operator", "cpo")`로
보호 (기존 admin layout과 동일).

Grafana 자체는 anonymous viewer (read-only). 편집 / dashboard 추가는 Grafana
admin 로그인 (별 계정 — `/admin/grafana/login` 별 라우트, infra 운영자만).

## 5. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| iframe 빈 화면 | `frame-ancestors` CSP 누락 | grafana.ini + nginx 헤더 모두 점검 |
| iframe 안에서 "embedding not allowed" | `allow_embedding=false` | grafana.ini 갱신 + 재시작 |
| 401 / 로그인 폼 | anonymous 비활성 | `[auth.anonymous] enabled=true` |
| 데이터 없음 | datasource 미연결 | Loki / Prometheus URL 확인 |

## 6. 참조

- SPRINT-5.md
- ADR-022 (Backup 대시보드)
- ADR-019 (MCP 대시보드)
- `docs/integrations/loki.md` / `docs/integrations/sentry.md`
