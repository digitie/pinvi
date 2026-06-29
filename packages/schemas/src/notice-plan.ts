import { z } from 'zod';
import { Iso8601Schema, NonNegativeDecimalStringSchema } from './common';

const CurrencyPattern = /^[A-Z]{3}$/;
const MarkerColorPattern = /^P-\d{2}$/;

export const NoticePoiSchema = z.object({
  notice_poi_id: z.string().uuid(),
  notice_plan_id: z.string().uuid(),
  day_index: z.number().int(),
  sort_order: z.string(),
  feature_id: z.string().nullable(),
  feature_snapshot: z.record(z.string(), z.unknown()),
  memo: z.string().nullable(),
  budget_amount: NonNegativeDecimalStringSchema.nullable(),
  currency: z.string().regex(CurrencyPattern),
  user_url: z.string().nullable().optional(),
  custom_marker_color: z.string().nullable(),
  custom_marker_icon: z.string().nullable(),
  version: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type NoticePoi = z.infer<typeof NoticePoiSchema>;
export const NoticePoiResponseSchema = NoticePoiSchema;
export type NoticePoiResponse = NoticePoi;

export const NoticePlanResponseSchema = z.object({
  notice_plan_id: z.string().uuid(),
  slug: z.string(),
  title: z.string(),
  category: z.string(),
  summary: z.string().nullable(),
  source_name: z.string().nullable(),
  destination: z.string().nullable(),
  starts_on: z.string().date().nullable(),
  ends_on: z.string().date().nullable(),
  is_published: z.boolean(),
  version: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
  pois: z.array(NoticePoiSchema).default([]),
});
export type NoticePlan = z.infer<typeof NoticePlanResponseSchema>;

export const NoticePlanCreateSchema = z.object({
  slug: z
    .string()
    .min(1)
    .max(160)
    .regex(/^[a-z0-9][a-z0-9-]*$/),
  title: z.string().min(1).max(200),
  category: z.string().min(1).max(80).default('recommended'),
  summary: z.string().nullable().optional(),
  source_name: z.string().max(200).nullable().optional(),
  destination: z.string().max(120).nullable().optional(),
  starts_on: z.string().date().nullable().optional(),
  ends_on: z.string().date().nullable().optional(),
  is_published: z.boolean().default(false),
});
export type NoticePlanCreate = z.infer<typeof NoticePlanCreateSchema>;

export const NoticePlanUpdateSchema = z.object({
  title: z.string().min(1).max(200).optional(),
  category: z.string().min(1).max(80).optional(),
  summary: z.string().nullable().optional(),
  source_name: z.string().max(200).nullable().optional(),
  destination: z.string().max(120).nullable().optional(),
  starts_on: z.string().date().nullable().optional(),
  ends_on: z.string().date().nullable().optional(),
  is_published: z.boolean().optional(),
});
export type NoticePlanUpdate = z.infer<typeof NoticePlanUpdateSchema>;

export const NoticePoiCreateSchema = z.object({
  day_index: z.number().int().min(1).default(1),
  sort_order: z.string().min(1).max(80),
  feature_id: z.string().min(1).max(200).nullable().optional(),
  feature_snapshot: z.record(z.string(), z.unknown()).default({}),
  memo: z.string().nullable().optional(),
  budget_amount: NonNegativeDecimalStringSchema.nullable().optional(),
  currency: z.string().regex(CurrencyPattern).default('KRW'),
  user_url: z.string().max(2000).nullable().optional(),
  custom_marker_color: z.string().regex(MarkerColorPattern).nullable().optional(),
  custom_marker_icon: z.string().max(64).nullable().optional(),
});
export type NoticePoiCreate = z.infer<typeof NoticePoiCreateSchema>;

export const NoticePoiUpdateSchema = NoticePoiCreateSchema.partial();
export type NoticePoiUpdate = z.infer<typeof NoticePoiUpdateSchema>;

export const NoticePoiReorderRequestSchema = z.object({
  items: z
    .array(
      z.object({
        notice_poi_id: z.string().uuid(),
        day_index: z.number().int().min(1),
        sort_order: z.string().min(1).max(80),
      }),
    )
    .min(1),
});
export type NoticePoiReorderRequest = z.infer<typeof NoticePoiReorderRequestSchema>;

export const NoticePlanCopyRequestSchema = z.object({
  target_trip_id: z.string().uuid().nullable().optional(),
  trip_title: z.string().max(200).nullable().optional(),
  trip_start_date: z.string().date().nullable().optional(),
  trip_end_date: z.string().date().nullable().optional(),
  poi_ids: z.array(z.string().uuid()).default([]),
});
export type NoticePlanCopyRequest = z.infer<typeof NoticePlanCopyRequestSchema>;

export const NoticePlanCopyResponseSchema = z.object({
  trip_id: z.string().uuid(),
  created_trip: z.boolean(),
  copied_poi_ids: z.array(z.string().uuid()),
  copied_attachment_count: z.number().int(),
});
export type NoticePlanCopyResponse = z.infer<typeof NoticePlanCopyResponseSchema>;
