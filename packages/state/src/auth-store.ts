import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { StateStorage } from 'zustand/middleware';

/** 인증 store — accessToken은 메모리만, refresh는 cookie (서버 관리). */
interface AuthState {
  authenticatedUserId: string | null;
  status: 'unauthenticated' | 'authenticated' | 'loading';
  setAuth: (userId: string) => void;
  clear: () => void;
  setStatus: (status: AuthState['status']) => void;
}

/**
 * 플랫폼별 storage 어댑터를 받아 인증 store 인스턴스를 만든다.
 * - 웹: `localStorage` (또는 빈 storage — JWT cookie 사용 시)
 * - 모바일: `AsyncStorage`
 */
export const createAuthStore = (storage: StateStorage) =>
  create<AuthState>()(
    persist(
      (set) => ({
        authenticatedUserId: null,
        status: 'unauthenticated',
        setAuth: (userId) => set({ authenticatedUserId: userId, status: 'authenticated' }),
        clear: () => set({ authenticatedUserId: null, status: 'unauthenticated' }),
        setStatus: (status) => set({ status }),
      }),
      {
        name: 'tripmate-auth',
        storage: createJSONStorage(() => storage),
        partialize: (state) => ({ authenticatedUserId: state.authenticatedUserId }),
      },
    ),
  );
