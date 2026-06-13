import { createAuthStore } from '@pinvi/state';
import { asyncStorageAdapter } from './storage';

/**
 * 모바일 인증 store — AsyncStorage 어댑터 주입 (frontend.md §4.4).
 * 웹은 동일 `createAuthStore`에 localStorage(또는 빈 storage)를 주입한다.
 */
export const useAuthStore = createAuthStore(asyncStorageAdapter);
