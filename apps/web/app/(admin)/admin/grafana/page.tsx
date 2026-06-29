'use client';

import { useEffect, useMemo, useState } from 'react';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import {
  DEFAULT_GRAFANA_DASHBOARD_PATH,
  GRAFANA_DASHBOARDS,
  buildGrafanaEmbedUrl,
  getGrafanaOrigin,
} from '@/lib/admin/grafana';

type GrafanaHealthStatus = 'checking' | 'ok' | 'degraded';

type GrafanaHealthPayload = {
  status: 'ok' | 'degraded';
  origin: string;
  status_code: number | null;
  message: string;
};

const healthTone: Record<GrafanaHealthStatus, string> = {
  checking: 'border-amber-200 bg-amber-50 text-amber-800',
  ok: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  degraded: 'border-rose-200 bg-rose-50 text-rose-800',
};

const healthLabel: Record<GrafanaHealthStatus, string> = {
  checking: '확인 중',
  ok: '정상',
  degraded: '강등',
};

export default function AdminGrafanaPage() {
  const [dashboardPath, setDashboardPath] = useState(
    process.env.NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH?.trim() || DEFAULT_GRAFANA_DASHBOARD_PATH,
  );
  const grafanaUrl = useMemo(
    () =>
      buildGrafanaEmbedUrl({
        baseUrl: process.env.NEXT_PUBLIC_GRAFANA_URL,
        dashboardPath,
      }),
    [dashboardPath],
  );
  const grafanaOrigin = useMemo(() => getGrafanaOrigin(grafanaUrl), [grafanaUrl]);
  const [frameKey, setFrameKey] = useState(0);
  const [health, setHealth] = useState<GrafanaHealthPayload | null>(null);
  const [healthStatus, setHealthStatus] = useState<GrafanaHealthStatus>('checking');

  useEffect(() => {
    let cancelled = false;
    setHealthStatus('checking');
    fetch('/admin/grafana/health', { cache: 'no-store' })
      .then(async (response) => {
        const payload = (await response.json()) as GrafanaHealthPayload;
        if (cancelled) return;
        setHealth(payload);
        setHealthStatus(payload.status);
      })
      .catch(() => {
        if (cancelled) return;
        setHealth({
          status: 'degraded',
          origin: grafanaOrigin,
          status_code: null,
          message: 'Grafana health 확인 필요',
        });
        setHealthStatus('degraded');
      });
    return () => {
      cancelled = true;
    };
  }, [frameKey, grafanaOrigin]);

  const refresh = () => setFrameKey((value) => value + 1);

  return (
    <AdminPage
      title="Grafana"
      description="운영 대시보드 iframe embed와 Grafana health probe."
      actions={
        <>
          <button
            type="button"
            onClick={refresh}
            className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
            data-testid="admin-grafana-refresh"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            새로고침
          </button>
          <a
            href={grafanaUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-10 items-center gap-2 rounded-sm bg-primary px-3 text-sm font-semibold text-white"
          >
            <ExternalLink className="h-4 w-4" aria-hidden="true" />새 창
          </a>
        </>
      }
    >
      <Section title="상태">
        <div className="grid gap-3 text-sm md:grid-cols-[180px_1fr]">
          <div
            className={`rounded-sm border px-3 py-2 font-semibold ${healthTone[healthStatus]}`}
            data-testid="admin-grafana-health-status"
          >
            {healthLabel[healthStatus]}
          </div>
          <div className="min-w-0 text-muted" data-testid="admin-grafana-health-message">
            {health?.message ?? 'Grafana health 확인 중'} · {health?.origin ?? grafanaOrigin}
          </div>
        </div>
      </Section>

      <Section title="Dashboard">
        <div className="flex flex-wrap gap-2" data-testid="admin-grafana-dashboard-list">
          {GRAFANA_DASHBOARDS.map((dashboard) => {
            const selected = dashboard.path === dashboardPath;
            return (
              <button
                key={dashboard.key}
                type="button"
                onClick={() => {
                  setDashboardPath(dashboard.path);
                  refresh();
                }}
                className={`h-9 rounded-sm border px-3 text-sm font-semibold ${
                  selected
                    ? 'border-primary bg-primary text-white'
                    : 'border-hairline bg-white text-ink hover:bg-surface-soft'
                }`}
                data-testid={`admin-grafana-dashboard-${dashboard.key}`}
              >
                {dashboard.label}
              </button>
            );
          })}
        </div>
      </Section>

      <section className="h-[calc(100vh-220px)] min-h-[560px] overflow-hidden rounded-sm border border-hairline bg-white">
        <iframe
          key={frameKey}
          src={grafanaUrl}
          title="Pinvi Grafana"
          className="h-full w-full border-0"
          sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
          referrerPolicy="no-referrer"
          data-testid="admin-grafana-frame"
        />
      </section>

      <Section title="Embed">
        <dl className="grid gap-3 text-sm md:grid-cols-2">
          <div>
            <dt className="text-xs font-semibold uppercase tracking-normal text-muted">origin</dt>
            <dd className="mt-1 break-all text-ink" data-testid="admin-grafana-origin">
              {grafanaOrigin}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-normal text-muted">
              dashboard
            </dt>
            <dd className="mt-1 break-all text-ink" data-testid="admin-grafana-dashboard-path">
              {grafanaUrl}
            </dd>
          </div>
        </dl>
      </Section>
    </AdminPage>
  );
}
