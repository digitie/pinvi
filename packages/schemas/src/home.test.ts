import { describe, expect, it } from 'vitest';
import { UserHomeSchema } from './home';

const home = {
  today: '2026-11-16',
  stats: {
    trip_count: 2,
    upcoming_trip_count: 1,
    ongoing_trip_count: 0,
    completed_trip_count: 1,
    undated_trip_count: 0,
    travel_day_count: 2,
    visited_place_count: 1,
    region_count: 1,
  },
  next_trip: {
    trip_id: '11111111-1111-4111-8111-111111111111',
    title: '다음 제주',
    region_hint: '제주',
    region_name: '제주',
    start_date: '2026-11-21',
    end_date: '2026-11-22',
    phase: 'upcoming',
    days_until: 5,
    place_count: 0,
  },
  upcoming_trips: [],
  recent_trips: [],
  recent_places: [
    {
      poi_id: '22222222-2222-4222-8222-222222222222',
      trip_id: '33333333-3333-4333-8333-333333333333',
      trip_title: '지난 강릉',
      name: '경포해변',
      category: null,
      visited_on: '2026-11-06',
      region_name: '강원',
    },
  ],
  regions: [{ code: '51', name: '강원', place_count: 1, trip_count: 1 }],
};

describe('UserHomeSchema', () => {
  it('API 응답을 그대로 받는다', () => {
    expect(UserHomeSchema.parse(home).next_trip?.days_until).toBe(5);
  });

  it('알 수 없는 여행 단계는 거부한다', () => {
    const bad = { ...home, next_trip: { ...home.next_trip, phase: 'draft' } };
    expect(UserHomeSchema.safeParse(bad).success).toBe(false);
  });
});
