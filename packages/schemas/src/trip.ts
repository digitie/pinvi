import { z } from 'zod';
import { Iso8601Schema, NonNegativeDecimalStringSchema } from './common';
import { PoiRiseSetResponseSchema } from './poi';

/** `docs/api/trips.md`. */
export const TripStatusSchema = z.enum([
  'draft',
  'planned',
  'in_progress',
  'completed',
  'archived',
]);
export const TripVisibilitySchema = z.enum(['private', 'unlisted', 'public']);
const RegionCodeSchema = z.string().regex(/^[0-9]{2,10}$/);
export const TripPrimaryRegionSourceSchema = z.enum(['manual', 'poi_snapshot', 'geocoded']);
export const TripCompanionRoleSchema = z.enum(['co_owner', 'editor', 'viewer']);
export const TripShareLinkVisibilitySchema = z.enum(['view_only', 'comment', 'edit']);
export type TripStatus = z.infer<typeof TripStatusSchema>;
export type TripVisibility = z.infer<typeof TripVisibilitySchema>;
export type TripPrimaryRegionSource = z.infer<typeof TripPrimaryRegionSourceSchema>;
export type TripCompanionRole = z.infer<typeof TripCompanionRoleSchema>;
export type TripShareLinkVisibility = z.infer<typeof TripShareLinkVisibilitySchema>;

export const TripCompanionInviteSchema = z.object({
  email: z.string().email().max(320),
  display_name: z.string().max(80).nullable().optional(),
  role: TripCompanionRoleSchema.default('editor'),
});
export type TripCompanionInvite = z.infer<typeof TripCompanionInviteSchema>;

export const TripCompanionResponseSchema = z.object({
  companion_id: z.string().uuid(),
  trip_id: z.string().uuid(),
  user_id: z.string().uuid().nullable(),
  invited_email: z.string().email().nullable(),
  invited_nickname: z.string().nullable(),
  role: TripCompanionRoleSchema,
  invited_at: Iso8601Schema,
  joined_at: Iso8601Schema.nullable(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type TripCompanionResponse = z.infer<typeof TripCompanionResponseSchema>;

export const TripCommentTargetSchema = z.enum(['trip', 'day', 'poi']);
export const TripCommentCreateSchema = z.object({
  body: z.string().trim().min(1).max(2000),
  target_type: TripCommentTargetSchema.default('trip'),
  target_id: z.string().uuid().nullable().optional(),
  day_index: z.number().int().min(1).nullable().optional(),
});
export type TripCommentCreate = z.infer<typeof TripCommentCreateSchema>;

export const TripCommentResponseSchema = z.object({
  comment_id: z.string().uuid(),
  trip_id: z.string().uuid(),
  author_user_id: z.string().uuid().nullable(),
  body: z.string(),
  target_type: TripCommentTargetSchema,
  target_id: z.string().uuid().nullable(),
  day_index: z.number().int().nullable(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type TripCommentResponse = z.infer<typeof TripCommentResponseSchema>;

export const TripShareLinkCreateSchema = z.object({
  visibility: TripShareLinkVisibilitySchema.default('view_only'),
  expires_at: Iso8601Schema.nullable().optional(),
});
export type TripShareLinkCreate = z.infer<typeof TripShareLinkCreateSchema>;

export const TripShareLinkResponseSchema = z.object({
  share_id: z.string().uuid(),
  trip_id: z.string().uuid(),
  visibility: TripShareLinkVisibilitySchema,
  token: z.string(),
  url: z.string().url(),
  expires_at: Iso8601Schema.nullable(),
  revoked_at: Iso8601Schema.nullable(),
  last_used_at: Iso8601Schema.nullable(),
  created_at: Iso8601Schema,
});
export type TripShareLinkResponse = z.infer<typeof TripShareLinkResponseSchema>;

export const TripCreateSchema = z.object({
  title: z.string().min(1).max(200),
  description: z.string().nullable().optional(),
  region_hint: z.string().max(120).nullable().optional(),
  primary_region_code: RegionCodeSchema.nullable().optional(),
  start_date: z.string().date().nullable().optional(),
  end_date: z.string().date().nullable().optional(),
  visibility: TripVisibilitySchema.default('private'),
  companions: z.array(TripCompanionInviteSchema).default([]),
});
export type TripCreate = z.infer<typeof TripCreateSchema>;

export const TripUpdateSchema = z.object({
  title: z.string().min(1).max(200).optional(),
  description: z.string().nullable().optional(),
  region_hint: z.string().max(120).nullable().optional(),
  primary_region_code: RegionCodeSchema.nullable().optional(),
  cover_attachment_id: z.string().uuid().nullable().optional(),
  start_date: z.string().date().nullable().optional(),
  end_date: z.string().date().nullable().optional(),
  visibility: TripVisibilitySchema.optional(),
  status: TripStatusSchema.optional(),
});
export type TripUpdate = z.infer<typeof TripUpdateSchema>;

export const TripResponseSchema = z.object({
  trip_id: z.string().uuid(),
  owner_user_id: z.string().uuid(),
  title: z.string(),
  description: z.string().nullable(),
  region_hint: z.string().nullable(),
  primary_region_code: RegionCodeSchema.nullable(),
  primary_region_source: TripPrimaryRegionSourceSchema.nullable(),
  start_date: z.string().date().nullable(),
  end_date: z.string().date().nullable(),
  visibility: TripVisibilitySchema,
  status: TripStatusSchema,
  version: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type TripResponse = z.infer<typeof TripResponseSchema>;

export const TripViewPoiSchema = z.object({
  poi_id: z.string().uuid(),
  feature_id: z.string(),
  sort_order: z.string(),
  title: z.string().nullable(),
  feature: z.record(z.string(), z.unknown()),
  marker_color: z.string().nullable(),
  marker_icon: z.string().nullable(),
  is_broken: z.boolean(),
  user_note: z.string().nullable(),
  planned_arrival_at: Iso8601Schema.nullable(),
  planned_departure_at: Iso8601Schema.nullable(),
  budget_amount: NonNegativeDecimalStringSchema.nullable(),
  actual_amount: NonNegativeDecimalStringSchema.nullable(),
  currency: z.string().regex(/^[A-Z]{3}$/),
  user_url: z.string().nullable(),
  rise_set: PoiRiseSetResponseSchema.nullable(),
  feature_link_broken_at: Iso8601Schema.nullable(),
  version: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type TripViewPoi = z.infer<typeof TripViewPoiSchema>;

export const TripViewDaySchema = z.object({
  day_index: z.number().int(),
  date: z.string().date().nullable(),
  title: z.string().nullable(),
  pois: z.array(TripViewPoiSchema),
});
export type TripViewDay = z.infer<typeof TripViewDaySchema>;

export const TripViewShareLinkSchema = z.object({
  share_id: z.string().uuid(),
  visibility: TripShareLinkVisibilitySchema,
  expires_at: Iso8601Schema.nullable(),
  revoked_at: Iso8601Schema.nullable(),
  last_used_at: Iso8601Schema.nullable(),
  created_at: Iso8601Schema,
});
export type TripViewShareLink = z.infer<typeof TripViewShareLinkSchema>;

export const TripViewSchema = z.object({
  trip: TripResponseSchema,
  days: z.array(TripViewDaySchema),
  companions: z.array(TripCompanionResponseSchema),
  share_links: z.array(TripViewShareLinkSchema),
  broken_feature_count: z.number().int().nonnegative(),
});
export type TripView = z.infer<typeof TripViewSchema>;
