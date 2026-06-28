'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Ban, Loader2, RefreshCw, RotateCcw, ShieldCheck } from 'lucide-react';
import { ApiError, adminApi, queryKeys, type AdminRateLimitAbuseParams } from '@pinvi/api-client';
import type {
  AdminRateLimitBucketRecord,
  AdminRateLimitOverrideRecord,
  AdminRateLimitSuspiciousActivityRecord,
} from '@pinvi/schemas';
import { AdminPage, FilterBar, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { apiClient } from '@/lib/api';

const POLICY_IDENTITY = {
  public: 'ip',
  auth_low: 'ip_email',
  oauth: 'ip',
  storage_upload_urls: 'user',
  feature_search: 'user',
  trip_exports: 'user',
  shared_trip: 'shared_token',
  authenticated_default: 'user',
} as const;

type PolicyName = keyof typeof POLICY_IDENTITY;
type IdentityKind = (typeof POLICY_IDENTITY)[PolicyName];
type OverrideAction = 'blocked' | 'allowed';

const inputClass =
  'h-10 rounded-sm border border-hairline px-3 text-sm outline-none focus:border-primary';
const textareaClass =
  'min-h-20 rounded-sm border border-hairline px-3 py-2 text-sm outline-none focus:border-primary';

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '-';
}

function StatusPill({ status }: { status: string }) {
  const cls =
    status === 'ok' || status === 'allowed'
      ? 'bg-success-bg text-success-text'
      : status === 'degraded' || status === 'blocked'
        ? 'bg-error-bg text-error-text'
        : 'bg-surface-soft text-muted';
  return <span className={`rounded-sm px-2 py-1 text-xs font-semibold ${cls}`}>{status}</span>;
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
      <div className="mt-1 truncate text-lg font-semibold text-ink">{value ?? '-'}</div>
    </div>
  );
}

