import { describe, expect, it } from 'vitest';
import {
  DEFAULT_GRAFANA_DASHBOARD_PATH,
  DEFAULT_GRAFANA_URL,
  GRAFANA_DASHBOARDS,
  buildGrafanaEmbedUrl,
  buildGrafanaHealthUrl,
  buildGrafanaHealthUrlFromEnv,
  getGrafanaOrigin,
} from '../lib/admin/grafana';

describe('Grafana admin embed config', () => {
  it('기본 로컬 Grafana URL을 만든다', () => {
    expect(buildGrafanaEmbedUrl()).toBe(
      new URL(DEFAULT_GRAFANA_DASHBOARD_PATH, DEFAULT_GRAFANA_URL).toString(),
    );
  });

  it('prod public origin과 dashboard path를 조합한다', () => {
    expect(
      buildGrafanaEmbedUrl({
        baseUrl: 'https://grafana.example.com',
        dashboardPath: '/d/pinvi/overview?orgId=1&kiosk=tv',
      }),
    ).toBe('https://grafana.example.com/d/pinvi/overview?orgId=1&kiosk=tv');
  });

  it('잘못된 env 값은 안전한 로컬 fallback으로 되돌린다', () => {
    expect(
      buildGrafanaEmbedUrl({
        baseUrl: 'not a url',
        dashboardPath: '/d/custom',
      }),
    ).toBe(new URL(DEFAULT_GRAFANA_DASHBOARD_PATH, DEFAULT_GRAFANA_URL).toString());
  });

  it('CSP에 사용할 origin만 추출한다', () => {
    expect(getGrafanaOrigin('https://grafana.example.com/d/pinvi/overview')).toBe(
      'https://grafana.example.com',
    );
  });

  it('운영 dashboard catalog 4종 이상을 고정 uid path로 제공한다', () => {
    expect(GRAFANA_DASHBOARDS.map((dashboard) => dashboard.key)).toEqual([
      'overview',
      'api',
      'db',
      'websocket',
      'etl-backup',
    ]);
    expect(GRAFANA_DASHBOARDS.map((dashboard) => dashboard.path).join('\n')).not.toMatch(
      /secret|token|password|api[_-]?key/i,
    );
  });

  it('Grafana health probe URL은 origin만 사용한다', () => {
    expect(
      buildGrafanaHealthUrl('https://grafana.example.com/d/pinvi/overview?orgId=1&kiosk=tv'),
    ).toBe('https://grafana.example.com/api/health');
  });

  it('server-side Grafana health probe는 내부 origin env를 우선한다', () => {
    const previous = process.env.PINVI_GRAFANA_HEALTH_URL;
    process.env.PINVI_GRAFANA_HEALTH_URL = 'http://grafana:3000';
    try {
      expect(buildGrafanaHealthUrlFromEnv('https://grafana.example.com/d/pinvi')).toBe(
        'http://grafana:3000/api/health',
      );
    } finally {
      if (previous === undefined) {
        delete process.env.PINVI_GRAFANA_HEALTH_URL;
      } else {
        process.env.PINVI_GRAFANA_HEALTH_URL = previous;
      }
    }
  });
});
