'use client';

import { type ReactNode, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import type { PoiUpdate, TripViewPoi } from '@pinvi/schemas';
import { MARKER_PALETTE, type MarkerColorKey } from '@pinvi/design-tokens';
import { buildPoiDetailPatch, isoToDatetimeLocal, type PoiDetailForm } from '@pinvi/domain';
import { FormField } from '@/components/forms/FormField';
import { FormTextArea } from '@/components/forms/FormTextArea';
import { MakiIcon } from '@/components/map/MakiIcon';
import { MARKER_ICON_OPTIONS, type MarkerIconOption } from '@pinvi/domain';

const COLOR_KEYS = Object.keys(MARKER_PALETTE) as MarkerColorKey[];

const POI_LABEL = 'block text-xs font-semibold text-ink';
const POI_INPUT = 'h-9 px-2 focus:border-primary';

export interface PoiEditorProps {
  poi: TripViewPoi;
  currentDayIndex?: number;
  dayOptions?: { day_index: number; title: string | null }[];
  saving?: boolean;
  onSave: (patch: PoiUpdate) => void;
  onCancel: () => void;
}

/** 고르기 목록 + (목록에 없으면) 지금 아이콘을 맨 앞에 — 카테고리가 준 아이콘을 저장으로 잃지 않게. */
function iconOptionsFor(current: string): readonly MarkerIconOption[] {
  if (MARKER_ICON_OPTIONS.some((option) => option.icon === current)) return MARKER_ICON_OPTIONS;
  return [{ icon: current, label: '지금 아이콘' }, ...MARKER_ICON_OPTIONS];
}

function colorKeyOf(value: string | null): MarkerColorKey {
  return value != null && value in MARKER_PALETTE ? (value as MarkerColorKey) : 'P-13';
}

function timeSummary(arrival: string, departure: string): string {
  const short = (value: string) => value.replace('T', ' ').slice(5, 16);
  if (!arrival && !departure) return '미정';
  return [arrival && `${short(arrival)} 도착`, departure && `${short(departure)} 출발`]
    .filter(Boolean)
    .join(' · ');
}

function costSummary(budget: string, actual: string, currency: string | null): string {
  if (!budget && !actual) return '없음';
  const unit = currency ? ` ${currency}` : '';
  return [budget && `예산 ${budget}${unit}`, actual && `실제 ${actual}${unit}`]
    .filter(Boolean)
    .join(' · ');
}

/**
 * 접히는 편집 항목 — 기본은 접힘이고 머리글에 현재 값을 요약한다(2026-11-16 소유자 요청 11).
 * 펼친 내용은 열렸을 때만 그린다(입력값은 상위 form 상태라 접어도 보존된다).
 */
function EditorSection({
  id,
  title,
  summary,
  children,
}: {
  id: string;
  title: string;
  summary: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-hairline pt-2" data-testid={id}>
      <div className="flex min-w-0 items-center gap-2">
        {/* 버튼 이름은 항목명만 — 요약 값(예: 색 이름)이 안의 선택 버튼 이름과 겹치지 않게 밖에 둔다. */}
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls={open ? `${id}-body` : undefined}
          className="inline-flex min-h-8 shrink-0 items-center gap-1.5 rounded-sm pr-1 text-left text-xs font-semibold text-ink hover:bg-surface-soft"
        >
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted" aria-hidden="true" />
          )}
          {title}
        </button>
        <span className="min-w-0 truncate text-xs text-muted" data-testid={`${id}-summary`}>
          {summary}
        </span>
      </div>
      {open && (
        <div id={`${id}-body`} className="mt-2">
          {children}
        </div>
      )}
    </div>
  );
}

