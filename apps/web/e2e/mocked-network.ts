import type { APIRequestContext, BrowserContext, Route } from '@playwright/test';
import { MOCK_API_ORIGIN } from './mocked-origins';

const SAFE_SEGMENTS = new Set([
  'auth',
  'users',
  'trips',
  'shared',
  'admin',
  'features',
  'transport',
  'search',
  'storage',
  'legal',
  'notices',
  'files',
  'ws',
  'me',
  'health',
  'status',
  'summary',
  'retention',
  'storage-retention',
  'attachments',
  'days',
  'pois',
  'comments',
  'telegram-targets',
  'telegram-notifications',
  'telegram-notification-preferences',
  'consents',
  'oauth',
  'providers',
  'refresh',
  'runs',
  'dry-run',
  'execute',
  'quotas',
  'usage',
  'preferences',
  'targets',
  'pending',
  'gc',
  'download',
]);

/** 정본 endpoint 이름만 남기고 ID·token·서명 query·헤더는 진단에 넣지 않는다. */
function label(url: URL, method: string): string {
  const path = url.pathname
    .split('/')
    .filter(Boolean)
    .slice(0, 6)
    .map((part) => (SAFE_SEGMENTS.has(part) ? part : ':id'))
    .join('/');
  return method + ' /' + path;
}

/** 동일 앱이어도 서버의 다른 origin 조회를 유발하는 proxy는 명시 mock 없이는 허용하지 않는다. */
function allowedAppRequest(target: URL, appOrigin: string): boolean {
  let path: string;
  try { path = decodeURIComponent(target.pathname); } catch { return false; }
  return target.origin === appOrigin && path !== '/admin/grafana/health' && path !== '/_next/image';
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
  let closing = false;
  context.on('close', () => { closing = true; });
  const disposedDuringClose = (error: unknown, route?: Route) => {
    if (!(error instanceof Error)) return false;
    const terminal = /Request context disposed|Fetch response has been disposed|Target page, context or browser has been closed|route\.(?:fetch|fulfill|abort): Test ended\./.test(error.message);
    let pageClosed = false;
    try { pageClosed = route?.request().frame().page().isClosed() ?? false; } catch { /* frame 생성 전 요청 */ }
    // page fixture와 worker가 context보다 먼저 끝내는 요청도 Playwright의 명시 종료 사유로 구분한다.
    const testEnded = /route\.(?:fetch|fulfill|abort): Test ended\./.test(error.message);
    return terminal && (closing || pageClosed || testEnded);
  };
  const close = context.close.bind(context);
  context.close = async (...args: Parameters<BrowserContext['close']>) => {
    closing = true;
    await close(...args);
  };
  const note = (url: URL, method: string) => {
    const message = label(url, method);
    if (!violations.includes(message)) violations.push(message);
  };
  // page.request도 같은 context의 request를 읽으므로 모든 직접 API 전송에 동일 경계를 적용한다.
  Object.defineProperty(context, 'request', {
    value: guardMockedRequest(context.request, appOrigin),
    configurable: true,
  });
  await context.route('**/*', async (route) => {
    try {
      const request = route.request();
      const url = new URL(request.url());
      if (allowedAppRequest(url, appOrigin)) {
        const response = await route.fetch({ maxRedirects: 0 });
        if (response.status() >= 300 && response.status() < 400 && response.headers()['location']) {
          // 브라우저는 redirect 다음 요청을 route에 다시 주지 않는다. mock 없는 redirect는
          // chain 전체를 허용하지 않고 기능별 page mock에서 명시하도록 한다.
          note(url, 'REDIRECT');
          await route.abort('blockedbyclient');
          return;
        }
        await route.fulfill({ response });
        return;
      }
      note(url, request.method());
      await route.abort('blockedbyclient');
    } catch (error) {
      // context.close가 취소한 로컬 prefetch만 정리한다. 실행 중의 오류는 계속 실패시킨다.
      if (!disposedDuringClose(error, route)) throw error;
    }
  });
  // 공통 새 사용자/새 여행의 명시적인 read-only 초기 상태. POST/PUT은
  // 여기에 포함하지 않으며 기능별 page mock이 항상 우선한다.
  const emptyLists = [
    /^\/users\/me\/telegram-(targets|notifications)$/,
    /^\/trips\/[0-9a-f-]{36}\/telegram-targets$/,
    /^\/trips\/[0-9a-f-]{36}\/(days\/\d+|pois\/[0-9a-f-]{36})\/attachments$/,
  ];
  await context.route(
    (url) =>
      url.origin === MOCK_API_ORIGIN &&
      (emptyLists.some((pattern) => pattern.test(url.pathname)) ||
        url.pathname === '/transport/status' ||
        url.pathname === '/users/me/telegram-notification-preferences'),
    async (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      const path = new URL(route.request().url()).pathname;
      const data =
        path === '/transport/status'
          ? { enabled: false, layers: [] }
          : path === '/users/me/telegram-notification-preferences'
            ? {
                weather_enabled: false,
                daily_enabled: false,
                weekly_enabled: false,
                send_time: '08:00',
                weekly_day: 0,
                weekly_target_id: null,
              }
            : [];
      try {
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data }) });
      } catch (error) {
        if (!disposedDuringClose(error, route)) throw error;
      }
    },
  );
  await context.routeWebSocket('**/*', async (socket) => {
    const url = new URL(socket.url());
    // 협업 전용 검사는 ControlledWebSocket을 사용한다. 그 밖의 여행 화면은
    // 실제 realtime 서버에 연결하지 않고 명시적인 연결 거절 fixture를 쓴다.
    const apiSocketOrigin = MOCK_API_ORIGIN.replace(/^http/, 'ws');
    if (url.origin !== apiSocketOrigin || !/^\/ws\/trips\/[0-9a-f-]+$/.test(url.pathname)) {
      note(url, 'WEBSOCKET');
    }
    try {
      await socket.close({ code: 1008, reason: 'mocked suite has no realtime upstream' });
    } catch (error) {
      if (!disposedDuringClose(error)) throw error;
    }
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
  if (!allowedAppRequest(target, new URL(baseURL).origin)) {
    throw new Error('mocked suite: APIRequestContext network denied: ' + label(target, 'REQUEST'));
  }
}

/** APIRequestContext는 browser route를 우회하므로 전송 전 검사하고 redirect를 자동 추적하지 않는다. */
export function guardMockedRequest(request: APIRequestContext, baseURL: string): APIRequestContext {
  const methods = new Set(['fetch', 'get', 'post', 'put', 'patch', 'delete', 'head']);
  return new Proxy(request, {
    get(target, key) {
      const value = Reflect.get(target, key);
      if (typeof value !== 'function') return value;
      if (!methods.has(String(key))) return value.bind(target);
      return async (url: string | { url(): string }, options?: Record<string, unknown>) => {
        assertLocalRequest(typeof url === 'string' ? url : url.url(), baseURL);
        const resolved = typeof url === 'string' ? new URL(url, baseURL).href : url;
        return value.call(target, resolved, { ...options, maxRedirects: 0 });
      };
    },
  }) as APIRequestContext;
}
