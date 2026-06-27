'use client';

import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminSeedScenario } from '@pinvi/schemas';
import { Play, RefreshCw } from 'lucide-react';
import { AdminPage } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';

export default function AdminSeedPage() {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [confirm, setConfirm] = useState('');
  const [accessReason, setAccessReason] = useState('');
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [mutationNotice, setMutationNotice] = useState<string | null>(null);

  const scenariosQuery = useQuery({
    queryKey: queryKeys.admin.seedScenarios(),
    queryFn: () => adminApi(apiClient).listSeedScenarios(),
  });
  const data = scenariosQuery.data ?? null;
  const scenarios = useMemo(() => data?.scenarios ?? [], [data?.scenarios]);
  const selected = scenarios.find((scenario) => scenario.key === selectedKey) ?? scenarios[0] ?? null;
  const unavailable =
    scenariosQuery.isError &&
    scenariosQuery.error instanceof ApiError &&
    scenariosQuery.error.status === 404;
  const error =
    scenariosQuery.isError && !unavailable
      ? scenariosQuery.error instanceof ApiError
        ? scenariosQuery.error.message
        : 'seed scenario 조회에 실패했습니다.'
      : null;

  useEffect(() => {
    if (!selected) return;
    setSelectedKey(selected.key);
    setConfirm('');
    setMutationError(null);
    setMutationNotice(null);
  }, [selected]);

  const runMutation = useMutation({
    mutationFn: (scenario: AdminSeedScenario) =>
      adminApi(apiClient).runSeedScenario(scenario.key, {
        confirm,
        access_reason: accessReason.trim(),
        dry_run: true,
      }),
    onMutate: () => {
      setMutationError(null);
      setMutationNotice(null);
    },
    onError: (error) => {
      setMutationError(error instanceof ApiError ? error.message : 'seed dry-run에 실패했습니다.');
    },
    onSuccess: (result) => {
      setMutationNotice(`${result.target} dry-run 감사 로그 #${result.audit_log_id} 기록 완료`);
    },
  });

  const columns: AdminTableColumn<AdminSeedScenario>[] = [
    {
      key: 'scenario',
      header: 'scenario',
      sortable: true,
      sortValue: (row) => row.key,
      cell: (row) => (
        <div>
          <div className="font-medium">{row.title}</div>
          <div className="font-mono text-xs text-muted">{row.key}</div>
        </div>
      ),
    },
    {
      key: 'confirm',
      header: 'confirm',
      sortable: true,
      sortValue: (row) => row.confirm_phrase,
      cell: (row) => <span className="font-mono text-xs">{row.confirm_phrase}</span>,
    },
    {
      key: 'steps',
      header: 'steps',
      sortValue: (row) => row.steps.length,
      sortable: true,
      cell: (row) => row.steps.length.toLocaleString('ko-KR'),
      align: 'right',
    },
  ];

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    if (!accessReason.trim()) {
      setMutationError('운영 사유를 입력하세요.');
      return;
    }
    runMutation.mutate(selected);
  };

  return (
    <AdminPage
      title="시드 시나리오"
      description="개발/스테이징 전용 dry-run"
      actions={
        <button
          type="button"
          onClick={() => void scenariosQuery.refetch()}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
          data-testid="admin-seed-refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          갱신
        </button>
      }
    >
      {unavailable ? (
        <p className="rounded-sm border border-hairline bg-surface-soft p-4 text-sm text-muted">
          seed route가 비활성화되어 있습니다.
        </p>
      ) : (
        <>
          {error && (
            <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
              {error}
            </p>
          )}
          <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_28rem]">
            <AdminTable
              columns={columns}
              rows={scenarios}
              loading={scenariosQuery.isLoading}
              rowKey={(row) => row.key}
              rowTestId={(row) => `admin-seed-row-${row.key}`}
              onRowClick={(row) => setSelectedKey(row.key)}
              empty="seed scenario가 없습니다."
            />
            <section
              className="space-y-4 rounded-sm border border-hairline bg-white p-4 text-sm"
              data-testid="admin-seed-detail"
            >
              {selected ? (
                <>
                  <div>
                    <h2 className="text-sm font-semibold text-ink">{selected.title}</h2>
                    <p className="font-mono text-xs text-muted">{selected.key}</p>
                  </div>
                  <ol className="list-decimal space-y-1 pl-5 text-xs text-muted">
                    {selected.steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                  <form className="space-y-3 border-t border-hairline pt-3" onSubmit={submit}>
                    <label className="block text-xs text-muted">
                      확인 문구
                      <input
                        value={confirm}
                        onChange={(event) => setConfirm(event.target.value)}
                        className={`${inputClass} mt-1 w-full font-mono`}
                        data-testid="admin-seed-confirm"
                      />
                    </label>
                    <label className="block text-xs text-muted">
                      운영 사유
                      <textarea
                        value={accessReason}
                        onChange={(event) => setAccessReason(event.target.value)}
                        className="mt-1 w-full rounded-sm border border-hairline px-2 py-1 text-sm"
                        rows={3}
                        data-testid="admin-seed-reason"
                      />
                    </label>
                    {mutationError && (
                      <p
                        role="alert"
                        className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
                        data-testid="admin-seed-error"
                      >
                        {mutationError}
                      </p>
                    )}
                    {mutationNotice && (
                      <p
                        className="rounded-sm bg-surface-soft p-3 text-sm text-body"
                        data-testid="admin-seed-notice"
                      >
                        {mutationNotice}
                      </p>
                    )}
                    <button
                      type="submit"
                      disabled={runMutation.isPending}
                      className="inline-flex items-center gap-1 rounded-sm border border-hairline bg-ink px-3 py-1 text-sm text-white disabled:opacity-50"
                      data-testid="admin-seed-run"
                    >
                      <Play className="h-3.5 w-3.5" aria-hidden="true" />
                      dry-run
                    </button>
                  </form>
                </>
              ) : (
                <p className="text-muted">scenario를 선택하세요.</p>
              )}
            </section>
          </section>
        </>
      )}
    </AdminPage>
  );
}
