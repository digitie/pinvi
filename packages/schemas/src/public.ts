import { z } from 'zod';
import { Iso8601Schema } from './common';
import { FeatureIdSchema, MarkerColorSchema } from './feature';

const JsonObjectSchema = z.record(z.string(), z.unknown());

/** 공개 해수욕장 목록/상세 view. */
export const PublicBeachViewSchema = z.object({
  feature_id: FeatureIdSchema,
  display_name: z.string(),
  address: JsonObjectSchema,
  source_providers: z.array(z.string()),
  updated_at: Iso8601Schema,
  beach_kind: z.string().nullable().optional(),
  beach_width_m: z.number().nullable().optional(),
  beach_length_m: z.number().nullable().optional(),
  beach_material: z.string().nullable().optional(),
  emergency_contact: z.string().nullable().optional(),
  homepage_url: z.string().nullable().optional(),
  image_url: z.string().nullable().optional(),
  road_address: z.string().nullable().optional(),
  jibun_address: z.string().nullable().optional(),
  legal_dong_code: z.string().nullable().optional(),
  sido_code: z.string().nullable().optional(),
  sigungu_code: z.string().nullable().optional(),
  lon: z.number().nullable().optional(),
  lat: z.number().nullable().optional(),
  marker_color: MarkerColorSchema.nullable().optional(),
  marker_icon: z.string().nullable().optional(),
  latest_water_quality: JsonObjectSchema.nullable().optional(),
  latest_weather: JsonObjectSchema.nullable().optional(),
  upcoming_index_forecasts: z.array(JsonObjectSchema).optional().default([]),
});
export type PublicBeachView = z.infer<typeof PublicBeachViewSchema>;

export const PublicBeachListSchema = z.object({
  items: z.array(PublicBeachViewSchema),
});
export type PublicBeachList = z.infer<typeof PublicBeachListSchema>;

export const PublicFestivalStatusSchema = z.enum(['scheduled', 'ongoing', 'ended', 'unknown']);
export type PublicFestivalStatus = z.infer<typeof PublicFestivalStatusSchema>;

/** 공개 축제 목록/상세 view. */
export const PublicFestivalViewSchema = z.object({
  feature_id: FeatureIdSchema,
  festival_name: z.string(),
  event_status: PublicFestivalStatusSchema,
  address: JsonObjectSchema,
  source_providers: z.array(z.string()),
  updated_at: Iso8601Schema,
  event_start_date: z.string().date().nullable().optional(),
  event_end_date: z.string().date().nullable().optional(),
  venue_name: z.string().nullable().optional(),
  road_address: z.string().nullable().optional(),
  jibun_address: z.string().nullable().optional(),
  sido_code: z.string().nullable().optional(),
  sigungu_code: z.string().nullable().optional(),
  lon: z.number().nullable().optional(),
  lat: z.number().nullable().optional(),
  homepage_url: z.string().nullable().optional(),
  festival_content: z.string().nullable().optional(),
  organizer_name: z.string().nullable().optional(),
  auspc_instt_name: z.string().nullable().optional(),
  suprt_instt_name: z.string().nullable().optional(),
  phone_number: z.string().nullable().optional(),
  provider_org_name: z.string().nullable().optional(),
  reference_date: z.string().date().nullable().optional(),
  marker_color: MarkerColorSchema.nullable().optional(),
  marker_icon: z.string().nullable().optional(),
});
export type PublicFestivalView = z.infer<typeof PublicFestivalViewSchema>;

export const PublicFestivalMonthSchema = z.object({
  year: z.number().int(),
  month: z.number().int().min(1).max(12),
  count: z.number().int().min(0),
});
export type PublicFestivalMonth = z.infer<typeof PublicFestivalMonthSchema>;

export const PublicFestivalMonthlySchema = z.object({
  months: z.array(PublicFestivalMonthSchema),
  items: z.array(PublicFestivalViewSchema),
});
export type PublicFestivalMonthly = z.infer<typeof PublicFestivalMonthlySchema>;

export const PublicMapMarkerSchema = z.object({
  feature_id: FeatureIdSchema,
  name: z.string(),
  lon: z.number(),
  lat: z.number(),
  sigungu_code: z.string().nullable().optional(),
});
export type PublicMapMarker = z.infer<typeof PublicMapMarkerSchema>;

export const PublicMapLayerKeySchema = z.enum(['beach', 'festival']);
export type PublicMapLayerKey = z.infer<typeof PublicMapLayerKeySchema>;

export const PublicMapMarkerLayerSchema = z.object({
  layer_key: PublicMapLayerKeySchema,
  display_name: z.string(),
  marker_icon: z.string(),
  marker_color: MarkerColorSchema,
  items: z.array(PublicMapMarkerSchema),
});
export type PublicMapMarkerLayer = z.infer<typeof PublicMapMarkerLayerSchema>;
