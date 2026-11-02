import { afterEach, describe, expect, it, vi } from 'vitest';
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

  afterEach(() => {
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
    await act(async () => {
      root = hydrateRoot(host, <LoginPage />, {
        onRecoverableError: (error) => recoverable.push(error),
      });
    });

    const after = host.querySelector<HTMLButtonElement>('[data-testid="login-submit"]');
    expect(after?.disabled).toBe(false);
    expect(recoverable).toEqual([]);
  });
});
