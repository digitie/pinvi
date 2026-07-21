'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, Pencil, Plus, Trash2 } from 'lucide-react';
import { MARKER_PALETTE, type MarkerColorKey, paletteHex } from '@pinvi/domain';
import { useDialogAutoFocus } from '@/lib/useDialogAutoFocus';
import { useEscapeKey } from '@/lib/useEscapeKey';

const PALETTE_KEYS = Object.keys(MARKER_PALETTE) as MarkerColorKey[];

export interface TripDayControlsProps {
  selectedDay: {
    day_index: number;
    title: string | null;
    date: string | null;
    marker_color?: string | null;
  } | null;
  onAdd: () => void;
  onUpdate: (
    dayIndex: number,
    patch: { title: string; date: string | null; marker_color: string | null },
  ) => void;
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
  const [color, setColor] = useState<string | null>(selectedDay?.marker_color ?? null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const addDisabled = busy || !canAdd;

  useEffect(() => {
    setTitle(selectedDay?.title ?? '');
    setDate(selectedDay?.date ?? '');
    setColor(selectedDay?.marker_color ?? null);
    setSettingsOpen(false);
  }, [
    selectedDay?.date,
    selectedDay?.day_index,
    selectedDay?.title,
    selectedDay?.marker_color,
  ]);

  const saveSettings = () => {
    if (!selectedDay) return;
    onUpdate(selectedDay.day_index, {
      title: title.trim(),
      date: date || null,
      marker_color: color,
    });
    setSettingsOpen(false);
  };
  const closeSettings = () => {
    setTitle(selectedDay?.title ?? '');
    setDate(selectedDay?.date ?? '');
    setColor(selectedDay?.marker_color ?? null);
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
              currentColor={selectedDay.marker_color ?? null}
              title={title}
              date={date}
              color={color}
              busy={busy}
              onTitleChange={setTitle}
              onDateChange={setDate}
              onColorChange={setColor}
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
  currentColor: string | null;
  title: string;
  date: string;
  color: string | null;
  busy: boolean;
  onTitleChange: (title: string) => void;
  onDateChange: (date: string) => void;
  onColorChange: (color: string | null) => void;
  onSave: () => void;
  onClose: () => void;
}

function DaySettingsDialog({
  dayIndex,
  currentTitle,
  currentDate,
  currentColor,
  title,
  date,
  color,
  busy,
  onTitleChange,
  onDateChange,
  onColorChange,
  onSave,
  onClose,
}: DaySettingsDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  useEscapeKey(onClose);
  useDialogAutoFocus(inputRef);
  const normalizedTitle = title.trim();
  const unchanged =
    normalizedTitle === (currentTitle ?? '') &&
    (date || null) === currentDate &&
    color === currentColor;

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
        <span className="block text-sm font-semibold text-ink">일자 색</span>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="일자 마커 색" data-testid="trip-day-color-picker">
          {/* 기본색(팔레트 순환) = null override 제거. */}
          <button
            type="button"
            onClick={() => onColorChange(null)}
            aria-pressed={color === null}
            aria-label="기본 색"
            title="기본 색(일자 순서 팔레트)"
            className={
              color === null
                ? 'flex h-7 w-7 items-center justify-center rounded-full border border-dashed border-border-strong text-[10px] font-bold text-muted ring-2 ring-primary ring-offset-1'
                : 'flex h-7 w-7 items-center justify-center rounded-full border border-dashed border-border-strong text-[10px] font-bold text-muted'
            }
          >
            기본
          </button>
          {PALETTE_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => onColorChange(key)}
              aria-pressed={color === key}
              aria-label={`${MARKER_PALETTE[key].name} 색`}
              title={MARKER_PALETTE[key].name}
              data-testid={`trip-day-color-${key}`}
              style={{ backgroundColor: paletteHex(key) }}
              className={
                color === key
                  ? 'flex h-7 w-7 items-center justify-center rounded-full ring-2 ring-primary ring-offset-1'
                  : 'h-7 w-7 rounded-full'
              }
            >
              {color === key && <Check className="h-4 w-4 text-white" aria-hidden="true" />}
            </button>
          ))}
        </div>
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
