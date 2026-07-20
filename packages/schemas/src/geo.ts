import { z } from 'zod';

/** kor-travel-geo v2 candidate는 풍부/가변이라 pass-through(record). 좌표는 (lon, lat). */
const CandidateSchema = z.record(z.string(), z.unknown());

export const BoundaryLevelSchema = z.enum(['sido', 'sigungu', 'legal_dong']);
export type BoundaryLevel = z.infer<typeof BoundaryLevelSchema>;

export const GeoSearchKindSchema = z.enum(['address', 'place', 'district', 'road', 'category']);
export type GeoSearchKind = z.infer<typeof GeoSearchKindSchema>;

/** `/geo/{geocode,reverse,search}` + `/regions/within-radius` 공통 응답. */
export const GeoCandidateListSchema = z.object({
  status: z.string(),
  candidates: z.array(CandidateSchema),
  total: z.number().int().nullable().optional(),
});
export type GeoCandidateList = z.infer<typeof GeoCandidateListSchema>;

/** `/regions/covering-point` 단건 행정구역. */
export const RegionCoveringSchema = z.object({
  boundary_level: BoundaryLevelSchema,
  region: CandidateSchema,
});
export type RegionCovering = z.infer<typeof RegionCoveringSchema>;

/** 통합 검색 결과 소스 태그(ADR-054). internal(feature/my_poi/address) + 외부(kakao/naver). */
export const PlaceSearchSourceSchema = z.enum(['feature', 'my_poi', 'address', 'kakao', 'naver']);
export type PlaceSearchSource = z.infer<typeof PlaceSearchSourceSchema>;

export const PlaceCoordSchema = z.object({ lon: z.number(), lat: z.number() });
export type PlaceCoord = z.infer<typeof PlaceCoordSchema>;

/**
 * `GET /search`의 한 행. source에 따라 채워지는 필드가 다르다. kakao/naver row의 phone/category
 * 등 provider 파생 콘텐츠는 표시 전용이며 저장 대상은 external_ref뿐이다(ADR-054 §7).
 */
export const PlaceSearchResultSchema = z.object({
  source: PlaceSearchSourceSchema,
  name: z.string(),
  coord: PlaceCoordSchema.nullable().default(null),
  feature_id: z.string().nullable().default(null),
  poi_id: z.string().nullable().default(null),
  trip_id: z.string().nullable().default(null),
  trip_title: z.string().nullable().default(null),
  external_id: z.string().nullable().default(null),
  address: z.string().nullable().default(null),
  road_address: z.string().nullable().default(null),
  category: z.string().nullable().default(null),
  marker_color: z.string().nullable().default(null),
  marker_icon: z.string().nullable().default(null),
  provider_url: z.string().nullable().default(null),
  phone: z.string().nullable().default(null),
});
export type PlaceSearchResult = z.infer<typeof PlaceSearchResultSchema>;

/** `GET /search` 응답 — internal → kakao → naver 순 정렬 + 소스별 degrade. */
export const PlaceSearchResponseSchema = z.object({
  results: z.array(PlaceSearchResultSchema),
  degraded_sources: z.array(z.string()),
});
export type PlaceSearchResponse = z.infer<typeof PlaceSearchResponseSchema>;
