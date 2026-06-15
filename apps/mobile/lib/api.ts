import * as SecureStore from 'expo-secure-store';
import { ApiClient } from '@pinvi/api-client';
import { mobileConfig } from './config';

const ACCESS_TOKEN_KEY = 'pinvi.access_token';

/**
 * 모바일 ApiClient. 웹은 httpOnly cookie를 쓰지만(ADR-032), 모바일은
 * SecureStore에 보관한 access token을 Authorization 헤더로 붙인다
 * (frontend.md §4.2). endpoint 함수/응답 파싱은 @pinvi/api-client 공용.
 */
export const apiClient = new ApiClient({
  baseUrl: mobileConfig.apiBaseUrl,
  getAuthToken: () => SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
});

export async function setAccessToken(token: string | null): Promise<void> {
  if (token === null) {
    await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
    return;
  }
  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, token);
}
