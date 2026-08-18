'use client';

import { useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { RegisterRequestSchema } from '@pinvi/schemas';
import type { ConsentType } from '@pinvi/schemas';
import { ApiClient, ApiError, authApi } from '@pinvi/api-client';
import { FormField } from '@/components/forms/FormField';
import { Button } from '@/components/ui/Button';
import { validateForm, type FieldErrors } from '@pinvi/domain';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const CONSENT_VERSION = 'v1.0';

type ConsentItem = { type: ConsentType; label: string; summary: string; legalSlug?: string };

// 전문은 /legal/<slug>(lib/legalDocs.ts) — 동의 항목에서 바로 열 수 있어야 한다(Hallmark audit Mj14).
const REQUIRED_CONSENTS: ConsentItem[] = [
  {
    type: 'tos',
    label: '이용약관',
    summary: '서비스 이용 조건과 계정 운영 기준',
    legalSlug: 'terms-of-service',
  },
  {
    type: 'privacy',
    label: '개인정보 처리방침',
    summary: '계정, 여행계획, 첨부파일 처리 기준',
    legalSlug: 'privacy-policy',
  },
  {
    type: 'lbs_tos',
    label: '위치기반서비스 이용약관',
    summary: '여행 지도와 위치 기반 기능 이용 조건',
    legalSlug: 'lbs-terms',
  },
  {
    type: 'location_collection',
    label: '개인위치정보 수집·이용',
    summary: '현재 위치 기반 검색과 여행 일정 표시',
    legalSlug: 'location-consent',
  },
];

const OPTIONAL_CONSENTS: ConsentItem[] = [
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

// 20px 커스텀 체크박스 — 스타일은 globals.css `.checkbox`(네이티브 13px는 터치 타깃 미달).
const CHECKBOX_CLASS = 'checkbox';

/** 동의 항목 한 행 — 44px 행, 라벨 전체가 클릭 영역, 전문 링크는 새 창. */
function ConsentRow({
  item,
  required,
  checked,
  onChange,
}: {
  item: ConsentItem;
  required: boolean;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const inputId = `signup-consent-${item.type}`;
  return (
    <div className="flex items-start gap-3 py-2">
      <input
        id={inputId}
        type="checkbox"
        className={`${CHECKBOX_CLASS} mt-0.5`}
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        data-testid={inputId}
      />
      <label htmlFor={inputId} className="min-h-6 flex-1 cursor-pointer text-sm text-ink">
        <span className="font-medium">
          {required ? '(필수) ' : '(선택) '}
          {item.label}
        </span>
        <span className="block text-sm text-muted">{item.summary}</span>
      </label>
      {item.legalSlug ? (
        <Link
          href={`/legal/${item.legalSlug}`}
          target="_blank"
          rel="noopener"
          className="focus-ring inline-flex min-h-11 shrink-0 items-center rounded-sm px-1 text-sm text-ink underline decoration-hairline underline-offset-4 hover:decoration-ink"
          aria-label={`${item.label} 전문 보기(새 창)`}
        >
          전문
        </Link>
      ) : null}
    </div>
  );
}

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
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight text-ink">회원가입</h1>
        <p className="text-sm text-muted">이메일 인증을 마치면 바로 여행을 만들 수 있어요.</p>
      </div>

      <form onSubmit={onSubmit} className="space-y-5" data-testid="signup-form" noValidate>
        {/* 입력 3개를 먼저, 동의는 제출 직전에 — 필드 순서를 끊지 않는다. */}
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

        <fieldset className="space-y-1 border-t border-hairline pt-4">
          <legend className="sr-only">약관 동의</legend>
          <div className="flex items-center gap-3 border-b border-hairline pb-2">
            <input
              id="signup-consent-required-all"
              type="checkbox"
              className={CHECKBOX_CLASS}
              checked={allRequiredConsents}
              onChange={(event) => setAllRequired(event.target.checked)}
              data-testid="signup-consent-required-all"
            />
            <label
              htmlFor="signup-consent-required-all"
              className="min-h-11 flex-1 cursor-pointer py-2.5 text-sm font-semibold text-ink"
            >
              필수 항목 전체 동의
            </label>
          </div>
          {REQUIRED_CONSENTS.map((item) => (
            <ConsentRow
              key={item.type}
              item={item}
              required
              checked={consents[item.type]}
              onChange={(checked) => toggleConsent(item.type, checked)}
            />
          ))}
          {OPTIONAL_CONSENTS.map((item) => (
            <ConsentRow
              key={item.type}
              item={item}
              required={false}
              checked={consents[item.type]}
              onChange={(checked) => toggleConsent(item.type, checked)}
            />
          ))}
        </fieldset>

        {error && (
          <p className="text-sm text-error-text" role="alert" data-testid="signup-error">
            {error}
          </p>
        )}

        <div className="space-y-2">
          <Button
            type="submit"
            fullWidth
            loading={loading}
            disabled={!allRequiredConsents}
            data-testid="signup-submit"
          >
            {loading ? '가입 중…' : '회원가입'}
          </Button>
          {/* disabled 사유는 색이 아니라 문장으로. */}
          {!allRequiredConsents ? (
            <p className="text-sm text-muted" role="status">
              필수 약관 4개에 동의하면 가입할 수 있어요.
            </p>
          ) : null}
        </div>
      </form>

      <p className="text-center text-sm text-muted">
        이미 계정이 있으신가요?{' '}
        <Link
          href="/login"
          className="focus-ring rounded-sm font-medium text-ink underline decoration-hairline underline-offset-4 hover:decoration-ink"
        >
          로그인
        </Link>
      </p>
    </div>
  );
}
