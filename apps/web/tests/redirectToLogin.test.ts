import { afterEach, describe, expect, it } from 'vitest';
import { redirectToLogin } from '@/lib/api';

const originalLocation = window.location;

function fakeLocation(path: string): { href: string } {
  const url = new URL(path, 'https://pinvi.example.com');
  const loc = { pathname: url.pathname, search: url.search, hash: url.hash, href: url.href };
  Object.defineProperty(window, 'location', { configurable: true, value: loc });
  return loc;
}

afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
});

// #671 — 세션 만료 시 로그인 이동 URL(`/login?next=`)에 공유·저장소 토큰이 실리면 안 된다.
describe('redirectToLogin', () => {
  it('공유 화면에서는 토큰을 뺀 /shared/{tripId}로 복귀한다', () => {
    const loc = fakeLocation('/shared/trip-1/share-secret?x=1#c');
    redirectToLogin();
    expect(loc.href).toBe('/login?next=' + encodeURIComponent('/shared/trip-1'));
    expect(loc.href).not.toContain('share-secret');
  });

  it('비밀 query는 지우고 일반 화면 경로는 보존한다', () => {
    const loc = fakeLocation('/trips/abc?token=q-secret&day=2#comments');
    redirectToLogin();
    expect(loc.href).toBe('/login?next=' + encodeURIComponent('/trips/abc?day=2#comments'));
  });
});
