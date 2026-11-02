import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { hydrateRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

import LoginPage from '@/app/(auth)/login/page';

// 2026-11-02 prod e2e — 하이드레이션 전에 누른 "로그인"은 아무 일도 하지 않았다(폼이 네이티브로
// /login에 제출되고 입력이 사라짐). 서버 HTML의 제출 버튼은 하이드레이션 전까지 비활성이어야 한다.
describe('로그인 제출 버튼', () => {
  let root: Root | null = null;
  let container: HTMLElement | null = null;
  const actEnv = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const previousActEnv = actEnv.IS_REACT_ACT_ENVIRONMENT;

  beforeAll(() => {
    actEnv.IS_REACT_ACT_ENVIRONMENT = true;
  });

  afterAll(() => {
    actEnv.IS_REACT_ACT_ENVIRONMENT = previousActEnv;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    act(() => root?.unmount());
    container?.remove();
    root = null;
    container = null;
    vi.unstubAllGlobals();
  });

  it('서버 렌더(하이드레이션 전)에서는 비활성이다', () => {
    const html = renderToString(<LoginPage />);
    const button = html.match(/<button[^>]*data-testid="login-submit"[^>]*>/)?.[0] ?? '';
    expect(button).not.toBe('');
    expect(button).toMatch(/\sdisabled(=""|\s|>)/);
  });

  it('하이드레이션 뒤에는 활성이고, 불일치 오류가 없다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{"data":null}', { status: 401 })),
    );
    const host = document.createElement('div');
    container = host;
    host.innerHTML = renderToString(<LoginPage />);
    document.body.append(host);
    const before = host.querySelector<HTMLButtonElement>('[data-testid="login-submit"]');
    expect(before?.disabled).toBe(true);

    const recoverable: unknown[] = [];
    // React 19는 속성 불일치를 onRecoverableError가 아니라 console.error로만 알린다.
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    await act(async () => {
      root = hydrateRoot(host, <LoginPage />, {
        onRecoverableError: (error) => recoverable.push(error),
      });
    });
    const mismatches = consoleError.mock.calls.filter((call) =>
      /hydrat|didn't match|did not match/i.test(String(call[0])),
    );
    consoleError.mockRestore();

    const after = host.querySelector<HTMLButtonElement>('[data-testid="login-submit"]');
    expect(after?.disabled).toBe(false);
    expect(recoverable).toEqual([]);
    expect(mismatches).toEqual([]);
  });
});
