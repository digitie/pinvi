'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Loader2 } from 'lucide-react';
import { ApiError, noticePlanApi, tripApi } from '@tripmate/api-client';
import type { NoticePlan, NoticePlanCopyResponse, TripResponse } from '@tripmate/schemas';
import { apiClient } from '@/lib/api';
import { buildCopyRequest, canCopy, type CopyForm } from '@/lib/noticePlanCopy';
import { useEscapeKey } from '@/lib/useEscapeKey';
import { useDialogAutoFocus } from '@/lib/useDialogAutoFocus';
import { FormField } from '@/components/forms/FormField';

const DIALOG_LABEL = 'block text-sm font-semibold text-ink';
const DIALOG_INPUT = 'h-9 px-2 focus:border-primary';

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

  useEscapeKey(onClose);
  useDialogAutoFocus(titleRef);

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

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="추천 여행 가져오기"
      data-testid="notice-copy-dialog"
    >
      <div className="w-full max-w-md space-y-4 rounded-md border border-hairline bg-white p-5 shadow-lg">
        <h2 className="text-base font-bold text-ink">추천 여행 가져오기</h2>
        <p className="truncate text-sm text-muted">{plan.title}</p>

        {result ? (
          <div className="space-y-3">
            <p className="flex items-center gap-2 rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              {result.created_trip ? '새 여행을 만들었습니다.' : '기존 여행에 추가했습니다.'} 장소{' '}
              {result.copied_poi_ids.length}곳 복사.
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="h-9 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
              >
                닫기
              </button>
              <Link
                href={`/trips/${result.trip_id}`}
                className="inline-flex h-9 items-center rounded-sm bg-primary px-4 text-sm font-semibold text-white"
              >
                여행 열기
              </Link>
            </div>
          </div>
        ) : (
          <>
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
                      ? 'h-9 flex-1 rounded-sm bg-ink text-sm font-semibold text-white'
                      : 'h-9 flex-1 rounded-sm border border-hairline bg-white text-sm font-semibold text-ink hover:bg-surface-soft'
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
                  className={DIALOG_INPUT}
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
                    className={DIALOG_INPUT}
                    value={form.startDate}
                    onChange={(event) => update({ startDate: event.target.value })}
                  />
                  <FormField
                    id="notice-copy-end"
                    label="종료일"
                    type="date"
                    labelClassName={DIALOG_LABEL}
                    className={DIALOG_INPUT}
                    value={form.endDate}
                    onChange={(event) => update({ endDate: event.target.value })}
                  />
                </div>
              </div>
            ) : loadingTrips ? (
              <div className="flex h-24 items-center justify-center text-sm text-muted">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                여행 목록 불러오는 중…
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
                          ? 'block w-full rounded-sm border border-primary bg-surface-soft px-3 py-2 text-left text-sm font-medium text-ink'
                          : 'block w-full rounded-sm border border-hairline px-3 py-2 text-left text-sm text-ink hover:bg-surface-soft'
                      }
                    >
                      {trip.title}
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {error && (
              <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">{error}</p>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="h-9 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
              >
                취소
              </button>
              <button
                type="button"
                onClick={() => void copy()}
                disabled={copying || !canCopy(form)}
                data-testid="notice-copy-confirm"
                className="inline-flex h-9 items-center gap-1 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
              >
                {copying && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                복사
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
