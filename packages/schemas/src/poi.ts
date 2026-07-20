import { z } from 'zod';
import { Iso8601Schema, NonNegativeDecimalStringSchema } from './common';

/** `docs/api/pois.md`. */
const MarkerColorPattern = /^P-(0[1-9]|1[0-6])$/;
const CurrencyPattern = /^[A-Z]{3}$/;

export const PoiRiseSetStatusSchema = z.enum([
  'pending_date',
  'pending_coord',
  'pending_fetch',
  'success',
  'failed',
]);
export type PoiRiseSetStatus = z.infer<typeof PoiRiseSetStatusSchema>;

export const PoiRiseSetResponseSchema = z.object({
  status: PoiRiseSetStatusSchema,
  locdate: z.string().date().nullable(),
  sunrise_at: Iso8601Schema.nullable(),
  sunset_at: Iso8601Schema.nullable(),
  moonrise_at: Iso8601Schema.nullable(),
  moonset_at: Iso8601Schema.nullable(),
  fetched_at: Iso8601Schema.nullable(),
  updated_at: Iso8601Schema,
});
export type PoiRiseSetResponse = z.infer<typeof PoiRiseSetResponseSchema>;

export const PoiCreateSchema = z.object({
  day_index: z.number().int().min(1),
  sort_order: z.string().min(1).max(80),
  feature_id: z.string().min(1).max(200).nullable().optional(),
  feature_snapshot: z.record(z.string(), z.unknown()).default({}),
  custom_marker_color: z.string().regex(MarkerColorPattern).nullable().optional(),
  custom_marker_icon: z.string().max(64).nullable().optional(),
  planned_arrival_at: Iso8601Schema.nullable().optional(),
  planned_departure_at: Iso8601Schema.nullable().optional(),
  user_note: z.string().nullable().optional(),
  budget_amount: z.number().nonnegative().nullable().optional(),
  actual_amount: z.number().nonnegative().nullable().optional(),
  currency: z.string().regex(CurrencyPattern).default('KRW'),
  user_url: z.string().max(2000).nullable().optional(),
});
export type PoiCreate = z.infer<typeof PoiCreateSchema>;

export const PoiUpdateSchema = z.object({
  sort_order: z.string().min(1).max(80).optional(),
  feature_snapshot: z.record(z.string(), z.unknown()).nullable().optional(),
  custom_marker_color: z.string().regex(MarkerColorPattern).nullable().optional(),
  custom_marker_icon: z.string().max(64).nullable().optional(),
  planned_arrival_at: Iso8601Schema.nullable().optional(),
  planned_departure_at: Iso8601Schema.nullable().optional(),
  user_note: z.string().nullable().optional(),
  budget_amount: z.number().nonnegative().nullable().optional(),
  actual_amount: z.number().nonnegative().nullable().optional(),
  currency: z.string().regex(CurrencyPattern).nullable().optional(),
  user_url: z.string().max(2000).nullable().optional(),
});
export type PoiUpdate = z.infer<typeof PoiUpdateSchema>;

export const PoiReorderRequestSchema = z.object({
  moves: z
    .array(
      z.object({
        poi_id: z.string().uuid(),
        new_sort_order: z.string().min(1).max(80),
      }),
    )
    .min(1)
    .max(200),
});
export type PoiReorderRequest = z.infer<typeof PoiReorderRequestSchema>;

export const PoiResponseSchema = z.object({
  attachment_id: z.string().uuid(),
  trip_id: z.string().uuid(),
  day_index: z.number().int(),
  sort_order: z.string(),
  feature_id: z.string().nullable(),
  feature_link_broken_at: Iso8601Schema.nullable(),
  feature_snapshot: z.record(z.string(), z.unknown()),
  custom_marker_color: z.string().nullable(),
  custom_marker_icon: z.string().nullable(),
  planned_arrival_at: Iso8601Schema.nullable(),
  planned_departure_at: Iso8601Schema.nullable(),
  user_note: z.string().nullable(),
  budget_amount: NonNegativeDecimalStringSchema.nullable(),
  actual_amount: NonNegativeDecimalStringSchema.nullable(),
  currency: z.string().regex(CurrencyPattern),
  user_url: z.string().nullable(),
  rise_set: PoiRiseSetResponseSchema.nullable(),
  version: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type PoiResponse = z.infer<typeof PoiResponseSchema>;
