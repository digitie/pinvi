'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminLocationAuditEntry } from '@pinvi/schemas';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { apiClient } from '@/lib/api';

const formatDateTime = (value: string) => new Date(value).toLocaleString('ko-KR');

const columns: AdminTableColumn<AdminLocationAuditEntry>[] = [
  {
    key: 'log_id',
    header: '#',
    width: '80px',
    sortable: true,
    sortValue: (row) => row.log_id,
    cell: (row) => row.log_id,
  },
  {
    key: 'user',
    header: 'User',
    cell: (row) => (
      <span className="font-mono text-xs" title={row.user_id}>
        {row.user_id.slice(0, 8)}
      </span>
    ),
  },
  { key: 'purpose', header: 'Purpose', sortable: true, sortValue: (row) => row.purpose, cell: (row) => row.purpose },
  {
    key: 'endpoint',
    header: 'Endpoint',
    sortable: true,
    sortValue: (row) => row.endpoint,
    cell: (row) => <span className="font-mono text-xs">{row.endpoint}</span>,
  },
  {
    key: 'coord',
    header: '좌표',
    cell: (row) =>
      row.lat_masked && row.lng_masked ? `${row.lng_masked}, ${row.lat_masked}` : '—',
  },
  {
    key: 'request',
    header: 'Request',
    cell: (row) => (
      <span className="font-mono text-xs" title={row.request_id}>
        {row.request_id.slice(0, 8)}
      </span>
    ),
  },
  {
    key: 'hash',
    header: 'hash[:8]',
    cell: (row) => (
      <span className="font-mono text-xs" title={row.content_hash}>
        {row.content_hash.slice(0, 8)}
      </span>
    ),
  },
  {
    key: 'occurred',
    header: '발생',
    sortable: true,
    sortValue: (row) => new Date(row.occurred_at).getTime(),
    cell: (row) => formatDateTime(row.occurred_at),
  },
];

export default function AdminLocationAuditPage() {
  const [userIdInput, setUserIdInput] = useState('');
  const [fromInput, setFromInput] = useState('');
  const [toInput, setToInput] = useState('');
  const [filters, setFilters] = useState({ userId: '', from: '', to: '' });

  const locationAuditQuery = useQuery({
    queryKey: queryKeys.admin.locationAudit({
      userId: filters.userId || undefined,
      from: filters.from || undefined,
      to: filters.to || undefined,
      limit: 100,
    }),
    queryFn: () =>
      adminApi(apiClient).listLocationAudit({
        userId: filters.userId || undefined,
        from: filters.from || undefined,
        to: filters.to || undefined,
        limit: 100,
      }),
  });

  const rows = locationAuditQuery.data ?? [];
  const error = locationAuditQuery.isError
    ? locationAuditQuery.error instanceof ApiError
      ? locationAuditQuery.error.message
      : '위치 감사 로그를 불러오지 못했습니다.'
    : null;

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFilters({
      userId: userIdInput.trim(),
      from: fromInput ? new Date(fromInput).toISOString() : '',
      to: toInput ? new Date(toInput).toISOString() : '',
    });
  };

  return (
    <AdminPage
      title="위치 감사 로그"
      description="location_access_log CPO 전용 조회. 좌표는 4자리로 마스킹됩니다."
      actions={
        <Link
          href="/admin/audit"
          className="rounded-sm border border-hairline bg-white px-3 py-2 text-sm font-semibold text-ink"
        >
          일반 감사 로그
        </Link>
      }
    >
      <FilterBar>
        <form onSubmit={onSubmit} className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label htmlFor="admin-location-user" className="text-xs text-muted">
            User ID
          </label>
          <input
            id="admin-location-user"
            value={userIdInput}
            onChange={(event) => setUserIdInput(event.target.value)}
            className="min-w-64 rounded-sm border border-hairline px-2 py-1 text-sm"
            data-testid="admin-location-user"
          />
          <label htmlFor="admin-location-from" className="text-xs text-muted">
            From
          </label>
          <input
            id="admin-location-from"
            type="datetime-local"
            value={fromInput}
            onChange={(event) => setFromInput(event.target.value)}
            className="rounded-sm border border-hairline px-2 py-1 text-sm"
            data-testid="admin-location-from"
          />
          <label htmlFor="admin-location-to" className="text-xs text-muted">
            To
          </label>
          <input
            id="admin-location-to"
            type="datetime-local"
            value={toInput}
            onChange={(event) => setToInput(event.target.value)}
            className="rounded-sm border border-hairline px-2 py-1 text-sm"
            data-testid="admin-location-to"
          />
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-location-submit"
          >
            조회
          </button>
        </form>
      </FilterBar>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>
      )}

      <AdminTable
        columns={columns}
        rows={rows}
        loading={locationAuditQuery.isLoading}
        rowKey={(row) => String(row.log_id)}
        rowTestId={(row) => `admin-location-row-${row.log_id}`}
        virtualized
        maxHeight="70vh"
      />
    </AdminPage>
  );
}
