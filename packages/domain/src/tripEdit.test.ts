import { describe, expect, it } from 'vitest';
import {
  buildTripUpdate,
  isValidIsoDate,
  validateTripDateRange,
  type TripEditForm,
} from './tripEdit';

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

  it('buildTripUpdate: 날짜 공백은 trim(검증과 동일 값 전송), 공백만이면 null', () => {
    const patch = buildTripUpdate({ ...base, startDate: ' 2026-07-01 ', endDate: '   ' });
    expect(patch.start_date).toBe('2026-07-01');
    expect(patch.end_date).toBeNull();
  });

  it('isValidIsoDate: 형식 + 실제 달력 날짜', () => {
    expect(isValidIsoDate('2026-07-01')).toBe(true);
    expect(isValidIsoDate('2024-02-29')).toBe(true);
    expect(isValidIsoDate('2026-02-29')).toBe(false); // 평년
    expect(isValidIsoDate('2026-13-01')).toBe(false);
    expect(isValidIsoDate('2026-7-1')).toBe(false);
    expect(isValidIsoDate('20260701')).toBe(false);
    expect(isValidIsoDate('')).toBe(false);
  });

  it('validateTripDateRange: 둘 다 비움/정상 범위 → null', () => {
    expect(validateTripDateRange('', '')).toBeNull();
    expect(validateTripDateRange('  ', '')).toBeNull();
    expect(validateTripDateRange('2026-07-01', '2026-07-03')).toBeNull();
    expect(validateTripDateRange('2026-07-01', '2026-07-01')).toBeNull(); // 당일치기
  });

  it('validateTripDateRange: 형식 오류는 해당 필드', () => {
    expect(validateTripDateRange('2026/07/01', '2026-07-03')).toEqual({
      field: 'startDate',
      message: '날짜는 YYYY-MM-DD 형식으로 입력해 주세요.',
    });
    expect(validateTripDateRange('2026-07-01', '2026-02-30')).toEqual({
      field: 'endDate',
      message: '날짜는 YYYY-MM-DD 형식으로 입력해 주세요.',
    });
  });

  it('validateTripDateRange: 한쪽만 입력 → 비어 있는 쪽에 함께 입력 안내(웹 문구)', () => {
    expect(validateTripDateRange('2026-07-01', '')).toEqual({
      field: 'endDate',
      message: '시작일과 종료일을 함께 입력하거나 둘 다 비워두세요.',
    });
    expect(validateTripDateRange('', '2026-07-03')?.field).toBe('startDate');
  });

  it('validateTripDateRange: 종료 < 시작 → endDate(웹 문구)', () => {
    expect(validateTripDateRange('2026-07-03', '2026-07-01')).toEqual({
      field: 'endDate',
      message: '종료일은 시작일 이후여야 합니다.',
    });
  });
});
