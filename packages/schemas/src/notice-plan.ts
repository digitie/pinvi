import { z } from 'zod';
import { Iso8601Schema, NonNegativeDecimalStringSchema } from './common';

const CurrencyPattern = /^[A-Z]{3}$/;

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
  custom_marker_color: z.string().nullable(),
  custom_marker_icon: z.string().nullable(),
  version: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type NoticePoi = z.infer<typeof NoticePoiSchema>;

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
