import { z } from 'zod';
import { CoordSchema, Iso8601Schema } from './common';

/** `python-krtour-map` 의 7가지 kind. */
export const FeatureKindSchema = z.enum([
  'place',
  'event',
  'notice',
  'price',
  'weather',
  'route',
  'area',
]);
export type FeatureKind = z.infer<typeof FeatureKindSchema>;

/** krtour-map `make_feature_id` 출력. TripMate는 포맷을 해석하지 않는다. */
export const FeatureIdSchema = z.string().min(1).max(200);
export type FeatureId = z.infer<typeof FeatureIdSchema>;

/** viewport bounding box (한국 범위, ADR-018). */
export const BBoxSchema = z.object({
  lng_min: z.number().min(124).max(132),
  lat_min: z.number().min(33).max(43),
  lng_max: z.number().min(124).max(132),
  lat_max: z.number().min(33).max(43),
});
export type BBox = z.infer<typeof BBoxSchema>;

/** 16색 팔레트 P-01~P-16. */
export const MarkerColorSchema = z.string().regex(/^P-\d{2}$/, 'marker color는 P-01~P-16 형식.');

/** 마커 표시용 요약. */
export const FeatureSummarySchema = z.object({
  feature_id: FeatureIdSchema,
  kind: FeatureKindSchema,
  title: z.string(),
  coord: CoordSchema,
  marker_color: MarkerColorSchema,
  marker_icon: z.string().max(64),
  category: z.string().nullable().optional(),
  summary: z.string().nullable().optional(),
});
export type FeatureSummary = z.infer<typeof FeatureSummarySchema>;

/** 클러스터 마커 (zoom < 14). */
export const FeatureClusterSchema = z.object({
  cluster_id: z.string(),
  center: CoordSchema,
  feature_count: z.number().int().min(2),
  sample_kinds: z.array(FeatureKindSchema).max(8),
  bbox: BBoxSchema,
});
export type FeatureCluster = z.infer<typeof FeatureClusterSchema>;

/** viewport 응답 — features + clusters. */
export const FeaturesInBoundsResponseSchema = z.object({
  features: z.array(FeatureSummarySchema),
  clusters: z.array(FeatureClusterSchema),
  zoom: z.number().int().min(5).max(19),
  bbox: BBoxSchema,
});
export type FeaturesInBoundsResponse = z.infer<typeof FeaturesInBoundsResponseSchema>;

/** 상세 응답. */
export const FeatureDetailSchema = z.object({
  feature_id: FeatureIdSchema,
  kind: FeatureKindSchema,
  title: z.string(),
  coord: CoordSchema,
  marker_color: MarkerColorSchema,
  marker_icon: z.string().max(64),
  category: z.string().nullable().optional(),
  address: z.string().nullable().optional(),
  address_road: z.string().nullable().optional(),
  bjd_code: z.string().nullable().optional(),
  sigungu_code: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  detail: z.record(z.string(), z.unknown()),
  source_ids: z.array(z.string()),
  updated_at: Iso8601Schema,
});
export type FeatureDetail = z.infer<typeof FeatureDetailSchema>;

/** KMA timepoint. */
export const WeatherTimepointSchema = z.object({
  asof: Iso8601Schema,
  temp_c: z.number().nullable().optional(),
  precipitation_mm: z.number().nullable().optional(),
  precipitation_prob: z.number().nullable().optional(),
  condition: z.string().nullable().optional(),
  wind_speed_ms: z.number().nullable().optional(),
  humidity_pct: z.number().nullable().optional(),
});
export type WeatherTimepoint = z.infer<typeof WeatherTimepointSchema>;

/** KMA weather card. */
export const FeatureWeatherCardSchema = z.object({
  feature_id: FeatureIdSchema,
  asof: Iso8601Schema,
  short_term: z.array(WeatherTimepointSchema),
  daily: z.array(WeatherTimepointSchema),
  sources: z.array(z.string()),
});
export type FeatureWeatherCard = z.infer<typeof FeatureWeatherCardSchema>;

/** Feature 요청 큐 등록 (Sprint 6 Admin 검토 → 라이브러리 적재). */
export const FeatureRequestCreateSchema = z.object({
  kind: FeatureKindSchema,
  title: z.string().min(1).max(200),
  coord: CoordSchema,
  note: z.string().max(2000).nullable().optional(),
});
export type FeatureRequestCreate = z.infer<typeof FeatureRequestCreateSchema>;

export const FeatureRequestResponseSchema = z.object({
  request_id: z.string().uuid(),
  status: z.literal('pending'),
});
export type FeatureRequestResponse = z.infer<typeof FeatureRequestResponseSchema>;
