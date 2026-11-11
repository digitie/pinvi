import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnchorHTMLAttributes } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppShell } from '@/components/app/AppShell';
const state = vi.hoisted(() => ({ path: '/trips', mobile: true }));
vi.mock('next/navigation', () => ({ usePathname: () => state.path }));
vi.mock('next/link', () => ({
  default: ({ href, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props} />
  ),
}));
vi.mock('@/lib/useMobileWebLayout', () => ({ useMobileWebLayout: () => state.mobile }));
beforeEach(() => {
  state.path = '/trips';
  state.mobile = true;
});
function Page() {
  return (
    <AppShell>
      <button>바깥 항목</button>
    </AppShell>
  );
}
const menu = () => screen.getByRole('dialog', { name: '더보기 메뉴' });
const toggle = () => screen.getByTestId('app-nav-more-toggle');
describe('공개 더보기 공통 Popover', () => {
  it('토글/연결ID/기존폭·메뉴를 유지하고 시작 포커스를 빼앗지 않는다', async () => {
    const view = render(<Page />);
    await userEvent.setup().click(toggle());
    expect(toggle()).toHaveAttribute('aria-expanded', 'true');
    expect(toggle()).toHaveFocus();
    expect(menu().id).toBe(toggle().getAttribute('aria-controls'));
    expect(menu()).toHaveClass('w-48', 'bg-canvas', 'rounded-md');
    expect(document.body).toContainElement(menu());
    expect(view.container).not.toContainElement(menu());
    expect(menu()).toHaveTextContent('설정');
    expect(menu()).toHaveTextContent('프로필');
  });
  it('바깥 포인터로 닫고 클릭한 항목의 포커스를 유지한다', async () => {
    render(<Page />);
    const user = userEvent.setup();
    await user.click(toggle());
    const outside = screen.getByRole('button', { name: '바깥 항목' });
    await user.click(outside);
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: '더보기 메뉴' })).not.toBeInTheDocument(),
    );
    expect(outside).toHaveFocus();
  });
  it('바깥 포커스 이탈로 닫는다', async () => {
    render(<Page />);
    await userEvent.setup().click(toggle());
    act(() => screen.getByRole('button', { name: '바깥 항목' }).focus());
    await waitFor(() => expect(toggle()).toHaveAttribute('aria-expanded', 'false'));
  });
  it('Escape로 닫은 뒤 토글로 포커스를 돌린다', async () => {
    render(<Page />);
    const user = userEvent.setup();
    await user.click(toggle());
    await user.keyboard('{Escape}');
    await waitFor(() => expect(toggle()).toHaveFocus());
    expect(toggle()).toHaveAttribute('aria-expanded', 'false');
  });
  it('경로가 바뀌면 닫는다', async () => {
    const { rerender } = render(<Page />);
    await userEvent.setup().click(toggle());
    expect(menu()).toBeInTheDocument();
    state.path = '/settings/mcp-tokens';
    rerender(<Page />);
    await waitFor(() => expect(toggle()).toHaveAttribute('aria-expanded', 'false'));
  });
  it('데스크톱 전환 뒤 portal 메뉴가 남지 않는다', async () => {
    const { rerender } = render(<Page />);
    await userEvent.setup().click(toggle());
    expect(menu()).toBeInTheDocument();
    state.mobile = false;
    rerender(<Page />);
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: '더보기 메뉴' })).not.toBeInTheDocument(),
    );
  });
});
