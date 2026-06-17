'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminEmailEntry } from '@pinvi/schemas';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const STATUSES = [
  { value: '', label: '전체' },
  { value: 'pending', label: '대기' },
  { value: 'sent', label: '전송' },
  { value: 'delivered', label: '도달' },
  { value: 'bounced', label: '반송' },
  { value: 'complained', label: '신고' },
  { value: 'failed', label: '실패' },
];

export default function AdminEmailsPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');

  const emailsQuery = useQuery({
    queryKey: queryKeys.admin.emails({ status: statusFilter, limit: 100 }),
    queryFn: () => adminApi(apiClient).listEmails({ status: statusFilter || undefined, limit: 100 }),
  });

  const resendMutation = useMutation({
    mutationFn: (emailId: string) => adminApi(apiClient).resendEmail(emailId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'emails'] }),
  });

  const error = emailsQuery.isError
    ? emailsQuery.error instanceof ApiError
      ? emailsQuery.error.message
      : '조회 실패'
    : resendMutation.isError
      ? resendMutation.error instanceof ApiError
        ? resendMutation.error.message
        : '재발송 실패'
      : null;

  const resendingId = resendMutation.isPending ? resendMutation.variables : null;

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
    <AdminPage title="이메일 큐" description="email_queue 행 + 재발송 trigger (status=pending로 reset).">
      <FilterBar>
        <label htmlFor="admin-emails-status-filter" className="text-xs text-muted">상태</label>
        <select
          id="admin-emails-status-filter"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
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
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>
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
