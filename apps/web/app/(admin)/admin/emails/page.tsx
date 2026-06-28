'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import { AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react';
import type { AdminEmailDeliverability, AdminEmailEntry } from '@pinvi/schemas';
import { AdminPage, FilterBar, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { apiClient } from '@/lib/api';

const STATUSES = [
  { value: '', label: '전체' },
  { value: 'pending', label: '대기' },
  { value: 'sent', label: '전송' },
  { value: 'delivered', label: '도달' },
  { value: 'delivery_delayed', label: '지연' },
  { value: 'bounced', label: '반송' },
  { value: 'complained', label: '신고' },
  { value: 'suppressed', label: '차단' },
  { value: 'failed', label: '실패' },
];

function formatMetric(value: number | null | undefined) {
  return new Intl.NumberFormat('ko-KR').format(value ?? 0);
}

function statusClass(status: AdminEmailDeliverability['status']) {
  if (status === 'ok') return 'bg-success-bg text-success-text';
  if (status === 'degraded') return 'bg-error-bg text-error-text';
  return 'bg-surface-soft text-muted';
}

function checkClass(status: 'ok' | 'warn' | 'error' | 'unknown') {
  if (status === 'ok') return 'bg-success-bg text-success-text';
  if (status === 'error') return 'bg-error-bg text-error-text';
  return 'bg-surface-soft text-muted';
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

export default function AdminEmailsPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');

  const emailsQuery = useQuery({
    queryKey: queryKeys.admin.emails({ status: statusFilter, limit: 100 }),
    queryFn: () =>
      adminApi(apiClient).listEmails({ status: statusFilter || undefined, limit: 100 }),
  });

  const deliverabilityQuery = useQuery({
    queryKey: queryKeys.admin.emailDeliverability(),
    queryFn: () => adminApi(apiClient).getEmailDeliverability(),
  });

  const resendMutation = useMutation({
    mutationFn: (emailId: string) => adminApi(apiClient).resendEmail(emailId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.admin.emailsAll() }),
  });

  const error = emailsQuery.isError
    ? emailsQuery.error instanceof ApiError
      ? emailsQuery.error.message
      : '조회 실패'
    : deliverabilityQuery.isError
      ? deliverabilityQuery.error instanceof ApiError
        ? deliverabilityQuery.error.message
        : 'deliverability 조회 실패'
      : resendMutation.isError
        ? resendMutation.error instanceof ApiError
          ? resendMutation.error.message
          : '재발송 실패'
        : null;

  const resendingId = resendMutation.isPending ? resendMutation.variables : null;
  const deliverability = deliverabilityQuery.data ?? null;
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.admin.emailsAll() });
  };

  const columns: AdminTableColumn<AdminEmailEntry>[] = [
    {
      key: 'to_email',
      header: '수신자',
      sortable: true,
      sortValue: (r) => r.to_email,
      cell: (r) => <span className="font-mono text-xs">{r.to_email}</span>,
    },
    {
      key: 'template',
      header: '템플릿',
      sortable: true,
      sortValue: (r) => r.template,
      cell: (r) => r.template,
    },
    {
      key: 'status',
      header: '상태',
      sortable: true,
      sortValue: (r) => r.status,
      cell: (r) => r.status,
    },
    {
      key: 'attempts',
      header: '시도',
      sortable: true,
      sortValue: (r) => r.attempts,
      cell: (r) => r.attempts,
    },
    {
      key: 'bounce',
      header: 'bounce',
      cell: (r) => r.bounce_type ?? '—',
    },
    {
      key: 'scheduled',
      header: '예약',
      sortable: true,
      sortValue: (r) => new Date(r.scheduled_at).getTime(),
      cell: (r) => new Date(r.scheduled_at).toLocaleString('ko-KR'),
    },
    {
      key: 'action',
      header: '재발송',
      cell: (r) => (
        <button
          type="button"
          disabled={resendingId === r.email_id}
          onClick={(e) => {
            e.stopPropagation();
            resendMutation.mutate(r.email_id);
          }}
          className="rounded-sm border border-primary px-2 py-1 text-xs text-primary disabled:opacity-50"
          data-testid={`admin-email-resend-${r.email_id}`}
        >
          {resendingId === r.email_id ? '...' : '재발송'}
        </button>
      ),
    },
  ];

  return (
    <AdminPage
      title="이메일 큐"
      description="email_queue 행 + deliverability 상태"
      actions={
        <button
          type="button"
          onClick={refresh}
          className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
          data-testid="admin-emails-refresh"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          새로고침
        </button>
      }
    >
      <Section title="Deliverability">
        <div className="grid gap-3 text-sm lg:grid-cols-4" data-testid="admin-email-deliverability">
          <MetricBox
            label="status"
            value={deliverability?.status}
            testId="admin-email-deliverability-status"
          />
          <MetricBox label="from domain" value={deliverability?.domain.from_domain} />
          <MetricBox
            label="domain"
            value={deliverability?.domain.domain_status ?? deliverability?.domain.error_class}
            testId="admin-email-domain-status"
          />
          <MetricBox
            label="active suppressions"
            value={deliverability?.suppression.active_suppressions}
            testId="admin-email-suppression-count"
          />
        </div>

        <div className="mt-3 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-sm border border-hairline p-3">
            <div className="mb-2 flex items-center gap-2 font-semibold text-ink">
              {deliverability?.status === 'ok' ? (
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              ) : (
                <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              )}
              <span
                className={`rounded-sm px-2 py-1 text-xs ${statusClass(deliverability?.status ?? 'unknown')}`}
              >
                {deliverability?.status ?? 'unknown'}
              </span>
            </div>
            <div className="grid gap-1 text-xs text-muted">
              <div>api {deliverability?.resend_api_configured ? 'configured' : 'missing'}</div>
              <div>console {deliverability?.console_mode ? 'on' : 'off'}</div>
              <div>sending {deliverability?.domain.sending_capability ?? '-'}</div>
            </div>
          </div>

          <div className="rounded-sm border border-hairline p-3">
            <div className="mb-2 text-sm font-semibold text-ink">Webhook</div>
            <div className="grid gap-1 text-xs text-muted">
              <div>
                signature {deliverability?.webhook.signature_configured ? 'configured' : 'missing'}
              </div>
              <div>
                unsigned {deliverability?.webhook.unsigned_allowed ? 'allowed' : 'disabled'}
              </div>
              <div>
                bounced {formatMetric(deliverability?.webhook.recent_events['email.bounced'])}
              </div>
            </div>
          </div>

          <div className="rounded-sm border border-hairline p-3">
            <div className="mb-2 text-sm font-semibold text-ink">Queue</div>
            <div className="grid grid-cols-2 gap-1 text-xs text-muted">
              <div>pending {formatMetric(deliverability?.queue.pending)}</div>
              <div>failed {formatMetric(deliverability?.queue.failed)}</div>
              <div>delayed {formatMetric(deliverability?.queue.delivery_delayed)}</div>
              <div>suppressed {formatMetric(deliverability?.queue.suppressed)}</div>
            </div>
          </div>

          <div className="rounded-sm border border-hairline p-3">
            <div className="mb-2 text-sm font-semibold text-ink">Checks</div>
            <div className="flex flex-wrap gap-1" data-testid="admin-email-checks">
              {(deliverability?.checks ?? []).map((check) => (
                <span
                  key={check.key}
                  className={`rounded-sm px-2 py-1 text-xs ${checkClass(check.status)}`}
                  title={check.message ?? undefined}
                >
                  {check.label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </Section>

      <FilterBar>
        <label htmlFor="admin-emails-status-filter" className="text-xs text-muted">
          상태
        </label>
        <select
          id="admin-emails-status-filter"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            // 목록 컨텍스트가 바뀌면 이전 재발송 실패 배너를 정리(원래 reload-시-에러초기화 동작 복원).
            resendMutation.reset();
          }}
          className="rounded-sm border border-hairline px-2 py-1 text-sm"
          data-testid="admin-emails-status-filter"
        >
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </FilterBar>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
          {error}
        </p>
      )}

      <AdminTable
        columns={columns}
        rows={emailsQuery.data ?? []}
        loading={emailsQuery.isLoading}
        rowKey={(r) => r.email_id}
        rowTestId={(r) => `admin-emails-row-${r.email_id}`}
      />
    </AdminPage>
  );
}
