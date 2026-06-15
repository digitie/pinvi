import { describe, expect, it } from 'vitest';
import { buildCopyRequest, canCopy, type CopyForm } from './noticePlanCopy';

const base: CopyForm = {
  mode: 'new',
  title: '부산 2박3일',
  startDate: '2026-07-01',
  endDate: '2026-07-03',
  targetTripId: null,
};

describe('noticePlanCopy', () => {
  it('buildCopyRequest: 새 여행 → trip_title + 날짜, poi_ids=[]', () => {
    expect(buildCopyRequest(base)).toEqual({
      trip_title: '부산 2박3일',
      trip_start_date: '2026-07-01',
      trip_end_date: '2026-07-03',
      poi_ids: [],
    });
  });

  it('buildCopyRequest: 새 여행 빈 날짜 → null', () => {
    expect(buildCopyRequest({ ...base, startDate: '', endDate: '' })).toEqual({
      trip_title: '부산 2박3일',
      trip_start_date: null,
      trip_end_date: null,
      poi_ids: [],
    });
  });

  it('buildCopyRequest: 기존 여행 → target_trip_id 만', () => {
    expect(
      buildCopyRequest({ ...base, mode: 'existing', targetTripId: 'trip-1' })
    ).toEqual({ target_trip_id: 'trip-1', poi_ids: [] });
  });

  it('canCopy: 새=제목 필요, 기존=trip 선택 필요', () => {
    expect(canCopy(base)).toBe(true);
    expect(canCopy({ ...base, title: '  ' })).toBe(false);
    expect(canCopy({ ...base, mode: 'existing', targetTripId: null })).toBe(false);
    expect(canCopy({ ...base, mode: 'existing', targetTripId: 't1' })).toBe(true);
  });
});
