'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { CheckCircle2, Loader2, RotateCcw, ShieldAlert, X, XCircle } from 'lucide-react';
import { ApiError, adminApi } from '@pinvi/api-client';
import type {
  AdminBackupRestorePhase,
  AdminBackupRestoreRun,
  AdminBackupSnapshot,
} from '@pinvi/schemas';
import { apiClient } from '@/lib/api';

interface RestoreHotswapDialogProps {
  snapshot: AdminBackupSnapshot | null;
  onClose: () => void;
  onComplete: (run: AdminBackupRestoreRun) => void;
}

const phaseOrder: AdminBackupRestorePhase['name'][] = [
  'preparing',
  'restoring',
  'validating',
  'draining',
  'switching',
];

const phaseLabels: Record<AdminBackupRestorePhase['name'], string> = {
  preparing: 'schema 준비',
  restoring: 'pg_restore',
  validating: 'validate',
  draining: 'write drain',
  switching: 'schema-swap',
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
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const reasonRef = useRef<HTMLTextAreaElement | null>(null);
  const [reason, setReason] = useState('운영 복구 훈련');
  const [confirmed, setConfirmed] = useState(false);
  const [confirmation, setConfirmation] = useState('');
  const [restoring, setRestoring] = useState(false);
  const [run, setRun] = useState<AdminBackupRestoreRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!snapshot) return;
    setReason('운영 복구 훈련');
    setConfirmed(false);
    setConfirmation('');
    setRestoring(false);
    setRun(null);
    setError(null);
  }, [snapshot]);

  useEffect(() => {
    if (!snapshot) return;
    reasonRef.current?.focus();
  }, [snapshot]);

  const closeIfIdle = useCallback(() => {
    if (!restoring) onClose();
  }, [onClose, restoring]);

  const handleDialogKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        closeIfIdle();
        return;
      }
      if (event.key !== 'Tab') return;

      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not(:disabled), [href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => !element.hasAttribute('disabled') && element.offsetParent !== null);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last?.focus();
        return;
      }
      if (!event.shiftKey && active === last) {
        event.preventDefault();
        first?.focus();
      }
    },
    [closeIfIdle],
  );

  const pendingPhases: AdminBackupRestorePhase[] = useMemo(
    () =>
      phaseOrder.map((name, index) => ({
        name,
        status: index === 0 ? 'running' : 'pending',
        message: index === 0 ? 'restore request submitted' : null,
      })),
    [],
  );

  if (!snapshot) return null;

  const phases = run?.phases ?? (restoring ? pendingPhases : []);
  const confirmationText = snapshot.filename;
  const confirmationMatches = confirmation.trim() === confirmationText;
  const canSubmit = Boolean(reason.trim()) && confirmed && confirmationMatches && !restoring && !run;

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
    if (!confirmationMatches) {
      setError('snapshot 파일명 확인 문구가 일치하지 않습니다.');
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      data-testid="restore-hotswap-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) closeIfIdle();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="restore-hotswap-title"
        aria-describedby="restore-hotswap-description"
        tabIndex={-1}
        onKeyDown={handleDialogKeyDown}
        className="w-full max-w-2xl rounded-sm bg-white shadow-xl outline-none"
        data-testid="restore-hotswap-dialog"
      >
        <div className="flex items-start justify-between gap-3 border-b border-hairline p-4">
          <div>
            <h2 id="restore-hotswap-title" className="text-lg font-bold text-ink">
              Restore schema-swap
            </h2>
            <p
              id="restore-hotswap-description"
              className="mt-1 text-sm text-muted"
              data-testid="restore-snapshot-name"
            >
              {snapshot.filename}
            </p>
          </div>
          <button
            type="button"
            onClick={closeIfIdle}
            disabled={restoring}
            className="inline-flex h-9 w-9 items-center justify-center rounded-sm border border-hairline text-muted hover:bg-surface-soft"
            aria-label="닫기"
            data-testid="restore-close"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <form className="space-y-4 p-4" onSubmit={(event) => void submit(event)}>
          {error && (
            <p
              role="alert"
              className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
              data-testid="restore-error"
            >
              {error}
            </p>
          )}

          <label className="space-y-1 text-sm font-semibold text-ink">
            복구 사유
            <textarea
              ref={reasonRef}
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

          <label className="space-y-1 text-sm font-semibold text-ink">
            snapshot 파일명 확인
            <input
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              className="h-10 w-full rounded-sm border border-hairline px-3 font-mono text-sm font-normal text-ink outline-none focus:border-primary"
              aria-invalid={confirmation.length > 0 && !confirmationMatches ? 'true' : undefined}
              data-testid="restore-confirmation"
            />
            <span className="block text-xs font-normal text-muted">
              <code>{confirmationText}</code>
            </span>
          </label>

          {phases.length > 0 && (
            <div className="space-y-3 rounded-sm border border-hairline p-3" data-testid="restore-progress">
              <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                <ShieldAlert className="h-4 w-4" aria-hidden="true" />
                <span data-testid="restore-run-id">
                  {run?.restore_id ?? 'restore request running'}
                </span>
              </div>
              {run && (
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
              )}
              <ol className="space-y-2">
                {phases.map((phase) => (
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
              onClick={closeIfIdle}
              disabled={restoring}
              className="inline-flex h-10 items-center justify-center rounded-sm border border-hairline px-4 text-sm font-semibold text-ink hover:bg-surface-soft"
            >
              닫기
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
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
