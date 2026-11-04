import { describe, expect, it } from 'vitest';
import { OAuthStartRequestSchema } from '@pinvi/schemas';
import { safeLoginReturnTo, sharedLoginHref } from '@/lib/loginReturnTo';

describe('로그인 복귀 경로', () => {
  it('일정 경로·쿼리·hash를 보존한다', () => {
    expect(safeLoginReturnTo('/trips/abc?day=2#comments')).toBe('/trips/abc?day=2#comments');
  });
  // #671 — 복귀 경로는 /login?next=·OAuth return_to_path·접근 로그·Referer로 퍼진다. 토큰을 싣지 않는다.
  it.each([
    ['/shared/abc/share-secret', '/shared/abc'],
    ['/shared/abc/share-secret?x=1#c', '/shared/abc'],
    ['/shared/abc/share-secret/more', '/shared/abc'],
    ['/shared/abc', '/shared/abc'],
  ])('공유 토큰 segment %s 는 tripId까지만 남긴다', (path, expected) => {
    expect(safeLoginReturnTo(path)).toBe(expected);
  });
  it.each(['/storage/downloads/dl-secret', '/api/v1/storage/uploads/up-secret?x=1'])(
    '저장소 토큰 경로 %s 는 복귀 대상이 아니다', (path) => {
      expect(safeLoginReturnTo(path)).toBe('/trips');
    },
  );
  it('비밀 query 이름은 지우고 나머지는 그대로 둔다', () => {
    expect(safeLoginReturnTo('/trips/abc?token=s3cret&day=2#c')).toBe('/trips/abc?day=2#c');
    expect(safeLoginReturnTo('/map?Share_Token=s3cret')).toBe('/map');
    expect(safeLoginReturnTo('/trips?tags[]=a;b&sort=-updated_at')).toBe('/trips?tags[]=a;b&sort=-updated_at');
  });
  it('공유 화면 로그인 링크는 토큰 없이 tripId만 싣는다', () => {
    const href = sharedLoginHref('11111111-1111-4111-8111-111111111111');
    expect(href).toBe('/login?next=%2Fshared%2F11111111-1111-4111-8111-111111111111');
    expect(OAuthStartRequestSchema.parse({ return_to: safeLoginReturnTo(new URL(href, 'https://x').searchParams.get('next')) }).return_to)
      .toBe('/shared/11111111-1111-4111-8111-111111111111');
  });
  it.each(['/trips/abc?day=2#comments', '/trips?q=%EB%B6%80%EC%82%B0', '/map?suggest=126.978,37.566', '/trips?tags[]=a;b&sort=-updated_at'])(
    'OAuth 발급 계약도 복귀 경로 %s를 허용한다', (path) => {
      expect(OAuthStartRequestSchema.parse({ return_to: safeLoginReturnTo(path) }).return_to).toBe(path);
    },
  );
  it('서버 저장 한도(255자)를 넘는 쿼리·hash는 버리고 경로만 남긴다', () => {
    const long = `/trips/abc?q=${'가'.repeat(300)}#c`;
    const result = safeLoginReturnTo(long);
    expect(result).toBe('/trips/abc');
    expect(OAuthStartRequestSchema.parse({ return_to: result }).return_to).toBe('/trips/abc');
    expect(safeLoginReturnTo(`/${'a'.repeat(300)}`)).toBe('/trips');
    expect(() => OAuthStartRequestSchema.parse({ return_to: `/${'a'.repeat(255)}` })).toThrow();
  });
  it.each([null, '', 'https://evil.example', '//evil.example', '/\\evil.example', '/\nevil.example', '/login', '/admin/features', '/register', '/a/..//attacker.example/landing', '/trips//x'])(
    '외부 또는 인증 반복 경로 %s를 차단한다', (path) => {
      expect(safeLoginReturnTo(path)).toBe('/trips');
    },
  );
});
