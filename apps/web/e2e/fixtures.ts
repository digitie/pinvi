import {
  test as base,
  expect,
  type BrowserContext,
  type BrowserContextOptions,
} from '@playwright/test';
import { guardMockedRequest, installMockedNetwork } from './mocked-network';

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
    await use(guardMockedRequest(request, baseURL));
  },
});

export { expect };

export type * from '@playwright/test';
