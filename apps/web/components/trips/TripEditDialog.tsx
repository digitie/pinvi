'use client';

import { useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import type { TripResponse, TripStatus, TripUpdate, TripVisibility } from '@pinvi/schemas';
import {
  STATUS_LABEL,
  VISIBILITY_LABEL,
  buildTripUpdate,
  type TripEditForm,
} from '@/lib/tripEdit';
import { useEscapeKey } from '@/lib/useEscapeKey';
import { useDialogAutoFocus } from '@/lib/useDialogAutoFocus';
import { FormField } from '@/components/forms/FormField';

const DIALOG_LABEL = 'block text-sm font-semibold text-ink';
const DIALOG_INPUT = 'h-9 px-2 focus:border-primary';

const STATUSES: TripStatus[] = ['draft', 'planned', 'in_progress', 'completed', 'archived'];
const VISIBILITIES: TripVisibility[] = ['private', 'unlisted', 'public'];

export interface TripEditDialogProps {
  trip: TripResponse;
  saving?: boolean;
  error?: string | null;
  onSave: (patch: TripUpdate) => void;
  onClose: () => void;
}

export function TripEditDialog({ trip, saving = false, error = null, onSave, onClose }: TripEditDialogProps) {
  useEscapeKey(onClose);
  const titleRef = useRef<HTMLInputElement>(null);
  useDialogAutoFocus(titleRef);
  const [form, setForm] = useState<TripEditForm>({
    title: trip.title,
    regionHint: trip.region_hint ?? '',
    startDate: trip.start_date ?? '',
    endDate: trip.end_date ?? '',
    visibility: trip.visibility,
    status: trip.status,
  });

  const update = (patch: Partial<TripEditForm>) => setForm((prev) => ({ ...prev, ...patch }));

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="여행 편집"
      data-testid="trip-edit-dialog"
    >
      <div className="w-full max-w-md space-y-3 rounded-md border border-hairline bg-white p-5 shadow-lg">
        <h2 className="text-base font-bold text-ink">여행 편집</h2>

        <FormField
          ref={titleRef}
          id="trip-edit-title"
          label="제목"
          labelClassName={DIALOG_LABEL}
          className={DIALOG_INPUT}
          value={form.title}
          onChange={(event) => update({ title: event.target.value })}
          maxLength={200}
        />
        <FormField
          id="trip-edit-region"
          label="지역"
          labelClassName={DIALOG_LABEL}
          className={DIALOG_INPUT}
          value={form.regionHint}
          onChange={(event) => update({ regionHint: event.target.value })}
          maxLength={120}
        />
        <div className="grid grid-cols-2 gap-2">
          <FormField
            id="trip-edit-start"
            label="시작일"
            type="date"
            labelClassName={DIALOG_LABEL}
            className={DIALOG_INPUT}
            value={form.startDate}
            onChange={(event) => update({ startDate: event.target.value })}
          />
          <FormField
            id="trip-edit-end"
            label="종료일"
            type="date"
            labelClassName={DIALOG_LABEL}
            className={DIALOG_INPUT}
            value={form.endDate}
            onChange={(event) => update({ endDate: event.target.value })}
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="block text-sm font-semibold text-ink">
            상태
            <select
              value={form.status}
              onChange={(event) => update({ status: event.target.value as TripStatus })}
              className="mt-1 h-9 w-full rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-semibold text-ink">
            공개 범위
            <select
              value={form.visibility}
              onChange={(event) => update({ visibility: event.target.value as TripVisibility })}
              className="mt-1 h-9 w-full rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
            >
              {VISIBILITIES.map((v) => (
                <option key={v} value={v}>
                  {VISIBILITY_LABEL[v]}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && (
          <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">
            {error}
          </p>
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
            onClick={() => onSave(buildTripUpdate(form))}
            disabled={saving || !form.title.trim()}
            data-testid="trip-edit-save"
            className="inline-flex h-9 items-center gap-1 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
