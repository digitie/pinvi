'use client';

import { useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { RegisterRequestSchema } from '@pinvi/schemas';
import type { ConsentType } from '@pinvi/schemas';
import { ApiClient, ApiError, authApi } from '@pinvi/api-client';
import { FormField } from '@/components/forms/FormField';
import { validateForm, type FieldErrors } from '@/lib/formValidation';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const CONSENT_VERSION = 'v1.0';

const REQUIRED_CONSENTS: { type: ConsentType; label: string; summary: string }[] = [
  {
    type: 'tos',
    label: '이용약관',
    summary: '서비스 이용 조건과 계정 운영 기준',
  },
  {
    type: 'privacy',
    label: '개인정보 처리방침',
    summary: '계정, 여행계획, 첨부파일 처리 기준',
  },
  {
    type: 'lbs_tos',
    label: '위치기반서비스 이용약관',
    summary: '여행 지도와 위치 기반 기능 이용 조건',
  },
  {
    type: 'location_collection',
    label: '개인위치정보 수집·이용',
    summary: '현재 위치 기반 검색과 여행 일정 표시',
  },
];

const OPTIONAL_CONSENTS: { type: ConsentType; label: string; summary: string }[] = [
  {
    type: 'marketing',
    label: '마케팅·이벤트 이메일 수신',
    summary: '업데이트, 이벤트, 베타 안내 수신',
  },
];

const INITIAL_CONSENTS: Record<ConsentType, boolean> = {
  tos: false,
  privacy: false,
  lbs_tos: false,
  location_collection: false,
  demographic_use: false,
  marketing: false,
};

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [nickname, setNickname] = useState('');
  const [consents, setConsents] = useState<Record<ConsentType, boolean>>(INITIAL_CONSENTS);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const nicknameRef = useRef<HTMLInputElement>(null);

  const allRequiredConsents = REQUIRED_CONSENTS.every((item) => consents[item.type]);

  const focusField = (field: string | null) => {
    if (field === 'email') emailRef.current?.focus();
    else if (field === 'password') passwordRef.current?.focus();
    else if (field === 'nickname') nicknameRef.current?.focus();
  };

  const toggleConsent = (type: ConsentType, checked: boolean) => {
    setConsents((current) => ({ ...current, [type]: checked }));
  };

  const setAllRequired = (checked: boolean) => {
    setConsents((current) => {
      const next = { ...current };
      for (const item of REQUIRED_CONSENTS) {
        next[item.type] = checked;
      }
      return next;
    });
  };

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    if (!allRequiredConsents) {
      setError('필수 약관에 모두 동의해 주세요.');
      return;
    }

    const consentItems = [...REQUIRED_CONSENTS, ...OPTIONAL_CONSENTS]
      .filter((item) => consents[item.type])
      .map((item) => ({ consent_type: item.type, version: CONSENT_VERSION }));

    const result = validateForm(RegisterRequestSchema, {
      email,
      password,
      nickname,
      consents: consentItems,
    });
    setFieldErrors(result.fieldErrors);
    if (!result.success || !result.data) {
      focusField(result.firstField);
      return;
    }

    setLoading(true);
    try {
      const registered = await authApi(apiClient).register(result.data);
      router.push(
        `/signup/verify-pending?email=${encodeURIComponent(result.data.email)}&dispatched=${registered.verification_email_dispatched}`,
      );
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'EMAIL_ALREADY_USED') {
          setError('이미 가입된 이메일입니다.');
        } else {
          setError(err.message);
        }
      } else {
        setError('알 수 없는 오류가 발생했습니다.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-ink">회원가입</h1>

      <form onSubmit={onSubmit} className="space-y-4" data-testid="signup-form" noValidate>
        <FormField
          ref={emailRef}
          id="signup-email"
          label="이메일"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={fieldErrors.email}
          data-testid="signup-email"
        />

        <fieldset className="space-y-3 rounded-sm border border-hairline p-3">
          <legend className="px-1 text-sm font-semibold text-ink">필수 약관 동의</legend>
          <label className="flex items-center gap-2 text-sm font-semibold text-ink">
            <input
              type="checkbox"
              checked={allRequiredConsents}
              onChange={(event) => setAllRequired(event.target.checked)}
              data-testid="signup-consent-required-all"
            />
            <span>필수 항목 전체 동의</span>
          </label>
          <div className="space-y-2">
            {REQUIRED_CONSENTS.map((item) => (
              <label key={item.type} className="flex items-start gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={consents[item.type]}
                  onChange={(event) => toggleConsent(item.type, event.target.checked)}
                  data-testid={`signup-consent-${item.type}`}
                />
                <span>
                  <span className="font-semibold">(필수) {item.label}</span>
                  <span className="block text-xs text-muted">{item.summary}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="space-y-2 rounded-sm border border-hairline p-3">
          <legend className="px-1 text-sm font-semibold text-ink">선택 동의</legend>
          {OPTIONAL_CONSENTS.map((item) => (
            <label key={item.type} className="flex items-start gap-2 text-sm text-ink">
              <input
                type="checkbox"
                className="mt-1"
                checked={consents[item.type]}
                onChange={(event) => toggleConsent(item.type, event.target.checked)}
                data-testid={`signup-consent-${item.type}`}
              />
              <span>
                <span className="font-semibold">(선택) {item.label}</span>
                <span className="block text-xs text-muted">{item.summary}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <FormField
          ref={passwordRef}
          id="signup-password"
          label="비밀번호"
          hint="8자 이상"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={fieldErrors.password}
          data-testid="signup-password"
        />

        <FormField
          ref={nicknameRef}
          id="signup-nickname"
          label="닉네임"
          type="text"
          autoComplete="nickname"
          required
          maxLength={80}
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          error={fieldErrors.nickname}
          data-testid="signup-nickname"
        />

        {error && (
          <p className="text-sm text-error-text" role="alert" data-testid="signup-error">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading || !allRequiredConsents}
          className="w-full rounded-sm bg-primary py-3 text-sm font-semibold text-white hover:bg-primary-active disabled:opacity-60"
          data-testid="signup-submit"
        >
          {loading ? '가입 중...' : '회원가입'}
        </button>
      </form>

      <p className="text-center text-xs text-muted">
        이미 계정이 있으신가요?{' '}
        <Link href="/login" className="text-primary underline">
          로그인
        </Link>
      </p>

      <p className="text-xs text-muted-soft">
        회원가입 후 이메일 인증을 거치면 여행계획을 만들 수 있습니다. Google OAuth는 로그인
        화면에서 시작할 수 있습니다.
      </p>
    </div>
  );
}
