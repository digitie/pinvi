'use client';

import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { CheckCircle2, Loader2, RotateCcw, ShieldAlert, XCircle } from 'lucide-react';
import { ApiError, adminApi } from '@tripmate/api-client';
import type {
  AdminBackupRestorePhase,
  AdminBackupRestoreRun,
  AdminBackupSnapshot,
} from '@tripmate/schemas';
import { apiClient } from '@/lib/api';

interface RestoreHotswapDialogProps {
  snapshot: AdminBackupSnapshot | null;
  onClose: () => void;
  onComplete: (run: AdminBackupRestoreRun) => void;
}

const phaseLabels: Record<AdminBackupRestorePhase['name'], string> = {
  preparing: 'preparing',
  restoring: 'restoring',
  validating: 'validating',
  draining: 'draining',
  switching: 'switching',
};

function phaseIcon(phase: AdminBackupRestorePhase) {
  if (phase.status === 'success') {
    return <CheckCircle2 className="h-4 w-4 text-success-text" aria-hidden="true" />;
  }
  if (phase.status === 'failed') {
    return <XCircle className="h-4 w-4 text-error-text" aria-hidden="true" />;
  }
  if (phase.status === 'running') {
    return <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />;
  }
  return <span className="h-4 w-4 rounded-full border border-hairline" aria-hidden="true" />;
}

export function RestoreHotswapDialog({
  snapshot,
  onClose,
  onComplete,
}: RestoreHotswapDialogProps) {
  const [reason, setReason] = useState('운영 복구 훈련');
  const [confirmed, setConfirmed] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [run, setRun] = useState<AdminBackupRestoreRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!snapshot) return;
    setReason('운영 복구 훈련');
    setConfirmed(false);
    setRestoring(false);
    setRun(null);
    setError(null);
  }, [snapshot]);

  if (!snapshot) return null;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = reason.trim();
    if (!trimmed) {
      setError('복구 사유를 입력하세요.');
      return;
    }
    if (!confirmed) {
      setError('schema-swap 복구 확인이 필요합니다.');
      return;
    }
    setRestoring(true);
    setError(null);
    try {
      const result = await adminApi(apiClient).restoreBackupHotswap({
        snapshot_id: snapshot.snapshot_id,
        access_reason: trimmed,
        confirm_schema_swap: true,
      });
      setRun(result);
      onComplete(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '핫스왑 복구 요청에 실패했습니다.');
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-2xl rounded-sm bg-white shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-hairline p-4">
          <div>
            <h2 className="text-lg font-bold text-ink">Restore schema-swap</h2>
            <p className="mt-1 text-sm text-muted" data-testid="restore-snapshot-name">
              {snapshot.filename}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 w-9 items-center justify-center rounded-sm border border-hairline text-muted hover:bg-surface-soft"
            aria-label="닫기"
          >
            ×
          </button>
        </div>

        <form className="space-y-4 p-4" onSubmit={(event) => void submit(event)}>
          {error && (
            <p
              className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
              data-testid="restore-error"
            >
              {error}
            </p>
          )}

          <label className="space-y-1 text-sm font-semibold text-ink">
            복구 사유
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              className="min-h-20 w-full rounded-sm border border-hairline px-3 py-2 text-sm font-normal text-ink outline-none focus:border-primary"
              maxLength={500}
              data-testid="restore-reason"
            />
          </label>

          <label className="flex items-start gap-2 rounded-sm border border-hairline bg-error-bg p-3 text-sm text-error-text">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
              className="mt-1"
              data-testid="restore-confirm"
            />
            <span>
              선택한 snapshot으로 동일 DB `app` schema를 교체하고 previous schema를 남깁니다.
            </span>
          </label>

          {run && (
            <div className="space-y-3 rounded-sm border border-hairline p-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                <ShieldAlert className="h-4 w-4" aria-hidden="true" />
                <span data-testid="restore-run-id">{run.restore_id}</span>
              </div>
              <dl className="grid gap-2 text-xs text-muted md:grid-cols-2">
                <div>
                  <dt>restore schema</dt>
                  <dd className="font-mono text-ink">{run.restore_schema}</dd>
                </div>
                <div>
                  <dt>previous schema</dt>
                  <dd className="font-mono text-ink">{run.previous_schema}</dd>
                </div>
              </dl>
              <ol className="space-y-2">
                {run.phases.map((phase) => (
                  <li
                    key={phase.name}
                    className="flex items-start gap-2 text-sm"
                    data-testid={`restore-phase-${phase.name}`}
                  >
                    {phaseIcon(phase)}
                    <span className="min-w-24 font-semibold text-ink">
                      {phaseLabels[phase.name]}
                    </span>
                    <span className="text-muted">
                      {phase.status}
                      {phase.message ? ` · ${phase.message}` : ''}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 items-center justify-center rounded-sm border border-hairline px-4 text-sm font-semibold text-ink hover:bg-surface-soft"
            >
              닫기
            </button>
            <button
              type="submit"
              disabled={restoring}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-error-text px-4 text-sm font-semibold text-white hover:bg-error-text-hover disabled:opacity-50"
              data-testid="restore-submit"
            >
              {restoring ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
              )}
              Restore
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
