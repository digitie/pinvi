import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RouteError } from '@/components/feedback/RouteError';
import {
  errorReloadStorageKey,
  installPageUnloadTracking,
  isPageUnloading,
  PAGE_UNLOAD_RESET_MS,
  shouldAutoReloadForError,
} from '@/lib/error-recovery';

// Firefox가 문서 이동 중 옛 문서의 fetch를 끊을 때 던지는 오류.
const firefoxAbort = () => new TypeError('NetworkError when attempting to fetch resource.');

let reload: ReturnType<typeof vi.fn>;
let restoreLocation: () => void;
let uninstall: () => void = () => {};

function stubLocationReload() {
  const original = window.location;
  reload = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...original, pathname: '/trips', reload },
  });
  restoreLocation = () => {
    Object.defineProperty(window, 'location', { configurable: true, value: original });
  };
}

describe('error recovery during page unload', () => {
  beforeEach(() => {
    // 모듈 로드 시 자동 설치된 리스너를 떼고 깨끗한 상태로 다시 건다.
    installPageUnloadTracking()();
    uninstall = installPageUnloadTracking();
    window.sessionStorage.clear();
    stubLocationReload();
  });

  afterEach(() => {
    uninstall();
    restoreLocation();
    vi.useRealTimers();
  });

  it('이탈 중이 아니면 Firefox NetworkError는 기존대로 1회 자동 reload한다', () => {
    expect(isPageUnloading()).toBe(false);
    expect(shouldAutoReloadForError(firefoxAbort())).toBe(true);

    render(<RouteError error={firefoxAbort()} reset={() => {}} />);

    expect(reload).toHaveBeenCalledTimes(1);
    expect(window.sessionStorage.getItem(errorReloadStorageKey('/trips'))).toBe('1');
  });

  it('beforeunload 뒤(이동 시작) 끊긴 fetch 오류는 reload하지 않고 claim도 소모하지 않는다', () => {
    window.dispatchEvent(new Event('beforeunload'));
    expect(isPageUnloading()).toBe(true);
    expect(shouldAutoReloadForError(firefoxAbort())).toBe(false);

    render(<RouteError error={firefoxAbort()} reset={() => {}} />);

    expect(reload).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem(errorReloadStorageKey('/trips'))).toBeNull();
  });

  it('pagehide 뒤 오류도 reload하지 않고, bfcache 복귀(pageshow)하면 다시 복구한다', () => {
    window.dispatchEvent(new Event('pagehide'));
    render(<RouteError error={firefoxAbort()} reset={() => {}} />);
    expect(reload).not.toHaveBeenCalled();

    window.dispatchEvent(new Event('pageshow'));
    expect(isPageUnloading()).toBe(false);
    expect(shouldAutoReloadForError(firefoxAbort())).toBe(true);
  });

  it('beforeunload 뒤 이동이 취소되면 일정 시간 후 자동 복구가 되살아난다', () => {
    vi.useFakeTimers();
    window.dispatchEvent(new Event('beforeunload'));
    expect(isPageUnloading()).toBe(true);
    act(() => {
      vi.advanceTimersByTime(PAGE_UNLOAD_RESET_MS);
    });
    expect(isPageUnloading()).toBe(false);
    expect(shouldAutoReloadForError(firefoxAbort())).toBe(true);
  });

  it('복구 후보가 아닌 오류는 이탈 여부와 무관하게 reload하지 않는다', () => {
    expect(shouldAutoReloadForError(new Error('Cannot read properties of undefined'))).toBe(false);
  });
});
