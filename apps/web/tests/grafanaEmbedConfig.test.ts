import { describe, expect, it } from 'vitest';
import {
  DEFAULT_GRAFANA_DASHBOARD_PATH,
  DEFAULT_GRAFANA_URL,
  buildGrafanaEmbedUrl,
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
});
