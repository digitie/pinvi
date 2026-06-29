'use client';

import { useState, type FormEvent } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import { Play, RefreshCw } from 'lucide-react';
import { AdminPage } from '@/components/admin/AdminPage';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';

export default function AdminResetPage() {
  const [confirm, setConfirm] = useState('');
  const [accessReason, setAccessReason] = useState('');
  const [includeSeed, setIncludeSeed] = useState(true);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [mutationNotice, setMutationNotice] = useState<string | null>(null);

  const statusQuery = useQuery({
    queryKey: queryKeys.admin.resetStatus(),
    queryFn: () => adminApi(apiClient).getResetStatus(),
  });
  const status = statusQuery.data ?? null;
  const unavailable =
    statusQuery.isError &&
    statusQuery.error instanceof ApiError &&
    statusQuery.error.status === 404;
  const error =
    statusQuery.isError && !unavailable
      ? statusQuery.error instanceof ApiError
        ? statusQuery.error.message
        : 'reset 상태 조회에 실패했습니다.'
      : null;

  const resetMutation = useMutation({
    mutationFn: () =>
      adminApi(apiClient).runReset({
        confirm,
        access_reason: accessReason.trim(),
        dry_run: true,
        include_seed: includeSeed,
      }),
    onMutate: () => {
      setMutationError(null);
      setMutationNotice(null);
    },
    onError: (error) => {
      setMutationError(error instanceof ApiError ? error.message : 'reset dry-run에 실패했습니다.');
    },
    onSuccess: (result) => {
      setMutationNotice(`reset dry-run 감사 로그 #${result.audit_log_id} 기록 완료`);
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!accessReason.trim()) {
      setMutationError('운영 사유를 입력하세요.');
      return;
    }
    resetMutation.mutate();
  };

  return (
    <AdminPage
      title="DB 리셋"
      description="개발/스테이징 전용 dry-run"
      actions={
        <button
          type="button"
          onClick={() => void statusQuery.refetch()}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
          data-testid="admin-reset-refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          갱신
        </button>
      }
    >
      {unavailable ? (
        <p className="rounded-sm border border-hairline bg-surface-soft p-4 text-sm text-muted">
          reset route가 비활성화되어 있습니다.
        </p>
      ) : (
        <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_28rem]">
          <div className="space-y-3 rounded-sm border border-hairline bg-white p-4 text-sm">
            {error && (
              <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
                {error}
              </p>
            )}
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2">
              <dt className="text-muted">environment</dt>
              <dd data-testid="admin-reset-environment">{status?.environment ?? '—'}</dd>
              <dt className="text-muted">mode</dt>
              <dd>{status?.mode ?? '—'}</dd>
              <dt className="text-muted">target</dt>
              <dd>{status?.target_schemas.join(', ') ?? '—'}</dd>
              <dt className="text-muted">confirm</dt>
              <dd className="font-mono">{status?.confirm_phrase ?? 'RESET'}</dd>
            </dl>
          </div>

          <form
            className="space-y-3 rounded-sm border border-hairline bg-white p-4 text-sm"
            onSubmit={submit}
          >
            <label className="block text-xs text-muted">
              확인 문구
              <input
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                className={`${inputClass} mt-1 w-full font-mono`}
                data-testid="admin-reset-confirm"
              />
            </label>
            <label className="block text-xs text-muted">
              운영 사유
              <textarea
                value={accessReason}
                onChange={(event) => setAccessReason(event.target.value)}
                className="mt-1 w-full rounded-sm border border-hairline px-2 py-1 text-sm"
                rows={3}
                data-testid="admin-reset-reason"
              />
            </label>
            <label className="flex items-center gap-2 text-xs text-muted">
              <input
                type="checkbox"
                checked={includeSeed}
                onChange={(event) => setIncludeSeed(event.target.checked)}
                data-testid="admin-reset-include-seed"
              />
              seed 포함
            </label>
            {mutationError && (
              <p
                role="alert"
                className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
                data-testid="admin-reset-error"
              >
                {mutationError}
              </p>
            )}
            {mutationNotice && (
              <p
                className="rounded-sm bg-surface-soft p-3 text-sm text-body"
                data-testid="admin-reset-notice"
              >
                {mutationNotice}
              </p>
            )}
            <button
              type="submit"
              disabled={resetMutation.isPending}
              className="inline-flex items-center gap-1 rounded-sm border border-hairline bg-ink px-3 py-1 text-sm text-white disabled:opacity-50"
              data-testid="admin-reset-run"
            >
              <Play className="h-3.5 w-3.5" aria-hidden="true" />
              dry-run
            </button>
          </form>
        </section>
      )}
    </AdminPage>
  );
}
