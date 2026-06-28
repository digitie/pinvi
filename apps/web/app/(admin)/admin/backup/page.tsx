'use client';

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DatabaseBackup, Loader2, RefreshCw, RotateCcw } from 'lucide-react';
import { ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminBackupRestoreRun, AdminBackupSnapshot } from '@pinvi/schemas';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { RestoreHotswapDialog } from '@/components/admin/RestoreHotswapDialog';
import { apiClient } from '@/lib/api';

const restoreHotswapUiEnabled = process.env.NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED === '1';
const snapshotListLimit = 50;

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

const columns: AdminTableColumn<AdminBackupSnapshot>[] = [
  {
    key: 'filename',
    header: '파일',
    sortable: true,
    sortValue: (row) => row.filename,
    cell: (row) => <span data-testid="admin-backup-filename">{row.filename}</span>,
  },
  {
    key: 'created_at',
    header: '생성',
    sortable: true,
    sortValue: (row) => new Date(row.created_at).getTime(),
    cell: (row) => formatDateTime(row.created_at),
  },
  {
    key: 'size',
    header: '크기',
    sortable: true,
    sortValue: (row) => row.size_bytes,
    cell: (row) => formatBytes(row.size_bytes),
  },
  {
    key: 'status',
    header: '상태',
    sortable: true,
    sortValue: (row) => row.status,
    cell: (row) => row.status,
  },
  {
    key: 'checksum',
    header: 'sha256',
    cell: (row) => row.checksum_sha256?.slice(0, 12) ?? '없음',
  },
];

