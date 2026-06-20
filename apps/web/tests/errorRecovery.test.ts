import { describe, expect, it } from 'vitest';
import {
  claimErrorReloadAttempt,
  clearErrorReloadAttempt,
  errorRecoveryMessage,
  errorReloadStorageKey,
  isLikelyRecoverableNextRuntimeError,
} from '@/lib/error-recovery';

describe('error recovery helpers (T-278)', () => {
  it('Next chunk/RSC 계열 런타임 오류를 자동 reload 후보로 분류한다', () => {
    expect(
      isLikelyRecoverableNextRuntimeError(new Error('ChunkLoadError: Loading chunk 351 failed')),
    ).toBe(true);
    expect(
      isLikelyRecoverableNextRuntimeError(new Error('Importing a module script failed.')),
    ).toBe(true);
    expect(isLikelyRecoverableNextRuntimeError(new Error('Failed to fetch RSC payload'))).toBe(true);
  });

  it('일반 화면 코드 오류는 자동 reload 후보로 보지 않는다', () => {
    expect(
      isLikelyRecoverableNextRuntimeError(new Error('Cannot read properties of undefined')),
    ).toBe(false);
  });

  it('digest와 pathname을 복구 UI에 필요한 형태로 보존한다', () => {
    const error = Object.assign(new Error('boom'), { digest: 'abc123' });
    expect(errorRecoveryMessage(error)).toContain('abc123');
    expect(errorReloadStorageKey('/admin/ops')).toBe('pinvi.web.error-reload:/admin/ops');
  });

  it('동일 pathname의 자동 reload 시도는 storage key로 한 번만 허용한다', () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
      removeItem: (key: string) => {
        values.delete(key);
      },
    };

    expect(claimErrorReloadAttempt('/admin/ops', storage)).toBe(true);
    expect(claimErrorReloadAttempt('/admin/ops', storage)).toBe(false);
    clearErrorReloadAttempt('/admin/ops', storage);
    expect(claimErrorReloadAttempt('/admin/ops', storage)).toBe(true);
  });

  it('browser storage가 막혀도 복구 helper가 error boundary를 다시 깨지 않는다', () => {
    const storage = {
      getItem: () => {
        throw new Error('SecurityError');
      },
      setItem: () => {
        throw new Error('SecurityError');
      },
      removeItem: () => {
        throw new Error('SecurityError');
      },
    };

    expect(claimErrorReloadAttempt('/admin/ops', storage)).toBe(false);
    expect(() => clearErrorReloadAttempt('/admin/ops', storage)).not.toThrow();
  });
});
