import AdminLayout from '@/app/(admin)/admin/layout';
import { AdminPage } from '@/components/admin/AdminPage';
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
  it('기존 "1"/"0" 저장값을 읽고 같은 형식으로 접힘을 저장한다', async () => {
    localStorage.setItem('pinvi.admin.sidebar.collapsed', '0');
    await open();
    const rail = document.querySelector('[data-slot="admin-shell-rail"]');
    expect(rail).not.toHaveAttribute('data-collapsed');
    await userEvent.click(screen.getByRole('button', { name: 'Admin 메뉴 접기' }));
    expect(rail).toHaveAttribute('data-collapsed', 'true');
    expect(localStorage.getItem('pinvi.admin.sidebar.collapsed')).toBe('1');
    expect(screen.getByRole('link', { name: '사용자' })).toHaveAttribute('aria-label', '사용자');
    await userEvent.click(screen.getByRole('button', { name: 'Admin 메뉴 펼치기' }));
    expect(localStorage.getItem('pinvi.admin.sidebar.collapsed')).toBe('0');
  });
  it('저장된 "1"이면 접힌 rail로 시작한다', async () => {
    localStorage.setItem('pinvi.admin.sidebar.collapsed', '1');
    await open();
    expect(document.querySelector('[data-slot="admin-shell-rail"]')).toHaveAttribute(
      'data-collapsed',
      'true',
    );
    expect(screen.getByRole('button', { name: 'Admin 메뉴 펼치기' })).toBeInTheDocument();
  });
  it('상단 바 한 줄에 "영역 - 페이지" 제목만 두고 페이지 설명은 작게 둔다', async () => {
    mocks.pathname = '/admin/users';
    render(
      <AdminLayout>
        <AdminPage title="사용자" description="운영 계정 조회와 상태 관리">
          본문
        </AdminPage>
      </AdminLayout>,
    );
    const heading = await screen.findByRole('heading', { level: 1 });
    expect(heading).toHaveTextContent('Pinvi 운영 - 사용자');
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    const header = heading.closest('[data-slot="admin-shell-header"]');
    expect(header).not.toBeNull();
    expect(header?.querySelector('[data-slot="admin-shell-description"]')).toHaveTextContent(
      '운영 계정 조회와 상태 관리',
    );
    expect(screen.getByRole('main')).not.toHaveTextContent('운영 계정 조회와 상태 관리');
    expect(screen.getByRole('button', { name: 'Admin 메뉴 열기' })).toBeInTheDocument();
  });
  it('하위 경로는 가장 가까운 메뉴 그룹을 영역으로 쓴다', async () => {
    mocks.pathname = '/admin/debug/request/abc';
    render(
      <AdminLayout>
        <AdminPage title="Request timeline">본문</AdminPage>
      </AdminLayout>,
    );
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(
      '지도 데이터 - Request timeline',
    );
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
