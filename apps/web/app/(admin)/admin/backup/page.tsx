'use client';

import { useEffect, useState } from 'react';
import { DatabaseBackup, Loader2, RefreshCw, RotateCcw } from 'lucide-react';
import { ApiError, adminApi } from '@tripmate/api-client';
import type { AdminBackupRestoreRun, AdminBackupSnapshot } from '@tripmate/schemas';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { DataTable } from '@/components/admin/DataTable';
import { RestoreHotswapDialog } from '@/components/admin/RestoreHotswapDialog';
import { apiClient } from '@/lib/api';

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

export default function AdminBackupPage() {
  const [snapshots, setSnapshots] = useState<AdminBackupSnapshot[]>([]);
  const [reason, setReason] = useState('정기 수동 점검');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [restoreSnapshot, setRestoreSnapshot] = useState<AdminBackupSnapshot | null>(null);

  const loadSnapshots = async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await adminApi(apiClient).listBackupSnapshots();
      setSnapshots(items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '백업 snapshot을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const completeRestore = (run: AdminBackupRestoreRun) => {
    setMessage(`핫스왑 restore 요청이 완료됐습니다. restore id: ${run.restore_id}`);
  };

  useEffect(() => {
    void loadSnapshots();
  }, []);

  const createSnapshot = async () => {
    const trimmed = reason.trim();
    if (!trimmed) {
      setError('백업 사유를 입력하세요.');
      return;
    }
    setCreating(true);
    setMessage(null);
    setError(null);
    try {
      const snapshot = await adminApi(apiClient).createBackupSnapshot({
        access_reason: trimmed,
      });
      setSnapshots((current) => [
        snapshot,
        ...current.filter((item) => item.snapshot_id !== snapshot.snapshot_id),
      ]);
      setMessage('수동 백업 snapshot을 생성했습니다.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '수동 백업을 시작하지 못했습니다.');
    } finally {
      setCreating(false);
    }
  };

  return (
    <AdminPage
      title="Backup"
      description="ADR-022 수동 snapshot trigger와 복구 준비 상태."
      actions={
        <button
          type="button"
          onClick={() => void loadSnapshots()}
          className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
          disabled={loading}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          )}
          새로고침
        </button>
      }
    >
      {message && (
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">
          {message}
        </p>
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
            />
          </label>
          <button
            type="button"
            onClick={() => void createSnapshot()}
            disabled={creating}
            className="mt-6 inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50 md:mt-auto"
            data-testid="admin-backup-create"
          >
            {creating ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <DatabaseBackup className="h-4 w-4" aria-hidden="true" />
            )}
            지금 백업
          </button>
        </div>
      </Section>

      <Section title="Snapshot 목록">
        <DataTable
          rows={snapshots}
          loading={loading}
          empty="생성된 snapshot이 없습니다."
          rowKey={(row) => row.snapshot_id}
          columns={[
            {
              key: 'filename',
              header: '파일',
              cell: (row) => <span data-testid="admin-backup-filename">{row.filename}</span>,
            },
            {
              key: 'created_at',
              header: '생성',
              cell: (row) => formatDateTime(row.created_at),
            },
            {
              key: 'size',
              header: '크기',
              cell: (row) => formatBytes(row.size_bytes),
            },
            {
              key: 'status',
              header: '상태',
              cell: (row) => row.status,
            },
            {
              key: 'checksum',
              header: 'sha256',
              cell: (row) => row.checksum_sha256?.slice(0, 12) ?? '없음',
            },
            {
              key: 'restore',
              header: 'restore',
              cell: (row) => (
                <button
                  type="button"
                  onClick={() => setRestoreSnapshot(row)}
                  className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-2 text-xs font-semibold text-ink hover:bg-surface-soft"
                  data-testid="admin-backup-restore"
                >
                  <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                  Restore
                </button>
              ),
            },
          ]}
        />
      </Section>

      <Section title="Restore">
        <p className="text-sm text-muted">
          핫스왑 restore는 동일 DB schema-swap 스크립트로 실행되며 결과 단계와 schema
          이름이 audit log에 남는다.
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
