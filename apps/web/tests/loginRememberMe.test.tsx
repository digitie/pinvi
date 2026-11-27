import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// "로그인 유지" — 체크박스 선택이 이메일 로그인 본문과 소셜 로그인 start 본문에 같이 실린다.
// 세션 수명(365일)은 서버가 정하고, OAuth는 서버가 start 값을 login state에 저장한다(callback 쿼리 X).
const mocks = vi.hoisted(() => ({
  login: vi.fn(),
  startOAuth: vi.fn(),
  oauthProviders: vi.fn(),
  push: vi.fn(),
  assign: vi.fn(),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push, replace: vi.fn(), refresh: vi.fn() }),
}));
vi.mock('@pinvi/api-client', () => ({
  ApiClient: class {},
  ApiError: class extends Error {
    code = '';
  },
  authApi: () => ({
    login: mocks.login,
    startOAuth: mocks.startOAuth,
    oauthProviders: mocks.oauthProviders,
  }),
}));

import LoginPage from '@/app/(auth)/login/page';

const originalLocation = window.location;

beforeEach(() => {
  vi.clearAllMocks();
  mocks.login.mockResolvedValue({ user_id: 'u1' });
  mocks.startOAuth.mockResolvedValue({ authorize_url: 'https://accounts.example.test/auth' });
  mocks.oauthProviders.mockResolvedValue({
    providers: [
      { provider: 'google', enabled: true },
      { provider: 'naver', enabled: false },
      { provider: 'kakao', enabled: false },
    ],
  });
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { search: '', assign: mocks.assign },
  });
});

afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
});

/** provider 목록 응답까지 기다린다(마운트 effect의 state 갱신을 act 안에서 끝낸다). */
async function renderLogin() {
  render(<LoginPage />);
  await screen.findByRole('button', { name: 'Google로 계속하기' });
}

async function fillCredentials() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('이메일'), 'traveler@example.test');
  await user.type(screen.getByLabelText('비밀번호'), 'example-pass-123');
  return user;
}

describe('로그인 유지', () => {
  it('기본은 해제이고 라벨·설명으로 접근 가능한 체크박스다', async () => {
    await renderLogin();
    const checkbox = screen.getByRole('checkbox', { name: '로그인 유지' });
    expect(checkbox).not.toBeChecked();
    expect(checkbox).toHaveAccessibleDescription(/1년 동안 로그인 상태를 유지/);
  });

  it('해제한 채 로그인하면 remember_me=false를 보낸다', async () => {
    await renderLogin();
    const user = await fillCredentials();
    await user.click(screen.getByRole('button', { name: '로그인' }));
    await waitFor(() =>
      expect(mocks.login).toHaveBeenCalledWith({
        email: 'traveler@example.test',
        password: 'example-pass-123',
        remember_me: false,
      }),
    );
  });

  it('체크하고 로그인하면 remember_me=true를 보낸다', async () => {
    await renderLogin();
    const user = await fillCredentials();
    await user.click(screen.getByRole('checkbox', { name: '로그인 유지' }));
    await user.click(screen.getByRole('button', { name: '로그인' }));
    await waitFor(() =>
      expect(mocks.login).toHaveBeenCalledWith({
        email: 'traveler@example.test',
        password: 'example-pass-123',
        remember_me: true,
      }),
    );
  });

  it('소셜 로그인 start도 같은 선택을 싣는다', async () => {
    render(<LoginPage />);
    const user = userEvent.setup();
    const google = await screen.findByRole('button', { name: 'Google로 계속하기' });
    await user.click(screen.getByRole('checkbox', { name: '로그인 유지' }));
    await user.click(google);
    await waitFor(() =>
      expect(mocks.startOAuth).toHaveBeenCalledWith('google', {
        return_to: '/home',
        mode: 'login',
        remember_me: true,
      }),
    );
    expect(mocks.assign).toHaveBeenCalledWith('https://accounts.example.test/auth');
  });

  it('체크하지 않은 소셜 로그인은 remember_me=false다', async () => {
    render(<LoginPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Google로 계속하기' }));
    await waitFor(() =>
      expect(mocks.startOAuth).toHaveBeenCalledWith('google', {
        return_to: '/home',
        mode: 'login',
        remember_me: false,
      }),
    );
  });
});
