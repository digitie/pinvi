'use client';

import { useEffect, useRef, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { ApiError, noticePlanApi, tripApi } from '@pinvi/api-client';
import type { NoticePlan, NoticePlanCopyResponse, TripResponse } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { buildCopyRequest, canCopy, type CopyForm } from '@pinvi/domain';
import { FormField } from '@/components/forms/FormField';
import { Button, ButtonLink } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';

const DIALOG_LABEL = 'block text-sm font-semibold text-ink';

export interface NoticePlanCopyDialogProps {
  plan: NoticePlan;
  onClose: () => void;
  onCopied?: (result: NoticePlanCopyResponse) => void;
}

export function NoticePlanCopyDialog({ plan, onClose, onCopied }: NoticePlanCopyDialogProps) {
  const [form, setForm] = useState<CopyForm>({
    mode: 'new',
    title: plan.title,
    startDate: plan.starts_on ?? '',
    endDate: plan.ends_on ?? '',
    targetTripId: null,
  });
  const [trips, setTrips] = useState<TripResponse[]>([]);
  const [loadingTrips, setLoadingTrips] = useState(true);
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<NoticePlanCopyResponse | null>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const successCloseRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let cancelled = false;
    tripApi(apiClient)
      .list({ limit: 50 })
      .then((items) => {
        if (!cancelled) setTrips(items);
      })
      .catch(() => {
        /* 기존 여행 목록 실패는 새 여행 모드로 진행 가능. */
      })
      .finally(() => {
        if (!cancelled) setLoadingTrips(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const update = (patch: Partial<CopyForm>) => setForm((prev) => ({ ...prev, ...patch }));

  // 성공 화면으로 바뀌면 눌렀던 복사 버튼이 사라져 포커스가 body로 떨어진다 — 닫기로 옮긴다.
  useEffect(() => {
    if (result) successCloseRef.current?.focus();
  }, [result]);

  const copy = async () => {
    setCopying(true);
    setError(null);
    try {
      const res = await noticePlanApi(apiClient).copy(plan.notice_plan_id, buildCopyRequest(form));
      setResult(res);
      onCopied?.(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '복사에 실패했습니다.');
    } finally {
      setCopying(false);
    }
  };

  const footer = result ? (
    <>
      <Button ref={successCloseRef} variant="secondary" onClick={onClose}>
        닫기
      </Button>
      <ButtonLink href={`/trips/${result.trip_id}`}>여행 열기</ButtonLink>
    </>
  ) : (
    <>
      <Button variant="secondary" onClick={onClose} disabled={copying}>
        취소
      </Button>
      <Button
        onClick={() => void copy()}
        disabled={!canCopy(form)}
        loading={copying}
        data-testid="notice-copy-confirm"
      >
        복사
      </Button>
    </>
  );

  return (
    <Dialog
      open
      onClose={onClose}
      busy={copying}
      size="sm"
      title="추천 여행 가져오기"
      description={plan.title}
      initialFocusRef={titleRef}
      testId="notice-copy-dialog"
      footer={footer}
    >
      {result ? (
        <p
          className="flex items-center gap-2 rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text"
          role="status"
        >
          <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
          {result.created_trip ? '새 여행을 만들었습니다.' : '기존 여행에 추가했습니다.'} 장소{' '}
          {result.copied_poi_ids.length}곳 복사.
        </p>
      ) : (
        <div className="space-y-4">
          <div className="flex gap-2" role="radiogroup" aria-label="복사 대상">
            {(['new', 'existing'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                role="radio"
                aria-checked={form.mode === mode}
                onClick={() => update({ mode })}
                className={
                  form.mode === mode
                    ? 'focus-ring min-h-11 flex-1 rounded-sm bg-ink text-sm font-semibold text-canvas'
                    : 'focus-ring min-h-11 flex-1 rounded-sm border border-hairline bg-canvas text-sm font-semibold text-ink hover:bg-surface-soft'
                }
              >
                {mode === 'new' ? '새 여행으로' : '기존 여행에 추가'}
              </button>
            ))}
          </div>

          {form.mode === 'new' ? (
            <div className="space-y-3">
              <FormField
                ref={titleRef}
                id="notice-copy-title"
                label="여행 제목"
                labelClassName={DIALOG_LABEL}
                value={form.title}
                onChange={(event) => update({ title: event.target.value })}
                maxLength={200}
              />
              <div className="grid grid-cols-2 gap-2">
                <FormField
                  id="notice-copy-start"
                  label="시작일"
                  type="date"
                  labelClassName={DIALOG_LABEL}
                  value={form.startDate}
                  onChange={(event) => update({ startDate: event.target.value })}
                />
                <FormField
                  id="notice-copy-end"
                  label="종료일"
                  type="date"
                  labelClassName={DIALOG_LABEL}
                  value={form.endDate}
                  onChange={(event) => update({ endDate: event.target.value })}
                />
              </div>
            </div>
          ) : loadingTrips ? (
            <div className="space-y-2" aria-busy="true" aria-live="polite">
              <span className="sr-only">여행 목록을 불러오는 중…</span>
              {[0, 1, 2].map((row) => (
                <div key={row} className="h-11 animate-pulse rounded-sm bg-surface-soft" />
              ))}
            </div>
          ) : trips.length === 0 ? (
            <p className="rounded-sm bg-surface-soft px-3 py-2 text-sm text-muted">
              추가할 여행이 없습니다. 새 여행으로 만들어 보세요.
            </p>
          ) : (
            <ul className="max-h-48 space-y-1 overflow-auto">
              {trips.map((trip) => (
                <li key={trip.trip_id}>
                  <button
                    type="button"
                    onClick={() => update({ targetTripId: trip.trip_id })}
                    aria-pressed={form.targetTripId === trip.trip_id}
                    className={
                      form.targetTripId === trip.trip_id
                        ? 'focus-ring block min-h-11 w-full rounded-sm border border-ink bg-surface-soft px-3 py-2 text-left text-sm font-medium text-ink'
                        : 'focus-ring block min-h-11 w-full rounded-sm border border-hairline px-3 py-2 text-left text-sm text-ink hover:bg-surface-soft'
                    }
                  >
                    {trip.title}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {error ? (
            <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">
              {error}
            </p>
          ) : null}
        </div>
      )}
    </Dialog>
  );
}
