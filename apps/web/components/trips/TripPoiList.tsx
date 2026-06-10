'use client';

import { AlertTriangle, MapPin } from 'lucide-react';
import type { TripViewPoi } from '@tripmate/schemas';
import { paletteHex } from '@/lib/markerPalette';

function formatTime(value: string | null): string | null {
  if (!value) return null;
  return new Intl.DateTimeFormat('ko-KR', { hour: '2-digit', minute: '2-digit' }).format(
    new Date(value)
  );
}

export interface TripPoiListProps {
  pois: TripViewPoi[];
  selectedPoiId?: string | null;
  onSelectPoi?: (poiId: string) => void;
}

export function TripPoiList({ pois, selectedPoiId = null, onSelectPoi }: TripPoiListProps) {
  if (pois.length === 0) {
    return (
      <div className="flex min-h-32 items-center justify-center rounded-sm border border-hairline bg-white px-4 text-center text-sm text-muted">
        이 날에 등록된 장소가 없습니다.
      </div>
    );
  }

  return (
    <ol className="space-y-2" data-testid="trip-poi-list">
      {pois.map((poi, index) => {
        const arrival = formatTime(poi.planned_arrival_at);
        const selected = poi.poi_id === selectedPoiId;
        return (
          <li key={poi.poi_id}>
            <button
              type="button"
              onClick={() => onSelectPoi?.(poi.poi_id)}
              aria-current={selected}
              className={
                selected
                  ? 'flex w-full items-start gap-3 rounded-sm border border-primary bg-surface-soft p-3 text-left'
                  : 'flex w-full items-start gap-3 rounded-sm border border-hairline bg-white p-3 text-left hover:bg-surface-soft'
              }
            >
              <span
                className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white"
                style={{ backgroundColor: paletteHex(poi.marker_color) }}
                aria-hidden="true"
              >
                {index + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  <span className="truncate text-sm font-semibold text-ink">
                    {poi.title ?? poi.feature_id}
                  </span>
                  {poi.is_broken && (
                    <AlertTriangle
                      className="h-3.5 w-3.5 shrink-0 text-error-text"
                      aria-label="링크 끊김"
                    />
                  )}
                </span>
                <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                  {arrival && <span>{arrival} 도착</span>}
                  {poi.budget_amount && <span>예산 {poi.budget_amount} {poi.currency}</span>}
                </span>
                {poi.user_note && (
                  <span className="mt-1 line-clamp-2 block text-xs text-body">{poi.user_note}</span>
                )}
              </span>
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
            </button>
          </li>
        );
      })}
    </ol>
  );
}
