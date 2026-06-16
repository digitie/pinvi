import * as SecureStore from 'expo-secure-store';

/**
 * 모바일 인증 토큰 보관 — SecureStore(Keychain/Keystore).
 * 웹은 httpOnly cookie(ADR-032)지만 모바일은 cookie를 못 쓰므로 access/refresh
 * 토큰을 본문으로 받아(`/mobile/auth/*`) 여기에 보관한다(expo-implementation-plan §3).
 */
const ACCESS_TOKEN_KEY = 'pinvi.access_token';
const REFRESH_TOKEN_KEY = 'pinvi.refresh_token';

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
}

/** access + refresh 토큰을 한 번에 저장(로그인/회전 시). */
export async function setTokens(access: string, refresh: string): Promise<void> {
  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, access);
  await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refresh);
}

/** access 토큰만 갱신(refresh 회전 없이 access만 재발급한 경우). */
export async function setAccessToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, token);
}

/** 로그아웃 — 두 토큰 모두 폐기. */
export async function clearTokens(): Promise<void> {
  await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
  await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
}
