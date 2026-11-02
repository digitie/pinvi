import { describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

import LoginPage from '@/app/(auth)/login/page';

// 2026-11-02 prod e2e — 하이드레이션 전에 누른 "로그인"은 아무 일도 하지 않았다(폼이 네이티브로
// /login에 제출되고 입력이 사라짐). 서버 HTML의 제출 버튼은 하이드레이션 전까지 비활성이어야 한다.
describe('로그인 제출 버튼', () => {
  it('서버 렌더(하이드레이션 전)에서는 비활성이다', () => {
    const html = renderToString(<LoginPage />);
    const button = html.match(/<button[^>]*data-testid="login-submit"[^>]*>/)?.[0] ?? '';
    expect(button).not.toBe('');
    expect(button).toMatch(/\sdisabled(=""|\s|>)/);
  });
});
