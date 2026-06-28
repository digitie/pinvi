import { NextResponse } from 'next/server';
import {
  buildGrafanaEmbedUrlFromEnv,
  buildGrafanaHealthUrlFromEnv,
  getGrafanaOrigin,
} from '@/lib/admin/grafana';

export const dynamic = 'force-dynamic';

type GrafanaHealthStatus = 'ok' | 'degraded';

type GrafanaHealthPayload = {
  status: GrafanaHealthStatus;
  origin: string;
  status_code: number | null;
  message: string;
};

const GRAFANA_HEALTH_TIMEOUT_MS = 2500;

export async function GET() {
  const grafanaUrl = buildGrafanaEmbedUrlFromEnv();
  const origin = getGrafanaOrigin(grafanaUrl);
  const healthUrl = buildGrafanaHealthUrlFromEnv(grafanaUrl);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), GRAFANA_HEALTH_TIMEOUT_MS);

  try {
    const response = await fetch(healthUrl, {
      cache: 'no-store',
      signal: controller.signal,
    });
    return NextResponse.json(
      healthPayload({
        status: response.ok ? 'ok' : 'degraded',
        origin,
        statusCode: response.status,
      }),
      { status: response.ok ? 200 : 503 },
    );
  } catch {
    return NextResponse.json(
      healthPayload({
        status: 'degraded',
        origin,
        statusCode: null,
      }),
      { status: 503 },
    );
  } finally {
    clearTimeout(timeout);
  }
}

function healthPayload(input: {
  status: GrafanaHealthStatus;
  origin: string;
  statusCode: number | null;
}): GrafanaHealthPayload {
  return {
    status: input.status,
    origin: input.origin,
    status_code: input.statusCode,
    message: input.status === 'ok' ? 'Grafana health 확인' : 'Grafana health 확인 필요',
  };
}
