import AdminLayout from '@/app/(admin)/admin/layout';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  pathname: '/admin/users/detail',
  replace: vi.fn(),
  me: vi.fn(),
  logout: vi.fn(),
}));
vi.mock('next/navigation', () => ({
  redirect: (href: string) => mocks.replace(href),
  usePathname: () => mocks.pathname,
  useRouter: () => ({ replace: mocks.replace }),
}));
vi.mock('@pinvi/api-client', () => ({
  ApiClient: class {},
  ApiError: class extends Error {},
  authApi: () => ({ me: mocks.me, logout: mocks.logout }),
  queryKeys: { admin: { me: () => ['admin', 'me'] } },
}));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mocks.pathname = '/admin/users/detail';
  mocks.me.mockResolvedValue({ email: 'admin@example.com', roles: ['user', 'admin'] });
  mocks.logout.mockResolvedValue(undefined);
});
async function open() {
  render(
    <AdminLayout>
      <h1>사용자 관리</h1>
    </AdminLayout>,
  );
  return screen.findByRole('navigation', { name: '관리자 주요 메뉴' });
}
describe('PinVi 공통 관리자 셸', () => {
  it('기존30개 메뉴와 document 링크를 보존하고 최장 경로 하나만 활성화한다', async () => {
    const nav = await open();
    const links = within(nav).getAllByRole('link');
    expect(links).toHaveLength(30);
    expect(links[0]).toHaveAttribute('href', '/admin');
    expect(links.at(-1)).toHaveAttribute('href', '/admin/reset');
    expect(nav.querySelectorAll('[aria-current="page"]')).toHaveLength(1);
    expect(within(nav).getByRole('link', { name: '사용자' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('link', { name: '본문으로 건너뛰기' })).toHaveAttribute(
      'href',
      '#admin-main-content',
    );
    expect(screen.getByRole('main')).toHaveAttribute('tabindex', '-1');
  });
  it('접힘을 저장하면서 메뉴의 접근성 이름을 보존한다', async () => {
    await open();
    await userEvent.click(screen.getByRole('button', { name: 'Admin 메뉴 접기' }));
    expect(screen.getByTestId('admin-sidebar')).toHaveAttribute('data-collapsed', 'true');
    expect(localStorage.getItem('pinvi.admin.sidebar.collapsed')).toBe('1');
    expect(screen.getByRole('link', { name: '사용자' })).toHaveAttribute('aria-label', '사용자');
  });
  it('로그아웃 실패 시 이동하지 않고 재시도 성공 후 로그인으로 이동한다', async () => {
    mocks.logout.mockRejectedValueOnce(new Error('내부 오류 원문'));
    await open();
    await userEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('로그아웃하지 못했습니다.');
    expect(screen.getByRole('alert')).not.toHaveTextContent('내부 오류 원문');
    expect(mocks.replace).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith('/admin/login'));
  });
  it('로그인 페이지는 권한 조회와 메뉴를 렌더하지 않는다', () => {
    mocks.pathname = '/admin/login';
    render(<AdminLayout>로그인</AdminLayout>);
    expect(mocks.me).not.toHaveBeenCalled();
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });
  it('관리자 역할이 없는 사용자의 메뉴 노출을 차단한다', async () => {
    mocks.me.mockResolvedValue({ email: 'user@example.com', roles: ['user'] });
    render(<AdminLayout>보호된 본문</AdminLayout>);
    await waitFor(() =>
      expect(mocks.replace).toHaveBeenCalledWith('/admin/login?reason=forbidden'),
    );
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    expect(screen.queryByText('보호된 본문')).not.toBeInTheDocument();
  });
});
