/** mocked suite 전용. 실제 API·Grafana 주소와 공개 지도 키를 상속하지 않는다. */
export const MOCK_API_ORIGIN = 'http://pinvi-api.e2e.invalid:12801';
export const MOCK_GRAFANA_ORIGIN = 'http://pinvi-grafana.e2e.invalid:12205';

export const MOCK_VWORLD_API_KEY = 'pinvi-e2e-not-a-live-key';

export const MOCKED_SERVICE_ENV = {
  NEXT_PUBLIC_PINVI_API_URL: MOCK_API_ORIGIN,
  NEXT_PUBLIC_GRAFANA_URL: MOCK_GRAFANA_ORIGIN,
  PINVI_GRAFANA_HEALTH_URL: MOCK_GRAFANA_ORIGIN,
  NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH: '/d/pinvi/overview?orgId=1&kiosk=tv',
  NEXT_PUBLIC_VWORLD_API_KEY:
    process.env.PINVI_E2E_EXPECT_VWORLD_CANVAS === '1' ? MOCK_VWORLD_API_KEY : '',
};

/** 잘못 상속한 live URL을 webServer probe가 읽기 전에 거절한다. */
export function mockedAppURL(input?: string): URL {
  let url: URL;
  try {
    url = new URL(input ?? 'http://127.0.0.1:13805');
  } catch {
    throw new Error('mocked suite requires an isolated local HTTP origin');
  }
  const productionPorts = new Set(['12801', '12805', '12205', '12701', '14101']);
  if (
    url.protocol !== 'http:' ||
    !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) ||
    Number(url.port || '80') < 1024 ||
    productionPorts.has(url.port) ||
    url.username ||
    url.password ||
    url.pathname !== '/' ||
    url.search ||
    url.hash
  ) {
    throw new Error('mocked suite requires an isolated local HTTP origin');
  }
  return url;
}
