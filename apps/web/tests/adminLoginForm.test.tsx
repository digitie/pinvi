import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AdminLoginPage from '@/app/(admin)/admin/login/page';

const mocks = vi.hoisted(() => ({ login: vi.fn(), logout: vi.fn(), push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@pinvi/api-client', () => ({
  ApiClient: class {},
  ApiError: class extends Error {},
  authApi: () => ({ login: mocks.login, logout: mocks.logout }),
}));
beforeEach(() => {
  vi.clearAllMocks();
  mocks.login.mockResolvedValue({ roles: ['admin'] });
});
function openLogin() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <AdminLoginPage />
    </QueryClientProvider>,
  );
  const username = rendered.container.querySelector<HTMLInputElement>('[name=username]')!;
  const password = rendered.container.querySelector<HTMLInputElement>('[name=password]')!;
  return { ...rendered, username, password, form: rendered.container.querySelector('form')! };
}
describe('Pinvi 공통 관리자 로그인', () => {
  it('RHF 입력을 Pinvi 인증 계약으로 전달하고 관리자 화면으로 이동한다', async () => {
    const { username, password } = openLogin();
    const user = userEvent.setup();
    await user.type(username, 'admin@example.test');
    await user.type(password, 'example-pass-123');
    await user.click(screen.getByRole('button', { name: '로그인' }));
    await waitFor(() =>
      expect(mocks.login).toHaveBeenCalledWith({
        email: 'admin@example.test',
        password: 'example-pass-123',
      }),
    );
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/admin'));
  });
  it('change 이벤트 없는 비밀번호 관리자 자동완성도 제출 시 실제 DOM 값을 읽는다', async () => {
    const { username, password, form } = openLogin();
    username.value = 'admin@example.test';
    password.value = 'example-pass-123';
    fireEvent.submit(form);
    await waitFor(() =>
      expect(mocks.login).toHaveBeenCalledWith({
        email: 'admin@example.test',
        password: 'example-pass-123',
      }),
    );
  });
  it('Pinvi Zod 이메일 검증 실패는 API를 부르지 않고 이메일 입력에 표시한다', async () => {
    const { username, password } = openLogin();
    const user = userEvent.setup();
    await user.type(username, 'not-an-email');
    await user.type(password, 'example-pass-123');
    await user.click(screen.getByRole('button', { name: '로그인' }));
    await waitFor(() => expect(username).toHaveAttribute('aria-invalid', 'true'));
    expect(username).toHaveValue('not-an-email');
    expect(mocks.login).not.toHaveBeenCalled();
  });
});
