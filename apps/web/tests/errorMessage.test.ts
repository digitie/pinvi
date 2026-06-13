import { describe, expect, it } from 'vitest';
import { ApiError } from '@pinvi/api-client';
import { errorDigest, friendlyErrorText } from '@/lib/errorMessage';

describe('friendlyErrorText', () => {
  it('maps ApiError status codes to guidance', () => {
    expect(friendlyErrorText(new ApiError('unauthorized', 'x', 401))).toContain('세션');
    expect(friendlyErrorText(new ApiError('forbidden', 'x', 403))).toContain('권한');
    expect(friendlyErrorText(new ApiError('not_found', 'x', 404))).toContain('찾을 수 없');
    expect(friendlyErrorText(new ApiError('server', 'x', 500))).toContain('서버');
    expect(friendlyErrorText(new ApiError('server', 'x', 503))).toContain('서버');
  });

  it('falls back to ApiError message for other 4xx', () => {
    expect(friendlyErrorText(new ApiError('bad', '잘못된 요청', 400))).toBe('잘못된 요청');
  });

  it('uses message for a plain Error', () => {
    expect(friendlyErrorText(new Error('boom'))).toBe('boom');
  });

  it('returns a default for empty / unknown errors', () => {
    expect(friendlyErrorText(new Error(''))).toBe('예기치 못한 오류가 발생했습니다.');
    expect(friendlyErrorText('nope')).toBe('예기치 못한 오류가 발생했습니다.');
    expect(friendlyErrorText(undefined)).toBe('예기치 못한 오류가 발생했습니다.');
  });
});

describe('errorDigest', () => {
  it('extracts a string digest', () => {
    const err = Object.assign(new Error('x'), { digest: 'abc123' });
    expect(errorDigest(err)).toBe('abc123');
  });

  it('returns null when digest is absent or non-string', () => {
    expect(errorDigest(new Error('x'))).toBeNull();
    expect(errorDigest(Object.assign(new Error('x'), { digest: 42 }))).toBeNull();
    expect(errorDigest(null)).toBeNull();
  });
});
