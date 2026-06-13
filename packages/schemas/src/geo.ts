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

/** `GET /search` 통합 결과 — feature + address + 내 POI(소스별 degrade 가능). */
export const UnifiedSearchResultSchema = z.object({
  features: z.array(CandidateSchema),
  addresses: z.array(CandidateSchema),
  my_pois: z.array(CandidateSchema),
  degraded_sources: z.array(z.string()),
});
export type UnifiedSearchResult = z.infer<typeof UnifiedSearchResultSchema>;
