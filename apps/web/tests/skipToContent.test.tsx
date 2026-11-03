import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AppShell } from '@/components/app/AppShell';
import { PublicMasthead } from '@/components/app/PublicChrome';
vi.mock('next/navigation', () => ({ usePathname: () => '/trips/trash' }));
vi.mock('@/lib/useMobileWebLayout', () => ({ useMobileWebLayout: () => true }));

describe('본문 건너뛰기', () => {
  it('앱 본문에 focus 가능한 target이 있고 휴지통은 모바일 메뉴를 유지한다', () => {
    render(<AppShell><h1>휴지통</h1></AppShell>);
    expect(screen.getByRole('link', { name: '본문으로 건너뛰기' })).toHaveAttribute('href', '#main');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
    expect(screen.getByRole('main')).toHaveAttribute('tabindex', '-1');
    expect(screen.getByRole('navigation', { name: '주요 메뉴' })).toBeInTheDocument();
  });
  it('공개 화면도 동일한 건너뛰기 링크를 제공한다', () => {
    render(<><PublicMasthead /><main id="main" tabIndex={-1}>본문</main></>);
    expect(screen.getByRole('link', { name: '본문으로 건너뛰기' })).toHaveAttribute('href', '#main');
  });
});
