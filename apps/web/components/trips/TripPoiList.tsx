'use client';

import { useState } from 'react';
import { AlertTriangle, GripVertical, Pencil, Trash2 } from 'lucide-react';
import type { TripViewPoi } from '@tripmate/schemas';
import { paletteHex, type MarkerColorKey } from '@/lib/markerPalette';
import { arrayMove } from '@/lib/poiRank';
import { PoiEditor } from '@/components/trips/PoiEditor';

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
  /** 편집 가능(쓰기 권한)일 때만 D&D·편집·삭제 노출. */
  editable?: boolean;
  onReorder?: (orderedPoiIds: string[]) => void;
  onEditMarker?: (poi: TripViewPoi, color: MarkerColorKey, icon: string) => void;
  onDelete?: (poiId: string) => void;
  savingPoiId?: string | null;
}

export function TripPoiList({
  pois,
  selectedPoiId = null,
  onSelectPoi,
  editable = false,
  onReorder,
  onEditMarker,
  onDelete,
  savingPoiId = null,
}: TripPoiListProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [editingPoiId, setEditingPoiId] = useState<string | null>(null);

  if (pois.length === 0) {
    return (
      <div className="flex min-h-32 items-center justify-center rounded-sm border border-hairline bg-white px-4 text-center text-sm text-muted">
        이 날에 등록된 장소가 없습니다.
      </div>
    );
  }

  const dndEnabled = editable && onReorder != null;

  const handleDrop = (toIndex: number) => {
    if (dragIndex == null || dragIndex === toIndex) {
      setDragIndex(null);
      return;
    }
    const order = arrayMove(
      pois.map((p) => p.poi_id),
      dragIndex,
      toIndex
    );
    onReorder?.(order);
    setDragIndex(null);
  };

  return (
    <ol className="space-y-2" data-testid="trip-poi-list">
      {pois.map((poi, index) => {
        const arrival = formatTime(poi.planned_arrival_at);
        const selected = poi.poi_id === selectedPoiId;
        const editing = poi.poi_id === editingPoiId;
        return (
          <li
            key={poi.poi_id}
            draggable={dndEnabled}
            onDragStart={dndEnabled ? () => setDragIndex(index) : undefined}
            onDragOver={dndEnabled ? (event) => event.preventDefault() : undefined}
            onDrop={dndEnabled ? () => handleDrop(index) : undefined}
            onDragEnd={dndEnabled ? () => setDragIndex(null) : undefined}
            className={dragIndex === index ? 'opacity-50' : undefined}
          >
            <div
              className={
                selected
                  ? 'rounded-sm border border-primary bg-surface-soft p-3'
                  : 'rounded-sm border border-hairline bg-white p-3'
              }
            >
              <div className="flex items-start gap-2">
                {dndEnabled && (
                  <span
                    className="mt-0.5 shrink-0 cursor-grab text-muted"
                    aria-hidden="true"
                    title="끌어서 순서 변경"
                  >
                    <GripVertical className="h-4 w-4" />
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => onSelectPoi?.(poi.poi_id)}
                  aria-current={selected}
                  className="flex min-w-0 flex-1 items-start gap-3 text-left"
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
                      {poi.budget_amount && (
                        <span>
                          예산 {poi.budget_amount} {poi.currency}
                        </span>
                      )}
                    </span>
                    {poi.user_note && (
                      <span className="mt-1 line-clamp-2 block text-xs text-body">
                        {poi.user_note}
                      </span>
                    )}
                  </span>
                </button>
                {editable && (
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setEditingPoiId(editing ? null : poi.poi_id)}
                      aria-label="마커 편집"
                      aria-expanded={editing}
                      className="rounded-sm p-1 text-muted hover:bg-surface-soft hover:text-ink"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    {onDelete && (
                      <button
                        type="button"
                        onClick={() => onDelete(poi.poi_id)}
                        aria-label="장소 삭제"
                        className="rounded-sm p-1 text-muted hover:bg-error-bg hover:text-error-text"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                )}
              </div>
              {editing && onEditMarker && (
                <PoiEditor
                  initialColor={poi.marker_color}
                  initialIcon={poi.marker_icon}
                  saving={savingPoiId === poi.poi_id}
                  onSave={(color, icon) => {
                    onEditMarker(poi, color, icon);
                    setEditingPoiId(null);
                  }}
                  onCancel={() => setEditingPoiId(null)}
                />
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
