import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TripPoiList } from '@/components/trips/TripPoiList';
import { TripViewPoiSchema } from '@pinvi/schemas';

function poi(feature: Record<string, unknown>) {
  return TripViewPoiSchema.parse({
    poi_id: '00000000-0000-4000-8000-000000000002',
    feature_id: '01a2-course',
    sort_order: 'a0',
    title: '노고단고개 ~ 천왕봉',
    feature,
    marker_color: null,
    marker_icon: null,
    feature_resolution_state: 'found',
    user_note: null,
    planned_arrival_at: null,
    planned_departure_at: null,
    budget_amount: null,
    actual_amount: null,
    currency: 'KRW',
    user_url: null,
    rise_set: null,
    feature_link_broken_at: null,
    version: 1,
    created_at: '2026-11-27T00:00:00Z',
    updated_at: '2026-11-27T00:00:00Z',
  });
}

describe('일정 항목의 등산 코스 요약 줄 (Map ADR-128)', () => {
  it('코스(kind=route)면 거리·소요시간 줄을 보인다', () => {
    render(
      <TripPoiList
        pois={[
          poi({
            kind: 'route',
            route: {
              route_type: 'hiking_course',
              length_m: 4210.5,
              duration_minutes: 150,
              duration_basis: 'estimated',
              difficulty: 'moderate',
              shape: 'path',
            },
          }),
        ]}
      />,
    );
    expect(screen.getByTestId('trip-poi-route-summary')).toHaveTextContent(
      '등산 코스 · 4.2 km · 약 2시간 30분(추정) · 보통',
    );
  });

  it('장소(kind=place)에는 요약 줄이 없다', () => {
    render(
      <TripPoiList
        pois={[poi({ kind: 'place', route: { route_type: 'hiking_course', length_m: 10 } })]}
      />,
    );
    expect(screen.queryByTestId('trip-poi-route-summary')).not.toBeInTheDocument();
  });
});
