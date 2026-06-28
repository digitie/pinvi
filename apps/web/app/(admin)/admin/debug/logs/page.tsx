'use client';

import { useRouter } from 'next/navigation';
import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  queryKeys,
  type AdminSystemLogListParams,
  type AdminUpstreamApiCallLogListParams,
} from '@pinvi/api-client';
import type { AdminUpstreamApiCallLogRecord, AdminUpstreamSystemLogRecord } from '@pinvi/schemas';
import { RefreshCw, Search } from 'lucide-react';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const LEVEL_OPTIONS = [
  { value: 'all', label: 'level 전체' },
  { value: 'debug', label: 'debug' },
  { value: 'info', label: 'info' },
  { value: 'warning', label: 'warning' },
  { value: 'error', label: 'error' },
  { value: 'critical', label: 'critical' },
] as const;

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '—';
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
      {message}
    </p>
  );
}

export default function AdminDebugLogsPage() {
  const router = useRouter();
  const [level, setLevel] = useState<(typeof LEVEL_OPTIONS)[number]['value']>('error');
  const [source, setSource] = useState('');
  const [queryInput, setQueryInput] = useState('');
  const [submittedQ, setSubmittedQ] = useState('');
  const [method, setMethod] = useState('');
  const [minStatus, setMinStatus] = useState('500');
  const [path, setPath] = useState('');
  const [timelineRequestId, setTimelineRequestId] = useState('');
  const [timelineError, setTimelineError] = useState<string | null>(null);

  const systemParams = useMemo<AdminSystemLogListParams>(
    () => ({
      level: level === 'all' ? undefined : level,
      source: source.trim() || undefined,
      q: submittedQ || undefined,
      pageSize: 50,
    }),
    [level, source, submittedQ],
  );
  const apiParams = useMemo<AdminUpstreamApiCallLogListParams>(
    () => ({
      method: method.trim() || undefined,
      minStatus: minStatus.trim() ? Number(minStatus) : undefined,
      path: path.trim() || undefined,
      pageSize: 50,
    }),
    [method, minStatus, path],
  );

  const systemLogsQuery = useQuery({
    queryKey: queryKeys.admin.upstreamSystemLogs(systemParams),
    queryFn: () => adminApi(apiClient).listUpstreamSystemLogs(systemParams),
    placeholderData: keepPreviousData,
  });
  const apiLogsQuery = useQuery({
    queryKey: queryKeys.admin.upstreamApiCallLogs(apiParams),
    queryFn: () => adminApi(apiClient).listUpstreamApiCallLogs(apiParams),
    placeholderData: keepPreviousData,
  });

  const systemError = systemLogsQuery.isError
    ? systemLogsQuery.error instanceof ApiError
      ? systemLogsQuery.error.message
      : 'system log 조회에 실패했습니다.'
    : null;
  const apiError = apiLogsQuery.isError
    ? apiLogsQuery.error instanceof ApiError
      ? apiLogsQuery.error.message
      : 'API call log 조회에 실패했습니다.'
    : null;

  const systemColumns: AdminTableColumn<AdminUpstreamSystemLogRecord>[] = [
    {
      key: 'log',
      header: 'log',
      sortable: true,
      sortValue: (item) => item.log_id,
      cell: (item) => (
        <div>
          <div className="font-mono text-xs">{item.log_id}</div>
          <div className="font-mono text-xs text-muted">{item.request_id ?? '—'}</div>
        </div>
      ),
    },
    {
      key: 'level',
      header: 'level',
      sortable: true,
      sortValue: (item) => item.level,
      cell: (item) => item.level,
    },
    {
      key: 'source',
      header: 'source',
      sortable: true,
      sortValue: (item) => item.source,
      cell: (item) => item.source,
    },
    {
      key: 'event',
      header: 'event',
      sortable: true,
      sortValue: (item) => item.event,
      cell: (item) => item.event,
    },
    {
      key: 'message',
      header: 'message',
      sortable: true,
      sortValue: (item) => item.message,
      cell: (item) => item.message,
    },
    {
      key: 'created',
      header: '생성',
      sortable: true,
      sortValue: (item) => new Date(item.created_at).getTime(),
      cell: (item) => formatDateTime(item.created_at),
    },
  ];

  const apiColumns: AdminTableColumn<AdminUpstreamApiCallLogRecord>[] = [
    {
      key: 'log',
      header: 'log',
      sortable: true,
      sortValue: (item) => item.log_id,
      cell: (item) => (
        <div>
          <div className="font-mono text-xs">{item.log_id}</div>
          <div className="font-mono text-xs text-muted">{item.request_id ?? '—'}</div>
        </div>
      ),
    },
    {
      key: 'method',
      header: 'method',
      sortable: true,
      sortValue: (item) => item.method,
      cell: (item) => item.method,
    },
    {
      key: 'path',
      header: 'path',
      sortable: true,
      sortValue: (item) => item.path,
      cell: (item) => <span className="font-mono text-xs">{item.path}</span>,
    },
    {
      key: 'status',
      header: 'status',
      sortable: true,
      sortValue: (item) => item.status_code,
      cell: (item) => item.status_code,
      align: 'right',
    },
    {
      key: 'duration',
      header: 'duration',
      sortable: true,
      sortValue: (item) => item.duration_ms,
      cell: (item) => `${item.duration_ms}ms`,
      align: 'right',
    },
    {
      key: 'created',
      header: '생성',
      sortable: true,
      sortValue: (item) => new Date(item.created_at).getTime(),
      cell: (item) => formatDateTime(item.created_at),
    },
  ];

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmittedQ(queryInput.trim());
  };
  const onTimelineSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextRequestId = timelineRequestId.trim();
    if (!UUID_RE.test(nextRequestId)) {
      setTimelineError('UUID request id를 입력하세요.');
      return;
    }
    setTimelineError(null);
    router.push(`/admin/debug/request/${encodeURIComponent(nextRequestId)}`);
  };

  return (
    <AdminPage
      title="Debug logs"
      description="kor-travel-map sanitized system/API logs"
      actions={
        <button
          type="button"
          onClick={() => {
            void systemLogsQuery.refetch();
            void apiLogsQuery.refetch();
          }}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
          data-testid="admin-debug-refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          갱신
        </button>
      }
    >
      <FilterBar>
        <form
          onSubmit={onTimelineSearch}
          className="flex min-w-0 flex-1 flex-wrap items-center gap-2"
        >
          <label htmlFor="admin-debug-request-id" className="text-xs text-muted">
            Request ID
          </label>
          <input
            id="admin-debug-request-id"
            value={timelineRequestId}
            onChange={(event) => setTimelineRequestId(event.target.value)}
            className={`${inputClass} w-[24rem] max-w-full font-mono`}
            placeholder="00000000-0000-0000-0000-000000000000"
            data-testid="admin-debug-request-id"
          />
          <button
            type="submit"
            className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-debug-request-submit"
          >
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
            Timeline
          </button>
        </form>
      </FilterBar>

      {timelineError && <ErrorBox message={timelineError} />}

      <FilterBar>
        <form onSubmit={onSearch} className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <select
            value={level}
            onChange={(event) => setLevel(event.target.value as typeof level)}
            className={inputClass}
            data-testid="admin-debug-level"
          >
            {LEVEL_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <input
            value={source}
            onChange={(event) => setSource(event.target.value)}
            className={`${inputClass} w-36`}
            placeholder="source"
            data-testid="admin-debug-source"
          />
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-2 h-4 w-4 text-muted" />
            <input
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              className={`${inputClass} w-48 pl-7`}
              placeholder="message"
              data-testid="admin-debug-q"
            />
          </div>
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-debug-submit"
          >
            조회
          </button>
        </form>
        <input
          value={method}
          onChange={(event) => setMethod(event.target.value)}
          className={`${inputClass} w-20`}
          placeholder="method"
          data-testid="admin-debug-method"
        />
        <input
          value={minStatus}
          onChange={(event) => setMinStatus(event.target.value)}
          className={`${inputClass} w-24`}
          inputMode="numeric"
          placeholder="min"
          data-testid="admin-debug-min-status"
        />
        <input
          value={path}
          onChange={(event) => setPath(event.target.value)}
          className={`${inputClass} w-40`}
          placeholder="path"
          data-testid="admin-debug-path"
        />
      </FilterBar>

      {systemError && <ErrorBox message={systemError} />}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">System logs</h2>
        <AdminTable
          columns={systemColumns}
          rows={systemLogsQuery.data?.items ?? []}
          loading={systemLogsQuery.isLoading}
          rowKey={(item) => item.log_id}
          rowTestId={(item) => `admin-debug-system-row-${item.log_id}`}
          empty="system log가 없습니다."
        />
      </section>

      {apiError && <ErrorBox message={apiError} />}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">API call logs</h2>
        <AdminTable
          columns={apiColumns}
          rows={apiLogsQuery.data?.items ?? []}
          loading={apiLogsQuery.isLoading}
          rowKey={(item) => item.log_id}
          rowTestId={(item) => `admin-debug-api-row-${item.log_id}`}
          empty="API call log가 없습니다."
        />
      </section>
    </AdminPage>
  );
}
