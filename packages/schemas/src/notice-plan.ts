import { z } from 'zod';
import { Iso8601Schema, NonNegativeDecimalStringSchema } from './common';

const CurrencyPattern = /^[A-Z]{3}$/;
const MarkerColorPattern = /^P-\d{2}$/;

export const NoticePoiSchema = z.object({
  notice_poi_id: z.string().uuid(),
  notice_plan_id: z.string().uuid(),
  source_curation_item_id: z.string().uuid().nullable().optional(),
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
  source_system: z.literal('kor-travel-map').nullable().optional(),
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
  title: z.string().min(1).max(300),
  category: z.string().min(1).max(128).default('recommended'),
  summary: z.string().nullable().optional(),
  source_name: z.string().max(200).nullable().optional(),
  destination: z.string().max(120).nullable().optional(),
  starts_on: z.string().date().nullable().optional(),
  ends_on: z.string().date().nullable().optional(),
  is_published: z.boolean().default(false),
});
export type NoticePlanCreate = z.infer<typeof NoticePlanCreateSchema>;

export const NoticePlanUpdateSchema = z.object({
  title: z.string().min(1).max(300).optional(),
  category: z.string().min(1).max(128).optional(),
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

export const KorTravelMapCurationCollectionImportRequestSchema = z.object({
  collection_id: z.string().uuid(),
  mode: z.enum(['create', 'refresh']).default('create'),
  is_published: z.boolean().nullable().optional(),
});
export type KorTravelMapCurationCollectionImportRequest = z.infer<
  typeof KorTravelMapCurationCollectionImportRequestSchema
>;

export const KorTravelMapCurationCollectionImportResponseSchema = z.object({
  notice_plan_id: z.string().uuid(),
  created_plan: z.boolean(),
  not_modified: z.boolean(),
  source_system: z.literal('kor-travel-map'),
  source_curation_collection_id: z.string().uuid(),
  source_curation_collection_revision: z.string().regex(/^[1-9][0-9]*$/),
  source_curation_collection_etag: z.string().regex(/^"sha256:[0-9a-f]{64}"$/),
  source_curation_item_set_hash_version: z.literal('ktm-db-item-set-v1'),
  source_curation_item_set_hash: z.string().regex(/^[0-9a-f]{64}$/),
  source_curation_item_count: z.number().int().min(0).max(2_000),
  copied_poi_count: z.number().int().min(0).max(2_000),
  removed_poi_count: z.number().int().min(0).max(2_000),
});
export type KorTravelMapCurationCollectionImportResponse = z.infer<
  typeof KorTravelMapCurationCollectionImportResponseSchema
>;

export const KorTravelMapCurationCutoverLegacyPreflightIssueSchema = z.object({
  code: z.string().min(1).max(128),
  detail: z.string().min(1).max(500),
  notice_plan_id: z.string().uuid().nullable(),
  notice_poi_id: z.string().uuid().nullable(),
});
export type KorTravelMapCurationCutoverLegacyPreflightIssue = z.infer<
  typeof KorTravelMapCurationCutoverLegacyPreflightIssueSchema
>;

export const KorTravelMapCurationCutoverLegacyPreflightResponseSchema = z.object({
  map_release_revision: z.string().regex(/^[0-9a-f]{40}$/),
  mapping_receipt_id: z.string().uuid().nullable(),
  mapping_root: z
    .string()
    .regex(/^[0-9a-f]{64}$/)
    .nullable(),
  mapping_count: z.number().int().min(0),
  legacy_plan_count: z.number().int().min(0),
  legacy_source_poi_count: z.number().int().min(0),
  manual_poi_count: z.number().int().min(0),
  backfillable_plan_count: z.number().int().min(0),
  ready: z.boolean(),
  issues: z.array(KorTravelMapCurationCutoverLegacyPreflightIssueSchema),
});
export type KorTravelMapCurationCutoverLegacyPreflightResponse = z.infer<
  typeof KorTravelMapCurationCutoverLegacyPreflightResponseSchema
>;

export const KorTravelMapCurationCutoverBackfillRequestSchema = z.object({
  notice_plan_id: z.string().uuid(),
});
export type KorTravelMapCurationCutoverBackfillRequest = z.infer<
  typeof KorTravelMapCurationCutoverBackfillRequestSchema
>;

export const KorTravelMapCurationCutoverBackfillResponseSchema = z.object({
  backfill_receipt_id: z.string().uuid(),
  mapping_receipt_id: z.string().uuid(),
  legacy_curated_feature_id: z.string().uuid(),
  import_result: KorTravelMapCurationCollectionImportResponseSchema,
  replayed: z.boolean(),
});
export type KorTravelMapCurationCutoverBackfillResponse = z.infer<
  typeof KorTravelMapCurationCutoverBackfillResponseSchema
>;
