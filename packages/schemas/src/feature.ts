import { z } from 'zod';
import { CoordSchema, CoordSourceSchema, Iso8601Schema } from './common';

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
 * kor_travel_map 평면 `lon`/`lat`(nullable), 표시명 `name`에 정합. `status`는 Map 3축 state
 * cutover(`1f2bdc3a`)로 user 표면에서 사라져 공개 계약에서도 제거했다(T-VN-42).
 * `distance_m`은 nearby 응답에만 채워진다.
 */
/** Map 정본 WGS84 도형. nullable 장소 좌표를 도형 중심으로 대체하지 않는다. */
const GeometryPositionSchema = z
  .tuple([z.number().finite().min(-180).max(180), z.number().finite().min(-90).max(90)])
  .rest(z.number().finite());
const GeometryLineSchema = z.array(GeometryPositionSchema).min(2);
const GeometryRingSchema = z
  .array(GeometryPositionSchema)
  .min(4)
  .refine((ring) => {
    const first = ring[0];
    const last = ring[ring.length - 1];
    return (
      ring.length >= 4 &&
      first !== undefined &&
      last !== undefined &&
      first[0] === last[0] &&
      first[1] === last[1]
    );
  }, '다각형의 시작점과 끝점이 같아야 합니다.');
const GeometryPolygonSchema = z.array(GeometryRingSchema).min(1);
export const FeatureGeometrySchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('LineString'), coordinates: GeometryLineSchema }),
  z.object({ type: z.literal('MultiLineString'), coordinates: z.array(GeometryLineSchema).min(1) }),
  z.object({ type: z.literal('Polygon'), coordinates: GeometryPolygonSchema }),
  z.object({ type: z.literal('MultiPolygon'), coordinates: z.array(GeometryPolygonSchema).min(1) }),
]);
export type FeatureGeometry = z.infer<typeof FeatureGeometrySchema>;

/** route 출발·도착 지점 (kor_travel_map `RouteEndpointOut`). */
export const RouteEndpointSchema = z.object({
  lon: z.number().finite().min(-180).max(180),
  lat: z.number().finite().min(-90).max(90),
  name: z.string().nullable().optional(),
});
export type RouteEndpoint = z.infer<typeof RouteEndpointSchema>;

/**
 * `kind=route` 요약 (kor_travel_map `RouteSummaryOut`, Map ADR-128).
 * 등산 코스(`hiking_course`)는 feature 좌표(`coord`)가 곧 `start`다 — 일정에 넣을 때 그 좌표를 쓴다.
 * `duration_basis='estimated'`이면 화면에 "추정"을 표시한다.
 */
export const RouteSummarySchema = z.object({
  route_type: z.string(),
  length_m: z.number().nonnegative().nullable().optional().catch(null),
  duration_minutes: z.number().int().nonnegative().nullable().optional().catch(null),
  duration_basis: z.enum(['source', 'estimated']).nullable().optional().catch(null),
  difficulty: z.string().nullable().optional().catch(null),
  shape: z.enum(['path', 'loop', 'network']).nullable().optional().catch(null),
  start: RouteEndpointSchema.nullable().optional().catch(null),
  end: RouteEndpointSchema.nullable().optional().catch(null),
});
export type RouteSummary = z.infer<typeof RouteSummarySchema>;

