import { describe, expect, it } from 'vitest';
import { buildTripUpdate, type TripEditForm } from './tripEdit';

const base: TripEditForm = {
  title: '  부산 여행  ',
  regionHint: '부산',
  startDate: '2026-07-01',
  endDate: '2026-07-03',
  visibility: 'private',
  status: 'planned',
};

describe('tripEdit', () => {
  it('buildTripUpdate: trim + 빈 값 null', () => {
    expect(buildTripUpdate(base)).toEqual({
      title: '부산 여행',
      region_hint: '부산',
      start_date: '2026-07-01',
      end_date: '2026-07-03',
      visibility: 'private',
      status: 'planned',
    });
  });

  it('buildTripUpdate: 빈 지역/날짜 → null', () => {
    const patch = buildTripUpdate({ ...base, regionHint: '', startDate: '', endDate: '' });
    expect(patch.region_hint).toBeNull();
    expect(patch.start_date).toBeNull();
    expect(patch.end_date).toBeNull();
  });
});
