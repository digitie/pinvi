import { describe, expect, it } from 'vitest';
import type { PoiResponse, TripView } from '@pinvi/schemas';
import { withCreatedPois } from '../lib/tripViewCreatedPoi';

// #733: 장소 추가 뒤 목록은 POST 응답만으로 곧바로 행을 보여야 한다. weather 보강을 기다리는
// `GET /trips/{id}` 재조회(2~7 s, 겹치면 15 s 이상)가 끝날 때까지 비어 있으면 안 된다.

const tripId = '11111111-1111-4111-8111-111111111111';

function viewPoi(poiId: string, sortOrder: string) {
  return {
    poi_id: poiId,
    feature_id: 'feat-old',
    sort_order: sortOrder,
    title: '기존 장소',
    feature: { coord: { lon: 129.1, lat: 35.1 } },
    marker_color: null,
    marker_icon: null,
    display_marker_color: 'P-01',
    feature_resolution_state: 'found' as const,
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
    created_at: '2026-11-11T12:00:00Z',
    updated_at: '2026-11-11T12:00:00Z',
  };
}

function view(): TripView {
  return {
    trip: { trip_id: tripId } as TripView['trip'],
    companions: [],
    share_links: [],
    broken_feature_count: 0,
    days: [1, 2].map((dayIndex) => ({
      day_index: dayIndex,
      note: null,
      date: null,
      effective_date: null,
      out_of_range: false,
      marker_color: null,
      title: null,
      version: 1,
      holidays: [],
      rise_set: null,
      rise_set_reference: null,
      weather_cards: {},
      weather_by_feature_id: {},
      pois: dayIndex === 1 ? [viewPoi('aaaaaaaa-0000-4000-8000-000000000001', 'a0')] : [],
    })),
  };
}

function created(overrides: Partial<PoiResponse> = {}): PoiResponse {
  return {
    attachment_id: 'bbbbbbbb-0000-4000-8000-000000000002',
    trip_id: tripId,
    day_index: 1,
    sort_order: 'a1',
    feature_id: 'feat-gossi',
    feature_link_broken_at: null,
    feature_snapshot: {
      coord: { lon: 128.49, lat: 37.18 },
      name: '고씨굴',
      title: '고씨굴',
      marker_color: 'P-05',
      marker_icon: 'cave',
    },
    custom_marker_color: null,
    custom_marker_icon: null,
    source: 'feature',
    external_ref: null,
    planned_arrival_at: null,
    planned_departure_at: null,
    user_note: null,
    budget_amount: null,
    actual_amount: null,
    currency: 'KRW',
    user_url: null,
    rise_set: null,
    version: 1,
    created_at: '2026-11-11T12:06:31Z',
    updated_at: '2026-11-11T12:06:31Z',
    ...overrides,
  };
}

describe('withCreatedPois (#733)', () => {
  it('POST 응답 POI를 그 일자 목록에 sort_order 순서로 넣는다', () => {
    const next = withCreatedPois(view(), [created()]);
    const day1 = next.days.find((d) => d.day_index === 1)!;
    expect(day1.pois.map((p) => p.poi_id)).toEqual([
      'aaaaaaaa-0000-4000-8000-000000000001',
      'bbbbbbbb-0000-4000-8000-000000000002',
    ]);
    const added = day1.pois[1]!;
    expect(added.title).toBe('고씨굴');
    expect(added.feature).toMatchObject({ coord: { lon: 128.49, lat: 37.18 } });
    expect(added.marker_color).toBe('P-05');
    expect(added.marker_icon).toBe('cave');
    expect(added.feature_resolution_state).toBe('found');
    // 사용자 지정 색이 없으면 서버처럼 일자 기본색(1일차 = P-01)을 쓴다.
    expect(added.display_marker_color).toBe('P-01');
    expect(next.days.find((d) => d.day_index === 2)!.pois).toEqual([]);
  });

  it('앞 순서 rank면 기존 행 앞에 들어간다', () => {
    const next = withCreatedPois(view(), [created({ sort_order: 'Zz' })]);
    expect(next.days[0]!.pois.map((p) => p.sort_order)).toEqual(['Zz', 'a0']);
  });

  it('사용자 지정 마커가 snapshot 마커보다 우선하고, feature 미연결은 not_linked다', () => {
    const next = withCreatedPois(view(), [
      created({
        feature_id: null,
        source: 'manual',
        custom_marker_color: 'P-08',
        custom_marker_icon: 'marker',
        feature_snapshot: { coord: { lon: 127, lat: 37 }, title: '주소 장소' },
      }),
    ]);
    const added = next.days[0]!.pois[1]!;
    expect(added.title).toBe('주소 장소');
    expect(added.marker_color).toBe('P-08');
    expect(added.display_marker_color).toBe('P-08');
    expect(added.marker_icon).toBe('marker');
    expect(added.feature_resolution_state).toBe('not_linked');
  });

  it('재조회 결과에 이미 있으면 그대로 둔다(서버 계산값 우선)', () => {
    const base = view();
    const server = { ...viewPoi('bbbbbbbb-0000-4000-8000-000000000002', 'a1'), title: '서버 제목' };
    base.days[0]!.pois.push(server);
    const next = withCreatedPois(base, [created()]);
    expect(next).toBe(base);
    expect(next.days[0]!.pois).toHaveLength(2);
    expect(next.days[0]!.pois[1]!.title).toBe('서버 제목');
  });

  it('일자 override 색이 있으면 그 색을 표시색으로 쓴다', () => {
    const base = view();
    base.days[1]!.marker_color = 'P-12';
    const next = withCreatedPois(base, [created({ day_index: 2 })]);
    expect(next.days[1]!.pois[0]!.display_marker_color).toBe('P-12');
  });

  it('재조회 결과의 다른 일자에 이미 있으면(이동됨) 다시 넣지 않는다', () => {
    const base = view();
    base.days[1]!.pois.push(viewPoi('bbbbbbbb-0000-4000-8000-000000000002', 'a0'));
    expect(withCreatedPois(base, [created()])).toBe(base);
  });

  it('다른 여행의 POI는 넣지 않는다', () => {
    const base = view();
    const other = created({ trip_id: '99999999-9999-4999-8999-999999999999' });
    expect(withCreatedPois(base, [other])).toBe(base);
  });

  it('없는 일자나 빈 목록이면 view를 바꾸지 않는다', () => {
    const base = view();
    expect(withCreatedPois(base, [])).toBe(base);
    expect(withCreatedPois(base, [created({ day_index: 9 })])).toBe(base);
  });
});
