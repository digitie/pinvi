/* eslint-disable no-restricted-imports, no-restricted-syntax -- 격리 정책 자체를 독립된 소유 context로 검증한다. */
import { test, expect, request as rawRequestFactory, type Browser } from '@playwright/test';
import { test as guardedTest } from './fixtures';
import { createServer, type Server } from 'node:http';
import { guardMockedRequest, installMockedNetwork } from './mocked-network';
import { MOCK_API_ORIGIN } from './mocked-origins';

async function ownedServer(redirect?: string, delayMs = 0) {
  const requests: string[] = [];
  const server = createServer(async (req, res) => {
    requests.push(req.url ?? '/');
    if (delayMs) await new Promise(resolve => setTimeout(resolve, delayMs));
    if (redirect && req.url !== '/') {
      res.writeHead(302, { location: redirect });
      res.end();
      return;
    }

    res.writeHead(200, { 'content-type': 'text/html', 'access-control-allow-origin': '*' });
    res.end('<!doctype html><title>owned isolation fixture</title>');
  });
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('fixture listen failed');
  return { server, requests, origin: 'http://127.0.0.1:' + address.port };
}

async function close(server: Server) {
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
}

async function scenario(browser: Browser) {
  const app = await ownedServer();
  const trap = await ownedServer();
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const fence = await installMockedNetwork(context, app.origin);
  const page = await context.newPage();
  await page.goto(app.origin);
  return {
    app,
    trap,
    context,
    fence,
    page,
    async dispose() {
      await context.close();
      await close(trap.server);
      await close(app.server);
    },
  };
}

test('미등록 HTTP 요청은 소유 수신 서버에 도달하기 전에 차단하고 비밀 없는 오류로 보고한다', async ({
  browser,
}) => {
  const s = await scenario(browser);
  try {
    const secret = 'owned-secret-618';
    const failed = await s.page.evaluate(
      (url) =>
        fetch(url).then(
          () => false,
          () => true,
        ),
      s.trap.origin + '/shared/' + secret + '?token=' + secret,
    );
    expect(failed).toBe(true);
    expect(s.trap.requests).toEqual([]);
    expect(() => s.fence.verify()).toThrow(/unhandled network/);
    expect(s.fence.violations.join(' ')).not.toContain(secret);
  } finally {
    await s.dispose();
  }
});

test('등록한 page mock은 context guard보다 먼저 처리하고 앱 정적 요청은 실제 서빙한다', async ({
  browser,
}) => {
  const s = await scenario(browser);
  try {
    await s.page.route(MOCK_API_ORIGIN + '/known', (route) =>
      route.fulfill({ contentType: 'application/json', body: '{"data":"owned"}' }),
    );
    const response = await s.page.evaluate(
      (url) => fetch(url).then((r) => r.json()),
      MOCK_API_ORIGIN + '/known',
    );
    expect(response).toEqual({ data: 'owned' });
    expect(s.app.requests).toContain('/');
    s.fence.verify();
  } finally {
    await s.dispose();
  }
});

test('공통 read-only 초기 fixture는 쓰기 요청을 성공으로 바꾸지 않는다', async ({ browser }) => {
  const s = await scenario(browser);
  try {
    const url = MOCK_API_ORIGIN + '/users/me/telegram-targets';
    expect(await s.page.evaluate((path) => fetch(path).then((r) => r.json()), url)).toEqual({
      data: [],
    });
    const failed = await s.page.evaluate(
      (path) =>
        fetch(path, { method: 'POST' }).then(
          () => false,
          () => true,
        ),
      url,
    );
    expect(failed).toBe(true);
    expect(() => s.fence.verify()).toThrow(/unhandled network/);
  } finally {
    await s.dispose();
  }
});

test('미등록 WebSocket도 실제 업스트림으로 연결하지 않는다', async ({ browser }) => {
  const s = await scenario(browser);
  try {
    await s.page.evaluate(
      (url) =>
        new Promise<void>((resolve) => {
          const socket = new WebSocket(url);
          socket.onclose = () => resolve();
          socket.onerror = () => resolve();
        }),
      s.trap.origin.replace('http:', 'ws:') + '/secret-618',
    );
    expect(s.trap.requests).toEqual([]);
    expect(() => s.fence.verify()).toThrow(/WEBSOCKET/);
    expect(s.fence.violations.join(' ')).not.toContain('secret-618');
  } finally {
    await s.dispose();
  }
});

