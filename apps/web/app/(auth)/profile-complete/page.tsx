'use client';

import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ProfileCompleteRequestSchema } from '@tripmate/schemas';
import { ApiClient, ApiError } from '@tripmate/api-client';
import { z } from 'zod';
import { FormField } from '@/components/forms/FormField';
import { validateForm, type FieldErrors } from '@/lib/formValidation';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? 'http://localhost:9021',
});

const REQUIRED: { type: string; label: string }[] = [
  { type: 'tos', label: '이용약관' },
  { type: 'privacy', label: '개인정보 처리방침' },
  { type: 'lbs_tos', label: '위치기반서비스 이용약관' },
  { type: 'location_collection', label: '개인위치정보 수집·이용' },
];

const OPTIONAL: { type: string; label: string }[] = [
  { type: 'demographic_use', label: '성별·생년월 통계·추천 활용' },
  { type: 'marketing', label: '마케팅·이벤트 이메일 수신' },
];

const CONSENT_VERSION = 'v1.0';

interface CheckedMap {
  [type: string]: boolean;
}

export default function ProfileCompletePage() {
  const router = useRouter();
  const [nickname, setNickname] = useState('');
  const [required, setRequired] = useState<CheckedMap>(
    Object.fromEntries(REQUIRED.map((c) => [c.type, false])),
  );
  const [optional, setOptional] = useState<CheckedMap>(
    Object.fromEntries(OPTIONAL.map((c) => [c.type, false])),
  );
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const nicknameRef = useRef<HTMLInputElement>(null);

  const allRequired = REQUIRED.every((c) => required[c.type]);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!allRequired) {
      setError('필수 동의 항목을 모두 체크해 주세요.');
      return;
    }
    const consents = [
      ...REQUIRED.filter((c) => required[c.type]).map((c) => ({
        consent_type: c.type as z.infer<typeof ProfileCompleteRequestSchema>['consents'][number]['consent_type'],
        version: CONSENT_VERSION,
      })),
      ...OPTIONAL.filter((c) => optional[c.type]).map((c) => ({
        consent_type: c.type as z.infer<typeof ProfileCompleteRequestSchema>['consents'][number]['consent_type'],
        version: CONSENT_VERSION,
      })),
    ];

    const result = validateForm(ProfileCompleteRequestSchema, {
      nickname,
      avatar_kind: 'default',
      consents,
    });
    setFieldErrors(result.fieldErrors);
    if (!result.success || !result.data) {
      if (result.firstField === 'nickname') nicknameRef.current?.focus();
      else setError('입력 값을 다시 확인해 주세요.');
      return;
    }
    setLoading(true);
    try {
      await apiClient.request('/users/me/profile/complete', {
        method: 'POST',
        body: JSON.stringify(result.data),
        schema: z.array(z.unknown()),
      });
      router.push('/trips');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-ink">프로필 완성하기</h1>
      <form onSubmit={onSubmit} className="space-y-5" data-testid="profile-complete-form" noValidate>
        <FormField
          ref={nicknameRef}
          id="profile-nickname"
          label="닉네임 (필수)"
          type="text"
          autoComplete="nickname"
          required
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          error={fieldErrors.nickname}
          data-testid="profile-nickname"
        />

        <fieldset className="space-y-2">
          <legend className="text-sm font-semibold text-ink">필수 동의</legend>
          {REQUIRED.map((c) => (
            <label key={c.type} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={required[c.type] ?? false}
                onChange={(e) =>
                  setRequired((prev) => ({ ...prev, [c.type]: e.target.checked }))
                }
                data-testid={`consent-required-${c.type}`}
              />
              <span>(필수) {c.label}</span>
            </label>
          ))}
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="text-sm font-semibold text-ink">선택 동의</legend>
          {OPTIONAL.map((c) => (
            <label key={c.type} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={optional[c.type] ?? false}
                onChange={(e) =>
                  setOptional((prev) => ({ ...prev, [c.type]: e.target.checked }))
                }
                data-testid={`consent-optional-${c.type}`}
              />
              <span>(선택) {c.label}</span>
            </label>
          ))}
        </fieldset>

        {error && (
          <p className="text-sm text-error-text" data-testid="profile-error">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading || !allRequired}
          className="w-full rounded-sm bg-primary py-3 text-sm font-semibold text-white hover:bg-primary-active disabled:opacity-60"
          data-testid="profile-submit"
        >
          {loading ? '저장 중...' : '완료'}
        </button>
      </form>
    </div>
  );
}
