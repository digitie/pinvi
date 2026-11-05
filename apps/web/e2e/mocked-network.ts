import type { BrowserContext } from '@playwright/test';
import { MOCK_API_ORIGIN } from './mocked-origins';

const SAFE_SEGMENTS = new Set([
  'auth', 'users', 'trips', 'shared', 'admin', 'features', 'transport', 'search',
  'storage', 'legal', 'notices', 'files', 'ws', 'me', 'health', 'status', 'summary',
  'retention', 'storage-retention', 'attachments', 'days', 'pois', 'comments',
  'telegram-targets', 'telegram-notifications', 'telegram-notification-preferences',
  'consents', 'oauth', 'providers', 'refresh', 'runs', 'dry-run', 'execute',
  'quotas', 'usage', 'preferences', 'targets', 'pending', 'gc', 'download',
]);

/** 정본 endpoint 이름만 남기고 ID·token·서명 query·헤더는 진단에 넣지 않는다. */
function label(url: URL, method: string): string {
  const path = url.pathname.split('/').filter(Boolean).slice(0, 6)
    .map((part) => SAFE_SEGMENTS.has(part) ? part : ':id').join('/');
  return method + ' /' + path;
}

export interface MockedNetworkFence {
  violations: string[];
  verify(): void;
}

export async function installMockedNetwork(
  context: BrowserContext,
  appOrigin: string,
): Promise<MockedNetworkFence> {
  const violations: string[] = [];
  const note = (url: URL, method: string) => {
    const message = label(url, method);
    if (!violations.includes(message)) violations.push(message);
  };
  await context.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin === appOrigin && url.pathname !== '/admin/grafana/health') {
      await route.continue();
      return;
    }
    note(url, request.method());
    await route.abort('blockedbyclient');
  });
  // 교통 기능을 검증하지 않는 화면의 공통 초기 상태. 개별 page mock이 우선한다.
  await context.route(MOCK_API_ORIGIN + '/transport/status', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: { enabled: false, layers: [] } }),
    }),
  );
  await context.routeWebSocket('**/*', async (socket) => {
    const url = new URL(socket.url());
    // 협업 전용 검사는 ControlledWebSocket을 사용한다. 그 밖의 여행 화면은
    // 실제 realtime 서버에 연결하지 않고 명시적인 연결 거절 fixture를 쓴다.
    const apiSocketOrigin = MOCK_API_ORIGIN.replace(/^http/, 'ws');
    if (url.origin !== apiSocketOrigin || !/^\/ws\/trips\/[0-9a-f-]+$/.test(url.pathname)) {
      note(url, 'WEBSOCKET');
    }
    await socket.close({ code: 1008, reason: 'mocked suite has no realtime upstream' });
  });
  return {
    violations,
    verify() {
      if (violations.length) {
        throw new Error('mocked suite: unhandled network requests: ' + violations.join(', '));
      }
    },
  };
}

export function assertLocalRequest(url: string, baseURL: string): void {
  const target = new URL(url, baseURL);
  if (target.origin !== new URL(baseURL).origin || target.pathname === '/admin/grafana/health') {
    throw new Error('mocked suite: APIRequestContext network denied: ' + label(target, 'REQUEST'));
  }
}
