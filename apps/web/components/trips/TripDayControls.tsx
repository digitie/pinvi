'use client';

import { useEffect, useRef, useState } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useDialogAutoFocus } from '@/lib/useDialogAutoFocus';
import { useEscapeKey } from '@/lib/useEscapeKey';

export interface TripDayControlsProps {
  selectedDay: { day_index: number; title: string | null; date: string | null } | null;
  onAdd: () => void;
  onUpdate: (dayIndex: number, patch: { title: string; date: string | null }) => void;
  onDelete: (dayIndex: number) => void;
  canAdd?: boolean;
  addDisabledReason?: string | null;
  showAdd?: boolean;
  busy?: boolean;
}

export function TripDayControls({
  selectedDay,
  onAdd,
  onUpdate,
  onDelete,
  canAdd = true,
  addDisabledReason = null,
  showAdd = true,
  busy = false,
}: TripDayControlsProps) {
  const [title, setTitle] = useState(selectedDay?.title ?? '');
  const [date, setDate] = useState(selectedDay?.date ?? '');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const addDisabled = busy || !canAdd;

  useEffect(() => {
    setTitle(selectedDay?.title ?? '');
    setDate(selectedDay?.date ?? '');
    setSettingsOpen(false);
  }, [selectedDay?.date, selectedDay?.day_index, selectedDay?.title]);

  const saveSettings = () => {
    if (!selectedDay) return;
    onUpdate(selectedDay.day_index, {
      title: title.trim(),
      date: date || null,
    });
    setSettingsOpen(false);
  };
  const closeSettings = () => {
    setTitle(selectedDay?.title ?? '');
    setDate(selectedDay?.date ?? '');
    setSettingsOpen(false);
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
            onClick={() => setSettingsOpen(true)}
            disabled={busy}
            aria-label={`${selectedDay.day_index}일차 설정`}
            title="일자 설정"
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
          {settingsOpen && (
            <DaySettingsDialog
              dayIndex={selectedDay.day_index}
              currentTitle={selectedDay.title}
              currentDate={selectedDay.date}
              title={title}
              date={date}
              busy={busy}
              onTitleChange={setTitle}
              onDateChange={setDate}
              onSave={saveSettings}
              onClose={closeSettings}
            />
          )}
        </>
      )}
    </div>
  );
}

interface DaySettingsDialogProps {
  dayIndex: number;
  currentTitle: string | null;
  currentDate: string | null;
  title: string;
  date: string;
  busy: boolean;
  onTitleChange: (title: string) => void;
  onDateChange: (date: string) => void;
  onSave: () => void;
  onClose: () => void;
}

function DaySettingsDialog({
  dayIndex,
  currentTitle,
  currentDate,
  title,
  date,
  busy,
  onTitleChange,
  onDateChange,
  onSave,
  onClose,
}: DaySettingsDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  useEscapeKey(onClose);
  useDialogAutoFocus(inputRef);
  const normalizedTitle = title.trim();
  const unchanged = normalizedTitle === (currentTitle ?? '') && (date || null) === currentDate;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="일자 설정"
      data-testid="trip-day-title-dialog"
    >
      <form
        className="w-full max-w-sm space-y-3 rounded-md border border-hairline bg-white p-5 shadow-lg"
        onSubmit={(event) => {
          event.preventDefault();
          if (!unchanged) onSave();
        }}
      >
        <h2 className="text-base font-bold text-ink">{dayIndex}일차 설정</h2>
        <label className="block text-sm font-semibold text-ink" htmlFor="trip-day-title-input">
          이름
        </label>
        <input
          ref={inputRef}
          id="trip-day-title-input"
          value={title}
          onChange={(event) => onTitleChange(event.target.value)}
          maxLength={200}
          placeholder={`${dayIndex}일차`}
          className="h-9 w-full rounded-sm border border-hairline px-2 text-sm text-ink outline-none focus:border-primary"
        />
        <label className="block text-sm font-semibold text-ink" htmlFor="trip-day-date-input">
          날짜
        </label>
        <input
          id="trip-day-date-input"
          type="date"
          value={date}
          onChange={(event) => onDateChange(event.target.value)}
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
