import AsyncStorage from '@react-native-async-storage/async-storage';
import { AuthUserSchema, type AuthUser } from '@pinvi/schemas';

/**
 * 마지막으로 확인된 AuthUser 프로필 캐시 — 오프라인 부팅 복구용(#202).
 * 비민감 프로필이므로 SecureStore가 아니라 AsyncStorage에 JSON으로 둔다
 * (토큰만 SecureStore, `lib/tokens.ts`). 네트워크 실패로 `me()`가 실패해도
 * 캐시된 프로필로 앱을 띄우고, 토큰은 보존해 이후 재시도로 복구한다.
 */
const CACHED_USER_KEY = 'pinvi.cached_user';

/** 로그인/`me()` 성공 시 최신 프로필을 캐시한다. */
export async function saveCachedUser(user: AuthUser): Promise<void> {
  await AsyncStorage.setItem(CACHED_USER_KEY, JSON.stringify(user));
}

/** 캐시된 프로필을 복원한다. 없거나 형식이 깨졌으면 null. */
export async function getCachedUser(): Promise<AuthUser | null> {
  const raw = await AsyncStorage.getItem(CACHED_USER_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = AuthUserSchema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

/** 세션 정리(확정 401) 시 캐시도 비운다. */
export async function clearCachedUser(): Promise<void> {
  await AsyncStorage.removeItem(CACHED_USER_KEY);
}
