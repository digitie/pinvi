'use client';

import { useEffect, useRef, useState } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useDialogAutoFocus } from '@/lib/useDialogAutoFocus';
import { useEscapeKey } from '@/lib/useEscapeKey';

export interface TripDayControlsProps {
  selectedDay: { day_index: number; title: string | null } | null;
  onAdd: () => void;
  onRename: (dayIndex: number, title: string) => void;
  onDelete: (dayIndex: number) => void;
  canAdd?: boolean;
  addDisabledReason?: string | null;
  showAdd?: boolean;
  busy?: boolean;
}

export function TripDayControls({
  selectedDay,
  onAdd,
  onRename,
  onDelete,
  canAdd = true,
  addDisabledReason = null,
  showAdd = true,
  busy = false,
}: TripDayControlsProps) {
  const [title, setTitle] = useState(selectedDay?.title ?? '');
  const [renameOpen, setRenameOpen] = useState(false);
  const addDisabled = busy || !canAdd;

  useEffect(() => {
    setTitle(selectedDay?.title ?? '');
    setRenameOpen(false);
  }, [selectedDay?.day_index, selectedDay?.title]);

  const saveTitle = () => {
    if (!selectedDay) return;
    onRename(selectedDay.day_index, title.trim());
    setRenameOpen(false);
  };
  const closeRename = () => {
    setTitle(selectedDay?.title ?? '');
    setRenameOpen(false);
  };

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="trip-day-controls">
      {showAdd && (
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
      )}
      {showAdd && addDisabledReason && (
        <p id="trip-day-add-disabled-reason" className="text-xs text-muted">
          {addDisabledReason}
        </p>
      )}
      {selectedDay && (
        <>
          <button
            type="button"
            onClick={() => setRenameOpen(true)}
            disabled={busy}
            aria-label={`${selectedDay.day_index}일차 이름 변경`}
            title="이름 변경"
            className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-hairline text-ink hover:bg-surface-soft disabled:opacity-50"
            data-testid="trip-day-rename"
          >
            <Pencil className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => onDelete(selectedDay.day_index)}
            disabled={busy}
            aria-label={`${selectedDay.day_index}일차 삭제`}
            title="삭제"
            className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-hairline text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
            data-testid="trip-day-delete"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </button>
          {renameOpen && (
            <DayTitleDialog
              dayIndex={selectedDay.day_index}
              currentTitle={selectedDay.title}
              title={title}
              busy={busy}
              onChange={setTitle}
              onSave={saveTitle}
              onClose={closeRename}
            />
          )}
        </>
      )}
    </div>
  );
}

interface DayTitleDialogProps {
  dayIndex: number;
  currentTitle: string | null;
  title: string;
  busy: boolean;
  onChange: (title: string) => void;
  onSave: () => void;
  onClose: () => void;
}

function DayTitleDialog({
  dayIndex,
  currentTitle,
  title,
  busy,
  onChange,
  onSave,
  onClose,
}: DayTitleDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  useEscapeKey(onClose);
  useDialogAutoFocus(inputRef);
  const normalizedTitle = title.trim();
  const unchanged = normalizedTitle === (currentTitle ?? '');

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="일자 이름 변경"
      data-testid="trip-day-title-dialog"
    >
      <form
        className="w-full max-w-sm space-y-3 rounded-md border border-hairline bg-white p-5 shadow-lg"
        onSubmit={(event) => {
          event.preventDefault();
          if (!unchanged) onSave();
        }}
      >
        <h2 className="text-base font-bold text-ink">{dayIndex}일차 이름</h2>
        <label className="block text-sm font-semibold text-ink" htmlFor="trip-day-title-input">
          이름
        </label>
        <input
          ref={inputRef}
          id="trip-day-title-input"
          value={title}
          onChange={(event) => onChange(event.target.value)}
          maxLength={200}
          placeholder={`${dayIndex}일차`}
          className="h-9 w-full rounded-sm border border-hairline px-2 text-sm text-ink outline-none focus:border-primary"
        />
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-9 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={busy || unchanged}
            className="h-9 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
          >
            저장
          </button>
        </div>
      </form>
    </div>
  );
}
