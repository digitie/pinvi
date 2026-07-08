'use client';

import { useState } from 'react';
import { AlertTriangle, GripVertical, Pencil, Trash2 } from 'lucide-react';
import type { PoiUpdate, TripViewPoi } from '@pinvi/schemas';
import { arrayMove, paletteHex } from '@pinvi/domain';
import { PoiEditor } from '@/components/trips/PoiEditor';
import { TripAttachments } from '@/components/trips/TripAttachments';
import { TripWeatherSummary } from '@/components/trips/TripWeatherSummary';

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
  tripId?: string;
  dayDate?: string | null;
  showInlineAttachments?: boolean;
  showWeather?: boolean;
  compact?: boolean;
  /** 편집 가능(쓰기 권한)일 때만 D&D·편집·삭제 노출. */
  editable?: boolean;
  onReorder?: (orderedPoiIds: string[]) => void;
  onEditPoi?: (poi: TripViewPoi, patch: PoiUpdate) => void | boolean | Promise<void | boolean>;
  onDelete?: (poiId: string) => void;
  savingPoiId?: string | null;
  /** 편집 중 POI(외부 제어 — 지도 마커 우클릭 등). 미지정 시 내부 상태. */
  editingPoiId?: string | null;
  onEditToggle?: (poiId: string | null) => void;
}

export function TripPoiList({
  pois,
  selectedPoiId = null,
  onSelectPoi,
  tripId,
  dayDate = null,
  showInlineAttachments = false,
  showWeather = false,
  compact = false,
  editable = false,
  onReorder,
  onEditPoi,
  onDelete,
  savingPoiId = null,
  editingPoiId: editingPoiIdProp,
  onEditToggle,
}: TripPoiListProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [editingInternal, setEditingInternal] = useState<string | null>(null);
  const controlled = editingPoiIdProp !== undefined;
  const editingPoiId = controlled ? editingPoiIdProp : editingInternal;
  const setEditingPoiId = (next: string | null) => {
    if (controlled) onEditToggle?.(next);
    else setEditingInternal(next);
  };

  if (pois.length === 0) {
    return (
      <div
        className={
          compact
            ? 'flex min-h-20 items-center justify-center rounded-sm bg-surface-soft px-3 text-center text-xs text-muted'
            : 'flex min-h-32 items-center justify-center rounded-sm border border-hairline bg-white px-4 text-center text-sm text-muted'
        }
      >
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
    <ol className={compact ? 'space-y-1.5' : 'space-y-2'} data-testid="trip-poi-list">
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
                compact
                  ? selected
                    ? 'rounded-sm bg-primary/5 p-2 ring-1 ring-primary/35'
                    : 'rounded-sm bg-white p-2'
                  : selected
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
                        {poi.title ?? poi.feature_id ?? '장소'}
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
              {editing && onEditPoi && (
                <PoiEditor
                  poi={poi}
                  saving={savingPoiId === poi.poi_id}
                  onSave={(patch) => {
                    const result = onEditPoi(poi, patch);
                    if (result && typeof (result as Promise<void | boolean>).then === 'function') {
                      void Promise.resolve(result).then((saved) => {
                        if (saved !== false) setEditingPoiId(null);
                      });
                      return;
                    }
                    if (result !== false) setEditingPoiId(null);
                  }}
                  onCancel={() => setEditingPoiId(null)}
                />
              )}
              {(showWeather || (showInlineAttachments && tripId)) && (
                <div className={compact ? 'mt-2 space-y-2 pl-8' : 'mt-3 space-y-2 pl-9'}>
                  {showWeather && (
                    <TripWeatherSummary
                      featureId={poi.feature_id}
                      date={dayDate}
                      label="장소 날씨"
                      compact
                    />
                  )}
                  {showInlineAttachments && tripId && (
                    <TripAttachments
                      tripId={tripId}
                      poiId={poi.poi_id}
                      title="장소 파일"
                      compact
                    />
                  )}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
