import {
  test as base,
  expect,
  type BrowserContext,
  type BrowserContextOptions,
} from '@playwright/test';
import { MOCK_VWORLD_API_KEY } from './mocked-origins';
import { guardMockedRequest, installMockedNetwork } from './mocked-network';

// 공개 key나 외부 tile 서버 없이 실제 MapLibre canvas·worker·카메라를 검증한다.
// 테스트용 key의 WMTS URL만 mock하며 나머지 요청은 기존 network fence가 차단한다.
async function installCanvasTiles(context: BrowserContext) {
  if (process.env.PINVI_E2E_EXPECT_VWORLD_CANVAS !== '1') return;
  await context.route(
    (url) =>
      url.protocol === 'https:' &&
      url.hostname === 'api.vworld.kr' &&
      url.pathname.startsWith('/req/wmts/1.0.0/' + MOCK_VWORLD_API_KEY + '/'),
    (route) =>
      route.fulfill({
        contentType: 'image/png',
        body: Buffer.from(
          'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
          'base64',
        ),
      }),
  );
  // public MakiMarker 기본 asset도 고정 버전의 SVG만 로컬 응답한다.
  await context.route(
    (url) =>
      url.protocol === 'https:' &&
      url.hostname === 'unpkg.com' &&
      /^\/@mapbox\/maki@8\.0\.0\/icons\/[a-z0-9-]+\.svg$/.test(url.pathname),
    (route) =>
      route.fulfill({
        contentType: 'image/svg+xml',
        body: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 15 15"><circle cx="7.5" cy="7.5" r="5"/></svg>',
      }),
  );
}

type ContextFactory = (options?: BrowserContextOptions) => Promise<BrowserContext>;

export const test = base.extend<{
  _mockedNetwork: void;
  newMockContext: ContextFactory;
}>({
  _mockedNetwork: [
    async ({ context, baseURL }, use) => {
      if (!baseURL) throw new Error('mocked suite requires a local app baseURL');
      const fence = await installMockedNetwork(context, new URL(baseURL).origin);
      await installCanvasTiles(context);
      try {
        await use();
      } finally {
        await context.close();
        fence.verify();
      }
    },
    { auto: true },
  ],
  newMockContext: async ({ browser, baseURL }, use) => {
    if (!baseURL) throw new Error('mocked suite requires a local app baseURL');
    const contexts: {
      context: BrowserContext;
      fence: Awaited<ReturnType<typeof installMockedNetwork>>;
    }[] = [];
    try {
      await use(async (options) => {
        const context = await browser.newContext({ ...options, serviceWorkers: 'block' });
        const fence = await installMockedNetwork(context, new URL(baseURL).origin);
        await installCanvasTiles(context);
        contexts.push({ context, fence });
        return context;
      });
    } finally {
      for (const { context } of contexts) await context.close();
      for (const { fence } of contexts) fence.verify();
    }
  },
  request: async ({ request, baseURL }, use) => {
    if (!baseURL) throw new Error('mocked suite requires a local app baseURL');
    await use(guardMockedRequest(request, baseURL));
  },
});

export { expect };

export type * from '@playwright/test';
