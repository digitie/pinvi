import { describe, expect, it } from 'vitest';
import { ApiError } from '@pinvi/api-client';
import { errorDigest, friendlyErrorText, isLocationConsentRequired } from './errorMessage';

describe('friendlyErrorText', () => {
  it('maps ApiError status codes to guidance', () => {
    expect(friendlyErrorText(new ApiError('unauthorized', 'x', 401))).toContain('세션');
    expect(friendlyErrorText(new ApiError('forbidden', 'x', 403))).toContain('권한');
    expect(friendlyErrorText(new ApiError('not_found', 'x', 404))).toContain('찾을 수 없');
    expect(friendlyErrorText(new ApiError('server', 'x', 500))).toContain('서버');
    expect(friendlyErrorText(new ApiError('server', 'x', 503))).toContain('서버');
  });

  // T-334: 사용자가 스스로 해소할 수 있는 403은 "권한이 없습니다"로 덮으면 안 된다.
  // 동의만 하면 되는 상태가 고칠 수 없는 상태처럼 보이면 사용자는 막다른 길에 선다.
  it('위치 동의 403은 서버가 보낸 안내 문구를 그대로 보여준다', () => {
    const err = new ApiError(
      'LOCATION_CONSENT_REQUIRED',
      '위치정보 이용 동의가 필요합니다. 설정에서 동의한 뒤 다시 시도해 주세요.',
      403,
    );
    expect(friendlyErrorText(err)).toBe(
      '위치정보 이용 동의가 필요합니다. 설정에서 동의한 뒤 다시 시도해 주세요.',
    );
    expect(friendlyErrorText(err)).not.toContain('권한이 없습니다');
  });

  it('코드가 붙지 않은 403은 여전히 일반 문구로 떨어진다', () => {
    expect(friendlyErrorText(new ApiError('forbidden', '서버 원문', 403))).toBe(
      '이 작업을 수행할 권한이 없습니다.',
    );
  });
});

describe('isLocationConsentRequired', () => {
  it('위치 동의 403만 참이다', () => {
    expect(
      isLocationConsentRequired(new ApiError('LOCATION_CONSENT_REQUIRED', 'x', 403)),
    ).toBe(true);
  });

  it.each([
    ['다른 403', new ApiError('forbidden', 'x', 403)],
    // status가 다르면 같은 코드여도 아니다 — 코드만 보고 판정하면 성공 응답 본문에 그 문자열이
    // 들어간 경우까지 동의 흐름을 열게 된다.
    ['같은 코드의 다른 status', new ApiError('LOCATION_CONSENT_REQUIRED', 'x', 400)],
    ['일반 Error', new Error('LOCATION_CONSENT_REQUIRED')],
    ['undefined', undefined],
  ])('%s는 거짓이다', (_name, err) => {
    expect(isLocationConsentRequired(err)).toBe(false);
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
