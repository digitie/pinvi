'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Archive,
  CheckCircle2,
  Loader2,
  PlayCircle,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminRetentionRun } from '@pinvi/schemas';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { apiClient } from '@/lib/api';

const SCOPE_OPTIONS = [
  { value: 'all', label: '전체' },
  { value: 'pii', label: 'PII' },
  { value: 'location', label: '위치 로그' },
] as const;

type RetentionScope = (typeof SCOPE_OPTIONS)[number]['value'];

const inputClass =
  'h-10 rounded-sm border border-hairline px-3 text-sm outline-none focus:border-primary';
const textareaClass =
  'min-h-20 rounded-sm border border-hairline px-3 py-2 text-sm outline-none focus:border-primary';

function formatMetric(value: number | null | undefined) {
  return new Intl.NumberFormat('ko-KR').format(value ?? 0);
}

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '-';
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function statusClass(status: AdminRetentionRun['status']) {
  if (status === 'completed' || status === 'dry_run') return 'bg-success-bg text-success-text';
  if (status === 'failed' || status === 'rolled_back') return 'bg-error-bg text-error-text';
  return 'bg-surface-soft text-muted';
}

function nestedNumber(value: Record<string, unknown>, section: string, key: string): number | null {
  const sectionValue = value[section];
  if (!sectionValue || typeof sectionValue !== 'object' || Array.isArray(sectionValue)) return null;
  const raw = (sectionValue as Record<string, unknown>)[key];
  return typeof raw === 'number' ? raw : null;
}

function MetricBox({
  label,
  value,
  testId,
}: {
  label: string;
  value: number | string | null | undefined;
  testId?: string;
}) {
  return (
    <div className="rounded-sm border border-hairline bg-white p-3" data-testid={testId}>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 truncate text-lg font-semibold text-ink">
        {typeof value === 'number' ? formatMetric(value) : (value ?? '-')}
      </div>
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
      {message}
    </p>
  );
}

