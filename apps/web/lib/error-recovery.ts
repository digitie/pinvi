// Next App Router 런타임 오류 복구 헬퍼 (kor-travel-geo T-278 이식).
// chunk/RSC/network 계열 오류를 자동 reload 후보로 분류하고, 같은 pathname당 1회만
// hard reload하도록 sessionStorage 키를 만든다.

const ERROR_RECOVERY_RELOAD_PREFIX = 'pinvi.web.error-reload';

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

export function errorReloadStorageKey(pathname: string): string {
  return `${ERROR_RECOVERY_RELOAD_PREFIX}:${pathname}`;
}
