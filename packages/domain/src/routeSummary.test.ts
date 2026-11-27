import { describe, expect, it } from 'vitest';
import { formatRouteDuration, formatRouteLength, routeSummaryLine } from './routeSummary';

describe('routeSummary', () => {
  it('formats length in m below 1 km and km above', () => {
    expect(formatRouteLength(850.4)).toBe('850 m');
    expect(formatRouteLength(4210.5)).toBe('4.2 km');
    expect(formatRouteLength(999.6)).toBe('1.0 km');
  });

  it('formats duration in hours and minutes', () => {
    expect(formatRouteDuration(45)).toBe('약 45분');
    expect(formatRouteDuration(120)).toBe('약 2시간');
    expect(formatRouteDuration(150)).toBe('약 2시간 30분');
  });

  it('builds the itinerary line for a hiking course', () => {
    expect(
      routeSummaryLine({
        route_type: 'hiking_course',
        length_m: 4210.5,
        duration_minutes: 150,
        duration_basis: 'estimated',
        difficulty: 'moderate',
        shape: 'path',
      }),
    ).toBe('등산 코스 · 4.2 km · 약 2시간 30분(추정) · 보통');
  });

  it('marks network length and keeps source durations unmarked', () => {
    expect(
      routeSummaryLine({
        route_type: 'hiking_course',
        length_m: 23003.7,
        duration_minutes: 775,
        duration_basis: 'source',
        difficulty: null,
        shape: 'network',
      }),
    ).toBe('등산 코스 · 23.0 km(갈래 포함) · 약 12시간 55분(갈래 포함)');
  });

  it('returns null for missing or unusable input', () => {
    expect(routeSummaryLine(undefined)).toBeNull();
    expect(routeSummaryLine('x')).toBeNull();
    expect(routeSummaryLine({ route_type: 'hiking_course' })).toBeNull();
    expect(routeSummaryLine({ length_m: -1, duration_minutes: Number.NaN })).toBeNull();
    expect(
      routeSummaryLine({ route_type: 'hiking_course', length_m: 0, duration_minutes: 0 }),
    ).toBeNull();
  });

  it('marks estimated network durations with both notes', () => {
    expect(
      routeSummaryLine({
        route_type: 'hiking_course',
        length_m: 1500,
        duration_minutes: 27,
        duration_basis: 'estimated',
        shape: 'network',
      }),
    ).toBe('등산 코스 · 1.5 km(갈래 포함) · 약 27분(추정·갈래 포함)');
  });
});
