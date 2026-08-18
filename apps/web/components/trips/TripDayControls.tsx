'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, Pencil, Plus, Trash2 } from 'lucide-react';
import { MARKER_PALETTE, type MarkerColorKey, paletteHex } from '@pinvi/domain';
import type { DayUpdateResult } from '@/components/trips/TripDetail';
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
    /** 다이얼로그를 연 시점의 version 스냅샷 원본 — 저장 시 If-Match로 쓴다. */
    version?: number;
  } | null;
  onAdd: () => void;
  /**
   * 저장 결과 — 다이얼로그는 **성공했을 때만** 닫고(실패 시 입력값 보존) 실패 원인은 모달 안에서
   * 보여 준다. `expectedVersion`은 다이얼로그를 연 시점의 version이다(열려 있는 동안 들어온
   * 서버 갱신 버전으로 저장하면 남의 변경을 조용히 덮는다).
   */
  onUpdate: (
    dayIndex: number,
    patch: { title: string; date: string | null; marker_color: string | null },
    expectedVersion?: number,
  ) => Promise<DayUpdateResult>;
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
  // 오류는 **이 다이얼로그 세션**이 소유한다 — 전역 오류를 그대로 넘기면 아무것도 하지 않은
  // 새 다이얼로그가 이전(또는 무관한) 실패를 띄운다(T-315 5차 리뷰).
  const [saveError, setSaveError] = useState<{ message: string; field?: 'date' } | null>(null);
  // 연 시점의 version — 열려 있는 동안 reload가 들어와도 이 값으로 저장해 409를 살린다.
  const openedVersionRef = useRef<number | undefined>(undefined);
  const addDisabled = busy || !canAdd;

  // 열려 있는 폼은 서버 갱신으로 덮지 않는다 — 409 후 reload가 사용자가 입력한 이름·날짜·색을
  // 지우고 다이얼로그까지 닫던 문제(T-315 4차 리뷰). 닫혀 있을 때만 서버 값과 동기화한다.
  // (인스턴스는 일자마다 key={day_index}로 분리돼 있어 '다른 일자로 전환' 분기는 필요 없다.)
  useEffect(() => {
    if (settingsOpen) return;
    setTitle(selectedDay?.title ?? '');
    setDate(selectedDay?.date ?? '');
    setColor(selectedDay?.marker_color ?? null);
  }, [settingsOpen, selectedDay?.title, selectedDay?.date, selectedDay?.marker_color]);

  const openSettings = () => {
    setSaveError(null);
    openedVersionRef.current = selectedDay?.version;
    setSettingsOpen(true);
  };

  const saveSettings = async () => {
    if (!selectedDay) return;
    // 저장이 끝나기 전에 닫으면 busy 잠금이 무의미해지고, 실패 시 입력값이 사라진다.
    const result = await onUpdate(
      selectedDay.day_index,
      { title: title.trim(), date: date || null, marker_color: color },
      openedVersionRef.current,
    );
    if (result.ok) {
      setSaveError(null);
      setSettingsOpen(false);
      return;
    }
    setSaveError({ message: result.message, field: result.field });
  };
  const closeSettings = () => {
    setSaveError(null);
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
            onClick={openSettings}
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
              saveError={saveError}
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
  /** 이 다이얼로그 세션에서 난 저장 실패/검증 오류(모달 안 표시). */
  saveError?: { message: string; field?: 'date' } | null;
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
  saveError = null,
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
        {saveError && !saveError.field && (
          // 실패해도 다이얼로그가 열린 채 남으므로 오류는 **모달 안**에 있어야 한다 —
          // 바깥 배너는 scrim 뒤라 보이지도, aria-modal 안에서 읽히지도 않는다(4차 리뷰).
          // 필드 원인이 분명한 오류는 아래 해당 FormField가 대신 announce한다(중복 방지).
          <p
            role="alert"
            data-testid="trip-day-settings-error"
            className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          >
            {saveError.message}
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
          error={saveError?.field === 'date' ? saveError.message : undefined}
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
            className={`disabled:cursor-not-allowed disabled:opacity-60 ${
              color === null
                ? 'flex h-7 w-7 items-center justify-center rounded-full border border-dashed border-border-strong text-xs font-bold text-muted ring-2 ring-primary ring-offset-1'
                : 'flex h-7 w-7 items-center justify-center rounded-full border border-dashed border-border-strong text-xs font-bold text-muted'
            }`}
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
              className={`disabled:cursor-not-allowed disabled:opacity-60 ${
                color === key
                  ? 'flex h-7 w-7 items-center justify-center rounded-full ring-2 ring-primary ring-offset-1'
                  : 'h-7 w-7 rounded-full'
              }`}
            >
              {color === key && <Check className="h-4 w-4 text-white" aria-hidden="true" />}
            </button>
          ))}
        </div>
      </form>
    </Dialog>
  );
}
