'use client';

import { useRef, useState } from 'react';
import type { TripResponse, TripStatus, TripUpdate, TripVisibility } from '@pinvi/schemas';
import {
  STATUS_LABEL,
  VISIBILITY_LABEL,
  buildTripUpdate,
  validateTripDateRange,
  type TripDateRangeError,
  type TripEditForm,
} from '@pinvi/domain';
import { FormField } from '@/components/forms/FormField';
import { FormSelect } from '@/components/forms/FormSelect';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';

const DIALOG_LABEL = 'block text-sm font-semibold text-ink';

const STATUSES: TripStatus[] = ['draft', 'planned', 'in_progress', 'completed', 'archived'];
const VISIBILITIES: TripVisibility[] = ['private', 'unlisted', 'public'];

export interface TripEditDialogProps {
  trip: TripResponse;
  saving?: boolean;
  error?: string | null;
  onSave: (patch: TripUpdate) => void;
  onClose: () => void;
  /** 저장 중 명시적 닫기 — 진행 중 요청을 취소하고 닫는다(T-316 요청 수명 계약 ⑤). */
  onCancelBusy?: () => void;
}

export function TripEditDialog({
  trip,
  saving = false,
  error = null,
  onSave,
  onClose,
  onCancelBusy,
}: TripEditDialogProps) {
  const titleRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState<TripEditForm>({
    title: trip.title,
    regionHint: trip.region_hint ?? '',
    startDate: trip.start_date ?? '',
    endDate: trip.end_date ?? '',
    visibility: trip.visibility,
    status: trip.status,
  });

  const [dateError, setDateError] = useState<TripDateRangeError | null>(null);
  const update = (patch: Partial<TripEditForm>) => {
    if ('startDate' in patch || 'endDate' in patch) setDateError(null);
    setForm((prev) => ({ ...prev, ...patch }));
  };
  // #624: 날짜 오류는 서버 왕복 전에 해당 날짜 필드에 붙인다. PATCH는 null 날짜를 '유지'로 다루므로
  // 이미 정한 기간을 비우는 입력도 여기서 막는다(저장 성공처럼 보이고 아무것도 바뀌지 않던 문제).
  const save = () => {
    const rangeError =
      validateTripDateRange(form.startDate, form.endDate) ??
      (trip.start_date && !form.startDate.trim() && !form.endDate.trim()
        ? { field: 'startDate' as const, message: '이미 정한 여행 기간은 비울 수 없습니다. 다른 날짜로 바꿔 주세요.' }
        : null);
    if (rangeError) {
      setDateError(rangeError);
      return;
    }
    onSave(buildTripUpdate(form));
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title="여행 편집"
      size="sm"
      busy={saving}
      onCancelBusy={onCancelBusy}
      initialFocusRef={titleRef}
      testId="trip-edit-dialog"
      footer={
        <>
          <Button
            variant="secondary"
            onClick={onCancelBusy && saving ? onCancelBusy : onClose}
            disabled={saving && !onCancelBusy}
          >
            취소
          </Button>
          <Button
            onClick={save}
            disabled={!form.title.trim()}
            loading={saving}
            data-testid="trip-edit-save"
          >
            저장
          </Button>
        </>
      }
    >
      <div className="space-y-2">
        <FormField
          ref={titleRef}
          id="trip-edit-title"
          label="제목"
          labelClassName={DIALOG_LABEL}
          value={form.title}
          onChange={(event) => update({ title: event.target.value })}
          maxLength={200}
        />
        <FormField
          id="trip-edit-region"
          label="지역"
          labelClassName={DIALOG_LABEL}
          value={form.regionHint}
          onChange={(event) => update({ regionHint: event.target.value })}
          maxLength={120}
        />
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <FormField
            id="trip-edit-start"
            label="시작일"
            type="date"
            labelClassName={DIALOG_LABEL}
            value={form.startDate}
            error={dateError?.field === 'startDate' ? dateError.message : undefined}
            onChange={(event) => update({ startDate: event.target.value })}
          />
          <FormField
            id="trip-edit-end"
            label="종료일"
            type="date"
            labelClassName={DIALOG_LABEL}
            value={form.endDate}
            error={dateError?.field === 'endDate' ? dateError.message : undefined}
            onChange={(event) => update({ endDate: event.target.value })}
          />
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <FormSelect
            id="trip-edit-status"
            label="상태"
            labelClassName={DIALOG_LABEL}
            value={form.status}
            onChange={(event) => update({ status: event.target.value as TripStatus })}
          >
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {STATUS_LABEL[status]}
              </option>
            ))}
          </FormSelect>
          <FormSelect
            id="trip-edit-visibility"
            label="공개 범위"
            labelClassName={DIALOG_LABEL}
            value={form.visibility}
            onChange={(event) => update({ visibility: event.target.value as TripVisibility })}
          >
            {VISIBILITIES.map((visibility) => (
              <option key={visibility} value={visibility}>
                {VISIBILITY_LABEL[visibility]}
              </option>
            ))}
          </FormSelect>
        </div>

        {error && (
          <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">
            {error}
          </p>
        )}
      </div>
    </Dialog>
  );
}
