export const DEFAULT_GRAFANA_URL = 'http://localhost:12205';
export const DEFAULT_GRAFANA_DASHBOARD_PATH = '/d/pinvi/overview?orgId=1&kiosk=tv';

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
