'use client';

import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

export interface TripDayControlsProps {
  selectedDay: { day_index: number; title: string | null } | null;
  onAdd: () => void;
  onRename: (dayIndex: number, title: string) => void;
  onDelete: (dayIndex: number) => void;
  canAdd?: boolean;
  addDisabledReason?: string | null;
  busy?: boolean;
}

export function TripDayControls({
  selectedDay,
  onAdd,
  onRename,
  onDelete,
  canAdd = true,
  addDisabledReason = null,
  busy = false,
}: TripDayControlsProps) {
  const [title, setTitle] = useState(selectedDay?.title ?? '');
  const addDisabled = busy || !canAdd;

  useEffect(() => {
    setTitle(selectedDay?.title ?? '');
  }, [selectedDay?.day_index, selectedDay?.title]);

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="trip-day-controls">
      <button
        type="button"
        onClick={onAdd}
        disabled={addDisabled}
        title={addDisabledReason ?? undefined}
        aria-describedby={addDisabledReason ? 'trip-day-add-disabled-reason' : undefined}
        className="inline-flex h-9 items-center gap-1 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
      >
        <Plus className="h-4 w-4" aria-hidden="true" />
        일자 추가
      </button>
      {addDisabledReason && (
        <p id="trip-day-add-disabled-reason" className="text-xs text-muted">
          {addDisabledReason}
        </p>
      )}
      {selectedDay && (
        <>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onBlur={() => {
              if ((title.trim() || '') !== (selectedDay.title ?? '')) {
                onRename(selectedDay.day_index, title.trim());
              }
            }}
            maxLength={200}
            placeholder={`${selectedDay.day_index}일차 이름`}
            aria-label="일자 이름"
            className="h-9 w-44 rounded-sm border border-hairline px-2 text-sm text-ink outline-none focus:border-primary"
          />
          <button
            type="button"
            onClick={() => onDelete(selectedDay.day_index)}
            disabled={busy}
            aria-label="일자 삭제"
            className="inline-flex h-9 items-center gap-1 rounded-sm border border-hairline px-3 text-sm font-semibold text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            삭제
          </button>
        </>
      )}
    </div>
  );
}
