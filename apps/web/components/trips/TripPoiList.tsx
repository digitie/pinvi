'use client';

import { PoiEditor } from '@/components/trips/PoiEditor';
import { TripAttachmentsDisclosure } from '@/components/trips/TripAttachments';
import { PoiRiseSetLine } from '@/components/trips/TripDayHeader';
import { TripWeatherSummary } from '@/components/trips/TripWeatherSummary';
import { PoiWeatherBadge } from '@/components/weather/WeatherBadge';
import { arrayMove, featureResolutionNotice, formatKstTime, paletteHex } from '@pinvi/domain';
import type {
  PoiUpdate,
  TripViewPoi,
  TripWeatherCard,
  TripWeatherRefreshResponse,
  TripWeatherResolution,
} from '@pinvi/schemas';
import { AlertTriangle, CloudOff, EyeOff, GripVertical, Pencil, Trash2 } from 'lucide-react';
import { type ReactNode, useState } from 'react';

function formatTime(value: string | null): string | null {
  return value ? formatKstTime(value) : null;
}

export interface TripPoiListProps {
  pois: TripViewPoi[];
  dayIndex?: number;
  dayOptions?: { day_index: number; title: string | null }[];
  selectedPoiId?: string | null;
  onSelectPoi?: (poiId: string) => void;
  tripId?: string;
  dayDate?: string | null;
  weatherCards?: Record<string, TripWeatherCard>;
  weatherByFeatureId?: Record<string, TripWeatherResolution>;
  showInlineAttachments?: boolean;
  showWeather?: boolean;
  /**
   * 장소 이름 옆 현재 날씨 배지(아이콘·기온·오늘 최고/최저, 누르면 예보 팝업). 로그인 사용자의
   * 여행 화면에서만 켠다 — 장소 날씨 API는 여행 멤버 전용이다. `tripId`가 필요하다.
   */
  showCurrentWeather?: boolean;
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
  /** 장소 날씨가 비었을 때 새로고침(요청 15). 없으면 버튼을 그리지 않는다. */
  onRefreshWeather?: (poiId: string) => Promise<TripWeatherRefreshResponse>;
}

type AttachmentParts = { trigger: ReactNode; panel: ReactNode };

/** 장소 파일 — 버튼은 편집 버튼 옆, 펼친 목록은 행 바로 아래(2026-11-16 소유자 요청 12). */
function PoiAttachments({
  tripId,
  poiId,
  children,
}: {
  tripId: string | undefined;
  poiId: string;
  children: (parts: AttachmentParts) => ReactNode;
}) {
  if (!tripId) return <>{children({ trigger: null, panel: null })}</>;
  return (
    <TripAttachmentsDisclosure tripId={tripId} poiId={poiId} title="장소 파일">
      {children}
    </TripAttachmentsDisclosure>
  );
}

const EMPTY_WEATHER_CARDS = {};
const EMPTY_WEATHER_BY_FEATURE = {};

