'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import type { PoiUpdate, TripViewPoi } from '@tripmate/schemas';
import { MARKER_PALETTE, type MarkerColorKey } from '@/lib/markerPalette';
import {
  buildPoiDetailPatch,
  isoToDatetimeLocal,
  type PoiDetailForm,
} from '@/lib/poiDetail';

const COLOR_KEYS = Object.keys(MARKER_PALETTE) as MarkerColorKey[];

export interface PoiEditorProps {
  poi: TripViewPoi;
  saving?: boolean;
  onSave: (patch: PoiUpdate) => void;
  onCancel: () => void;
}

function colorKeyOf(value: string | null): MarkerColorKey {
  return value != null && value in MARKER_PALETTE ? (value as MarkerColorKey) : 'P-13';
}

export function PoiEditor({ poi, saving = false, onSave, onCancel }: PoiEditorProps) {
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

  return (
    <div className="mt-2 space-y-3 rounded-sm border border-hairline bg-white p-3" data-testid="poi-editor">
      <div>
        <p className="mb-1.5 text-xs font-semibold text-ink">마커 색</p>
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
      </div>

      <label className="block text-xs font-semibold text-ink">
        maki 아이콘
        <input
          value={form.icon}
          onChange={(event) => update({ icon: event.target.value })}
          maxLength={64}
          placeholder="marker"
          className="mt-1 h-9 w-full rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
        />
      </label>

      <div className="grid grid-cols-2 gap-2">
        <label className="block text-xs font-semibold text-ink">
          도착
          <input
            type="datetime-local"
            value={form.arrival}
            onChange={(event) => update({ arrival: event.target.value })}
            className="mt-1 h-9 w-full rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
          />
        </label>
        <label className="block text-xs font-semibold text-ink">
          출발
          <input
            type="datetime-local"
            value={form.departure}
            onChange={(event) => update({ departure: event.target.value })}
            className="mt-1 h-9 w-full rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
          />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="block text-xs font-semibold text-ink">
          예산
          <input
            type="number"
            min={0}
            value={form.budget}
            onChange={(event) => update({ budget: event.target.value })}
            placeholder="0"
            className="mt-1 h-9 w-full rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
          />
        </label>
        <label className="block text-xs font-semibold text-ink">
          실제 비용
          <input
            type="number"
            min={0}
            value={form.actual}
            onChange={(event) => update({ actual: event.target.value })}
            placeholder="0"
            className="mt-1 h-9 w-full rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
          />
        </label>
      </div>

      <label className="block text-xs font-semibold text-ink">
        메모
        <textarea
          value={form.note}
          onChange={(event) => update({ note: event.target.value })}
          rows={2}
          className="mt-1 w-full rounded-sm border border-hairline px-2 py-1 text-sm font-normal text-ink outline-none focus:border-primary"
        />
      </label>

      <label className="block text-xs font-semibold text-ink">
        링크
        <input
          type="url"
          value={form.url}
          onChange={(event) => update({ url: event.target.value })}
          maxLength={2000}
          placeholder="https://"
          className="mt-1 h-9 w-full rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
        />
      </label>

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="h-8 rounded-sm border border-hairline px-3 text-xs font-semibold text-ink hover:bg-surface-soft"
        >
          취소
        </button>
        <button
          type="button"
          onClick={() => onSave(buildPoiDetailPatch(form))}
          disabled={saving}
          className="inline-flex h-8 items-center gap-1 rounded-sm bg-primary px-3 text-xs font-semibold text-white disabled:opacity-50"
        >
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
          저장
        </button>
      </div>
    </div>
  );
}
