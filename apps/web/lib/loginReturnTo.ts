/** OAuth 로그인 상태가 복귀 경로를 저장하는 컬럼 길이(`return_to_path` varchar(255)). */
export const LOGIN_RETURN_TO_MAX_LENGTH = 255;

/** 로그인 복귀는 같은 출처의 앱 경로만 허용한다. */
export function safeLoginReturnTo(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\u0000- ]/.test(value)) return '/trips';
  try {
    const base = 'https://pinvi.example.com';
    const url = new URL(value, base);
    if (url.origin !== base || url.pathname.includes('//') || /^\/(?:admin|login|register)(?:\/|$)/.test(url.pathname)) return '/trips';
    const full = url.pathname + url.search + url.hash;
    if (full.length <= LOGIN_RETURN_TO_MAX_LENGTH) return full;
    // 긴 검색어·hash는 버리고 화면 경로만 살린다 — 서버 계약(255자)을 넘기면 OAuth 시작이 거부된다.
    return url.pathname.length <= LOGIN_RETURN_TO_MAX_LENGTH ? url.pathname : '/trips';
  } catch { return '/trips'; }
}
