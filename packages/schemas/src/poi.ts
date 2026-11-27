import { z } from 'zod';
import { Iso8601Schema, NonNegativeDecimalStringSchema } from './common';
import { ExternalRefSchema } from './feature';

/** `docs/api/pois.md`. */
const MarkerColorPattern = /^P-(0[1-9]|1[0-6])$/;
const CurrencyPattern = /^[A-Z]{3}$/;

/** POI 출처 — feature 연결 / 수동 / 외부 provider pick(ADR-054). */
export const PoiSourceSchema = z.enum(['feature', 'manual', 'kakao', 'naver']);
export type PoiSource = z.infer<typeof PoiSourceSchema>;

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
  // ADR-054: 외부 pick(kakao/naver)이면 source + external_ref를 실어 보낸다(서버가 auto-fire).
  source: PoiSourceSchema.nullable().optional(),
  external_ref: ExternalRefSchema.nullable().optional(),
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
  day_index: z.number().int().min(1).nullable().optional(),
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
  day_index: z.number().int().min(1),
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

/**
 * `POST /trips/{trip_id}/pois/{poi_id}/move` — 장소 하나를 `day_index` 일자의 `before_poi_id`
 * 바로 앞(null이면 맨 끝)으로 옮긴다. 같은 일자 안 순서 변경도 이 요청이다.
 */
export const PoiMoveRequestSchema = z
  .object({
    day_index: z.number().int().min(1),
    before_poi_id: z.string().uuid().nullable(),
  })
  .strict();
export type PoiMoveRequest = z.infer<typeof PoiMoveRequestSchema>;

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
  source: z.string().nullable().default(null),
  external_ref: ExternalRefSchema.nullable().default(null),
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

/** 이동 응답 — `changed`는 정렬 위치·일자가 바뀐 장소 전부(옮긴 장소 포함). 그대로면 빈 목록. */
export const PoiMoveResponseSchema = z.object({
  poi: PoiResponseSchema,
  from_day_index: z.number().int(),
  changed: z.array(PoiResponseSchema),
});
export type PoiMoveResponse = z.infer<typeof PoiMoveResponseSchema>;

/**
 * 장소 영업 정보 — `GET|POST /trips/{id}/pois/{poi}/place-details[/refresh]`.
 * `status`: ready(값 있음) / empty(출처에 값 없음) / unavailable(출처 장애, 저장 안 됨).
 * `sources`: 필드 이름 → 출처 이름(`kor_travel_map`).
 */
export const PoiPlaceDetailsSchema = z.object({
  poi_id: z.string().uuid(),
  status: z.enum(['ready', 'empty', 'unavailable']),
  opening_hours: z.array(z.string()).default([]),
  closed_days: z.string().nullable().default(null),
  phone: z.string().nullable().default(null),
  website: z.string().nullable().default(null),
  sources: z.record(z.string(), z.string()).default({}),
  fetched_at: Iso8601Schema.nullable().default(null),
  refresh_available_at: Iso8601Schema.nullable().default(null),
});
export type PoiPlaceDetails = z.infer<typeof PoiPlaceDetailsSchema>;
