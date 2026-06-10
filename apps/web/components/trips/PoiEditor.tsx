'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { MARKER_PALETTE, type MarkerColorKey } from '@/lib/markerPalette';

const COLOR_KEYS = Object.keys(MARKER_PALETTE) as MarkerColorKey[];

export interface PoiEditorProps {
  initialColor: string | null;
  initialIcon: string | null;
  saving?: boolean;
  onSave: (color: MarkerColorKey, icon: string) => void;
  onCancel: () => void;
}

function isColorKey(value: string | null): value is MarkerColorKey {
  return value != null && value in MARKER_PALETTE;
}

export function PoiEditor({ initialColor, initialIcon, saving = false, onSave, onCancel }: PoiEditorProps) {
  const [color, setColor] = useState<MarkerColorKey>(isColorKey(initialColor) ? initialColor : 'P-13');
  const [icon, setIcon] = useState(initialIcon ?? 'marker');

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
              aria-pressed={key === color}
              onClick={() => setColor(key)}
              className={
                key === color
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
          value={icon}
          onChange={(event) => setIcon(event.target.value)}
          maxLength={64}
          placeholder="marker"
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
          onClick={() => onSave(color, icon.trim() || 'marker')}
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
