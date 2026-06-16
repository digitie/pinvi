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
import { ApiError, type MobileAuthResult } from '@pinvi/api-client';
import { api, endSession, persistSession, setUnauthorizedHandler } from './api';
import { getAccessToken } from './tokens';
import { clearCachedUser, getCachedUser, saveCachedUser } from './user-cache';
import { useAuthStore } from './stores';

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';
/** 로그인 자격 — 공용 `LoginRequestSchema`(api-client 바인딩)에서 유도. */
type LoginRequest = Parameters<typeof api.mobileAuth.login>[0];

interface AuthContextValue {
  user: AuthUser | null;
  status: AuthStatus;
  /** 네트워크 실패로 캐시 프로필로 부팅했을 때 true(저장된 정보로 표시 중). */
  offline: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  /** verify-email 등으로 받은 토큰 응답으로 세션을 확정한다. */
  adoptSession: (result: MobileAuthResult) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * 확정 인증 실패 판별 — 401 ApiError만 true.
 * me()가 401을 던질 때 api.ts `refreshingFetcher`는 이미 refresh 1회를 시도해
 * 실패한 상태이므로, 여기 도달한 401은 확정 인증 실패다. 네트워크/일시 오류는
 * 비-ApiError(RN `TypeError`) 또는 status >= 500이며 세션을 지우면 안 된다(#202).
 */
function isAuthFailure(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

/**
 * 모바일 인증 컨텍스트 — SecureStore 토큰 + `/mobile/auth/*` + `createAuthStore`.
 * 부팅 시 저장된 access 토큰으로 `/auth/me`를 시도한다(refresh 1회는 api.ts
 * `refreshingFetcher`가 투명 처리). 확정 401만 세션 정리, 네트워크/일시 오류는
 * 토큰을 보존하고 캐시 프로필로 부팅한다(#202).
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [offline, setOffline] = useState(false);
  const setStoreAuth = useAuthStore((s) => s.setAuth);
  const clearStoreAuth = useAuthStore((s) => s.clear);
  // setUser는 effect 의존성에서 제외하되 stale-closure를 피하려고 ref로도 잡는다.
  const setUserRef = useRef(setUser);
  setUserRef.current = setUser;

  const applyUser = useCallback(
    (next: AuthUser) => {
      setUser(next);
      setStatus('authenticated');
      setOffline(false);
      setStoreAuth(next.user_id);
      // 오프라인 부팅 복구용으로 최신 프로필을 캐시한다(#202).
      void saveCachedUser(next);
    },
    [setStoreAuth],
  );

  const clearSession = useCallback(() => {
    setUserRef.current(null);
    setStatus('unauthenticated');
    setOffline(false);
    clearStoreAuth();
    // 확정 인증 실패 경로만 여기 도달 → 캐시도 비운다.
    void clearCachedUser();
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
        // me()가 401을 만나면 api.ts refreshingFetcher가 refresh 1회를 투명하게
        // 시도한다. 여기 도달한 401(ApiError)은 refresh까지 실패한 확정 인증 실패.
        const me = await api.auth.me();
        if (active) applyUser(me);
      } catch (err) {
        if (!active) {
          return;
        }
        if (isAuthFailure(err)) {
          // 확정 인증 실패 → 토큰/캐시 정리.
          clearSession();
          return;
        }
        // 네트워크/일시 오류 → 토큰을 지우지 않는다. 캐시 프로필로 부팅.
        const cached = await getCachedUser();
        if (!active) {
          return;
        }
        if (cached) {
          applyUser(cached);
          setOffline(true);
        } else {
          // 캐시가 없어 앱을 띄울 순 없지만, 토큰은 보존해 이후 재시도로 복구한다.
          setStatus('unauthenticated');
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
    () => ({ user, status, offline, login, adoptSession, logout, refreshUser }),
    [user, status, offline, login, adoptSession, logout, refreshUser],
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
