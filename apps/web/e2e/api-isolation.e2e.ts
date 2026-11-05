/* eslint-disable no-restricted-imports, no-restricted-syntax -- 격리 정책 자체를 독립된 소유 context로 검증한다. */
import { test, expect, type Browser } from '@playwright/test';
import { test as guardedTest } from './fixtures';
import { createServer, type Server } from 'node:http';
import { installMockedNetwork } from './mocked-network';
import { MOCK_API_ORIGIN } from './mocked-origins';

async function ownedServer() {
  const requests: string[] = [];
  const server = createServer((req, res) => {
    requests.push(req.url ?? '/');
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
