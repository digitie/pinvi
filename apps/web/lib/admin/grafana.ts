export const DEFAULT_GRAFANA_URL = 'http://localhost:12205';
export const DEFAULT_GRAFANA_DASHBOARD_PATH = '/d/pinvi/overview?orgId=1&kiosk=tv';
export const DEFAULT_GRAFANA_HEALTH_PATH = '/api/health';
export const GRAFANA_DASHBOARDS = [
  {
    key: 'overview',
    label: 'Overview',
    path: DEFAULT_GRAFANA_DASHBOARD_PATH,
  },
  {
    key: 'api',
    label: 'API',
    path: '/d/pinvi-api-http/api-http?orgId=1&kiosk=tv',
  },
  {
    key: 'db',
    label: 'DB pool',
    path: '/d/pinvi-db-pool/db-pool?orgId=1&kiosk=tv',
  },
  {
    key: 'websocket',
    label: 'WebSocket',
    path: '/d/pinvi-websocket/websocket?orgId=1&kiosk=tv',
  },
  {
    key: 'etl-backup',
    label: 'ETL/Backup',
    path: '/d/pinvi-etl-backup/etl-backup?orgId=1&kiosk=tv',
  },
] as const;

type GrafanaEmbedInput = {
  baseUrl?: string | null;
  dashboardPath?: string | null;
};

function valueOrDefault(value: string | null | undefined, fallback: string): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : fallback;
}

export function buildGrafanaEmbedUrl(input: GrafanaEmbedInput = {}): string {
  const baseUrl = valueOrDefault(input.baseUrl, DEFAULT_GRAFANA_URL);
  const dashboardPath = valueOrDefault(input.dashboardPath, DEFAULT_GRAFANA_DASHBOARD_PATH);

  try {
    return new URL(dashboardPath, baseUrl).toString();
  } catch {
    return new URL(DEFAULT_GRAFANA_DASHBOARD_PATH, DEFAULT_GRAFANA_URL).toString();
  }
}

export function buildGrafanaEmbedUrlFromEnv(): string {
  return buildGrafanaEmbedUrl({
    baseUrl: process.env.NEXT_PUBLIC_GRAFANA_URL,
    dashboardPath: process.env.NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH,
  });
}

export function getGrafanaOrigin(url: string): string {
  try {
    return new URL(url).origin;
  } catch {
    return DEFAULT_GRAFANA_URL;
  }
}

export function buildGrafanaHealthUrl(url: string): string {
  try {
    return new URL(DEFAULT_GRAFANA_HEALTH_PATH, getGrafanaOrigin(url)).toString();
  } catch {
    return new URL(DEFAULT_GRAFANA_HEALTH_PATH, DEFAULT_GRAFANA_URL).toString();
  }
}

export function buildGrafanaHealthUrlFromEnv(publicGrafanaUrl: string): string {
  const healthOrigin = process.env.PINVI_GRAFANA_HEALTH_URL?.trim();
  if (!healthOrigin) {
    return buildGrafanaHealthUrl(publicGrafanaUrl);
  }
  try {
    return new URL(DEFAULT_GRAFANA_HEALTH_PATH, healthOrigin).toString();
  } catch {
    return buildGrafanaHealthUrl(publicGrafanaUrl);
  }
}
