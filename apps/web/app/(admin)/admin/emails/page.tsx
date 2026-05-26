'use client';

import { useEffect, useState } from 'react';
import { ApiClient, ApiError, adminApi } from '@tripmate/api-client';
import type { AdminEmailEntry } from '@tripmate/schemas';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { DataTable, type DataTableColumn } from '@/components/admin/DataTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? 'http://localhost:8001',
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
  const [rows, setRows] = useState<AdminEmailEntry[]>([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resendingId, setResendingId] = useState<string | null>(null);

  const reload = (status: string) => {
    setLoading(true);
    adminApi(apiClient)
      .listEmails({ status: status || undefined, limit: 100 })
      .then((res) => {
        setRows(res);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : '조회 실패'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    reload(statusFilter);
  }, [statusFilter]);

  const onResend = async (id: string) => {
    setResendingId(id);
    try {
      await adminApi(apiClient).resendEmail(id);
      reload(statusFilter);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '재발송 실패');
    } finally {
      setResendingId(null);
    }
  };

  const columns: DataTableColumn<AdminEmailEntry>[] = [
    {
      key: 'to_email',
      header: '수신자',
      cell: (r) => <span className="font-mono text-xs">{r.to_email}</span>,
    },
    { key: 'template', header: '템플릿', cell: (r) => r.template },
    { key: 'status', header: '상태', cell: (r) => r.status },
    { key: 'attempts', header: '시도', cell: (r) => r.attempts },
    {
      key: 'bounce',
      header: 'bounce',
      cell: (r) => r.bounce_type ?? '—',
    },
    {
      key: 'scheduled',
      header: '예약',
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
            onResend(r.email_id);
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
        <label className="text-xs text-muted">상태</label>
        <select
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
        <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>
      )}

      <DataTable columns={columns} rows={rows} loading={loading} rowKey={(r) => r.email_id} />
    </AdminPage>
  );
}
