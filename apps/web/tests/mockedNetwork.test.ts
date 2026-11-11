import { describe, expect, it, vi } from 'vitest';
import type { BrowserContext, Route } from '@playwright/test';
import { installMockedNetwork } from '../e2e/mocked-network';

async function pendingLocalRequest({ prefetch, method = 'GET' }: {
  prefetch: boolean;
  method?: string;
}) {
  let handler: ((route: Route) => Promise<void>) | undefined;
  const context = {
    request: {},
    on: vi.fn(),
    close: vi.fn(async () => {}),
    routeWebSocket: vi.fn(async () => {}),
    route: vi.fn(async (pattern: unknown, callback: (route: Route) => Promise<void>) => {
      if (pattern === '**/*') handler = callback;
    }),
  } as unknown as BrowserContext;
  const error = new Error('route.fetch: socket hang up (ECONNRESET)');
  const route = {
    request: () => ({
      url: () => 'http://127.0.0.1:13805/trips?_rsc=fixture',
      method: () => method,
      headers: () => prefetch ? { 'next-router-prefetch': '1', rsc: '1' } : {},
      frame: () => ({ page: () => ({ isClosed: () => false }) }),
    }),
    fetch: vi.fn(async () => { throw error; }),
    fulfill: vi.fn(),
    abort: vi.fn(),
  } as unknown as Route;
  await installMockedNetwork(context, 'http://127.0.0.1:13805');
  return { context, route, error, handle: () => handler!(route) };
}

describe('격리 브라우저의 로컬 prefetch 종료', () => {
  it('명시 context 종료가 취소한 GET RSC prefetch ECONNRESET만 정리한다', async () => {
    const fixture = await pendingLocalRequest({ prefetch: true });
    await fixture.context.close();
    await expect(fixture.handle()).resolves.toBeUndefined();
    expect(fixture.route.fetch).toHaveBeenCalledTimes(1);
  });

  it('실행 중의 같은 prefetch 오류는 그대로 실패시킨다', async () => {
    const fixture = await pendingLocalRequest({ prefetch: true });
    await expect(fixture.handle()).rejects.toBe(fixture.error);
  });

  it('종료 중이어도 일반 로컬 요청의 오류를 숨기지 않는다', async () => {
    const fixture = await pendingLocalRequest({ prefetch: false });
    await fixture.context.close();
    await expect(fixture.handle()).rejects.toBe(fixture.error);
  });

  it('종료 중이어도 POST에 붙인 prefetch 헤더로 오류를 숨기지 않는다', async () => {
    const fixture = await pendingLocalRequest({ prefetch: true, method: 'POST' });
    await fixture.context.close();
    await expect(fixture.handle()).rejects.toBe(fixture.error);
  });
});
