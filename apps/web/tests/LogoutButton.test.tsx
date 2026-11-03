import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LogoutButton } from '@/components/app/LogoutButton';
const state = vi.hoisted(() => ({ logout: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => state }));
vi.mock('@pinvi/api-client', async (original) => ({
  ...await original<typeof import('@pinvi/api-client')>(), authApi: () => ({ logout: state.logout }),
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));
beforeEach(() => vi.clearAllMocks());

describe('로그아웃', () => {
  it('서버 세션 종료가 성공한 뒤 로그인 화면으로 이동한다', async () => {
    let finish!: () => void;
    state.logout.mockReturnValueOnce(new Promise<void>((resolve) => { finish = resolve; }));
    render(<LogoutButton />);
    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    expect(state.replace).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '로그아웃 중…' })).toBeDisabled();
    finish();
    await waitFor(() => expect(state.replace).toHaveBeenCalledWith('/login'));
    expect(state.refresh).toHaveBeenCalled();
  });
  it('실패하면 오류를 알리고 다시 시도할 수 있다', async () => {
    state.logout.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(undefined);
    render(<LogoutButton />);
    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    await screen.findByRole('alert');
    expect(state.replace).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(state.replace).toHaveBeenCalledWith('/login'));
  });
});
