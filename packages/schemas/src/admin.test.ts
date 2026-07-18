import { describe, expect, it } from 'vitest';
import { AdminKorTravelMapEtlSummarySchema } from './admin';

describe('AdminKorTravelMapEtlSummarySchema', () => {
  it('accepts partial operation status counts and defaults an absent map', () => {
    expect(
      AdminKorTravelMapEtlSummarySchema.parse({
        status: 'ok',
        dagster_status: 'ok',
        operations_by_status: { running: 2 },
      }).operations_by_status,
    ).toEqual({ running: 2 });

    expect(
      AdminKorTravelMapEtlSummarySchema.parse({
        status: 'ok',
        dagster_status: 'ok',
      }).operations_by_status,
    ).toEqual({});
  });

  it('rejects operation status keys outside the canonical enum', () => {
    expect(
      AdminKorTravelMapEtlSummarySchema.safeParse({
        status: 'ok',
        dagster_status: 'ok',
        operations_by_status: { unknown: 1 },
      }).success,
    ).toBe(false);
  });
});
