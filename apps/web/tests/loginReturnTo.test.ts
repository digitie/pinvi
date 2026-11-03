import { describe, expect, it } from 'vitest';
import { OAuthStartRequestSchema } from '@pinvi/schemas';
import { safeLoginReturnTo } from '@/lib/loginReturnTo';

describe('로그인 복귀 경로', () => {
  it('일정과 공유 페이지의 경로·쿼리·hash를 보존한다', () => {
    expect(safeLoginReturnTo('/trips/abc?day=2#comments')).toBe('/trips/abc?day=2#comments');
    expect(safeLoginReturnTo('/shared/abc/token')).toBe('/shared/abc/token');
  });
  it.each(['/trips/abc?day=2#comments', '/trips?q=%EB%B6%80%EC%82%B0', '/map?suggest=126.978,37.566', '/trips?tags[]=a;b&sort=-updated_at'])(
    'OAuth 발급 계약도 복귀 경로 %s를 허용한다', (path) => {
      expect(OAuthStartRequestSchema.parse({ return_to: safeLoginReturnTo(path) }).return_to).toBe(path);
    },
  );
  it.each([null, '', 'https://evil.example', '//evil.example', '/\\evil.example', '/\nevil.example', '/login', '/admin/features', '/register', '/a/..//attacker.example/landing'])(
    '외부 또는 인증 반복 경로 %s를 차단한다', (path) => {
      expect(safeLoginReturnTo(path)).toBe('/trips');
    },
  );
});
