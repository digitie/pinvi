/** 로그인 복귀는 같은 출처의 앱 경로만 허용한다. */
export function safeLoginReturnTo(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\u0000-\u0020]/.test(value)) return '/trips';
  try {
    const base = 'https://pinvi.example.com';
    const url = new URL(value, base);
    if (url.origin !== base || /^\/(?:admin|login|register)(?:\/|$)/.test(url.pathname)) return '/trips';
    return url.pathname + url.search + url.hash;
  } catch { return '/trips'; }
}
