import { z } from 'zod';
import { Iso8601Schema } from './common';

/** `docs/api/pois.md`. */
const MarkerColorPattern = /^P-\d{2}$/;
const CurrencyPattern = /^[A-Z]{3}$/;

export const PoiCreateSchema = z.object({
  day_index: z.number().int().min(1),
  sort_order: z.string().min(1).max(80),
  feature_id: z.string().min(1).max(200),
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

export const PoiResponseSchema = z.object({
  attachment_id: z.string().uuid(),
  trip_id: z.string().uuid(),
  day_index: z.number().int(),
  sort_order: z.string(),
  feature_id: z.string(),
  feature_link_broken_at: Iso8601Schema.nullable(),
  feature_snapshot: z.record(z.string(), z.unknown()),
  custom_marker_color: z.string().nullable(),
  custom_marker_icon: z.string().nullable(),
  planned_arrival_at: Iso8601Schema.nullable(),
  planned_departure_at: Iso8601Schema.nullable(),
  user_note: z.string().nullable(),
  budget_amount: z.number().nonnegative().nullable(),
  actual_amount: z.number().nonnegative().nullable(),
  currency: z.string().regex(CurrencyPattern),
  user_url: z.string().nullable(),
  version: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type PoiResponse = z.infer<typeof PoiResponseSchema>;
