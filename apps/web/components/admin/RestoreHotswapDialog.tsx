'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { CheckCircle2, Loader2, RotateCcw, ShieldAlert, XCircle } from 'lucide-react';
import { ApiError, adminApi } from '@pinvi/api-client';
import type {
  AdminBackupRestorePhase,
  AdminBackupRestoreRun,
  AdminBackupSnapshot,
} from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { Dialog } from '@/components/ui/Dialog';

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

/* Hallmark · component: dialog(admin, destructive) · design-system: DESIGN.md
 * 프리미티브(`components/ui/Dialog`)로 뜬다 — T-316에서 훅에 body portal + 스택 인지형 배경 inert를
 * 넣으면서 이 컴포넌트가 손으로 들고 있던 격리(포털·inert·Tab 트랩·포커스 복원)를 전부 걷어냈다.
 * 파괴적 흐름이므로 `busy`(restoring) 동안 닫기 경로는 잠긴 채 유지한다. */
export function RestoreHotswapDialog({ snapshot, onClose, onComplete }: RestoreHotswapDialogProps) {
  const reasonRef = useRef<HTMLTextAreaElement | null>(null);
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [confirmation, setConfirmation] = useState('');
  const [restoring, setRestoring] = useState(false);
  const [run, setRun] = useState<AdminBackupRestoreRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  // snapshot(복구 대상)이 바뀌면 폼 상태를 리셋한다 — effect 대신 렌더 중 조정
  // (react-hooks/set-state-in-effect가 막는 effect 내부 동기 setState를 피한다).
  const [prevSnapshot, setPrevSnapshot] = useState(snapshot);
  if (snapshot !== prevSnapshot) {
    setPrevSnapshot(snapshot);
    if (snapshot) {
      setReason('');
      setConfirmed(false);
      setConfirmation('');
      setRestoring(false);
      setRun(null);
      setError(null);
    }
  }

  const closeIfIdle = useCallback(() => {
    if (!restoring) onClose();
  }, [onClose, restoring]);

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
  const canSubmit =
    Boolean(reason.trim()) && confirmed && confirmationMatches && !restoring && !run;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    // In-handler re-entry guard: never re-issue a destructive schema-swap once a
    // request is in flight or has already succeeded (defense in depth on top of
    // the disabled submit button).
    if (restoring || run) return;
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
    // 제출 버튼이 disabled되며 포커스가 body로 떨어지는 문제는 훅의 포커스 격납이 처리한다
    // (T-315 2·3차 리뷰에서 focusout 기반으로 고쳤다).
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
    <Dialog
      open
      onClose={closeIfIdle}
      busy={restoring}
      size="lg"
      title="Restore schema-swap"
      description={<span data-testid="restore-snapshot-name">{snapshot.filename}</span>}
      initialFocusRef={reasonRef}
      testId="restore-hotswap-dialog"
    >
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
            disabled={restoring || Boolean(run)}
            className="min-h-20 w-full rounded-sm border border-hairline px-3 py-2 text-sm font-normal text-ink outline-hidden focus:border-primary disabled:opacity-60"
            maxLength={500}
            placeholder="복구 사유를 입력하세요."
            data-testid="restore-reason"
          />
        </label>

        <label className="flex items-start gap-2 rounded-sm border border-hairline bg-error-bg p-3 text-sm text-error-text">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
            disabled={restoring || Boolean(run)}
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
            disabled={restoring || Boolean(run)}
            className="h-10 w-full rounded-sm border border-hairline px-3 font-mono text-sm font-normal text-ink outline-hidden focus:border-primary disabled:opacity-60"
            aria-invalid={confirmation.length > 0 && !confirmationMatches ? 'true' : undefined}
            data-testid="restore-confirmation"
          />
          <span className="block text-xs font-normal text-muted">
            <code>{confirmationText}</code>
          </span>
        </label>

        {phases.length > 0 && (
          <div
            className="space-y-3 rounded-sm border border-hairline p-3"
            data-testid="restore-progress"
          >
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
                  <span className="min-w-24 font-semibold text-ink">{phaseLabels[phase.name]}</span>
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
            className="inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-error-text px-4 text-sm font-semibold text-on-primary hover:bg-error-text-hover disabled:opacity-50"
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
    </Dialog>
  );
}
