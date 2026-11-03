import { describe, expect, it, vi } from 'vitest';
import { TripViewPoiSchema } from '@pinvi/schemas';
vi.mock('@/components/trips/TripMapView', () => ({ TripMapView: () => null }));
import { buildPoiConflictFields } from '@/components/trips/TripDetail';
import { pickConflictPatch } from '@/lib/conflictResolution';

describe('일자 이동 충돌 필드', () => {
  it('이동을 독립된 선택 항목으로 보여 메모만 다시 저장할 수 있다', () => {
    const poi = TripViewPoiSchema.parse({
      poi_id: '00000000-0000-4000-8000-000000000001', feature_id: null, sort_order: 'a0',
      title: '장소', feature: {}, marker_color: null, marker_icon: null,
      feature_resolution_state: 'not_linked', user_note: '서버 메모',
      planned_arrival_at: null, planned_departure_at: null, budget_amount: null,
      actual_amount: null, currency: 'KRW', user_url: null, rise_set: null,
      feature_link_broken_at: null, version: 2, created_at: '2026-11-03T09:00:00+09:00',
      updated_at: '2026-11-03T09:00:00+09:00',
    });
    const patch = { day_index: 2, user_note: '내 메모' };
    const fields = buildPoiConflictFields(patch, poi, 3);
    expect(fields.find((field) => field.key === 'day_index')).toMatchObject({
      label: '일자 이동', serverValue: '3', myValue: '2',
    });
    expect(pickConflictPatch(patch, ['user_note'])).toEqual({ user_note: '내 메모' });
  });
});
