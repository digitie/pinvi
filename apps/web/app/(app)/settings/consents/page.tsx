'use client';

import { useCallback, useEffect, useState } from 'react';
import { Loader2, ShieldCheck } from 'lucide-react';
import { ApiError, userApi } from '@tripmate/api-client';
import type { ConsentType, UserConsent } from '@tripmate/schemas';
import { apiClient } from '@/lib/api';

interface ConsentMeta {
  type: ConsentType;
  label: string;
  required: boolean;
  note?: string;
}

const CONSENTS: ConsentMeta[] = [
  { type: 'tos', label: '이용약관', required: true },
  { type: 'privacy', label: '개인정보 처리방침', required: true },
  { type: 'lbs_tos', label: '위치기반서비스 이용약관', required: true },
  {
    type: 'location_collection',
    label: '개인위치정보 수집·이용',
    required: true,
    note: '철회하면 내 위치·주변 검색 등 위치 기능이 비활성화됩니다(위치정보법 제16조).',
  },
  { type: 'demographic_use', label: '인구통계 정보 이용', required: false },
  { type: 'marketing', label: '마케팅·이벤트 수신', required: false },
];

// 철회 가능 항목(필수 약관 철회 = 회원 탈퇴 수준이라 본 화면에서는 제외).
const WITHDRAWABLE: ConsentType[] = ['location_collection', 'demographic_use', 'marketing'];

function statusOf(consents: UserConsent[], type: ConsentType): 'agreed' | 'withdrawn' | 'none' {
  const row = consents.find((c) => c.consent_type === type);
  if (!row) return 'none';
  return row.withdrawn_at ? 'withdrawn' : 'agreed';
}

export default function ConsentsSettingsPage() {
  const [consents, setConsents] = useState<UserConsent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<ConsentType | null>(null);

  const reload = useCallback(async () => {
    try {
      setConsents(await userApi(apiClient).getConsents());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '동의 정보를 불러오지 못했습니다.');
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void reload().finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [reload]);

  const withdraw = async (type: ConsentType) => {
    setPending(type);
    setError(null);
    try {
      await userApi(apiClient).withdrawConsent(type);
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '철회에 실패했습니다.');
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="space-y-5">
      <header className="border-b border-hairline pb-4">
        <p className="text-xs font-semibold uppercase tracking-normal text-primary">Settings</p>
        <h1 className="mt-1 flex items-center gap-2 text-2xl font-bold text-ink md:text-3xl">
          <ShieldCheck className="h-6 w-6 text-primary" aria-hidden="true" />
          동의 관리
        </h1>
        <p className="mt-1 text-sm text-muted">동의 현황을 확인하고 선택 항목을 철회할 수 있습니다.</p>
      </header>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text" data-testid="consents-error">
          {error}
        </p>
      )}

      {loading ? (
        <div className="flex min-h-32 items-center justify-center rounded-sm border border-hairline bg-white text-sm text-muted">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
          불러오는 중…
        </div>
      ) : (
        <ul className="space-y-2" data-testid="consents-list">
          {CONSENTS.map((meta) => {
            const status = statusOf(consents, meta.type);
            const canWithdraw = WITHDRAWABLE.includes(meta.type) && status === 'agreed';
            return (
              <li
                key={meta.type}
                className="flex flex-wrap items-center justify-between gap-3 rounded-sm border border-hairline bg-white p-4"
              >
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                    {meta.label}
                    <span className="rounded-sm bg-surface-soft px-1.5 py-0.5 text-xs font-medium text-muted">
                      {meta.required ? '필수' : '선택'}
                    </span>
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    {status === 'agreed' && '동의함'}
                    {status === 'withdrawn' && '철회함'}
                    {status === 'none' && '미동의'}
                    {meta.note ? ` · ${meta.note}` : ''}
                  </p>
                </div>
                {canWithdraw && (
                  <button
                    type="button"
                    onClick={() => void withdraw(meta.type)}
                    disabled={pending === meta.type}
                    className="inline-flex h-9 items-center gap-1 rounded-sm border border-hairline px-3 text-sm font-semibold text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
                  >
                    {pending === meta.type && (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    )}
                    철회
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
