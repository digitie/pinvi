'use client';

import { VirtualTable } from '@kor-travel/ui/virtual-table';

import { AdminPage, Section } from '@/components/admin/AdminPage';
import { apiClient } from '@/lib/api';
import { ApiError, adminApi } from '@pinvi/api-client';
import type { AdminSystemDetail, AdminSystemServiceStatus } from '@pinvi/schemas';
import { useEffect, useState } from 'react';

const displayFormatter1 = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

const statusMeta: Record<
  AdminSystemServiceStatus['status'],
  { label: string; className: string; dotClassName: string }
> = {
  ok: {
    label: '정상',
    className: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    dotClassName: 'bg-emerald-500',
  },
  degraded: {
    label: '주의',
    className: 'border-amber-200 bg-amber-50 text-amber-800',
    dotClassName: 'bg-amber-500',
  },
  down: {
    label: '중단',
    className: 'border-red-200 bg-red-50 text-red-800',
    dotClassName: 'bg-red-500',
  },
  unknown: {
    label: '미확인',
    className: 'border-hairline bg-surface-soft text-muted',
    dotClassName: 'bg-muted',
  },
};

const formatLatency = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : `${value} ms`;
const formatDateTime = (value: string | undefined) =>
  value ? displayFormatter1.format(new Date(value)) : '—';

function StatusBadge({ status }: { status: AdminSystemServiceStatus['status'] }) {
  const meta = statusMeta[status];
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-sm border px-2 py-1 text-xs font-semibold ${meta.className}`}
    >
      <span className={`h-2 w-2 rounded-full ${meta.dotClassName}`} />
      {meta.label}
    </span>
  );
}

function DependencyCard({ service }: { service: AdminSystemServiceStatus }) {
  return (
    <div
      className="rounded-sm border border-hairline bg-canvas p-4"
      data-testid={`admin-system-dependency-${service.key}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-ink">{service.label}</p>
          <p className="mt-1 text-xs text-muted">{service.message ?? '상태 정보 없음'}</p>
        </div>
        <StatusBadge status={service.status} />
      </div>
      <p className="mt-3 text-xs text-muted">latency {formatLatency(service.latency_ms)}</p>
    </div>
  );
}

export default function AdminSystemPage() {
  const [detail, setDetail] = useState<AdminSystemDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const admin = adminApi(apiClient);
    admin
      .getSystemDetail()
      .then((result) => {
        if (cancelled) return;
        setDetail(result);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : '시스템 상태를 불러오지 못했습니다.');
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const dependencies = detail?.dependencies ?? [];
  const docker = detail?.docker ?? {
    key: 'docker',
    label: 'Docker',
    status: 'unknown' as const,
    message: loading ? '확인 중' : '상태 정보 없음',
    latency_ms: null,
  };
  const containers = detail?.containers ?? [];

  return (
    <AdminPage title="시스템" description="Docker container와 의존 API 상태">
      {error && <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>}

      <Section title="의존 API">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {dependencies.map((service) => (
            <DependencyCard key={service.key} service={service} />
          ))}
          {!loading && dependencies.length === 0 && (
            <p className="rounded-sm border border-hairline bg-canvas p-4 text-sm text-muted">
              의존 API 상태 없음
            </p>
          )}
        </div>
      </Section>

      <Section title="Docker">
        <div
          className="rounded-sm border border-hairline bg-canvas p-4"
          data-testid="admin-system-docker"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-ink">{docker.label}</p>
              <p className="mt-1 text-xs text-muted">{docker.message ?? '상태 정보 없음'}</p>
            </div>
            <StatusBadge status={docker.status} />
          </div>
          <p className="mt-3 text-xs text-muted">
            latency {formatLatency(docker.latency_ms)} / 갱신 {formatDateTime(detail?.generated_at)}
          </p>
        </div>

        <div className="mt-3 overflow-x-auto rounded-sm border border-hairline bg-canvas">
          <VirtualTable
            data={containers}
            columns={[
              {
                id: 'c0',
                header: 'id',
                cell: ({ row: { original: container } }) => <>{container.container_id || '—'}</>,
                enableSorting: false,
              },
              {
                id: 'c1',
                header: 'container',
                cell: ({ row: { original: container } }) => (
                  <>
                    <p className="font-medium text-ink">{container.name}</p>
                    <p className="mt-1 text-xs text-muted">
                      {container.compose_service ?? 'service 미지정'}
                    </p>
                  </>
                ),
                enableSorting: false,
              },
              {
                id: 'c2',
                header: 'image',
                cell: ({ row: { original: container } }) => <>{container.image || '—'}</>,
                enableSorting: false,
              },
              {
                id: 'c3',
                header: 'state',
                cell: ({ row: { original: container } }) => (
                  <>
                    <span className="rounded-sm bg-surface-soft px-2 py-1 text-xs font-semibold text-ink">
                      {container.state}
                    </span>
                  </>
                ),
                enableSorting: false,
              },
              {
                id: 'c4',
                header: 'health',
                cell: ({ row: { original: container } }) => <>{container.health ?? '—'}</>,
                enableSorting: false,
              },
              {
                id: 'c5',
                header: 'status',
                cell: ({ row: { original: container } }) => <>{container.status}</>,
                enableSorting: false,
              },
            ]}
            getRowId={(container) => container.container_id || container.name}
            rowTestId={(container) => 'admin-system-container-' + container.name}
            tableTestId="admin-system-containers"
            isLoading={loading}
            emptyMessage="container 상태 없음"
          />
        </div>
      </Section>
    </AdminPage>
  );
}
