'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminRequestTimelineEvent, AdminRequestTimelineSource } from '@pinvi/schemas';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const formatDateTime = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString('ko-KR') : '—';

function firstParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
      {message}
    </p>
  );
}

const sourceColumns: AdminTableColumn<AdminRequestTimelineSource>[] = [
  {
    key: 'source',
    header: 'source',
    sortable: true,
    sortValue: (row) => row.source,
    cell: (row) => <span className="font-mono text-xs">{row.source}</span>,
  },
  {
    key: 'status',
    header: 'status',
    sortable: true,
    sortValue: (row) => row.status,
    cell: (row) => row.status,
  },
  {
    key: 'count',
    header: 'events',
    sortable: true,
    sortValue: (row) => row.event_count,
    cell: (row) => row.event_count,
    align: 'right',
  },
  {
    key: 'message',
    header: 'message',
    cell: (row) => row.message ?? '—',
  },
];

const eventColumns: AdminTableColumn<AdminRequestTimelineEvent>[] = [
  {
    key: 'time',
    header: 'time',
    sortable: true,
    sortValue: (row) => new Date(row.occurred_at).getTime(),
    cell: (row) => formatDateTime(row.occurred_at),
  },
  {
    key: 'source',
    header: 'source',
    sortable: true,
    sortValue: (row) => row.source,
    cell: (row) => <span className="font-mono text-xs">{row.source}</span>,
  },
  {
    key: 'title',
    header: 'title',
    sortable: true,
    sortValue: (row) => row.title,
    cell: (row) => row.title,
  },
  {
    key: 'status',
    header: 'status',
    sortable: true,
    sortValue: (row) => row.status ?? '',
    cell: (row) => row.status ?? '—',
  },
  {
    key: 'duration',
    header: 'duration',
    sortable: true,
    sortValue: (row) => row.duration_ms ?? 0,
    cell: (row) => (row.duration_ms === null ? '—' : `${row.duration_ms}ms`),
    align: 'right',
  },
  {
    key: 'error',
    header: 'error',
    cell: (row) => row.error_code ?? '—',
  },
  {
    key: 'detail',
    header: 'detail',
    cell: (row) => (
      <span className="font-mono text-xs" title={JSON.stringify(row.detail)}>
        {JSON.stringify(row.detail)}
      </span>
    ),
  },
];

export default function AdminRequestTimelinePage() {
  const params = useParams();
  const requestId = firstParam(params.request_id);

  const timelineQuery = useQuery({
    queryKey: requestId
      ? queryKeys.admin.requestTimeline(requestId)
      : queryKeys.admin.requestTimeline(''),
    queryFn: () => adminApi(apiClient).getRequestTimeline(requestId ?? ''),
    enabled: Boolean(requestId),
  });

  const timeline = timelineQuery.data ?? null;
  const error = timelineQuery.isError
    ? timelineQuery.error instanceof ApiError
      ? timelineQuery.error.message
      : 'request timeline을 불러오지 못했습니다.'
    : null;

  return (
    <AdminPage
      title="Request timeline"
      description={requestId ?? ''}
      actions={
        <>
          <Link
            href="/admin/debug/logs"
            className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            Logs
          </Link>
          <button
            type="button"
            onClick={() => void timelineQuery.refetch()}
            className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-request-timeline-refresh"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            갱신
          </button>
        </>
      }
    >
      {error && <ErrorBox message={error} />}

      {timeline && (
        <section className="grid gap-3 md:grid-cols-4" data-testid="admin-request-timeline-summary">
          <div className="rounded-sm border border-hairline bg-white p-3">
            <div className="text-xs uppercase text-muted">status</div>
            <div className="mt-1 font-mono text-sm">{timeline.status}</div>
          </div>
          <div className="rounded-sm border border-hairline bg-white p-3">
            <div className="text-xs uppercase text-muted">events</div>
            <div className="mt-1 font-mono text-sm">{timeline.events.length}</div>
          </div>
          <div className="rounded-sm border border-hairline bg-white p-3">
            <div className="text-xs uppercase text-muted">started</div>
            <div className="mt-1 text-sm">{formatDateTime(timeline.started_at)}</div>
          </div>
          <div className="rounded-sm border border-hairline bg-white p-3">
            <div className="text-xs uppercase text-muted">duration</div>
            <div className="mt-1 font-mono text-sm">
              {timeline.duration_ms === null ? '—' : `${timeline.duration_ms}ms`}
            </div>
          </div>
        </section>
      )}

      <Section title="Sources">
        <AdminTable
          columns={sourceColumns}
          rows={timeline?.sources ?? []}
          loading={timelineQuery.isLoading}
          rowKey={(row) => row.source}
          rowTestId={(row) => `admin-request-source-${row.source}`}
          empty="source가 없습니다."
        />
      </Section>

      <Section title="Events">
        <AdminTable
          columns={eventColumns}
          rows={timeline?.events ?? []}
          loading={timelineQuery.isLoading}
          rowKey={(row) => row.event_id}
          rowTestId={(row) => `admin-request-event-${row.event_id}`}
          empty="event가 없습니다."
          virtualized
        />
      </Section>
    </AdminPage>
  );
}
