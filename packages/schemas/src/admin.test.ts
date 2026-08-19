import { describe, expect, it } from 'vitest';
import { AdminKorTravelMapEtlSummarySchema, AdminProviderDatasetSummarySchema } from './admin';

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

describe('AdminProviderDatasetSummarySchema', () => {
  const row = {
    provider_dataset_id: 41,
    provider: 'kma',
    dataset_key: 'special_days',
    sync_scope: 'dataset_wide',
    operation_key: 'kma_special_days_refresh',
    status: 'healthy',
  };

  it('requires the canonical dataset membership triple', () => {
    expect(AdminProviderDatasetSummarySchema.parse(row)).toMatchObject(row);
    expect(
      AdminProviderDatasetSummarySchema.safeParse({ ...row, operation_key: null }).success,
    ).toBe(true);

    const { operation_key: _operationKey, ...withoutOperationKey } = row;
    expect(AdminProviderDatasetSummarySchema.safeParse(withoutOperationKey).success).toBe(false);
  });
});
