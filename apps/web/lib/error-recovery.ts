// Next App Router 런타임 오류 복구 헬퍼 (kor-travel-geo T-278 이식).
// chunk/RSC/network 계열 오류를 자동 reload 후보로 분류하고, 같은 pathname당 1회만
// hard reload하도록 sessionStorage 키를 만든다.

const ERROR_RECOVERY_RELOAD_PREFIX = 'pinvi.web.error-reload';
type ErrorReloadStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

const RECOVERABLE_PATTERNS = [
  'chunkloaderror',
  'loading chunk',
  'loading css chunk',
  'failed to fetch dynamically imported module',
  'importing a module script failed',
  'error loading dynamically imported module',
  '_rsc',
  'server component',
  'rsc payload',
  'networkerror when attempting to fetch resource',
  'load failed',
];

export function errorRecoveryMessage(error: Error & { digest?: string }): string {
  const parts = [error.name, error.message, error.digest, error.stack].filter(Boolean);
  return parts.join('\n');
}

export function isLikelyRecoverableNextRuntimeError(error: Error & { digest?: string }): boolean {
  const message = errorRecoveryMessage(error).toLowerCase();
  return RECOVERABLE_PATTERNS.some((pattern) => message.includes(pattern));
}

// ── 페이지 이탈(unload) 추적 ────────────────────────────────────────────────
// 사용자가 문서 이동(hard navigation)을 시작하면 브라우저는 옛 문서의 진행 중 fetch를
// 끊는다. Firefox는 이를 `NetworkError when attempting to fetch resource`로 던지는데,
// 이 문구는 위 RECOVERABLE_PATTERNS에 있어서 error boundary가 `location.reload()`를
// 부르고, reload가 사용자의 이동을 취소해 옛 화면이 다시 뜬다. 이탈 중에 난 오류는
// 런타임 불일치가 아니라 이동의 부수효과이므로 자동 reload 대상에서 뺀다.
//
// - `beforeunload`: 이동 시작 직후(옛 fetch가 끊기기 전) 표시한다. 이동이 취소될 수
//   있으므로(다운로드 응답, 204 등) 일정 시간 뒤 스스로 해제한다.
// - `pagehide`: 문서가 실제로 내려갈 때 표시한다(해제 타이머 없음).
// - `pageshow`: bfcache에서 되살아나면 해제한다.
export const PAGE_UNLOAD_RESET_MS = 10_000;

let pageUnloading = false;
let unloadResetTimer: ReturnType<typeof setTimeout> | null = null;
let unloadTrackingInstalled = false;

function clearUnloadResetTimer(): void {
  if (unloadResetTimer !== null) {
    clearTimeout(unloadResetTimer);
    unloadResetTimer = null;
  }
}

function onBeforeUnload(): void {
  pageUnloading = true;
  clearUnloadResetTimer();
  unloadResetTimer = setTimeout(() => {
    unloadResetTimer = null;
    pageUnloading = false;
  }, PAGE_UNLOAD_RESET_MS);
}

function onPageHide(): void {
  clearUnloadResetTimer();
  pageUnloading = true;
}

function onPageShow(): void {
  clearUnloadResetTimer();
  pageUnloading = false;
}

/** 현재 문서가 이탈(unload/navigation) 중인지. */
export function isPageUnloading(): boolean {
  return pageUnloading;
}

/**
 * window에 이탈 추적 리스너를 1회 건다. 모듈 로드 시 브라우저에서 자동 호출되며,
 * 반환 함수는 리스너를 떼고 상태를 초기화한다(테스트용).
 */
export function installPageUnloadTracking(
  target: Pick<Window, 'addEventListener' | 'removeEventListener'> | null = typeof window ===
  'undefined'
    ? null
    : window,
): () => void {
  if (!target || unloadTrackingInstalled) return () => {};
  unloadTrackingInstalled = true;
  target.addEventListener('beforeunload', onBeforeUnload);
  target.addEventListener('pagehide', onPageHide);
  target.addEventListener('pageshow', onPageShow);
  return () => {
    target.removeEventListener('beforeunload', onBeforeUnload);
    target.removeEventListener('pagehide', onPageHide);
    target.removeEventListener('pageshow', onPageShow);
    clearUnloadResetTimer();
    pageUnloading = false;
    unloadTrackingInstalled = false;
  };
}

installPageUnloadTracking();

/**
 * error boundary가 자동 hard reload를 시도해야 하는지. 복구 후보 오류라도 페이지 이탈
 * 중이면(fetch abort가 원인) reload하지 않는다 — reload가 사용자의 이동을 취소하기 때문.
 */
export function shouldAutoReloadForError(error: Error & { digest?: string }): boolean {
  return isLikelyRecoverableNextRuntimeError(error) && !isPageUnloading();
}

export function errorReloadStorageKey(pathname: string): string {
  return `${ERROR_RECOVERY_RELOAD_PREFIX}:${pathname}`;
}

function currentSessionStorage(): ErrorReloadStorage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function claimErrorReloadAttempt(
  pathname: string,
  storage: ErrorReloadStorage | null = currentSessionStorage(),
): boolean {
  if (!storage) return false;
  const key = errorReloadStorageKey(pathname);
  try {
    if (storage.getItem(key) === '1') return false;
    storage.setItem(key, '1');
    return true;
  } catch {
    return false;
  }
}

export function clearErrorReloadAttempt(
  pathname: string,
  storage: ErrorReloadStorage | null = currentSessionStorage(),
): void {
  if (!storage) return;
  try {
    storage.removeItem(errorReloadStorageKey(pathname));
  } catch {
    // Recovery UI must never fail because browser storage is unavailable.
  }
}
