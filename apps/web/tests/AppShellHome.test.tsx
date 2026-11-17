import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnchorHTMLAttributes } from 'react';
import { render, screen, within } from '@testing-library/react';
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

  it('모바일 하단 탭바는 홈이 첫 탭이고 파일은 더보기로 간다', async () => {
    state.mobile = true;
    render(<AppShell>본문</AppShell>);
    const tabbar = screen.getByRole('navigation', { name: '주요 메뉴' });
    const tabs = within(tabbar).getAllByRole('listitem');
    // 4개 목적지 + 더보기 = 5칸.
    expect(tabs).toHaveLength(5);
    expect(within(tabs[0]!).getByRole('link')).toHaveAttribute('href', '/home');
    expect(tabs.map((tab) => tab.textContent?.trim())).toEqual([
      '홈',
      '여행',
      '추천',
      '지도',
      '더보기',
    ]);
    await userEvent.setup().click(screen.getByTestId('app-nav-more-toggle'));
    expect(screen.getByTestId('app-nav--files-mobile')).toHaveAttribute('href', '/files');
    expect(screen.queryAllByTestId('app-nav--home-mobile')).toHaveLength(1);
    expect(screen.getByTestId('app-nav--profile-mobile')).toHaveTextContent('앱 메뉴 밖으로 이동');
  });
});
