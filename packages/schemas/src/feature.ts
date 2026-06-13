import { z } from 'zod';
import { CoordSchema, Iso8601Schema } from './common';

/** `kor-travel-map` 의 7가지 kind. */
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

/** kor-travel-map `make_feature_id` 출력. Pinvi는 포맷을 해석하지 않는다. */
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

/**
 * 마커/목록 표시용 요약 (in-bounds items / nearby / search).
 * kor_travel_map 평면 `lon`/`lat`(nullable), 표시명 `name`, lifecycle `status`에 정합.
 * `distance_m`은 nearby 응답에만 채워진다.
 */
export const FeatureSummarySchema = z.object({
  feature_id: FeatureIdSchema,
  kind: FeatureKindSchema,
  name: z.string(),
  coord: CoordSchema.nullable(),
  category: z.string().nullable().optional(),
  marker_color: MarkerColorSchema,
  marker_icon: z.string().max(64),
  status: z.string().nullable().optional(),
  distance_m: z.number().nullable().optional(),
});
export type FeatureSummary = z.infer<typeof FeatureSummarySchema>;

/** 서버(kor_travel_map) 클러스터 — `cluster_key`는 행정구역 코드(자연키). */
export const FeatureClusterSchema = z.object({
  cluster_key: z.string(),
  coord: CoordSchema,
  feature_count: z.number().int().min(1),
});
export type FeatureCluster = z.infer<typeof FeatureClusterSchema>;

/** viewport 응답 — 개별 feature(items) + 서버 cluster(clusters). */
export const FeaturesInBoundsResponseSchema = z.object({
  items: z.array(FeatureSummarySchema),
  clusters: z.array(FeatureClusterSchema),
  cluster_unit: z.string().nullable().optional(),
  zoom: z.number().int().min(5).max(19),
  bbox: BBoxSchema,
});
export type FeaturesInBoundsResponse = z.infer<typeof FeaturesInBoundsResponseSchema>;

/** 상세 응답 (kor_travel_map `FeatureDetailResponse` 투영). */
export const FeatureDetailSchema = z.object({
  feature_id: FeatureIdSchema,
  kind: FeatureKindSchema,
  name: z.string(),
  coord: CoordSchema.nullable(),
  category: z.string().nullable().optional(),
  address: z.record(z.string(), z.unknown()).nullable().optional(),
  legal_dong_code: z.string().nullable().optional(),
  sido_code: z.string().nullable().optional(),
  sigungu_code: z.string().nullable().optional(),
  marker_color: MarkerColorSchema,
  marker_icon: z.string().max(64),
  urls: z.record(z.string(), z.unknown()),
  detail: z.record(z.string(), z.unknown()),
  status: z.string().nullable().optional(),
  updated_at: Iso8601Schema,
});
export type FeatureDetail = z.infer<typeof FeatureDetailSchema>;

/** kor_travel_map 평탄 weather metric (forecast_style 태그). */
export const WeatherMetricSchema = z.object({
  metric_key: z.string(),
  metric_name: z.string().nullable().optional(),
  forecast_style: z.string(),
  timeline_bucket: z.string().nullable().optional(),
  valid_at: Iso8601Schema.nullable().optional(),
  issued_at: Iso8601Schema.nullable().optional(),
  observed_at: Iso8601Schema.nullable().optional(),
  value_number: z.number().nullable().optional(),
  value_text: z.string().nullable().optional(),
  unit: z.string().nullable().optional(),
  severity: z.string().nullable().optional(),
});
export type WeatherMetric = z.infer<typeof WeatherMetricSchema>;

/** weather card — 평탄 metric 목록 + source_styles (kor_travel_map `WeatherCardData`). */
export const FeatureWeatherCardSchema = z.object({
  feature_id: FeatureIdSchema,
  asof: Iso8601Schema.nullable().optional(),
  latest_at: Iso8601Schema.nullable().optional(),
  is_stale: z.boolean(),
  source_styles: z.array(z.string()),
  metrics: z.array(WeatherMetricSchema),
});
export type FeatureWeatherCard = z.infer<typeof FeatureWeatherCardSchema>;

/** 카테고리 카탈로그 1건 — 마커 범례 / 필터 칩 (kor_travel_map `CategorySummary` 투영). */
export const FeatureCategorySchema = z.object({
  code: z.string(),
  label: z.string(),
  parent_code: z.string().nullable().optional(),
  depth: z.number().int(),
  path: z.array(z.string()),
  maki_icon: z.string(),
  is_active: z.boolean(),
  sort_order: z.number().int(),
});
export type FeatureCategory = z.infer<typeof FeatureCategorySchema>;

/** Feature 요청 큐 등록 (Admin 검토 → kor_travel_map feature change). */
export const FeatureRequestCategorySchema = z.string().min(1).max(80);

export const FeatureRequestTypeSchema = z.enum(['new_place', 'correction', 'closure']);
export type FeatureRequestType = z.infer<typeof FeatureRequestTypeSchema>;

/** 사용자가 제안 가능한 kind는 장소/이벤트뿐(나머지는 운영 데이터). */
export const FeatureSuggestionKindSchema = z.enum(['place', 'event']);
export type FeatureSuggestionKind = z.infer<typeof FeatureSuggestionKindSchema>;

export const FeatureRequestCreateSchema = z
  .object({
    type: FeatureRequestTypeSchema.optional().default('new_place'),
    kind: FeatureSuggestionKindSchema,
    title: z.string().min(1).max(200),
    coord: CoordSchema,
    categories: z.array(FeatureRequestCategorySchema).max(10).optional().default([]),
    note: z.string().max(2000).nullable().optional(),
    // correction/closure(기존 feature 참조) 시 필수, new_place 시 금지.
    target_feature_id: z.string().min(1).max(200).nullable().optional(),
  })
  .refine((v) => v.type === 'new_place' || v.target_feature_id != null, {
    message: 'correction/closure 제안은 target_feature_id가 필요합니다.',
    path: ['target_feature_id'],
  })
  .refine((v) => v.type !== 'new_place' || v.target_feature_id == null, {
    message: 'new_place 제안은 target_feature_id를 가질 수 없습니다.',
    path: ['target_feature_id'],
  });
export type FeatureRequestCreate = z.infer<typeof FeatureRequestCreateSchema>;

export const FeatureRequestStatusSchema = z.enum([
  'pending',
  'approved',
  'rejected',
  'added',
  'duplicate',
]);
export type FeatureRequestStatus = z.infer<typeof FeatureRequestStatusSchema>;

export const FeatureRequestResponseSchema = z.object({
  request_id: z.string().uuid(),
  status: FeatureRequestStatusSchema,
  type: FeatureRequestTypeSchema,
  kind: FeatureKindSchema,
  title: z.string().min(1).max(200),
  coord: CoordSchema,
  categories: z.array(FeatureRequestCategorySchema).max(10),
  note: z.string().nullable().optional(),
  target_feature_id: z.string().nullable().optional(),
  created_at: Iso8601Schema,
  resolved_at: Iso8601Schema.nullable().optional(),
});
export type FeatureRequestResponse = z.infer<typeof FeatureRequestResponseSchema>;
