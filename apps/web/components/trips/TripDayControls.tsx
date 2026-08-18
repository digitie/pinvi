'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, Pencil, Plus, Trash2 } from 'lucide-react';
import { MARKER_PALETTE, type MarkerColorKey, paletteHex } from '@pinvi/domain';
import { FormField } from '@/components/forms/FormField';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';

const PALETTE_KEYS = Object.keys(MARKER_PALETTE) as MarkerColorKey[];
const DIALOG_LABEL = 'block text-sm font-semibold text-ink';
// 푸터 버튼이 다이얼로그 셸 밖(footer 슬롯)에 있어 form 속성으로 제출을 잇는다.
const FORM_ID = 'trip-day-settings-form';

export interface TripDayControlsProps {
  selectedDay: {
    day_index: number;
    title: string | null;
    date: string | null;
    marker_color?: string | null;
  } | null;
  onAdd: () => void;
  /** 성공하면 true — 다이얼로그는 **성공했을 때만** 닫는다(실패 시 입력값 보존). */
  onUpdate: (
    dayIndex: number,
    patch: { title: string; date: string | null; marker_color: string | null },
  ) => Promise<boolean>;
  onDelete: (dayIndex: number) => void;
  canAdd?: boolean;
  addDisabledReason?: string | null;
  showAdd?: boolean;
  busy?: boolean;
  /** 저장 실패/검증 오류 — 다이얼로그가 열린 채 남으므로 **모달 안에서** 보여야 한다. */
  error?: string | null;
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
  error = null,
}: TripDayControlsProps) {
  const [title, setTitle] = useState(selectedDay?.title ?? '');
  const [date, setDate] = useState(selectedDay?.date ?? '');
  const [color, setColor] = useState<string | null>(selectedDay?.marker_color ?? null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const addDisabled = busy || !canAdd;

  const lastDayIndexRef = useRef(selectedDay?.day_index);

  useEffect(() => {
    const dayChanged = lastDayIndexRef.current !== selectedDay?.day_index;
    lastDayIndexRef.current = selectedDay?.day_index;
    // 열려 있는 폼은 **같은 일자**의 서버 갱신으로 덮지 않는다 — 409 충돌 후 reload가 사용자가
    // 입력한 이름·날짜·색을 지우고 다이얼로그까지 닫던 문제(T-315 4차 리뷰).
    if (settingsOpen && !dayChanged) return;
    setTitle(selectedDay?.title ?? '');
    setDate(selectedDay?.date ?? '');
    setColor(selectedDay?.marker_color ?? null);
    if (dayChanged) setSettingsOpen(false);
  }, [
    settingsOpen,
    selectedDay?.day_index,
    selectedDay?.title,
    selectedDay?.date,
    selectedDay?.marker_color,
  ]);

  const saveSettings = async () => {
    if (!selectedDay) return;
    // 저장이 끝나기 전에 닫으면 busy 잠금이 무의미해지고, 실패 시 입력값이 사라진다.
    const ok = await onUpdate(selectedDay.day_index, {
      title: title.trim(),
      date: date || null,
      marker_color: color,
    });
    if (ok) setSettingsOpen(false);
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
          className="inline-flex h-9 items-center gap-1 rounded-sm border border-hairline bg-canvas px-3 text-sm font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
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
              busyError={error}
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
  /** 저장 실패/검증 오류 메시지(모달 안 표시). */
  busyError?: string | null;
  onTitleChange: (title: string) => void;
  onDateChange: (date: string) => void;
  onColorChange: (color: string | null) => void;
  onSave: () => void | Promise<void>;
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
  busyError = null,
  onTitleChange,
  onDateChange,
  onColorChange,
  onSave,
  onClose,
}: DaySettingsDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const normalizedTitle = title.trim();
  const unchanged =
    normalizedTitle === (currentTitle ?? '') &&
    (date || null) === currentDate &&
    color === currentColor;

  return (
    <Dialog
      open
      onClose={onClose}
      title={`${dayIndex}일차 설정`}
      size="sm"
      busy={busy}
      initialFocusRef={inputRef}
      testId="trip-day-title-dialog"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button type="submit" form={FORM_ID} disabled={unchanged} loading={busy}>
            저장
          </Button>
        </>
      }
    >
      <form
        id={FORM_ID}
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!unchanged) void onSave();
        }}
      >
        {busyError && (
          // 실패해도 다이얼로그가 열린 채 남으므로 오류는 **모달 안**에 있어야 한다 —
          // 바깥 배너는 scrim 뒤라 보이지도, aria-modal 안에서 읽히지도 않는다(4차 리뷰).
          <p
            role="alert"
            data-testid="trip-day-settings-error"
            className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          >
            {busyError}
          </p>
        )}
        <FormField
          ref={inputRef}
          id="trip-day-title-input"
          label="이름"
          labelClassName={DIALOG_LABEL}
          value={title}
          onChange={(event) => onTitleChange(event.target.value)}
          disabled={busy}
          maxLength={200}
          placeholder={`${dayIndex}일차`}
        />
        <FormField
          id="trip-day-date-input"
          label="날짜"
          type="date"
          labelClassName={DIALOG_LABEL}
          value={date}
          onChange={(event) => onDateChange(event.target.value)}
          disabled={busy}
        />
        <span className="block text-sm font-semibold text-ink">일자 색</span>
        <div
          className="flex flex-wrap gap-1.5"
          role="group"
          aria-label="일자 마커 색"
          data-testid="trip-day-color-picker"
        >
          {/* 기본색(팔레트 순환) = null override 제거. */}
          <button
            type="button"
            onClick={() => onColorChange(null)}
            aria-pressed={color === null}
            disabled={busy}
            aria-label="기본 색"
            title="기본 색(일자 순서 팔레트)"
            className={
              color === null
                ? 'flex h-7 w-7 items-center justify-center rounded-full border border-dashed border-border-strong text-xs font-bold text-muted ring-2 ring-primary ring-offset-1'
                : 'flex h-7 w-7 items-center justify-center rounded-full border border-dashed border-border-strong text-xs font-bold text-muted'
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
              disabled={busy}
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
      </form>
    </Dialog>
  );
}
