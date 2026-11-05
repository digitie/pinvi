import {
  test as base,
  expect,
  type APIRequestContext,
  type BrowserContext,
  type BrowserContextOptions,
} from '@playwright/test';
import { assertLocalRequest, installMockedNetwork } from './mocked-network';

type ContextFactory = (options?: BrowserContextOptions) => Promise<BrowserContext>;

export const test = base.extend<{
  _mockedNetwork: void;
  newMockContext: ContextFactory;
}>({
  _mockedNetwork: [
    async ({ context, baseURL }, use) => {
      if (!baseURL) throw new Error('mocked suite requires a local app baseURL');
      const fence = await installMockedNetwork(context, new URL(baseURL).origin);
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
    const methods = new Set(['fetch', 'get', 'post', 'put', 'patch', 'delete', 'head']);
    const guarded = new Proxy(request, {
      get(target, key) {
        const value = Reflect.get(target, key);
        if (typeof value !== 'function') return value;
        if (!methods.has(String(key))) return value.bind(target);
        return async (url: string | { url(): string }, ...args: unknown[]) => {
          assertLocalRequest(typeof url === 'string' ? url : url.url(), baseURL);
          return value.call(target, url, ...args);
        };
      },
    }) as APIRequestContext;
    await use(guarded);
  },
});

export { expect };

export type * from '@playwright/test';
