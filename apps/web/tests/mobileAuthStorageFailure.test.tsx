import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AuthProvider, useAuth } from '../../mobile/lib/auth';

const api = vi.hoisted(() => ({
  me: vi.fn(),
  endSession: vi.fn(),
  persistSession: vi.fn(),
  getAccessToken: vi.fn().mockRejectedValue(new Error('SecureStore unavailable')),
  setStoreAuth: vi.fn(),
  clearStoreAuth: vi.fn(),
}));
vi.mock('../../mobile/lib/api', () => ({
  api: { auth: { me: api.me } },
  endSession: api.endSession,
  persistSession: api.persistSession,
  setUnauthorizedHandler: vi.fn(),
}));
vi.mock('../../mobile/lib/tokens', () => ({ getAccessToken: api.getAccessToken }));
vi.mock('../../mobile/lib/user-cache', () => ({
  getCachedUser: vi.fn().mockResolvedValue(null),
  clearCachedUser: vi.fn(),
  saveCachedUser: vi.fn(),
}));
vi.mock('../../mobile/lib/stores', () => ({
  useAuthStore: (selector: (state: object) => unknown) =>
    selector({ setAuth: api.setStoreAuth, clear: api.clearStoreAuth }),
}));
function Status() {
  return <p>{useAuth().status}</p>;
}

describe('mobile auth boot storage failure', () => {
  it('저장소가 실패해도 부팅 상태를 끝내고 기존 세션은 폐기하지 않는다', async () => {
    render(
      <AuthProvider>
        <Status />
      </AuthProvider>,
    );
    expect(await screen.findByText('unauthenticated')).toBeInTheDocument();
    expect(api.me).not.toHaveBeenCalled();
    expect(api.endSession).not.toHaveBeenCalled();
    expect(api.clearStoreAuth).not.toHaveBeenCalled();
  });
});
