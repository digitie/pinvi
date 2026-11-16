import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnchorHTMLAttributes } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppShell } from '@/components/app/AppShell';

const state = vi.hoisted(() => ({ path: '/trips', mobile: false }));
vi.mock('next/navigation', () => ({ usePathname: () => state.path }));
vi.mock('next/link', () => ({
  default: ({ href, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props} />
  ),
}));
vi.mock('@/lib/useMobileWebLayout', () => ({ useMobileWebLayout: () => state.mobile }));

beforeEach(() => {
  state.path = '/trips';
  state.mobile = false;
});

describe('앱 셸 — 로고·홈은 개인 홈으로', () => {
  it('로고(워드마크)와 데스크톱 홈 탭은 /home을 가리킨다', () => {
    render(<AppShell>본문</AppShell>);
    expect(screen.getByRole('link', { name: 'Pinvi 홈' })).toHaveAttribute('href', '/home');
    expect(screen.getByTestId('app-nav--home')).toHaveAttribute('href', '/home');
  });

  it('/home에서는 홈 탭이 현재 위치다', () => {
    state.path = '/home';
    render(<AppShell>본문</AppShell>);
    expect(screen.getByTestId('app-nav--home')).toHaveAttribute('aria-current', 'page');
    expect(screen.getByTestId('app-nav--trips')).not.toHaveAttribute('aria-current');
  });

  it('모바일 더보기의 홈은 셸 안 목적지라 이동 안내를 붙이지 않는다', async () => {
    state.mobile = true;
    render(<AppShell>본문</AppShell>);
    await userEvent.setup().click(screen.getByTestId('app-nav-more-toggle'));
    const homeLink = screen.getByTestId('app-nav--home-mobile');
    expect(homeLink).toHaveAttribute('href', '/home');
    expect(homeLink).not.toHaveTextContent('앱 메뉴 밖으로 이동');
    expect(screen.getByTestId('app-nav--profile-mobile')).toHaveTextContent('앱 메뉴 밖으로 이동');
  });
});
