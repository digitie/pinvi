/**
 * POI 상세 편집 폼 ↔ `PoiUpdate` 변환 — `docs/api/pois.md`.
 */

import type { PoiUpdate } from '@pinvi/schemas';
import type { MarkerColorKey } from '@pinvi/design-tokens';

export interface PoiDetailForm {
  color: MarkerColorKey;
  icon: string;
  /** datetime-local 값(`YYYY-MM-DDTHH:mm`) 또는 ''. */
  arrival: string;
  departure: string;
  /** 숫자 문자열 또는 ''. */
  budget: string;
  actual: string;
  note: string;
  url: string;
}

/** 금액 입력 → 음수/비숫자/빈값은 null. */
export function parseAmount(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value < 0) return null;
  return value;
}

/** datetime-local 입력 → ISO(UTC) 또는 null. */
export function datetimeLocalToIso(local: string): string | null {
  if (!local) return null;
  const date = new Date(local);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** ISO → datetime-local 값(로컬 시간 기준). */
export function isoToDatetimeLocal(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`;
}

export function buildPoiDetailPatch(form: PoiDetailForm): PoiUpdate {
  return {
    custom_marker_color: form.color,
    custom_marker_icon: form.icon.trim() || 'marker',
    planned_arrival_at: datetimeLocalToIso(form.arrival),
    planned_departure_at: datetimeLocalToIso(form.departure),
    budget_amount: parseAmount(form.budget),
    actual_amount: parseAmount(form.actual),
    user_note: form.note.trim() || null,
    user_url: form.url.trim() || null,
  };
}
