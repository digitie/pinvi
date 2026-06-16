import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import type { AuthUser } from '@pinvi/schemas';
import type { MobileAuthResult } from '@pinvi/api-client';
import { api, endSession, persistSession, refreshSession, setUnauthorizedHandler } from './api';
import { getAccessToken } from './tokens';
import { useAuthStore } from './stores';

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';
/** 로그인 자격 — 공용 `LoginRequestSchema`(api-client 바인딩)에서 유도. */
type LoginRequest = Parameters<typeof api.mobileAuth.login>[0];

interface AuthContextValue {
  user: AuthUser | null;
  status: AuthStatus;
  login: (credentials: LoginRequest) => Promise<void>;
  /** verify-email 등으로 받은 토큰 응답으로 세션을 확정한다. */
  adoptSession: (result: MobileAuthResult) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * 모바일 인증 컨텍스트 — SecureStore 토큰 + `/mobile/auth/*` + `createAuthStore`.
 * 부팅 시 저장된 access 토큰으로 `/auth/me`를 시도하고, 401이면 refresh로 1회 복구한다.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>('loading');
  const setStoreAuth = useAuthStore((s) => s.setAuth);
  const clearStoreAuth = useAuthStore((s) => s.clear);
  // setUser는 effect 의존성에서 제외하되 stale-closure를 피하려고 ref로도 잡는다.
  const setUserRef = useRef(setUser);
  setUserRef.current = setUser;

  const applyUser = useCallback(
    (next: AuthUser) => {
      setUser(next);
      setStatus('authenticated');
      setStoreAuth(next.user_id);
    },
    [setStoreAuth],
  );

  const clearSession = useCallback(() => {
    setUserRef.current(null);
    setStatus('unauthenticated');
    clearStoreAuth();
  }, [clearStoreAuth]);

  // 401(refresh까지 실패) 시 전역 핸들러 → 세션 정리.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearSession();
    });
    return () => setUnauthorizedHandler(null);
  }, [clearSession]);

  // 부팅 복구.
  useEffect(() => {
    let active = true;
    (async () => {
      const token = await getAccessToken();
      if (!token) {
        if (active) setStatus('unauthenticated');
        return;
      }
      try {
        const me = await api.auth.me();
        if (active) applyUser(me);
      } catch {
        // me 실패(만료) → refresh 1회 시도.
        const ok = await refreshSession();
        if (!ok) {
          if (active) clearSession();
          return;
        }
        try {
          const me = await api.auth.me();
          if (active) applyUser(me);
        } catch {
          if (active) clearSession();
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [applyUser, clearSession]);

  const login = useCallback(
    async (credentials: LoginRequest) => {
      const result = await api.mobileAuth.login(credentials);
      await persistSession(result);
      applyUser(result.user);
    },
    [applyUser],
  );

  const adoptSession = useCallback(
    async (result: MobileAuthResult) => {
      await persistSession(result);
      applyUser(result.user);
    },
    [applyUser],
  );

  const logout = useCallback(async () => {
    await endSession();
    clearSession();
  }, [clearSession]);

  const refreshUser = useCallback(async () => {
    try {
      const me = await api.auth.me();
      applyUser(me);
    } catch {
      clearSession();
    }
  }, [applyUser, clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, login, adoptSession, logout, refreshUser }),
    [user, status, login, adoptSession, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within <AuthProvider>');
  }
  return ctx;
}
