'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { CheckCircle2, Loader2, RotateCcw, ShieldAlert, X, XCircle } from 'lucide-react';
import { ApiError, adminApi } from '@pinvi/api-client';
import type {
  AdminBackupRestorePhase,
  AdminBackupRestoreRun,
  AdminBackupSnapshot,
} from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { Button } from '@/components/admin/ui/button';
// T-356: 사용자 표면 `components/ui/Dialog`(useModalDialog) → admin base-ui `Dialog`.
// admin 화면에서는 두 모달 스택을 섞지 않는다. 사용자 표면은 계속 useModalDialog를 쓴다.
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/admin/ui/dialog';

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

/* Hallmark · component: dialog(admin, destructive) · design-system: design.md(KTM admin)
 * admin 프리미티브(`components/admin/ui/dialog`, base-ui)로 뜬다 — T-356에서 사용자 표면
 * `components/ui/Dialog`(useModalDialog)에서 옮겼다. 포털·배경 inert·Tab 트랩·Escape·포커스
 * 복원은 base-ui가 담당한다.
 *
 * 파괴적 흐름이므로 `restoring` 동안 닫기 경로는 잠긴 채 유지한다: Escape/scrim은
 * `onOpenChange` → `closeIfIdle`이 삼키고, 헤더 ×와 푸터 `닫기`는 native `disabled`다
 * (e2e가 `restore-hotswap-dialog-close`의 disabled를 직접 확인한다 — `aria-disabled`인
 * Button `loading`을 쓰면 안 된다). 이 다이얼로그는 진행 중 요청을 취소할 방법이 없다. */
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
      // 미저장 폼 입력 보호 — Escape/바깥클릭 닫기를 막는다(전환 전 수제 모달에는
      // 그 경로가 없었다). 명시적 닫기(×/취소/제출)는 그대로 동작한다.
      open
      hasUnsavedInput
      onOpenChange={(open) => {
        // restoring 중에는 closeIfIdle이 삼킨다 — Escape/scrim으로 파괴적 요청을 잃지 않는다.
        if (!open) closeIfIdle();
      }}
    >
      <DialogContent
        className="max-w-3xl"
        data-testid="restore-hotswap-dialog"
        initialFocus={reasonRef}
        viewportProps={{ 'data-testid': 'restore-hotswap-dialog-backdrop' }}
      >
        <DialogHeader>
          <div className="min-w-0">
            <DialogTitle>Restore schema-swap</DialogTitle>
            <DialogDescription className="mt-1">
              <span data-testid="restore-snapshot-name">{snapshot.filename}</span>
            </DialogDescription>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={closeIfIdle}
            disabled={restoring}
            aria-label="닫기"
            data-testid="restore-hotswap-dialog-close"
          >
            <X aria-hidden="true" />
          </Button>
        </DialogHeader>
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

          {/* 제출 버튼은 이 form 안에 남아야 submit이 발화한다 — KTM `DialogFooter`(Content 직계)
            대신 form 안 액션 행. e2e가 두 버튼의 native disabled를 직접 확인하므로 Button
            `loading`(aria-disabled)이 아니라 `disabled`를 쓴다. */}
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button type="button" variant="outline" onClick={closeIfIdle} disabled={restoring}>
              닫기
            </Button>
            <Button
              type="submit"
              variant="destructive-solid"
              disabled={!canSubmit}
              data-testid="restore-submit"
            >
              {restoring ? (
                <Loader2 data-icon="inline-start" className="animate-spin" aria-hidden="true" />
              ) : (
                <RotateCcw data-icon="inline-start" aria-hidden="true" />
              )}
              Restore
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
