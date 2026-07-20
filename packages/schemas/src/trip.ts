import { z } from 'zod';
import { Iso8601Schema, NonNegativeDecimalStringSchema } from './common';
import { PoiRiseSetResponseSchema } from './poi';
import { AttachmentCreateSchema, AttachmentResponseSchema } from './storage';

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

export const TripDeleteRequestSchema = z
  .object({
    mode: z.enum(['soft_delete', 'transfer_leader']).default('soft_delete'),
    new_owner_user_id: z.string().uuid().nullable().optional(),
  })
  .superRefine((value, ctx) => {
    if (value.mode === 'transfer_leader' && !value.new_owner_user_id) {
      ctx.addIssue({
        code: 'custom',
        path: ['new_owner_user_id'],
        message: 'new_owner_user_id is required for transfer_leader',
      });
    }
  });
export type TripDeleteRequest = z.infer<typeof TripDeleteRequestSchema>;

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

// 일자/POI 마커 색 override — 팔레트 키 P-01~P-16 (ADR-055).
const MarkerColorKeySchema = z.string().regex(/^P-(0[1-9]|1[0-6])$/, 'marker color는 P-01~P-16 형식.');

export const TripDayCreateSchema = z.object({
  day_index: z.number().int().min(1).optional(),
  date: z.string().date().nullable().optional(),
  title: z.string().max(200).nullable().optional(),
  note: z.string().nullable().optional(),
  marker_color: MarkerColorKeySchema.nullable().optional(),
});
export type TripDayCreate = z.infer<typeof TripDayCreateSchema>;

export const TripDayUpdateSchema = z.object({
  date: z.string().date().nullable().optional(),
  title: z.string().max(200).nullable().optional(),
  note: z.string().nullable().optional(),
  marker_color: MarkerColorKeySchema.nullable().optional(),
});
export type TripDayUpdate = z.infer<typeof TripDayUpdateSchema>;