export function TripPoiList({
  pois,
  dayIndex,
  dayOptions,
  selectedPoiId = null,
  onSelectPoi,
  tripId,
  dayDate = null,
  weatherCards = EMPTY_WEATHER_CARDS,
  weatherByFeatureId = EMPTY_WEATHER_BY_FEATURE,
  showInlineAttachments = false,
  showWeather = false,
  showCurrentWeather = false,
  compact = false,
  editable = false,
  onReorder,
  onEditPoi,
  onDelete,
  savingPoiId = null,
  editingPoiId: editingPoiIdProp,
  onEditToggle,
  onRefreshWeather,
}: TripPoiListProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [editingInternal, setEditingInternal] = useState<string | null>(null);
  const controlled = editingPoiIdProp !== undefined;
  const editingPoiId = controlled ? editingPoiIdProp : editingInternal;
  const setEditingPoiId = (next: string | null) => {
    if (controlled) onEditToggle?.(next);
    else setEditingInternal(next);
  };

  if (pois.length === 0) return null;

  const dndEnabled = editable && onReorder != null;

  const handleDrop = (toIndex: number) => {
    if (dragIndex == null || dragIndex === toIndex) {
      setDragIndex(null);
      return;
    }
    const order = arrayMove(
      pois.map((p) => p.poi_id),
      dragIndex,
      toIndex,
    );
    onReorder?.(order);
    setDragIndex(null);
  };

  return (
    <ol className={compact ? 'space-y-1.5' : 'space-y-2'} data-testid="trip-poi-list">
      {pois.map((poi, index) => {
        const arrival = formatTime(poi.planned_arrival_at);
        const departure = formatTime(poi.planned_departure_at);
        const selected = poi.poi_id === selectedPoiId;
        const editing = poi.poi_id === editingPoiId;
        const resolutionNotice = featureResolutionNotice(poi.feature_resolution_state);
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
            <PoiAttachments tripId={showInlineAttachments ? tripId : undefined} poiId={poi.poi_id}>
              {({ trigger: attachmentTrigger, panel: attachmentPanel }) => (
                <div
                  // 카드 안 카드 금지 — row는 표면 없이 padding + 선택 시 ink rule만 쓴다(T-316).
                  className={
                    (compact ? 'p-2 ' : 'p-3 ') +
                    (selected
                      ? 'border-l-2 border-ink bg-surface-soft'
                      : 'border-l-2 border-transparent')
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
                        // 마커 팔레트 인라인 색 위 순번이라 순백이 맞다(T-313 예외).
                        // eslint-disable-next-line no-restricted-syntax
                        className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white"
                        // ADR-055: 지도 핀과 동일한 서버 계산 display_marker_color로 뱃지 색을 맞춘다(parity).
                        style={{
                          backgroundColor: paletteHex(poi.display_marker_color ?? poi.marker_color),
                        }}
                        aria-hidden="true"
                      >
                        {index + 1}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5">
                          <span className="truncate text-sm font-semibold text-ink">
                            {poi.title ?? poi.feature_id ?? '장소'}
                          </span>
                          {(poi.feature_resolution_state === 'missing' ||
                            poi.feature_resolution_state === 'retired') && (
                            <AlertTriangle
                              className="h-3.5 w-3.5 shrink-0 text-error-text"
                              aria-label={resolutionNotice ?? undefined}
                            />
                          )}
                          {poi.feature_resolution_state === 'suppressed' && (
                            <EyeOff
                              className="h-3.5 w-3.5 shrink-0 text-muted"
                              aria-label={resolutionNotice ?? undefined}
                            />
                          )}
                          {poi.feature_resolution_state === 'unverified' && (
                            <CloudOff
                              className="h-3.5 w-3.5 shrink-0 text-muted"
                              aria-label={resolutionNotice ?? undefined}
                            />
                          )}
                        </span>
                        {(arrival || departure) && (
                          <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                            {arrival && <span>{arrival} 도착</span>}
                            {departure && <span>{departure} 출발</span>}
                          </span>
                        )}
                        {poi.user_note && (
                          <span className="mt-1 line-clamp-2 block text-xs text-body">
                            {poi.user_note}
                          </span>
                        )}
                        {/* 예산·실제 비용은 링크·메모 아래 마지막 줄(2026-11-16 소유자 요청 11). */}
                        {(poi.budget_amount || poi.actual_amount) && (
                          <span
                            className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted"
                            data-testid="trip-poi-cost"
                          >
                            {poi.budget_amount && (
                              <span>
                                예산 {poi.budget_amount} {poi.currency}
                              </span>
                            )}
                            {poi.actual_amount && (
                              <span>
                                실제 {poi.actual_amount} {poi.currency}
                              </span>
                            )}
                          </span>
                        )}
                      </span>
                    </button>
                    {showCurrentWeather && tripId && (
                      <PoiWeatherBadge
                        tripId={tripId}
                        poiId={poi.poi_id}
                        placeName={poi.title ?? '장소'}
                        className="mt-0.5"
                      />
                    )}
                    {(editable || attachmentTrigger) && (
                      <div className="flex shrink-0 items-center gap-1">
                        {attachmentTrigger}
                        {editable && (
                          <button
                            type="button"
                            onClick={() => setEditingPoiId(editing ? null : poi.poi_id)}
                            aria-label="마커 편집"
                            aria-expanded={editing}
                            className="rounded-sm p-1 text-muted hover:bg-surface-soft hover:text-ink"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                        )}
                        {editable && onDelete && (
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
                      dayOptions={dayOptions}
                      currentDayIndex={dayIndex}
                      saving={savingPoiId === poi.poi_id}
                      onSave={(patch) => {
                        const result = onEditPoi(poi, patch);
                        if (
                          result &&
                          typeof (result as Promise<void | boolean>).then === 'function'
                        ) {
                          void Promise.resolve(result).then((saved) => {
                            // 제어 모드에서는 부모가 저장·재조회 뒤 **그 장소의** 편집기만 닫는다(#699) — 그 사이
                            // 다른 장소 편집기를 열었으면 여기서 닫으면 엉뚱한 편집기가 닫힌다.
                            if (saved !== false && !controlled) setEditingPoiId(null);
                          });
                          return;
                        }
                        if (result !== false) setEditingPoiId(null);
                      }}
                      onCancel={() => setEditingPoiId(null)}
                    />
                  )}
                  {(showWeather || attachmentPanel) && (
                    <div className={compact ? 'mt-2 space-y-2 pl-8' : 'mt-3 space-y-2 pl-9'}>
                      {attachmentPanel}
                      {showWeather && (
                        <TripWeatherSummary
                          weather={
                            poi.feature_id ? (weatherByFeatureId[poi.feature_id] ?? null) : null
                          }
                          weatherCards={weatherCards}
                          date={dayDate}
                          label="장소 날씨"
                          compact
                          onRefresh={
                            onRefreshWeather ? () => onRefreshWeather(poi.poi_id) : undefined
                          }
                        />
                      )}
                      {showWeather && <PoiRiseSetLine riseSet={poi.rise_set} />}
                    </div>
                  )}
                </div>
              )}
            </PoiAttachments>
          </li>
        );
      })}
    </ol>
  );
}