export function PoiEditor({
  poi,
  currentDayIndex,
  dayOptions,
  saving = false,
  onSave,
  onCancel,
}: PoiEditorProps) {
  const [dayIndex, setDayIndex] = useState(currentDayIndex);
  const [form, setForm] = useState<PoiDetailForm>({
    color: colorKeyOf(poi.marker_color),
    icon: poi.marker_icon ?? 'marker',
    arrival: isoToDatetimeLocal(poi.planned_arrival_at),
    departure: isoToDatetimeLocal(poi.planned_departure_at),
    budget: poi.budget_amount ?? '',
    actual: poi.actual_amount ?? '',
    note: poi.user_note ?? '',
    url: poi.user_url ?? '',
  });

  const update = (patch: Partial<PoiDetailForm>) => setForm((prev) => ({ ...prev, ...patch }));
  const [iconOptions] = useState(() => iconOptionsFor(form.icon));
  const selectedHex = MARKER_PALETTE[form.color].hex;

  return (
    <div
      className="mt-2 space-y-3 rounded-sm border border-hairline bg-canvas p-3"
      data-testid="poi-editor"
    >
      {dayOptions && dayOptions.length > 1 && (
        <label className={POI_LABEL}>
          일자 이동
          <select
            value={dayIndex}
            onChange={(event) => setDayIndex(Number(event.target.value))}
            className="mt-1 min-h-11 w-full rounded-sm border border-hairline px-2"
          >
            {dayOptions.map((day) => (
              <option key={day.day_index} value={day.day_index}>
                {day.title ?? `${day.day_index}일차`}
              </option>
            ))}
          </select>
        </label>
      )}

      <EditorSection
        id="poi-edit-section-color"
        title="마커 색"
        summary={MARKER_PALETTE[form.color].name}
      >
        <div className="grid grid-cols-8 gap-1.5">
          {COLOR_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              aria-label={MARKER_PALETTE[key].name}
              aria-pressed={key === form.color}
              onClick={() => update({ color: key })}
              className={
                key === form.color
                  ? 'h-6 w-6 rounded-full ring-2 ring-ink ring-offset-1'
                  : 'h-6 w-6 rounded-full'
              }
              style={{ backgroundColor: MARKER_PALETTE[key].hex }}
            />
          ))}
        </div>
      </EditorSection>

      <EditorSection
        id="poi-edit-section-icon"
        title="아이콘"
        summary={iconOptions.find((option) => option.icon === form.icon)?.label ?? form.icon}
      >
        <fieldset data-testid="poi-edit-icon">
          <legend className="sr-only">마커 아이콘</legend>
          {/* 색 칩과 같은 방식의 아이콘 칩 — 고른 색 원 위에 흰 아이콘으로 지도 마커와 같게 보여 준다. */}
          <div className="grid grid-cols-[repeat(auto-fill,minmax(2.75rem,1fr))] gap-1">
            {iconOptions.map((option) => {
              const active = option.icon === form.icon;
              return (
                <button
                  key={option.icon}
                  type="button"
                  aria-pressed={active}
                  aria-label={option.label}
                  title={option.label}
                  data-marker-icon-option={option.icon}
                  onClick={() => update({ icon: option.icon })}
                  className={
                    active
                      ? 'flex size-11 items-center justify-center rounded-sm bg-surface-soft ring-2 ring-ink'
                      : 'flex size-11 items-center justify-center rounded-sm hover:bg-surface-soft'
                  }
                >
                  <span
                    className="flex size-7 items-center justify-center rounded-full"
                    style={{ backgroundColor: selectedHex }}
                  >
                    <MakiIcon icon={option.icon} size={15} testId="poi-edit-icon-glyph" />
                  </span>
                </button>
              );
            })}
          </div>
        </fieldset>
      </EditorSection>

      <EditorSection
        id="poi-edit-section-time"
        title="도착·출발"
        summary={timeSummary(form.arrival, form.departure)}
      >
        <div className="grid grid-cols-2 gap-2">
          <FormField
            id="poi-edit-arrival"
            label="도착"
            type="datetime-local"
            labelClassName={POI_LABEL}
            className={POI_INPUT}
            value={form.arrival}
            onChange={(event) => update({ arrival: event.target.value })}
          />
          <FormField
            id="poi-edit-departure"
            label="출발"
            type="datetime-local"
            labelClassName={POI_LABEL}
            className={POI_INPUT}
            value={form.departure}
            onChange={(event) => update({ departure: event.target.value })}
          />
        </div>
      </EditorSection>

      <FormTextArea
        id="poi-edit-note"
        label="메모"
        labelClassName={POI_LABEL}
        className="px-2 py-1 focus:border-primary"
        value={form.note}
        onChange={(event) => update({ note: event.target.value })}
        rows={2}
      />

      <FormField
        id="poi-edit-url"
        label="링크"
        type="url"
        labelClassName={POI_LABEL}
        className={POI_INPUT}
        value={form.url}
        onChange={(event) => update({ url: event.target.value })}
        maxLength={2000}
        placeholder="https://"
      />

      {/* 예산·실제 비용은 링크 아래(2026-11-16 소유자 요청 11). */}
      <EditorSection
        id="poi-edit-section-budget"
        title="예산·실제 비용"
        summary={costSummary(form.budget, form.actual, poi.currency)}
      >
        <div className="grid grid-cols-2 gap-2">
          <FormField
            id="poi-edit-budget"
            label="예산"
            type="number"
            min={0}
            labelClassName={POI_LABEL}
            className={POI_INPUT}
            value={form.budget}
            onChange={(event) => update({ budget: event.target.value })}
            placeholder="0"
          />
          <FormField
            id="poi-edit-actual"
            label="실제 비용"
            type="number"
            min={0}
            labelClassName={POI_LABEL}
            className={POI_INPUT}
            value={form.actual}
            onChange={(event) => update({ actual: event.target.value })}
            placeholder="0"
          />
        </div>
      </EditorSection>

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="min-h-11 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
        >
          취소
        </button>
        <button
          type="button"
          onClick={() =>
            onSave({
              ...buildPoiDetailPatch(form),
              ...(dayIndex != null && dayIndex !== currentDayIndex ? { day_index: dayIndex } : {}),
            })
          }
          disabled={saving}
          className="inline-flex min-h-11 items-center gap-1 rounded-sm bg-cta px-3 text-sm font-semibold text-on-primary hover:bg-cta-hover disabled:opacity-50"
        >
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
          저장
        </button>
      </div>
    </div>
  );
}