export default function AdminAbusePage() {
  const queryClient = useQueryClient();
  const [limitFilter, setLimitFilter] = useState('');
  const [limitName, setLimitName] = useState<PolicyName>('auth_low');
  const [identityKind, setIdentityKind] = useState<IdentityKind>('ip_email');
  const [ip, setIp] = useState('127.0.0.1');
  const [email, setEmail] = useState('');
  const [userId, setUserId] = useState('');
  const [sharedToken, setSharedToken] = useState('');
  const [action, setAction] = useState<OverrideAction>('blocked');
  const [ttlMinutes, setTtlMinutes] = useState('60');
  const [reason, setReason] = useState('');
  const [rollbackReason, setRollbackReason] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

  const params = useMemo<AdminRateLimitAbuseParams>(
    () => ({ limitName: limitFilter || undefined, pageSize: 100 }),
    [limitFilter],
  );
  const summaryQuery = useQuery({
    queryKey: queryKeys.admin.rateLimitAbuse(params),
    queryFn: () => adminApi(apiClient).getRateLimitAbuseSummary(params),
    placeholderData: keepPreviousData,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      adminApi(apiClient).createRateLimitOverride({
        limit_name: limitName,
        identity_kind: identityKind,
        ip: identityKind === 'ip' || identityKind === 'ip_email' ? ip.trim() : undefined,
        email: identityKind === 'ip_email' ? email.trim() : undefined,
        user_id: identityKind === 'user' ? userId.trim() : undefined,
        shared_token: identityKind === 'shared_token' ? sharedToken.trim() : undefined,
        action,
        ttl_minutes: Number.parseInt(ttlMinutes, 10),
        access_reason: reason.trim(),
      }),
    onSuccess: (row) => {
      setNotice(`${row.identity_label} override를 ${row.action} 상태로 등록했습니다.`);
      setReason('');
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.rateLimitAbuseAll() });
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: (overrideId: string) =>
      adminApi(apiClient).rollbackRateLimitOverride(overrideId, {
        access_reason: rollbackReason.trim() || 'rate-limit override rollback',
        rollback_reason: rollbackReason.trim() || undefined,
      }),
    onSuccess: (row) => {
      setNotice(`${row.identity_label} override를 rollback했습니다.`);
      setRollbackReason('');
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.rateLimitAbuseAll() });
    },
  });

  const summary = summaryQuery.data ?? null;
  const policies = summary?.policies ?? [];
  const error =
    (summaryQuery.isError &&
      (summaryQuery.error instanceof ApiError
        ? summaryQuery.error.message
        : 'abuse 상태 조회에 실패했습니다.')) ||
    (createMutation.isError &&
      (createMutation.error instanceof ApiError
        ? createMutation.error.message
        : 'override 등록에 실패했습니다.')) ||
    (rollbackMutation.isError &&
      (rollbackMutation.error instanceof ApiError
        ? rollbackMutation.error.message
        : 'override rollback에 실패했습니다.')) ||
    null;

  const bucketColumns: AdminTableColumn<AdminRateLimitBucketRecord>[] = [
    {
      key: 'bucket',
      header: 'Bucket',
      sortable: true,
      sortValue: (row) => row.bucket_hash_prefix,
      cell: (row) => <span className="font-mono text-xs">{row.bucket_hash_prefix}</span>,
    },
    { key: 'policy', header: 'Policy', sortable: true, sortValue: (row) => row.limit_name, cell: (row) => row.limit_name },
    { key: 'count', header: 'Count', sortable: true, sortValue: (row) => row.count, cell: (row) => `${row.count}/${row.limit}` },
    { key: 'remaining', header: 'Remaining', sortable: true, sortValue: (row) => row.remaining, cell: (row) => row.remaining },
    { key: 'status', header: 'Status', sortable: true, sortValue: (row) => row.status, cell: (row) => <StatusPill status={row.status} /> },
    { key: 'expires', header: 'Expires', sortable: true, sortValue: (row) => new Date(row.expires_at).getTime(), cell: (row) => formatDateTime(row.expires_at) },
  ];

  const suspiciousColumns: AdminTableColumn<AdminRateLimitSuspiciousActivityRecord>[] = [
    { key: 'signal', header: 'Signal', sortable: true, sortValue: (row) => row.signal, cell: (row) => row.signal },
    { key: 'policy', header: 'Policy', sortable: true, sortValue: (row) => row.bucket.limit_name, cell: (row) => row.bucket.limit_name },
    { key: 'bucket', header: 'Bucket', cell: (row) => <span className="font-mono text-xs">{row.bucket.bucket_hash_prefix}</span> },
    { key: 'count', header: 'Count', sortable: true, sortValue: (row) => row.bucket.count, cell: (row) => `${row.bucket.count}/${row.bucket.limit}` },
    { key: 'status', header: 'Status', cell: (row) => <StatusPill status={row.bucket.status} /> },
  ];

  const overrideColumns: AdminTableColumn<AdminRateLimitOverrideRecord>[] = [
    { key: 'identity', header: 'Identity', sortable: true, sortValue: (row) => row.identity_label, cell: (row) => <span className="font-mono text-xs">{row.identity_label}</span> },
    { key: 'policy', header: 'Policy', sortable: true, sortValue: (row) => row.limit_name, cell: (row) => row.limit_name },
    { key: 'action', header: 'Action', sortable: true, sortValue: (row) => row.action, cell: (row) => <StatusPill status={row.action} /> },
    { key: 'status', header: 'Status', sortable: true, sortValue: (row) => row.status, cell: (row) => row.status },
    { key: 'expires', header: 'Expires', sortable: true, sortValue: (row) => new Date(row.expires_at).getTime(), cell: (row) => formatDateTime(row.expires_at) },
    {
      key: 'rollback',
      header: 'Rollback',
      cell: (row) =>
        row.status === 'blocked' || row.status === 'allowed' ? (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              rollbackMutation.mutate(row.override_id);
            }}
            disabled={rollbackMutation.isPending}
            className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-2 text-xs font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
            data-testid={`admin-abuse-rollback-${row.override_id}`}
          >
            {rollbackMutation.isPending && rollbackMutation.variables === row.override_id ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            Rollback
          </button>
        ) : (
          '-'
        ),
    },
  ];

  const onLimitNameChange = (value: string) => {
    const next = value as PolicyName;
    setLimitName(next);
    setIdentityKind(POLICY_IDENTITY[next]);
  };

  const submitOverride = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setNotice(null);
    createMutation.mutate();
  };

  return (
    <AdminPage
      title="Rate-limit abuse"
      description="ADR-038 bucket 상태와 block/allow override"
      actions={
        <button
          type="button"
          onClick={() => queryClient.invalidateQueries({ queryKey: queryKeys.admin.rateLimitAbuseAll() })}
          className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
          data-testid="admin-abuse-refresh"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          새로고침
        </button>
      }
    >
      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
          {error}
        </p>
      )}
      {notice && (
        <p className="rounded-sm bg-success-bg p-3 text-sm text-success-text" data-testid="admin-abuse-notice">
          {notice}
        </p>
      )}

      <Section title="상태">
        <div className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-5" data-testid="admin-abuse-status">
          <MetricBox label="backend" value={summary?.backend.effective_backend} />
          <MetricBox label="store" value={summary?.backend.store_status} testId="admin-abuse-store-status" />
          <MetricBox label="fail-closed" value={summary?.backend.fail_closed ? 'true' : 'false'} />
          <MetricBox label="429 buckets" value={summary?.rate_limited_bucket_count ?? 0} />
          <MetricBox label="active overrides" value={summary?.active_override_count ?? 0} />
        </div>
        {summary?.backend.store_status === 'degraded' && (
          <p className="mt-3 rounded-sm bg-error-bg p-3 text-sm text-error-text">
            {summary.backend.store_error_class}: {summary.backend.store_error_message}
          </p>
        )}
      </Section>

      <Section title="Override 생성">
        <form className="grid gap-3 lg:grid-cols-6" onSubmit={submitOverride}>
          <select
            value={limitName}
            onChange={(event) => onLimitNameChange(event.target.value)}
            className={inputClass}
            aria-label="Policy"
            data-testid="admin-abuse-policy"
          >
            {(policies.length ? policies : Object.keys(POLICY_IDENTITY).map((name) => ({ name }))).map((policy) => (
              <option key={policy.name} value={policy.name}>
                {policy.name}
              </option>
            ))}
          </select>
          <select
            value={action}
            onChange={(event) => setAction(event.target.value as OverrideAction)}
            className={inputClass}
            aria-label="Action"
            data-testid="admin-abuse-action"
          >
            <option value="blocked">blocked</option>
            <option value="allowed">allowed</option>
          </select>
          <input
            value={ttlMinutes}
            onChange={(event) => setTtlMinutes(event.target.value)}
            className={inputClass}
            inputMode="numeric"
            aria-label="TTL minutes"
            placeholder="TTL"
            data-testid="admin-abuse-ttl"
          />
          {(identityKind === 'ip' || identityKind === 'ip_email') && (
            <input
              value={ip}
              onChange={(event) => setIp(event.target.value)}
              className={inputClass}
              aria-label="IP"
              placeholder="IP"
              data-testid="admin-abuse-ip"
            />
          )}
          {identityKind === 'ip_email' && (
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className={inputClass}
              aria-label="Email"
              placeholder="Email"
              data-testid="admin-abuse-email"
            />
          )}
          {identityKind === 'user' && (
            <input
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              className={inputClass}
              aria-label="User ID"
              placeholder="User ID"
              data-testid="admin-abuse-user-id"
            />
          )}
          {identityKind === 'shared_token' && (
            <input
              value={sharedToken}
              onChange={(event) => setSharedToken(event.target.value)}
              className={inputClass}
              aria-label="Share token"
              placeholder="Share token"
              data-testid="admin-abuse-shared-token"
            />
          )}
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className={`${textareaClass} lg:col-span-4`}
            aria-label="사유"
            placeholder="사유"
            data-testid="admin-abuse-reason"
          />
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-primary px-3 text-sm font-semibold text-white disabled:opacity-50"
            data-testid="admin-abuse-create"
          >
            {createMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : action === 'blocked' ? (
              <Ban className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            )}
            등록
          </button>
        </form>
        <div className="mt-3">
          <input
            value={rollbackReason}
            onChange={(event) => setRollbackReason(event.target.value)}
            className={`${inputClass} w-full max-w-xl`}
            aria-label="Rollback reason"
            placeholder="Rollback reason"
            data-testid="admin-abuse-rollback-reason"
          />
        </div>
      </Section>

      <Section title="Buckets">
        <FilterBar>
          <select
            value={limitFilter}
            onChange={(event) => setLimitFilter(event.target.value)}
            className={inputClass}
            aria-label="Bucket policy filter"
            data-testid="admin-abuse-filter"
          >
            <option value="">정책 전체</option>
            {policies.map((policy) => (
              <option key={policy.name} value={policy.name}>
                {policy.name}
              </option>
            ))}
          </select>
        </FilterBar>
        <AdminTable
          columns={bucketColumns}
          rows={summary?.buckets ?? []}
          loading={summaryQuery.isLoading}
          rowKey={(row) => `${row.limit_name}:${row.bucket_hash_prefix}`}
          rowTestId={(row) => `admin-abuse-bucket-${row.limit_name}-${row.bucket_hash_prefix}`}
          empty="bucket이 없습니다."
        />
      </Section>

      <Section title="Suspicious">
        <AdminTable
          columns={suspiciousColumns}
          rows={summary?.suspicious ?? []}
          loading={summaryQuery.isLoading}
          rowKey={(row) => `${row.signal}:${row.bucket.bucket_hash_prefix}`}
          rowTestId={(row) => `admin-abuse-suspicious-${row.signal}`}
          empty="suspicious activity가 없습니다."
        />
      </Section>

      <Section title="Overrides">
        <AdminTable
          columns={overrideColumns}
          rows={summary?.overrides ?? []}
          loading={summaryQuery.isLoading}
          rowKey={(row) => row.override_id}
          rowTestId={(row) => `admin-abuse-override-${row.override_id}`}
          empty="override가 없습니다."
        />
      </Section>
    </AdminPage>
  );
}
