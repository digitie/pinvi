'use client';

import { useMemo, useState } from 'react';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { AdminPage, Section } from '@/components/admin/AdminPage';

const DEFAULT_GRAFANA_URL = 'http://localhost:3002';
const DEFAULT_DASHBOARD_PATH = '/d/tripmate/overview?orgId=1&kiosk=tv';

function buildGrafanaUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_GRAFANA_URL ?? DEFAULT_GRAFANA_URL;
  const dashboardPath =
    process.env.NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH ?? DEFAULT_DASHBOARD_PATH;
  return new URL(dashboardPath, baseUrl).toString();
}

export default function AdminGrafanaPage() {
  const grafanaUrl = useMemo(() => buildGrafanaUrl(), []);
  const grafanaOrigin = useMemo(() => new URL(grafanaUrl).origin, [grafanaUrl]);
  const [frameKey, setFrameKey] = useState(0);

  return (
    <AdminPage
      title="Grafana"
      description="운영 대시보드 iframe embed."
      actions={
        <>
          <button
            type="button"
            onClick={() => setFrameKey((value) => value + 1)}
            className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
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
      <section className="h-[calc(100vh-220px)] min-h-[560px] overflow-hidden rounded-sm border border-hairline bg-white">
        <iframe
          key={frameKey}
          src={grafanaUrl}
          title="TripMate Grafana"
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
            <dt className="text-xs font-semibold uppercase tracking-normal text-muted">dashboard</dt>
            <dd className="mt-1 break-all text-ink">{grafanaUrl}</dd>
          </div>
        </dl>
      </Section>
    </AdminPage>
  );
}
