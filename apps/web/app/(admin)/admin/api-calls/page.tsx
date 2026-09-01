'use client';

import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminApiCallEntry } from '@pinvi/schemas';
import { AdminPage } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FilterActions, FilterBar, FilterField } from '@/components/admin/filter-bar';
import { Button } from '@/components/admin/ui/button';
import { Input } from '@/components/admin/ui/input';
import { apiClient } from '@/lib/api';

const formatDateTime = (value: string) => new Date(value).toLocaleString('ko-KR');

const columns: AdminTableColumn<AdminApiCallEntry>[] = [
  {
    key: 'provider',
    header: 'Provider',
    sortable: true,
    sortValue: (row) => row.provider,
    cell: (row) => row.provider,
  },
  {
    key: 'endpoint',
    header: 'Endpoint',
    sortable: true,
    sortValue: (row) => row.endpoint,
    cell: (row) => <span className="font-mono text-xs">{row.endpoint}</span>,
  },
  {
    key: 'status',
    header: 'Status',
    sortable: true,
    sortValue: (row) => row.status_code ?? 0,
    cell: (row) => row.status_code ?? '—',
  },
  {
    key: 'latency',
    header: 'Latency',
    sortable: true,
    sortValue: (row) => row.latency_ms ?? 0,
    cell: (row) => `${row.latency_ms ?? '—'} ms`,
  },
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
  {
    key: 'occurred',
    header: '발생',
    sortable: true,
    sortValue: (row) => new Date(row.occurred_at).getTime(),
    cell: (row) => formatDateTime(row.occurred_at),
  },
];

export default function AdminApiCallsPage() {
  const [providerInput, setProviderInput] = useState('');
  const [statusInput, setStatusInput] = useState('');
  const [errorClassInput, setErrorClassInput] = useState('');
  const [filters, setFilters] = useState({ provider: '', statusCode: '', errorClass: '' });

  const statusCode = filters.statusCode ? Number(filters.statusCode) : undefined;

  const apiCallsQuery = useQuery({
    queryKey: queryKeys.admin.apiCalls({
      provider: filters.provider || undefined,
      statusCode,
      errorClass: filters.errorClass || undefined,
      limit: 100,
    }),
    queryFn: () =>
      adminApi(apiClient).listApiCalls({
        provider: filters.provider || undefined,
        statusCode,
        errorClass: filters.errorClass || undefined,
        limit: 100,
      }),
  });

  const rows = apiCallsQuery.data ?? [];
  const error = apiCallsQuery.isError
    ? apiCallsQuery.error instanceof ApiError
      ? apiCallsQuery.error.message
      : 'API 호출 로그를 불러오지 못했습니다.'
    : null;

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
      {/* 세 필터 모두 제출로만 적용된다(전환 전과 동일) — form이 툴바 전체를 감싼다.
          폭(`w-36`/`w-24`/`w-40`)은 input이 아니라 FilterField가 갖는다: Input은 `w-full`이라
          라벨+컨트롤 열의 폭을 따라간다. */}
      <form onSubmit={onSubmit}>
        <FilterBar>
          <FilterField className="w-36" htmlFor="admin-api-provider" label="Provider">
            <Input
              id="admin-api-provider"
              value={providerInput}
              onChange={(event) => setProviderInput(event.target.value)}
              data-testid="admin-api-calls-provider"
            />
          </FilterField>
          <FilterField className="w-24" htmlFor="admin-api-status" label="Status">
            <Input
              id="admin-api-status"
              value={statusInput}
              onChange={(event) => setStatusInput(event.target.value)}
              inputMode="numeric"
              data-testid="admin-api-calls-status"
            />
          </FilterField>
          <FilterField className="w-40" htmlFor="admin-api-error" label="Error">
            <Input
              id="admin-api-error"
              value={errorClassInput}
              onChange={(event) => setErrorClassInput(event.target.value)}
              data-testid="admin-api-calls-error"
            />
          </FilterField>
          <FilterActions>
            <Button type="submit" variant="outline" data-testid="admin-api-calls-submit">
              조회
            </Button>
          </FilterActions>
        </FilterBar>
      </form>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
          {error}
        </p>
      )}

      <AdminTable
        columns={columns}
        rows={rows}
        loading={apiCallsQuery.isLoading}
        rowKey={(row) => String(row.log_id)}
        rowTestId={(row) => `admin-api-calls-row-${row.request_id ?? row.occurred_at}`}
        virtualized
        maxHeight="70dvh"
      />
    </AdminPage>
  );
}
