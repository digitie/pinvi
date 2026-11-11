import type { TripUpdate, PoiUpdate, TripView, TripViewPoi } from '@pinvi/schemas';
import type { ConflictField } from '@/components/trips/ConflictDialog';
export type TripConflictFieldKey = Extract<keyof TripUpdate, string>;

export type PoiConflictFieldKey = Extract<keyof PoiUpdate, string>;

function displayConflictValue(value: unknown): string {
  if (value == null || value === '') return '비움';
  if (typeof value === 'boolean') return value ? '예' : '아니오';
  return String(value);
}

export function hasOwnField<T extends object, K extends Extract<keyof T, string>>(
  target: T,
  key: K,
): boolean {
  return Object.prototype.hasOwnProperty.call(target, key);
}

const TRIP_CONFLICT_FIELDS: Array<{
  key: TripConflictFieldKey;
  label: string;
  serverValue: (trip: TripView['trip']) => unknown;
}> = [
  { key: 'title', label: '제목', serverValue: (trip) => trip.title },
  { key: 'region_hint', label: '지역', serverValue: (trip) => trip.region_hint },
  { key: 'start_date', label: '시작일', serverValue: (trip) => trip.start_date },
  { key: 'end_date', label: '종료일', serverValue: (trip) => trip.end_date },
  { key: 'visibility', label: '공개 범위', serverValue: (trip) => trip.visibility },
  { key: 'status', label: '상태', serverValue: (trip) => trip.status },
];

const POI_CONFLICT_FIELDS: Array<{
  key: PoiConflictFieldKey;
  label: string;
  serverValue: (poi: TripViewPoi) => unknown;
}> = [
  { key: 'custom_marker_color', label: '마커 색', serverValue: (poi) => poi.marker_color },
  { key: 'custom_marker_icon', label: '마커 아이콘', serverValue: (poi) => poi.marker_icon },
  { key: 'planned_arrival_at', label: '도착', serverValue: (poi) => poi.planned_arrival_at },
  { key: 'planned_departure_at', label: '출발', serverValue: (poi) => poi.planned_departure_at },
  { key: 'budget_amount', label: '예산', serverValue: (poi) => poi.budget_amount },
  { key: 'actual_amount', label: '실제 비용', serverValue: (poi) => poi.actual_amount },
  { key: 'currency', label: '통화', serverValue: (poi) => poi.currency },
  { key: 'user_note', label: '메모', serverValue: (poi) => poi.user_note },
  { key: 'user_url', label: '링크', serverValue: (poi) => poi.user_url },
];

export function buildTripConflictFields(
  patch: TripUpdate,
  trip: TripView['trip'],
): ConflictField[] {
  return TRIP_CONFLICT_FIELDS.filter((field) => hasOwnField(patch, field.key)).map((field) => ({
    key: field.key,
    label: field.label,
    serverValue: displayConflictValue(field.serverValue(trip)),
    myValue: displayConflictValue(patch[field.key]),
  }));
}

export function buildPoiConflictFields(
  patch: PoiUpdate,
  poi: TripViewPoi,
  dayIndex: number | null,
): ConflictField[] {
  const fields: ConflictField[] = [];
  if (hasOwnField(patch, 'day_index'))
    fields.push({
      key: 'day_index',
      label: '일자 이동',
      serverValue: displayConflictValue(dayIndex),
      myValue: displayConflictValue(patch.day_index),
    });
  return [
    ...fields,
    ...POI_CONFLICT_FIELDS.filter((field) => hasOwnField(patch, field.key)).map((field) => ({
      key: field.key,
      label: field.label,
      serverValue: displayConflictValue(field.serverValue(poi)),
      myValue: displayConflictValue(patch[field.key]),
    })),
  ];
}
