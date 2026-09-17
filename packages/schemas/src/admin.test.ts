import { describe, expect, it } from 'vitest';
import {
  AdminFeatureWeatherValuesResponseSchema,
  AdminKorTravelMapEtlSummarySchema,
  AdminProviderDatasetSummarySchema,
} from './admin';

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

describe('AdminFeatureWeatherValuesResponseSchema', () => {
  const response = {
    feature_id: 'f_weather_1',
    items: [
      {
        metric_key: 'T1H',
        forecast_style: 'nowcast',
        provider_dataset_id: 41,
        dataset_key: 'kma_vilage_forecast',
        dataset_display_name: '기상청 단기예보',
        known_at: '2026-06-12T09:35:00+09:00',
      },
    ],
  };

  it('preserves Admin weather dataset and knowledge provenance when present', () => {
    const parsed = AdminFeatureWeatherValuesResponseSchema.parse(response);

    expect(parsed.items[0]!).toMatchObject(response.items[0]!);
  });

  it('T-364(ADR-068): kor-travel-weather source has no provider_dataset_id/dataset_display_name/known_at — nullable, defaults to null', () => {
    const metric = { ...response.items[0] };
    delete (metric as Partial<typeof metric>).provider_dataset_id;
    delete (metric as Partial<typeof metric>).dataset_display_name;
    delete (metric as Partial<typeof metric>).known_at;

    const parsed = AdminFeatureWeatherValuesResponseSchema.safeParse({
      ...response,
      items: [metric],
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.items[0]).toMatchObject({
        provider_dataset_id: null,
        dataset_display_name: null,
        known_at: null,
      });
    }
  });

  it('still rejects an Admin weather metric missing dataset_key — both sources always have it', () => {
    const metric = { ...response.items[0] };
    delete (metric as Partial<typeof metric>).dataset_key;

    expect(
      AdminFeatureWeatherValuesResponseSchema.safeParse({ ...response, items: [metric] }).success,
    ).toBe(false);
  });
});