export default function AdminRetentionPage() {
  const queryClient = useQueryClient();
  const [dryScope, setDryScope] = useState<RetentionScope>('all');
  const [dryReason, setDryReason] = useState('');
  const [executeScope, setExecuteScope] = useState<RetentionScope>('all');
  const [executeReason, setExecuteReason] = useState('');
  const [confirmPhrase, setConfirmPhrase] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

  const summaryQuery = useQuery({
    queryKey: queryKeys.admin.retentionSummary(),
    queryFn: () => adminApi(apiClient).getRetentionSummary(),
  });

  const runsQuery = useQuery({
    queryKey: queryKeys.admin.retentionRuns({ pageSize: 20 }),
    queryFn: () => adminApi(apiClient).listRetentionRuns(20),
  });

  const summary = summaryQuery.data ?? null;
  const pii = summary?.pii_retention ?? null;
  const location = summary?.location_log_archive ?? null;
  const runs = runsQuery.data?.items ?? summary?.latest_runs ?? [];
  const expectedConfirmPhrase = summary?.confirm_phrase ?? 'EXECUTE RETENTION';

  const dryRunMutation = useMutation({
    mutationFn: () =>
      adminApi(apiClient).createRetentionDryRun({
        scope: dryScope,
        access_reason: dryReason.trim(),
      }),
    onSuccess: (run) => {
      setNotice(`${run.run_id} dry-run을 기록했습니다.`);
      setDryReason('');
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.retentionAll() });
    },
  });

  const executeMutation = useMutation({
    mutationFn: () =>
      adminApi(apiClient).executeRetention({
        scope: executeScope,
        access_reason: executeReason.trim(),
        confirm_phrase: confirmPhrase,
      }),
    onSuccess: (run) => {
      setNotice(`${run.run_id} retention execute가 완료됐습니다.`);
      setExecuteReason('');
      setConfirmPhrase('');
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.retentionAll() });
    },
  });

  const error =
    (summaryQuery.isError &&
      errorMessage(summaryQuery.error, 'retention summary 조회에 실패했습니다.')) ||
    (runsQuery.isError &&
      errorMessage(runsQuery.error, 'retention 실행 이력 조회에 실패했습니다.')) ||
    (dryRunMutation.isError &&
      errorMessage(dryRunMutation.error, 'retention dry-run 기록에 실패했습니다.')) ||
    (executeMutation.isError &&
      errorMessage(executeMutation.error, 'retention execute에 실패했습니다.')) ||
    null;

  const refresh = () => {
    setNotice(null);
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.retentionAll() });
  };

  const submitDryRun = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setNotice(null);
    dryRunMutation.mutate();
  };

  const submitExecute = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setNotice(null);
    executeMutation.mutate();
  };

  const columns = useMemo<AdminTableColumn<AdminRetentionRun>[]>(
    () => [
      {
        key: 'run',
        header: 'run',
        sortable: true,
        sortValue: (run) => run.created_at,
        cell: (run) => (
          <div>
            <div className="font-mono text-xs">{run.run_id}</div>
            <div className="text-xs text-muted">{formatDateTime(run.created_at)}</div>
          </div>
        ),
      },
      {
        key: 'mode',
        header: 'mode',
        sortable: true,
        sortValue: (run) => run.mode,
        cell: (run) => `${run.mode} / ${run.scope}`,
      },
      {
        key: 'status',
        header: 'status',
        sortable: true,
        sortValue: (run) => run.status,
        cell: (run) => (
          <span className={`rounded-sm px-2 py-1 text-xs font-semibold ${statusClass(run.status)}`}>
            {run.status}
          </span>
        ),
      },
      {
        key: 'result',
        header: 'result',
        cell: (run) => {
          const anonymized = nestedNumber(run.result, 'pii', 'anonymized_users');
          const archived = nestedNumber(run.result, 'location', 'archived_rows');
          if (anonymized === null && archived === null) return '-';
          return (
            <div className="text-xs">
              <div>users {formatMetric(anonymized)}</div>
              <div>location {formatMetric(archived)}</div>
            </div>
          );
        },
      },
      {
        key: 'actor',
        header: 'actor',
        cell: (run) => <span className="font-mono text-xs">{run.actor_user_id}</span>,
      },
    ],
    [],
  );

  const executeDisabled =
    !summary?.execute_enabled ||
    executeMutation.isPending ||
    !executeReason.trim() ||
    confirmPhrase !== expectedConfirmPhrase;

  return (
    <AdminPage
      title="Retention"
      description="PII 보존기간 정리와 위치 로그 archive 실행 상태"
      actions={
        <button
          type="button"
          onClick={refresh}
          className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
          data-testid="admin-retention-refresh"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          새로고침
        </button>
      }
    >
      {notice && (
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">{notice}</p>
      )}
      {error && <ErrorBox message={error} />}

      <Section title="실행 게이트">
        <div className="grid gap-3 text-sm sm:grid-cols-3" data-testid="admin-retention-summary">
          <MetricBox
            label="execute"
            value={summary?.execute_enabled ? 'enabled' : 'disabled'}
            testId="admin-retention-execute-enabled"
          />
          <MetricBox label="confirm phrase" value={expectedConfirmPhrase} />
          <MetricBox label="generated" value={formatDateTime(summary?.generated_at)} />
        </div>
        {!summary?.execute_enabled && (
          <p className="mt-3 rounded-sm bg-surface-soft p-3 text-sm text-muted">
            `PINVI_RETENTION_EXECUTE_ENABLED=false`
          </p>
        )}
      </Section>

      <Section title="대상 요약">
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-sm border border-hairline p-3">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
              PII
            </h3>
            <div className="grid gap-3 sm:grid-cols-3">
              <MetricBox
                label="candidates"
                value={pii?.total_candidates}
                testId="admin-retention-pii-total"
              />
              <MetricBox label="deleted users" value={pii?.deleted_user_pii_candidates} />
              <MetricBox
                label="sessions"
                value={(pii?.old_revoked_sessions ?? 0) + (pii?.old_expired_sessions ?? 0)}
              />
            </div>
            <div className="mt-3 grid gap-2 text-xs text-muted sm:grid-cols-2">
              <div>OAuth {formatMetric(pii?.expired_oauth_login_states)}</div>
              <div>mobile OAuth {formatMetric(pii?.expired_mobile_oauth_exchanges)}</div>
              <div>admin audit skip {formatMetric(pii?.admin_audit_pii_over_retention)}</div>
              <div>privileged excluded {formatMetric(pii?.excluded_privileged_deleted_users)}</div>
            </div>
          </div>

          <div className="rounded-sm border border-hairline p-3">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <Archive className="h-4 w-4" aria-hidden="true" />
              위치 로그 archive
            </h3>
            <div className="grid gap-3 sm:grid-cols-3">
              <MetricBox
                label="candidates"
                value={location?.total_candidates}
                testId="admin-retention-location-total"
              />
              <MetricBox label="active rows" value={location?.active_rows_after_cutoff} />
              <MetricBox
                label="pending outbox"
                value={`${formatMetric(location?.pending_outbox_before_cutoff)} / ${formatMetric(
                  location?.pending_outbox_total,
                )}`}
              />
            </div>
            <div className="mt-3 grid gap-2 text-xs text-muted sm:grid-cols-2">
              <div>cutoff {formatDateTime(location?.archive_cutoff)}</div>
              <div>blocked {location?.archive_blocked_by_pending_outbox ? 'yes' : 'no'}</div>
              <div>tail {location?.archive_tail_log_id ?? '-'}</div>
              <div>
                bridge{' '}
                {location?.chain_bridge_required
                  ? location.bridge_anchor_matches
                    ? 'match'
                    : 'mismatch'
                  : 'none'}
              </div>
            </div>
          </div>
        </div>
      </Section>

      <Section title="작업">
        <div className="grid gap-4 lg:grid-cols-2">
          <form className="space-y-3" onSubmit={submitDryRun}>
            <div className="flex items-center gap-2 text-sm font-semibold text-ink">
              <PlayCircle className="h-4 w-4" aria-hidden="true" />
              Dry-run
            </div>
            <select
              aria-label="Dry-run scope"
              className={inputClass}
              value={dryScope}
              onChange={(event) => setDryScope(event.target.value as RetentionScope)}
            >
              {SCOPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <textarea
              aria-label="Dry-run 사유"
              className={`${textareaClass} w-full`}
              value={dryReason}
              onChange={(event) => setDryReason(event.target.value)}
            />
            <button
              type="submit"
              disabled={dryRunMutation.isPending || !dryReason.trim()}
              className="inline-flex h-10 items-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
              data-testid="admin-retention-dry-run"
            >
              {dryRunMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              )}
              Dry-run 기록
            </button>
          </form>

          <form className="space-y-3" onSubmit={submitExecute}>
            <div className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              Execute
            </div>
            <select
              aria-label="Execute scope"
              className={inputClass}
              value={executeScope}
              onChange={(event) => setExecuteScope(event.target.value as RetentionScope)}
            >
              {SCOPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <textarea
              aria-label="Execute 사유"
              className={`${textareaClass} w-full`}
              value={executeReason}
              onChange={(event) => setExecuteReason(event.target.value)}
            />
            <input
              aria-label="Confirm phrase"
              className={`${inputClass} w-full font-mono`}
              value={confirmPhrase}
              onChange={(event) => setConfirmPhrase(event.target.value)}
            />
            <button
              type="submit"
              disabled={executeDisabled}
              className="inline-flex h-10 items-center gap-2 rounded-sm bg-error-text px-4 text-sm font-semibold text-white disabled:opacity-50"
              data-testid="admin-retention-execute"
            >
              {executeMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              )}
              Execute
            </button>
          </form>
        </div>
      </Section>

      <Section title="실행 이력">
        <AdminTable
          columns={columns}
          rows={runs}
          rowKey={(run) => run.run_id}
          loading={summaryQuery.isPending || runsQuery.isPending}
          empty="retention run이 없습니다."
          rowTestId={(run) => `admin-retention-row-${run.run_id}`}
          initialSort={{ columnKey: 'run', desc: true }}
        />
      </Section>
    </AdminPage>
  );
}
