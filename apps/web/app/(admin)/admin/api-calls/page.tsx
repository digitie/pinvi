'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { ApiError, adminApi } from '@tripmate/api-client';
import type { AdminApiCallEntry } from '@tripmate/schemas';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { DataTable, type DataTableColumn } from '@/components/admin/DataTable';
import { apiClient } from '@/lib/api';

const formatDateTime = (value: string) => new Date(value).toLocaleString('ko-KR');

const columns: DataTableColumn<AdminApiCallEntry>[] = [
  { key: 'provider', header: 'Provider', cell: (row) => row.provider },
  {
    key: 'endpoint',
    header: 'Endpoint',
    cell: (row) => <span className="font-mono text-xs">{row.endpoint}</span>,
  },
  { key: 'status', header: 'Status', cell: (row) => row.status_code ?? '—' },
  { key: 'latency', header: 'Latency', cell: (row) => `${row.latency_ms ?? '—'} ms` },
  { key: 'error', header: 'Error', cell: (row) => row.error_class ?? '—' },
  {
    key: 'request',
    header: 'Request',
    cell: (row) => (
      <span className="font-mono text-xs" title={row.request_id ?? undefined}>
        {row.request_id?.slice(0, 8) ?? '—'}
      </span>
    ),
  },
  { key: 'occurred', header: '발생', cell: (row) => formatDateTime(row.occurred_at) },
];

export default function AdminApiCallsPage() {
  const [rows, setRows] = useState<AdminApiCallEntry[]>([]);
  const [providerInput, setProviderInput] = useState('');
  const [statusInput, setStatusInput] = useState('');
  const [errorClassInput, setErrorClassInput] = useState('');
  const [filters, setFilters] = useState({ provider: '', statusCode: '', errorClass: '' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    adminApi(apiClient)
      .listApiCalls({
        provider: filters.provider || undefined,
        statusCode: filters.statusCode ? Number(filters.statusCode) : undefined,
        errorClass: filters.errorClass || undefined,
        limit: 100,
      })
      .then((result) => {
        if (cancelled) return;
        setRows(result);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : 'API 호출 로그를 불러오지 못했습니다.');
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [filters]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFilters({
      provider: providerInput.trim(),
      statusCode: statusInput.trim(),
      errorClass: errorClassInput.trim(),
    });
  };

  return (
    <AdminPage title="API 호출 로그" description="app.api_call_log read-only 조회">
      <FilterBar>
        <form onSubmit={onSubmit} className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label htmlFor="admin-api-provider" className="text-xs text-muted">
            Provider
          </label>
          <input
            id="admin-api-provider"
            value={providerInput}
            onChange={(event) => setProviderInput(event.target.value)}
            className="w-36 rounded-sm border border-hairline px-2 py-1 text-sm"
            data-testid="admin-api-calls-provider"
          />
          <label htmlFor="admin-api-status" className="text-xs text-muted">
            Status
          </label>
          <input
            id="admin-api-status"
            value={statusInput}
            onChange={(event) => setStatusInput(event.target.value)}
            inputMode="numeric"
            className="w-24 rounded-sm border border-hairline px-2 py-1 text-sm"
            data-testid="admin-api-calls-status"
          />
          <label htmlFor="admin-api-error" className="text-xs text-muted">
            Error
          </label>
          <input
            id="admin-api-error"
            value={errorClassInput}
            onChange={(event) => setErrorClassInput(event.target.value)}
            className="w-40 rounded-sm border border-hairline px-2 py-1 text-sm"
            data-testid="admin-api-calls-error"
          />
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-api-calls-submit"
          >
            조회
          </button>
        </form>
      </FilterBar>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>
      )}

      <DataTable columns={columns} rows={rows} loading={loading} rowKey={(row) => String(row.log_id)} />
    </AdminPage>
  );
}