export default function AdminBackupPage() {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState('정기 수동 점검');
  const [snapshotQuery, setSnapshotQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | AdminBackupSnapshot['status']>('all');
  const [message, setMessage] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [restoreSnapshot, setRestoreSnapshot] = useState<AdminBackupSnapshot | null>(null);

  const snapshotsQuery = useQuery({
    queryKey: queryKeys.admin.backupSnapshots({ limit: snapshotListLimit }),
    queryFn: () => adminApi(apiClient).listBackupSnapshots(snapshotListLimit),
  });

  const createMutation = useMutation({
    mutationFn: (access_reason: string) =>
      adminApi(apiClient).createBackupSnapshot({ access_reason }),
    onSuccess: (created) => {
      setMessage('수동 백업 snapshot을 생성했습니다.');
      setCreateError(null);
      // 생성된 snapshot을 캐시 목록 맨 앞에 낙관적으로 추가(원래 UX 유지 — 즉시 표시).
      queryClient.setQueryData<AdminBackupSnapshot[]>(
        queryKeys.admin.backupSnapshots({ limit: snapshotListLimit }),
        // snapshot_id 중복 제거(원본 동작 복원) — 재생성/경합 시 중복 행 방지.
        (old) =>
          [
            created,
            ...(old ?? []).filter((item) => item.snapshot_id !== created.snapshot_id),
          ].slice(0, snapshotListLimit),
      );
    },
    onError: (err) => {
      setCreateError(err instanceof ApiError ? err.message : '수동 백업을 시작하지 못했습니다.');
    },
  });

  const listError = snapshotsQuery.isError
    ? snapshotsQuery.error instanceof ApiError
      ? snapshotsQuery.error.message
      : '백업 snapshot을 불러오지 못했습니다.'
    : null;
  const error = createError ?? listError;
  const snapshots = useMemo(() => snapshotsQuery.data ?? [], [snapshotsQuery.data]);
  const filteredSnapshots = useMemo(() => {
    const query = snapshotQuery.trim().toLowerCase();
    return snapshots.filter((snapshot) => {
      if (statusFilter !== 'all' && snapshot.status !== statusFilter) return false;
      if (!query) return true;
      return (
        snapshot.filename.toLowerCase().includes(query) ||
        snapshot.snapshot_id.toLowerCase().includes(query) ||
        (snapshot.checksum_sha256?.toLowerCase().includes(query) ?? false)
      );
    });
  }, [snapshotQuery, snapshots, statusFilter]);

  const completeRestore = (run: AdminBackupRestoreRun) => {
    setMessage(`핫스왑 restore 요청이 완료됐습니다. restore id: ${run.restore_id}`);
  };

  const createSnapshot = () => {
    const trimmed = reason.trim();
    if (!trimmed) {
      setCreateError('백업 사유를 입력하세요.');
      return;
    }
    setMessage(null);
    setCreateError(null);
    createMutation.mutate(trimmed);
  };

  const restoreColumns: AdminTableColumn<AdminBackupSnapshot>[] = [
    ...columns,
    {
      key: 'restore',
      header: 'restore',
      cell: (row) => (
        <button
          type="button"
          onClick={() => setRestoreSnapshot(row)}
          disabled={!restoreHotswapUiEnabled}
          title={
            restoreHotswapUiEnabled ? undefined : 'NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=1'
          }
          className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-2 text-xs font-semibold text-ink hover:bg-surface-soft disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="admin-backup-restore"
        >
          <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
          Restore
        </button>
      ),
    },
  ];

  return (
    <AdminPage
      title="Backup"
      description="ADR-022 수동 snapshot trigger와 복구 준비 상태."
      actions={
        <button
          type="button"
          onClick={() => void snapshotsQuery.refetch()}
          className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
          disabled={snapshotsQuery.isFetching}
        >
          {snapshotsQuery.isFetching ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          )}
          새로고침
        </button>
      }
    >
      {message && (
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">{message}</p>
      )}
      {error && (
        <p
          className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          data-testid="admin-backup-error"
        >
          {error}
        </p>
      )}

      <Section title="수동 snapshot">
        <div className="grid gap-3 md:grid-cols-[1fr_auto]">
          <label className="space-y-1 text-sm font-semibold text-ink">
            사유
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              className="h-10 w-full rounded-sm border border-hairline px-3 text-sm font-normal text-ink outline-none focus:border-primary"
              maxLength={500}
              data-testid="admin-backup-reason"
            />
          </label>
          <button
            type="button"
            onClick={createSnapshot}
            disabled={createMutation.isPending}
            className="mt-6 inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50 md:mt-auto"
            data-testid="admin-backup-create"
          >
            {createMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <DatabaseBackup className="h-4 w-4" aria-hidden="true" />
            )}
            지금 백업
          </button>
        </div>
      </Section>

      <Section title="Snapshot 목록">
        <div className="mb-3 grid gap-3 md:grid-cols-[1fr_180px_auto]">
          <label className="space-y-1 text-sm font-semibold text-ink">
            검색
            <input
              value={snapshotQuery}
              onChange={(event) => setSnapshotQuery(event.target.value)}
              className="h-10 w-full rounded-sm border border-hairline px-3 text-sm font-normal text-ink outline-none focus:border-primary"
              data-testid="admin-backup-search"
              maxLength={120}
            />
          </label>
          <label className="space-y-1 text-sm font-semibold text-ink">
            상태
            <select
              value={statusFilter}
              onChange={(event) =>
                setStatusFilter(event.target.value as 'all' | AdminBackupSnapshot['status'])
              }
              className="h-10 w-full rounded-sm border border-hairline px-3 text-sm font-normal text-ink outline-none focus:border-primary"
              data-testid="admin-backup-status-filter"
            >
              <option value="all">전체</option>
              <option value="verified">verified</option>
              <option value="available">available</option>
            </select>
          </label>
          <p className="self-end pb-2 text-sm text-muted" data-testid="admin-backup-visible-count">
            {filteredSnapshots.length} / {snapshots.length}
          </p>
        </div>
        <AdminTable
          rows={filteredSnapshots}
          loading={snapshotsQuery.isLoading}
          empty={
            snapshots.length > 0
              ? '조건에 맞는 snapshot이 없습니다.'
              : '생성된 snapshot이 없습니다.'
          }
          rowKey={(row) => row.snapshot_id}
          rowTestId={(row) => `admin-backup-row-${row.filename}`}
          columns={restoreColumns}
        />
      </Section>

      <Section title="Restore">
        <p className="text-sm text-muted">
          핫스왑 restore는 동일 DB schema-swap 스크립트로 실행되며 결과 단계와 schema 이름이 audit
          log에 남는다.
        </p>
      </Section>

      <RestoreHotswapDialog
        snapshot={restoreSnapshot}
        onClose={() => setRestoreSnapshot(null)}
        onComplete={completeRestore}
      />
    </AdminPage>
  );
}
