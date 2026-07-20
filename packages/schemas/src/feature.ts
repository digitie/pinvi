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

/** detail-card 옵트인 외부 enrichment 1행(ADR-056, display-only). matched=false면 "일치 정보 없음". */
export const ExternalEnrichmentSchema = z.object({
  provider: z.enum(['kakao', 'naver']),
  matched: z.boolean().default(false),
  name: z.string().nullable().default(null),
  address: z.string().nullable().default(null),
  phone: z.string().nullable().default(null),
  provider_url: z.string().nullable().default(null),
  external_id: z.string().nullable().default(null),
});
export type ExternalEnrichment = z.infer<typeof ExternalEnrichmentSchema>;

// kind별 detail-card 공통 필드(일반 사용자 노출용). 원본 detail/urls dict는 노출하지 않는다.
const detailCardBase = {
  feature_id: z.string().min(1).max(200),
  name: z.string(),
  coord: CoordSchema.nullable().default(null),
  category: z.string().nullable().default(null),
  address_line: z.string().nullable().default(null),
  marker_color: z.string().default('P-13'),
  marker_icon: z.string().default('marker'),
  homepage_url: z.string().nullable().default(null),
  status: z.string().nullable().default(null),
  enrichment: z.array(ExternalEnrichmentSchema).default([]),
  degraded_providers: z.array(z.string()).default([]),
};

export const PlaceDetailCardSchema = z.object({
  ...detailCardBase,
  kind: z.literal('place'),
  phone: z.string().nullable().default(null),
  business_hours: z.string().nullable().default(null),
});
export const EventDetailCardSchema = z.object({
  ...detailCardBase,
  kind: z.literal('event'),
  start_date: z.string().nullable().default(null),
  end_date: z.string().nullable().default(null),
  venue: z.string().nullable().default(null),
});
export const NoticeDetailCardSchema = z.object({
  ...detailCardBase,
  kind: z.literal('notice'),
  body: z.string().nullable().default(null),
  start_date: z.string().nullable().default(null),
  end_date: z.string().nullable().default(null),
});
export const PriceItemSchema = z.object({
  name: z.string(),
  price: z.string().nullable().default(null),
});
export const PriceDetailCardSchema = z.object({
  ...detailCardBase,
  kind: z.literal('price'),
  unit: z.string().nullable().default(null),
  items: z.array(PriceItemSchema).default([]),
});
// weather/route/area는 리치 arm 없이 공통 필드만(generic fallback).
export const WeatherDetailCardSchema = z.object({ ...detailCardBase, kind: z.literal('weather') });
export const RouteDetailCardSchema = z.object({ ...detailCardBase, kind: z.literal('route') });
export const AreaDetailCardSchema = z.object({ ...detailCardBase, kind: z.literal('area') });

/** `GET /features/{id}/detail-card` — kind로 판별하는 discriminated union(ADR-056). */
export const FeatureDetailCardSchema = z.discriminatedUnion('kind', [
  PlaceDetailCardSchema,
  EventDetailCardSchema,
  NoticeDetailCardSchema,
  PriceDetailCardSchema,
  WeatherDetailCardSchema,
  RouteDetailCardSchema,
  AreaDetailCardSchema,
]);
export type FeatureDetailCard = z.infer<typeof FeatureDetailCardSchema>;

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

export const ExternalRefProviderSchema = z.enum(['kakao', 'naver']);
export type ExternalRefProvider = z.infer<typeof ExternalRefProviderSchema>;

/** 외부 provider opaque 참조(ADR-054 §7) — 식별자/딥링크만, provider 콘텐츠는 저장 안 함. */
export const ExternalRefSchema = z.object({
  provider: ExternalRefProviderSchema,
  external_id: z.string().min(1).max(200),
  deep_link_url: z.string().max(2000).nullable().optional(),
});
export type ExternalRef = z.infer<typeof ExternalRefSchema>;

/** 제안/POI 출처 태그. */
export const FeatureRequestSourceSchema = z.enum(['user', 'kakao', 'naver']);
export type FeatureRequestSource = z.infer<typeof FeatureRequestSourceSchema>;

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
    // ADR-054: Kakao/Naver pick에서 온 제안이면 source + external_ref(전역 dedup 키).
    source: FeatureRequestSourceSchema.optional().default('user'),
    external_ref: ExternalRefSchema.nullable().optional(),
  })
  .refine((v) => v.type === 'new_place' || v.target_feature_id != null, {
    message: 'correction/closure 제안은 target_feature_id가 필요합니다.',
    path: ['target_feature_id'],
  })
  .refine((v) => v.type !== 'new_place' || v.target_feature_id == null, {
    message: 'new_place 제안은 target_feature_id를 가질 수 없습니다.',
    path: ['target_feature_id'],
  })
  .refine((v) => v.external_ref == null || v.type === 'new_place', {
    message: '외부 참조(external_ref) 제안은 new_place만 가능합니다.',
    path: ['external_ref'],
  })
  .refine((v) => v.external_ref == null || v.source === v.external_ref.provider, {
    message: 'source는 external_ref.provider와 일치해야 합니다.',
    path: ['source'],
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
  source: z.string().default('user'),
  external_ref: ExternalRefSchema.nullable().default(null),
  created_at: Iso8601Schema,
  resolved_at: Iso8601Schema.nullable().optional(),
});
export type FeatureRequestResponse = z.infer<typeof FeatureRequestResponseSchema>;
