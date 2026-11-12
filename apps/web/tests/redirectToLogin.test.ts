import { afterEach, describe, expect, it } from 'vitest';
import { redirectToLogin } from '@/lib/api';

const originalLocation = window.location;

function fakeLocation(path: string, origin = 'https://pinvi.example.com'): { href: string } {
  const url = new URL(path, origin);
  const loc = { origin: url.origin, pathname: url.pathname, search: url.search, hash: url.hash, href: url.href };
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
    expect(loc.href).toBe('https://pinvi.example.com/login?next=' + encodeURIComponent('/shared/trip-1'));
    expect(loc.href).not.toContain('share-secret');
  });

  it('비밀 query는 지우고 일반 화면 경로는 보존한다', () => {
    const loc = fakeLocation('/trips/abc?token=q-secret&day=2#comments');
    redirectToLogin();
    expect(loc.href).toBe('https://pinvi.example.com/login?next=' + encodeURIComponent('/trips/abc?day=2#comments'));
  });

  it('현재 origin의 포트까지 보존해 같은 문서 출처로 이동한다', () => {
    const loc = fakeLocation('/map?layer=road', 'https://preview.example.test:8443');
    redirectToLogin();
    expect(loc.href).toBe('https://preview.example.test:8443/login?next=%2Fmap%3Flayer%3Droad');
  });

});
