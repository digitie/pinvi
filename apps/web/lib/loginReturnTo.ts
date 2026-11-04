/** OAuth 로그인 상태가 복귀 경로를 저장하는 컬럼 길이(`return_to_path` varchar(255)). */
export const LOGIN_RETURN_TO_MAX_LENGTH = 255;

/**
 * 복귀 경로에 실으면 안 되는 query 이름(소문자, 정확히 일치) — API `SENSITIVE_QUERY_KEYS`와 같은 취지.
 * 복귀 경로는 `/login?next=`·OAuth `return_to_path`·접근 로그·Referer로 퍼진다(#671).
 */
const SECRET_QUERY_KEYS = new Set([
  'access_token',
  'api_key',
  'apikey',
  'code',
  'id_token',
  'key',
  'password',
  'refresh_token',
  'secret',
  'share_token',
  'sig',
  'signature',
  'state',
  'token',
  'x-amz-credential',
  'x-amz-security-token',
  'x-amz-signature',
]);

/** 공유 링크 화면 `/shared/{tripId}/{token}` — 두 번째 segment가 공유 토큰(비밀)이다. */
const SHARED_PATH_RE = /^\/shared\/([^/]+)(?:\/|$)/;
/** 서명된 저장소 토큰이 path에 실리는 경로 — 복귀 대상이 될 화면이 아니다. */
const STORAGE_PATH_RE = /^\/(?:api\/v1\/)?storage(?:\/|$)/;

/**
 * 공유 토큰을 담지 않는 공유 화면 복귀 경로 `/shared/{tripId}`.
 * 로그인 뒤 그 화면이 같은 탭의 sessionStorage에서 토큰을 되찾는다(`sharedTokenStash`).
 */
export function sharedReturnPath(tripId: string): string {
  return `/shared/${encodeURIComponent(tripId)}`;
}

/** 공유 화면의 로그인 링크 — 토큰은 싣지 않는다(#671). */
export function sharedLoginHref(tripId: string): string {
  return `/login?next=${encodeURIComponent(sharedReturnPath(tripId))}`;
}

/** 로그인 복귀는 같은 출처의 앱 경로만 허용하고, 공유·저장소 토큰과 비밀 query는 지운다. */
export function safeLoginReturnTo(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\u0000- ]/.test(value)) return '/trips';
  try {
    const base = 'https://pinvi.example.com';
    const url = new URL(value, base);
    if (url.origin !== base || url.pathname.includes('//') || /^\/(?:admin|login|register)(?:\/|$)/.test(url.pathname)) return '/trips';
    if (STORAGE_PATH_RE.test(url.pathname)) return '/trips';
    const shared = SHARED_PATH_RE.exec(url.pathname);
    // 공유 화면은 tripId까지만 — 토큰 segment·query·hash는 버린다.
    if (shared) return `/shared/${shared[1]}`.length <= LOGIN_RETURN_TO_MAX_LENGTH ? `/shared/${shared[1]}` : '/trips';
    // 비밀 query가 있을 때만 다시 쓴다(다시 쓰면 나머지 query의 인코딩이 바뀐다).
    const secretNames = [...url.searchParams.keys()].filter((name) => SECRET_QUERY_KEYS.has(name.toLowerCase()));
    for (const name of secretNames) url.searchParams.delete(name);
    const full = url.pathname + url.search + url.hash;
    if (full.length <= LOGIN_RETURN_TO_MAX_LENGTH) return full;
    // 긴 검색어·hash는 버리고 화면 경로만 살린다 — 서버 계약(255자)을 넘기면 OAuth 시작이 거부된다.
    return url.pathname.length <= LOGIN_RETURN_TO_MAX_LENGTH ? url.pathname : '/trips';
  } catch { return '/trips'; }
}