export const FeatureSummarySchema = z.object({
  feature_id: FeatureIdSchema,
  kind: FeatureKindSchema,
  name: z.string(),
  coord: CoordSchema.nullable(),
  // Map 카테고리 코드(필터·마커 계약). 화면 표시는 `category_label`만 쓴다.
  category: z.string().nullable().optional(),
  category_label: z.string().nullable().optional(),
  marker_color: MarkerColorSchema,
  marker_icon: z.string().max(64),
  distance_m: z.number().nullable().optional(),
  // 도형 하나가 계약을 어기면 그 도형만 비운다 — 응답 전체(다른 경로·영역)를 버리지 않는다.
  geometry: FeatureGeometrySchema.nullable().optional().catch(null),
  // 요약이 계약을 어기면 요약만 비운다 — 목록 항목 자체는 살린다.
  route: RouteSummarySchema.nullable().optional().catch(null),
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
  truncated: z.boolean().optional(),
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
  category_label: z.string().nullable().optional(),
  address: z.record(z.string(), z.unknown()).nullable().optional(),
  legal_dong_code: z.string().nullable().optional(),
  sido_code: z.string().nullable().optional(),
  sigungu_code: z.string().nullable().optional(),
  marker_color: MarkerColorSchema,
  marker_icon: z.string().max(64),
  urls: z.record(z.string(), z.unknown()),
  detail: z.record(z.string(), z.unknown()),
  route: RouteSummarySchema.nullable().optional().catch(null),
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

/** 장소를 덮는 Map 공개 구역 1건(국립공원·보호지역·위험지역). 작은 면 먼저. */
export const ContainingAreaSchema = z.object({
  feature_id: z.string().min(1).max(200),
  name: z.string().min(1).max(200),
  area_kind: z.string().min(1).max(64),
  /** 지정 종류 표시 이름(도립·군립공원·명승…). 모르면 null. */
  category_label: z.string().max(200).nullable().default(null),
});
export type ContainingArea = z.infer<typeof ContainingAreaSchema>;

// kind별 detail-card 공통 필드(일반 사용자 노출용). 원본 detail/urls dict는 노출하지 않는다.
const detailCardBase = {
  feature_id: z.string().min(1).max(200),
  name: z.string(),
  coord: CoordSchema.nullable().default(null),
  category: z.string().nullable().default(null),
  category_label: z.string().nullable().default(null),
  address_line: z.string().nullable().default(null),
  marker_color: z.string().default('P-13'),
  marker_icon: z.string().default('marker'),
  homepage_url: z.string().nullable().default(null),
  enrichment: z.array(ExternalEnrichmentSchema).default([]),
  degraded_providers: z.array(z.string()).default([]),
  containing_areas: z.array(ContainingAreaSchema).default([]),
};

/**
 * 공공누리 유형 0~4 — 3·4유형은 변경금지, 2·4유형은 상업적 이용금지(kogl.or.kr licenseType{N}).
 * 표시용, 응답 파싱에는 쓰지 않음 — 응답은 문자열/정수로 받는다(아래 관용 규칙).
 */
export const KoglTypeSchema = z.union([
  z.literal(0),
  z.literal(1),
  z.literal(2),
  z.literal(3),
  z.literal(4),
]);
export type KoglType = z.infer<typeof KoglTypeSchema>;

/**
 * 출처 소개·이용 안내를 만든 원천(Map `PlaceVisitorInfo.source`, ADR-126).
 * 표시용, 응답 파싱에는 쓰지 않음 — 응답은 문자열/정수로 받는다(아래 관용 규칙).
 */
export const IntroductionProviderSchema = z.enum([
  'tourapi',
  'krheritage',
  'datagokr_museum',
  'krforest_recreation_forest',
]);
export type IntroductionProvider = z.infer<typeof IntroductionProviderSchema>;

/*
 * 클라이언트 관용 규칙: 서버(또는 그 뒤의 Map)가 원천·공공누리 유형·무장애 분류·요금 대상을 늘려도 이미 깔린
 * 앱이 상세 카드 전체를 버리지 않도록, 열거 값은 문자열/정수로 받고 화면이 아는 값만 보인다. 블록
 * (`introduction`·`visit_guide`) 하나가 모양이 어긋나면 그 블록만 null이 된다(`.catch(null)`).
 */

/**
 * 출처 원본 이미지 1장 — 원본 URL 그대로(서버 가공·썸네일 없음). 공공누리 표시는 이미지마다 다르다.
 * no_derivatives(제3·4유형)면 크롭·필터 없이 원본 비율로만 그린다.
 */
export const SourceImageSchema = z.object({
  url: z.string().max(2048),
  alt: z.string().max(200),
  kogl_type: z.number().int(),
  no_derivatives: z.boolean(),
  license_label: z.string().max(100),
  license_url: z.string().max(200),
});
export type SourceImage = z.infer<typeof SourceImageSchema>;

/** 출처 장소 소개 — 소개문(평문, 줄바꿈 보존, 텍스트로만 그린다)·원본 이미지 갤러리·출처 표시. */
export const SourceIntroductionSchema = z.object({
  provider: z.string(),
  attribution: z.string().max(100),
  reference_date: z.string().nullable().default(null),
  overview: z.string().max(20000).nullable().default(null),
  images: z.array(SourceImageSchema).max(10).default([]),
  /** @deprecated #809 클라이언트 호환 — 첫 이미지의 공공누리 표시. `images[]`의 값을 쓴다. */
  kogl_type: z.number().int().nullable().default(null),
  /** @deprecated 첫 이미지의 `license_label`. */
  license_label: z.string().max(100).nullable().default(null),
  /** @deprecated 첫 이미지의 `license_url`. */
  license_url: z.string().max(200).nullable().default(null),
});
export type SourceIntroduction = z.infer<typeof SourceIntroductionSchema>;

/** 요금 대상 — 표시용, 응답 파싱에는 쓰지 않음 — 응답은 문자열/정수로 받는다(아래 관용 규칙). */
export const FeeAudienceSchema = z.enum(['adult', 'youth', 'child']);
export type FeeAudience = z.infer<typeof FeeAudienceSchema>;
/** 무장애 분류 — 표시용, 응답 파싱에는 쓰지 않음 — 응답은 문자열/정수로 받는다(아래 관용 규칙). */
export const AccessibilityGroupSchema = z.enum(['physical', 'visual', 'hearing', 'infant_family']);
export type AccessibilityGroup = z.infer<typeof AccessibilityGroupSchema>;

/** 구조화 요금 1건 — 0원은 무료. */
export const VisitFeeSchema = z.object({
  audience: z.string(),
  amount_krw: z.number().int().min(0).max(10_000_000),
});
export type VisitFee = z.infer<typeof VisitFeeSchema>;

/** 무장애 안내 1항목 — label은 시설 한글 이름, text는 원천 문장 그대로. */
export const AccessibilityItemSchema = z.object({
  group: z.string(),
  facility: z.string().regex(/^[a-z_]{1,64}$/),
  label: z.string().max(2000),
  text: z.string().max(2000),
});
export type AccessibilityItem = z.infer<typeof AccessibilityItemSchema>;

export const VisitPetPolicySchema = z.object({
  companion_type: z.string().max(2000).nullable().default(null),
  allowed_pets: z.string().max(2000).nullable().default(null),
  requirements: z.string().max(2000).nullable().default(null),
  notes: z.string().max(2000).nullable().default(null),
});
export type VisitPetPolicy = z.infer<typeof VisitPetPolicySchema>;

const guideText = z.string().max(2000).nullable().default(null);

/**
 * 이용 안내(Map visitor_info 투영) — 이용시간·휴무·주차·요금·무장애·반려동물. 문장은 원천 문장 그대로의
 * 평문이며 텍스트로만 그린다. 배지는 accessibility 비지 않음·pet_policy 있음으로만 판단한다.
 */
export const VisitGuideSchema = z.object({
  provider: z.string(),
  attribution: z.string().max(100),
  reference_date: z.string().nullable().default(null),
  usage_hours: guideText,
  rest_days: guideText,
  parking: guideText,
  parking_fee: guideText,
  fees: z.array(VisitFeeSchema).max(3).default([]),
  fee_text: guideText,
  discount: guideText,
  reservation: guideText,
  inquiry: guideText,
  transport: guideText,
  facilities: guideText,
  capacity: guideText,
  accommodation_available: z.boolean().nullable().default(null),
  pet_note: guideText,
  accessibility: z.array(AccessibilityItemSchema).max(40).default([]),
  pet_policy: VisitPetPolicySchema.nullable().default(null),
});
export type VisitGuide = z.infer<typeof VisitGuideSchema>;

export const PlaceDetailCardSchema = z.object({
  ...detailCardBase,
  kind: z.literal('place'),
  phone: z.string().nullable().default(null),
  business_hours: z.string().nullable().default(null),
  introduction: SourceIntroductionSchema.nullable().default(null).catch(null),
  visit_guide: VisitGuideSchema.nullable().default(null).catch(null),
});
export const EventDetailCardSchema = z.object({
  ...detailCardBase,
  kind: z.literal('event'),
  start_date: z.string().nullable().default(null),
  end_date: z.string().nullable().default(null),
  venue: z.string().nullable().default(null),
  introduction: SourceIntroductionSchema.nullable().default(null).catch(null),
  visit_guide: VisitGuideSchema.nullable().default(null).catch(null),
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
  provider: z.string().nullable().optional(),
  weather_domain: z.string().nullable().optional(),
  valid_at: Iso8601Schema.nullable().optional(),
  valid_from: Iso8601Schema.nullable().optional(),
  valid_until: Iso8601Schema.nullable().optional(),
  effective_at: Iso8601Schema.nullable().optional(),
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

export const FeatureWeatherResolutionSchema = z.discriminatedUnion('state', [
  z.object({ state: z.literal('found'), card: FeatureWeatherCardSchema }),
  z.object({ state: z.literal('no_data') }),
  z.object({ state: z.literal('retired') }),
  z.object({ state: z.literal('suppressed') }),
  z.object({ state: z.literal('missing') }),
  z.object({ state: z.literal('unavailable') }),
]);
export type FeatureWeatherResolution = z.infer<typeof FeatureWeatherResolutionSchema>;

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

/** Feature 요청 큐 등록 (Admin 검토 뒤 신규 장소는 Map 범용 요청 큐로 제출). */
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
    // 좌표 출처(T-329). 기본은 지도에서 고른 지점 — 이 다이얼로그의 실사용 흐름이 그렇다.
    // (`source`는 provider 출처라 이름이 겹치지 않게 `coord_source`로 둔다.)
    coord_source: CoordSourceSchema.optional().default('map_pick'),
  })
  .refine((v) => v.type === 'new_place' || v.target_feature_id != null, {
    message: 'correction/closure 제안은 target_feature_id가 필요합니다.',
    path: ['target_feature_id'],
  })
  .refine((v) => v.type !== 'new_place' || v.target_feature_id == null, {
    message: 'new_place 제안은 target_feature_id를 가질 수 없습니다.',
    path: ['target_feature_id'],
  })
  .refine((v) => v.type !== 'new_place' || v.coord.lat <= 39.5, {
    message: 'new_place 제안 좌표의 lat은 39.5 이하여야 합니다.',
    path: ['coord', 'lat'],
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