test('동일 origin의 서버 proxy도 mock이 없으면 실행하지 않는다', async ({ browser }) => {
  const s = await scenario(browser);
  try {
    await s.page.evaluate(
      (url) => fetch(url).catch(() => null),
      s.app.origin + '/admin/grafana/health',
    );
    expect(s.app.requests).toEqual(['/']);
    expect(() => s.fence.verify()).toThrow(/unhandled network/);
  } finally {
    await s.dispose();
  }
});

guardedTest('APIRequestContext는 로컬 앱 정적 파일 외의 전송을 거절한다', async ({ request }) => {
  const trap = await ownedServer();
  try {
    await expect(request.get(trap.origin + '/secret-618?token=owned')).rejects.toThrow(
      /network denied/,
    );
    expect(trap.requests).toEqual([]);
    const worker = await request.get('/maplibre/maplibre-gl-worker.mjs');
    expect(worker.status()).toBe(200);
  } finally {
    await close(trap.server);
  }
});

test('APIRequestContext의 로컬 redirect가 다른 origin으로 이어지지 않는다', async () => {
  const trap = await ownedServer();
  const app = await ownedServer(trap.origin + '/secret-618');
  const raw = await rawRequestFactory.newContext();
  try {
    const request = guardMockedRequest(raw, app.origin);
    const response = await request.get('/redirect', { maxRedirects: 5 });
    expect(response.status()).toBe(302);
    expect(trap.requests).toEqual([]);
    expect(app.requests).toEqual(['/redirect']);
  } finally {
    await raw.dispose();
    await close(app.server);
    await close(trap.server);
  }
});

for (const action of ['navigation', 'fetch'] as const) {
  test('브라우저 redirect는 외부 수신 서버를 호출하지 않는다: ' + action, async ({ browser }) => {
    const trap = await ownedServer();
    const app = await ownedServer(trap.origin + '/secret-618');
    const context = await browser.newContext({ serviceWorkers: 'block' });
    const fence = await installMockedNetwork(context, app.origin);
    try {
      const page = await context.newPage();
      await page.goto(app.origin);
      if (action === 'navigation') await page.goto(app.origin + '/redirect').catch(() => null);
      else await page.evaluate((url) => fetch(url).catch(() => null), app.origin + '/redirect');
      expect(trap.requests).toEqual([]);
      expect(() => fence.verify()).toThrow(/unhandled network/);
    } finally {
      await context.close();
      await close(app.server);
      await close(trap.server);
    }
  });
}

guardedTest('기본·추가 context와 page의 request도 전송 guard를 사용한다', async ({
  context, page, newMockContext,
}) => {
  const trap = await ownedServer();
  const extra = await newMockContext();
  const extraPage = await extra.newPage();
  try {
    const outcomes = [];
    for (const request of [context.request, page.request, extra.request, extraPage.request]) {
      outcomes.push(await request.get(trap.origin + '/secret-618').then(() => false, () => true));
    }
    expect(trap.requests).toEqual([]);
    expect(outcomes).toEqual([true, true, true, true]);
  } finally {
    await close(trap.server);
  }
});

test('context를 닫는 동안 진행 중인 로컬 fetch가 후속 검사를 깨뜨리지 않는다', async ({ browser }) => {
  const app = await ownedServer(undefined, 500);
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const fence = await installMockedNetwork(context, app.origin);
  const page = await context.newPage();
  try {
    const pending = page.goto(app.origin).catch(() => null);
    await expect.poll(() => app.requests.length).toBe(1);
    await context.close();
    await pending;
    fence.verify();
  } finally {
    await context.close();
    await close(app.server);
  }
});

test('브라우저 image optimizer 요청은 서버 proxy로 전달하지 않는다', async ({ browser }) => {
  const s = await scenario(browser);
  try {
    await s.page.evaluate(url => fetch(url).catch(() => null),
      s.app.origin + '/_next/image?url=%2Fadmin%2Fgrafana%2Fhealth&w=64&q=75');
    expect(s.app.requests).toEqual(['/']);
    expect(() => s.fence.verify()).toThrow(/unhandled network/);
  } finally {
    await s.dispose();
  }
});

test('직접 request도 image optimizer를 서버 proxy로 사용하지 않는다', async () => {
  const app = await ownedServer();
  const raw = await rawRequestFactory.newContext();
  try {
    const request = guardMockedRequest(raw, app.origin);
    await expect(request.get('/_next/image?url=%2Fadmin%2Fgrafana%2Fhealth&w=64&q=75')).rejects.toThrow(/network denied/);
    expect(app.requests).toEqual([]);
  } finally {
    await raw.dispose();
    await close(app.server);
  }
});
