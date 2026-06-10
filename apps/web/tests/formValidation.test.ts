import { describe, expect, it } from 'vitest';
import { LoginRequestSchema, RegisterRequestSchema } from '@tripmate/schemas';
import { validateForm } from '@/lib/formValidation';

// RegisterRequestSchema는 필수 동의 4종을 superRefine으로 요구하므로,
// 필드 오류를 격리하려고 동의 항목을 모두 유효하게 채운다.
const VALID_CONSENTS = [
  { consent_type: 'tos', version: 'v1.0' },
  { consent_type: 'privacy', version: 'v1.0' },
  { consent_type: 'lbs_tos', version: 'v1.0' },
  { consent_type: 'location_collection', version: 'v1.0' },
];

describe('validateForm — success', () => {
  it('returns parsed data and no errors when valid', () => {
    const r = validateForm(LoginRequestSchema, { email: 'a@b.com', password: 'secret' });
    expect(r.success).toBe(true);
    expect(r.data).toEqual({ email: 'a@b.com', password: 'secret' });
    expect(r.fieldErrors).toEqual({});
    expect(r.firstField).toBeNull();
  });
});

describe('validateForm — field errors', () => {
  it('flags an invalid email with a Korean message', () => {
    const r = validateForm(LoginRequestSchema, { email: 'not-an-email', password: 'x' });
    expect(r.success).toBe(false);
    expect(r.fieldErrors.email).toContain('이메일');
    expect(r.firstField).toBe('email');
  });

  it('reports password min length for signup (8자)', () => {
    const r = validateForm(RegisterRequestSchema, {
      email: 'a@b.com',
      password: 'short',
      nickname: 'kim',
      consents: VALID_CONSENTS,
    });
    expect(r.success).toBe(false);
    expect(r.fieldErrors.password).toContain('8자');
    expect(r.firstField).toBe('password');
  });

  it('reports empty password as 입력 (login min 1, not 8자)', () => {
    const r = validateForm(LoginRequestSchema, { email: 'a@b.com', password: '' });
    expect(r.fieldErrors.password).toContain('입력');
    expect(r.fieldErrors.password).not.toContain('8자');
  });

  it('collects multiple field errors and picks first as firstField', () => {
    const r = validateForm(RegisterRequestSchema, {
      email: 'bad',
      password: '',
      nickname: '',
      consents: VALID_CONSENTS,
    });
    expect(Object.keys(r.fieldErrors).sort()).toEqual(['email', 'nickname', 'password']);
    expect(r.firstField).toBe('email');
  });

  it('flags an over-long nickname as 너무 깁니다', () => {
    const r = validateForm(RegisterRequestSchema, {
      email: 'a@b.com',
      password: 'longenough',
      nickname: 'x'.repeat(81),
      consents: VALID_CONSENTS,
    });
    expect(r.fieldErrors.nickname).toContain('너무');
  });
});