export const TripDayResponseSchema = z.object({
  trip_id: z.string().uuid(),
  day_index: z.number().int(),
  date: z.string().date().nullable(),
  title: z.string().nullable(),
  note: z.string().nullable(),
  // 일자 색 override(팔레트 키). NULL이면 인덱스 기본색으로 파생(ADR-055).
  marker_color: z.string().nullable().default(null),
  // backend는 항상 version을 보낸다. default는 version 컬럼 도입(T-287) 이전 응답/목업 호환용.
  version: z.number().int().default(1),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type TripDayResponse = z.infer<typeof TripDayResponseSchema>;

export const TripCopyRequestSchema = z
  .object({
    title: z.string().min(1).max(200).nullable().optional(),
    scope: z.enum(['all', 'day', 'range']).default('all'),
    day_index: z.number().int().min(1).nullable().optional(),
    start_day_index: z.number().int().min(1).nullable().optional(),
    end_day_index: z.number().int().min(1).nullable().optional(),
    date_shift_days: z.number().int().default(0),
    target_trip_id: z.string().uuid().nullable().optional(),
  })
  .superRefine((value, ctx) => {
    if (value.scope === 'day' && !value.day_index) {
      ctx.addIssue({ code: 'custom', path: ['day_index'], message: 'day_index is required' });
    }
    if (value.scope === 'range') {
      if (!value.start_day_index || !value.end_day_index) {
        ctx.addIssue({
          code: 'custom',
          path: ['start_day_index'],
          message: 'start_day_index/end_day_index are required',
        });
      } else if (value.end_day_index < value.start_day_index) {
        ctx.addIssue({
          code: 'custom',
          path: ['end_day_index'],
          message: 'end_day_index must be greater than or equal to start_day_index',
        });
      }
    }
  });
export type TripCopyRequest = z.infer<typeof TripCopyRequestSchema>;

export const TripCopyResponseSchema = z.object({
  trip: TripResponseSchema,
  created_trip: z.boolean(),
  copied_day_count: z.number().int().nonnegative(),
  copied_poi_count: z.number().int().nonnegative(),
  copied_attachment_count: z.number().int().nonnegative(),
});
export type TripCopyResponse = z.infer<typeof TripCopyResponseSchema>;

export const TripViewPoiSchema = z.object({
  poi_id: z.string().uuid(),
  feature_id: z.string().nullable(),
  sort_order: z.string(),
  title: z.string().nullable(),
  feature: z.record(z.string(), z.unknown()),
  marker_color: z.string().nullable(),
  marker_icon: z.string().nullable(),
  // 지도 핀·목록 뱃지 parity용 서버 계산 색(custom > 일자색). 항상 유효 팔레트 키(ADR-055).
  display_marker_color: z.string().nullable().default(null),
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

export const TripDayHolidaySchema = z.object({
  date: z.string().date(),
  name: z.string(),
  dataset: z.enum([
    'holidays',
    'national_holidays',
    'anniversaries',
    'solar_terms_24',
    'sundry_days',
  ]),
});
export type TripDayHoliday = z.infer<typeof TripDayHolidaySchema>;

export const TripViewDaySchema = z.object({
  day_index: z.number().int(),
  date: z.string().date().nullable(),
  // date는 override-only, effective_date는 파생(override 또는 start_date+day_index) — ADR-055.
  effective_date: z.string().date().nullable().default(null),
  // effective_date가 여행 [start,end] 밖이면 true(F1: 기간 축소 시 경고).
  out_of_range: z.boolean().default(false),
  // 일자 색 override(팔레트 키). NULL이면 인덱스 기본색으로 파생.
  marker_color: z.string().nullable().default(null),
  title: z.string().nullable(),
  // backend는 항상 version을 보낸다. default는 version 컬럼 도입(T-287) 이전 응답/목업 호환용.
  version: z.number().int().default(1),
  holidays: z.array(TripDayHolidaySchema).default([]),
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

export const TripSharedViewSchema = z.object({
  visibility: TripShareLinkVisibilitySchema,
  trip: TripResponseSchema,
  days: z.array(TripViewDaySchema),
  broken_feature_count: z.number().int().nonnegative(),
});
export type TripSharedView = z.infer<typeof TripSharedViewSchema>;

export const TripDayOptimizeRequestSchema = z.object({
  // two_opt = nearest-neighbor seed + 2-opt local search (스마트 정렬, 기본).
  strategy: z.enum(['nearest_neighbor', 'two_opt']).default('two_opt'),
  start_poi_id: z.string().uuid().nullable().optional(),
  persist: z.boolean().default(false),
});
export type TripDayOptimizeRequest = z.infer<typeof TripDayOptimizeRequestSchema>;

export const TripDayOptimizeMoveSchema = z.object({
  poi_id: z.string().uuid(),
  old_sort_order: z.string(),
  new_sort_order: z.string(),
});
export type TripDayOptimizeMove = z.infer<typeof TripDayOptimizeMoveSchema>;

export const TripDayOptimizeResponseSchema = z.object({
  trip_id: z.string().uuid(),
  day_index: z.number().int(),
  ordered_poi_ids: z.array(z.string().uuid()),
  moves: z.array(TripDayOptimizeMoveSchema),
  distance_meters: z.number().int().nullable(),
  previous_distance_meters: z.number().int().nullable().default(null),
  warnings: z.array(z.string()),
});
export type TripDayOptimizeResponse = z.infer<typeof TripDayOptimizeResponseSchema>;

export const TripDistanceMatrixResponseSchema = z.object({
  trip_id: z.string().uuid(),
  day_index: z.number().int(),
  poi_ids: z.array(z.string().uuid()),
  distances_meters: z.array(z.array(z.number().int().nullable())),
  warnings: z.array(z.string()),
});
export type TripDistanceMatrixResponse = z.infer<typeof TripDistanceMatrixResponseSchema>;

export const TripAttachmentCreateSchema = AttachmentCreateSchema;
export const TripAttachmentResponseSchema = AttachmentResponseSchema;
export type TripAttachmentCreate = z.infer<typeof TripAttachmentCreateSchema>;
export type TripAttachmentResponse = z.infer<typeof TripAttachmentResponseSchema>;
