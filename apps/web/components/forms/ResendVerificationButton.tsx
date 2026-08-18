'use client';

import { useEffect, useState } from 'react';
import { ApiClient, ApiError, authApi } from '@pinvi/api-client';
import { Button } from '@/components/ui/Button';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const COOLDOWN_SECONDS = 60;

/**
 * 인증 메일 재발송 — verify-pending 화면의 dead end 해소(Hallmark audit C12).
 * 성공/실패는 role=status 한 줄로 조용히, 재요청은 60초 쿨다운(서버 rate-limit과 정합).
 */
export function ResendVerificationButton({ email }: { email: string }) {
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [state, setState] = useState<'idle' | 'error' | 'success'>('idle');
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  const onResend = async () => {
    setLoading(true);
    setNotice(null);
    setState('idle');
    try {
      await authApi(apiClient).resendVerification({ email });
      setState('success');
      setNotice('인증 메일을 다시 보냈어요. 메일함(스팸함 포함)을 확인해 주세요.');
      setCooldown(COOLDOWN_SECONDS);
    } catch (err) {
      setState('error');
      setNotice(
        err instanceof ApiError && err.status === 429
          ? '잠시 후 다시 시도해 주세요. 재발송은 1분에 한 번만 가능합니다.'
          : '재발송에 실패했어요. 잠시 후 다시 시도해 주세요.',
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button
        variant="secondary"
        fullWidth
        loading={loading}
        disabled={cooldown > 0}
        state={state}
        onClick={onResend}
        data-testid="verify-pending-resend"
      >
        {cooldown > 0 ? `다시 보내기 (${cooldown}초 후 가능)` : '인증 메일 다시 보내기'}
      </Button>
      <p className="min-h-[1.25rem] text-sm text-muted" role="status" aria-live="polite">
        {notice}
      </p>
    </div>
  );
}
