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
import { Pause, Play, Radio, RefreshCw, Search } from 'lucide-react';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FilterActions, FilterBar, FilterField } from '@/components/admin/filter-bar';
import { Button } from '@/components/admin/ui/button';
import { Input } from '@/components/admin/ui/input';
import { NativeSelect } from '@/components/admin/ui/native-select';
import { NativeSelectOption } from '@/components/admin/ui/native-select-option';

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
  const [liveEnabled, setLiveEnabled] = useState(false);
  const [livePaused, setLivePaused] = useState(false);

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

  const streamStatusQuery = useQuery({
    queryKey: queryKeys.admin.debugLogStreamStatus(),
    queryFn: () => adminApi(apiClient).getDebugLogStreamStatus(),
  });
  const pollIntervalMs = streamStatusQuery.data?.poll_interval_ms ?? 5000;
  const liveRefetchInterval = liveEnabled && !livePaused ? pollIntervalMs : false;

  const systemLogsQuery = useQuery({
    queryKey: queryKeys.admin.upstreamSystemLogs(systemParams),
    queryFn: () => adminApi(apiClient).listUpstreamSystemLogs(systemParams),
    placeholderData: keepPreviousData,
    refetchInterval: liveRefetchInterval,
  });
  const apiLogsQuery = useQuery({
    queryKey: queryKeys.admin.upstreamApiCallLogs(apiParams),
    queryFn: () => adminApi(apiClient).listUpstreamApiCallLogs(apiParams),
    placeholderData: keepPreviousData,
    refetchInterval: liveRefetchInterval,
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
  const onLiveToggle = () => {
    const nextEnabled = !liveEnabled;
    setLiveEnabled(nextEnabled);
    setLivePaused(false);
    if (nextEnabled) {
      void systemLogsQuery.refetch();
      void apiLogsQuery.refetch();
    }
  };
  const onPauseToggle = () => {
    const nextPaused = !livePaused;
    setLivePaused(nextPaused);
    if (liveEnabled && livePaused) {
      void systemLogsQuery.refetch();
      void apiLogsQuery.refetch();
    }
  };
  const liveState = liveEnabled ? (livePaused ? 'paused' : 'live') : 'off';

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
          className="flex min-w-0 flex-1 flex-wrap items-end gap-x-3 gap-y-2"
        >
          <FilterField
            className="w-96 max-w-full"
            htmlFor="admin-debug-request-id"
            label="Request ID"
          >
            <Input
              id="admin-debug-request-id"
              value={timelineRequestId}
              onChange={(event) => setTimelineRequestId(event.target.value)}
              className="font-mono"
              placeholder="00000000-0000-0000-0000-000000000000"
              data-testid="admin-debug-request-id"
            />
          </FilterField>
          <FilterActions>
            <Button type="submit" variant="outline" data-testid="admin-debug-request-submit">
              <Search aria-hidden="true" />
              Timeline
            </Button>
          </FilterActions>
        </form>
      </FilterBar>

      {timelineError && <ErrorBox message={timelineError} />}

      <FilterBar>
        <div
          className="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-sm"
          data-testid="admin-debug-live-status"
        >
          <Radio className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
          <span className="font-mono">{streamStatusQuery.data?.mode ?? 'polling'}</span>
          <span className="rounded-sm border border-hairline px-2 py-0.5 font-mono text-xs">
            {liveState}
          </span>
          <span className="font-mono text-xs text-muted">{pollIntervalMs / 1000}s</span>
        </div>
        <button
          type="button"
          onClick={onLiveToggle}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
          data-testid="admin-debug-live-toggle"
        >
          <Radio className="h-3.5 w-3.5" aria-hidden="true" />
          {liveEnabled ? 'Live 끄기' : 'Live 켜기'}
        </button>
        <button
          type="button"
          onClick={onPauseToggle}
          disabled={!liveEnabled}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm disabled:opacity-50"
          data-testid="admin-debug-live-pause"
        >
          {livePaused ? (
            <Play className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <Pause className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          {livePaused ? '재개' : '일시정지'}
        </button>
      </FilterBar>

      <FilterBar>
        {/* system log 3종은 전환 전과 같이 한 form 안에 둔다(레벨/소스는 즉시, 메시지 검색만
            제출로 적용). API call log 3종은 form 밖이라 입력 즉시 적용된다. */}
        <form
          onSubmit={onSearch}
          className="flex min-w-0 flex-1 flex-wrap items-end gap-x-3 gap-y-2"
        >
          <FilterField htmlFor="admin-debug-level" label="레벨">
            <NativeSelect
              id="admin-debug-level"
              value={level}
              onChange={(event) => setLevel(event.target.value as typeof level)}
              data-testid="admin-debug-level"
            >
              {LEVEL_OPTIONS.map((item) => (
                <NativeSelectOption key={item.value} value={item.value}>
                  {item.label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </FilterField>
          <FilterField className="w-36" htmlFor="admin-debug-source" label="소스">
            <Input
              id="admin-debug-source"
              value={source}
              onChange={(event) => setSource(event.target.value)}
              placeholder="source"
              data-testid="admin-debug-source"
            />
          </FilterField>
          <FilterField className="w-48" htmlFor="admin-debug-q" label="메시지 검색">
            <div className="relative">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted"
                aria-hidden="true"
              />
              <Input
                id="admin-debug-q"
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
                className="pl-9"
                placeholder="message"
                data-testid="admin-debug-q"
              />
            </div>
          </FilterField>
          <FilterActions>
            <Button type="submit" variant="outline" data-testid="admin-debug-submit">
              조회
            </Button>
          </FilterActions>
        </form>
        <FilterField className="w-20" htmlFor="admin-debug-method" label="메서드">
          <Input
            id="admin-debug-method"
            value={method}
            onChange={(event) => setMethod(event.target.value)}
            placeholder="method"
            data-testid="admin-debug-method"
          />
        </FilterField>
        <FilterField className="w-24" htmlFor="admin-debug-min-status" label="최소 status">
          <Input
            id="admin-debug-min-status"
            value={minStatus}
            onChange={(event) => setMinStatus(event.target.value)}
            inputMode="numeric"
            placeholder="min"
            data-testid="admin-debug-min-status"
          />
        </FilterField>
        <FilterField className="w-40" htmlFor="admin-debug-path" label="경로">
          <Input
            id="admin-debug-path"
            value={path}
            onChange={(event) => setPath(event.target.value)}
            placeholder="path"
            data-testid="admin-debug-path"
          />
        </FilterField>
      </FilterBar>

      {systemError && <ErrorBox message={systemError} />}

      <Section title="System logs">
        <AdminTable
          columns={systemColumns}
          rows={systemLogsQuery.data?.items ?? []}
          loading={systemLogsQuery.isLoading}
          rowKey={(item) => item.log_id}
          rowTestId={(item) => `admin-debug-system-row-${item.log_id}`}
          empty="system log가 없습니다."
        />
      </Section>

      {apiError && <ErrorBox message={apiError} />}

      <Section title="API call logs">
        <AdminTable
          columns={apiColumns}
          rows={apiLogsQuery.data?.items ?? []}
          loading={apiLogsQuery.isLoading}
          rowKey={(item) => item.log_id}
          rowTestId={(item) => `admin-debug-api-row-${item.log_id}`}
          empty="API call log가 없습니다."
        />
      </Section>
    </AdminPage>
  );
}
