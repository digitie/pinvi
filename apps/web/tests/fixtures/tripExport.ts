import { TripResponseSchema, TripViewDaySchema, TripViewPoiSchema } from '@pinvi/schemas';
import type { TripExportSource } from '../../lib/tripExport';

const stamp = '2026-11-05T00:00:00+09:00';
export function exportSource(): TripExportSource {
  const poi = TripViewPoiSchema.parse({
    poi_id: '64100000-0000-4000-8000-000000000001',
    feature_id: null,
    sort_order: 'a',
    title: '부산 장소',
    feature: { coord: { lon: 129.1, lat: 35.2 }, address_label: '부산 주소' },
    marker_color: 'P-08',
    marker_icon: 'marker',
    feature_resolution_state: 'not_linked',
    user_note: '장소 메모',
    planned_arrival_at: '2026-11-05T00:30:00Z',
    planned_departure_at: '2026-11-05T02:00:00Z',
    budget_amount: null,
    actual_amount: null,
    currency: 'KRW',
    user_url: null,
    rise_set: null,
    feature_link_broken_at: null,
    version: 1,
    created_at: stamp,
    updated_at: stamp,
  });
  return {
    trip: TripResponseSchema.parse({
      trip_id: '64100000-0000-4000-8000-000000000641',
      owner_user_id: '64100000-0000-4000-8000-000000000000',
      title: '부산 여행',
      description: '여행 설명',
      region_hint: '부산',
      primary_region_code: '26',
      primary_region_source: 'manual',
      start_date: '2026-11-05',
      end_date: '2026-11-06',
      visibility: 'private',
      status: 'draft',
      version: 1,
      created_at: stamp,
      updated_at: stamp,
    }),
    days: [
      TripViewDaySchema.parse({
        day_index: 1,
        date: null,
        effective_date: '2026-11-05',
        title: '첫날',
        note: '일자 메모',
        pois: [poi],
        weather_cards: {},
        weather_by_feature_id: {},
      }),
    ],
  };
}
