import { z } from 'zod';
import { BBoxSchema } from './feature';
import { Iso8601Schema } from './common';

/**
 * 지도 transport 레이어 — Map `/v1/service/transport/*` 투영 (ADR-076).
 *
 * feature가 아니다. `feature_id`는 Map `make_feature_id` 값이라 POI·feature 상세가 쓰는 Map PG
 * feature UUID와 다른 이름공간이다 — `featureApi`·POI 추가로 흘려보내지 않는다(ADR-076 D7).
 */
export const TransportLayerSchema = z.enum([
  'fuel_station',
  'rest_area',
  'highway_incident',
  'airport',
]);
export type TransportLayer = z.infer<typeof TransportLayerSchema>;

export const TransportUnavailableReasonSchema = z.enum([
  'NOT_LOADED',
  'STORE_UNAVAILABLE',
  'UPSTREAM_UNAVAILABLE',
  'UPSTREAM_AUTH',
  'UPSTREAM_REJECTED',
  'UPSTREAM_CONTRACT',
]);
export type TransportUnavailableReason = z.infer<typeof TransportUnavailableReasonSchema>;

export const TransportFreshnessSchema = z.object({
  source_collected_at: Iso8601Schema.nullable(),
  loaded_at: Iso8601Schema,
  age_seconds: z.number().int(),
  max_age_seconds: z.number().int(),
  stale: z.boolean(),
});
export type TransportFreshness = z.infer<typeof TransportFreshnessSchema>;

const TransportCoordSchema = z.object({ lon: z.number(), lat: z.number() });
const TransportAddressSchema = z.object({
  road: z.string().nullable().optional(),
  jibun: z.string().nullable().optional(),
});
export type TransportAddress = z.infer<typeof TransportAddressSchema>;

export const FuelPriceSchema = z.object({
  product_key: z.string(),
  product_code: z.string(),
  product_name: z.string().nullable().optional(),
  price: z.number().nullable(),
  collected_at: Iso8601Schema,
  provider_updated_at: Iso8601Schema.nullable().optional(),
});
export type FuelPrice = z.infer<typeof FuelPriceSchema>;

const ItemBase = {
  feature_id: z.string().min(1).max(128),
  category: z.string(),
  marker_icon: z.string(),
  marker_color: z.string(),
  coord: TransportCoordSchema.nullable(),
  distance_m: z.number().nullable().optional(),
};

const optionalBool = z.boolean().nullable().optional();
const optionalText = z.string().nullable().optional();

export const FuelStationItemSchema = z.object({
  ...ItemBase,
  layer: z.literal('fuel_station'),
  name: z.string(),
  address: TransportAddressSchema,
  /** 오피넷 상표 코드(SKE·GSC·HDO·SOL…). 로고 선택에 쓴다 — 이름보다 우선한다. */
  brand_code: optionalText,
  brand_name: optionalText,
  phone: optionalText,
  is_self: optionalBool,
  is_24h: optionalBool,
  has_carwash: optionalBool,
  has_cvs: optionalBool,
  has_maintenance: optionalBool,
  lpg_available: optionalBool,
  prices: z.array(FuelPriceSchema),
  /** transport가 이 주유소(기준정보)를 원천에서 마지막으로 본 시각 — "기준정보 반영". */
  source_last_seen_at: Iso8601Schema.nullable().optional(),
});
export type FuelStationItem = z.infer<typeof FuelStationItemSchema>;

export const RestAreaFuelPricesSchema = z.object({
  gasoline_price: z.number().int().nullable().optional(),
  diesel_price: z.number().int().nullable().optional(),
  lpg_price: z.number().int().nullable().optional(),
  oil_company: optionalText,
  observed_at: Iso8601Schema,
});
export type RestAreaFuelPrices = z.infer<typeof RestAreaFuelPricesSchema>;

export const RestAreaItemSchema = z.object({
  ...ItemBase,
  layer: z.literal('rest_area'),
  name: z.string(),
  address: TransportAddressSchema,
  route_name: optionalText,
  direction: optionalText,
  phone: optionalText,
  has_gas_station: optionalBool,
  has_lpg_station: optionalBool,
  has_ev_charger: optionalBool,
  fuel_prices: RestAreaFuelPricesSchema.nullable().optional(),
});
export type RestAreaItem = z.infer<typeof RestAreaItemSchema>;

export const HighwayIncidentItemSchema = z.object({
  ...ItemBase,
  layer: z.literal('highway_incident'),
  title: z.string(),
  message: optionalText,
  incident_type: optionalText,
  process_status: optionalText,
  /** 고속도로 노선 번호("0010"). transport처럼 "0010 · 경부선"으로 보인다. */
  route_no: optionalText,
  route_name: optionalText,
  direction: optionalText,
  point_name: optionalText,
  congestion_length: z.number().nullable().optional(),
  occurred_at: Iso8601Schema.nullable().optional(),
});
export type HighwayIncidentItem = z.infer<typeof HighwayIncidentItemSchema>;

export const AirportItemSchema = z.object({
  ...ItemBase,
  layer: z.literal('airport'),
  name: z.string(),
  name_english: z.string(),
  iata_code: z.string(),
  icao_code: optionalText,
  municipality: optionalText,
  address: TransportAddressSchema,
});
export type AirportItem = z.infer<typeof AirportItemSchema>;

export const TransportItemSchema = z.discriminatedUnion('layer', [
  FuelStationItemSchema,
  RestAreaItemSchema,
  HighwayIncidentItemSchema,
  AirportItemSchema,
]);
export type TransportItem = z.infer<typeof TransportItemSchema>;

export const TransportLayerResultSchema = z.object({
  layer: TransportLayerSchema,
  status: z.enum(['ok', 'unavailable', 'disabled']),
  reason: TransportUnavailableReasonSchema.nullable().optional(),
  freshness: TransportFreshnessSchema.nullable().optional(),
  fuel_price_freshness: TransportFreshnessSchema.nullable().optional(),
  truncated: z.boolean(),
  items: z.array(TransportItemSchema),
});
export type TransportLayerResult = z.infer<typeof TransportLayerResultSchema>;

/** `GET /transport/markers-in-bounds`. */
export const TransportMarkersInBoundsResponseSchema = z.object({
  bbox: BBoxSchema,
  zoom: z.number().int(),
  layers: z.array(TransportLayerResultSchema),
});
export type TransportMarkersInBoundsResponse = z.infer<
  typeof TransportMarkersInBoundsResponseSchema
>;

/** `GET /transport/markers-near` — 여행 장소 반경(주유소 10 km·교통 돌발 20 km). */
export const TransportMarkersNearResponseSchema = z.object({
  radius_m: z.partialRecord(TransportLayerSchema, z.number().int()),
  layers: z.array(TransportLayerResultSchema),
});
export type TransportMarkersNearResponse = z.infer<typeof TransportMarkersNearResponseSchema>;

export const TransportLayerStatusSchema = z.object({
  layer: TransportLayerSchema,
  available: z.boolean(),
  reason: TransportUnavailableReasonSchema.nullable().optional(),
  freshness: TransportFreshnessSchema.nullable().optional(),
});
export type TransportLayerStatus = z.infer<typeof TransportLayerStatusSchema>;

/** `GET /transport/status` — `enabled=false`면 레이어 컨트롤을 숨긴다. */
export const TransportStatusResponseSchema = z.object({
  enabled: z.boolean(),
  layers: z.array(TransportLayerStatusSchema),
});
export type TransportStatusResponse = z.infer<typeof TransportStatusResponseSchema>;

/** 휴게소 메뉴 하나(한국도로공사 0502, Map ADR-127). */
export const RestAreaMenuItemSchema = z.object({
  name: z.string(),
  price: z.number().int().nullable().optional(),
  tags: z.array(z.enum(['best', 'premium', 'recommended'])).default([]),
  season: z.enum(['all_year', 'summer', 'winter']).nullable().optional(),
});
export type RestAreaMenuItem = z.infer<typeof RestAreaMenuItemSchema>;

/**
 * 휴게소 먹거리 요약 — 한국도로공사 원천 데이터(LLM 요약 아님). 주유소 상세에서는 같은 방향 휴게소의
 * 값이고 `paired_distance_m`이 채워진다.
 */
export const RestAreaFoodSchema = z.object({
  rest_area_name: z.string(),
  std_rest_code: z.string(),
  route_name: optionalText,
  menu_count: z.number().int().nonnegative(),
  price_min: z.number().int().nullable().optional(),
  price_median: z.number().int().nullable().optional(),
  price_max: z.number().int().nullable().optional(),
  featured: z.array(RestAreaMenuItemSchema).default([]),
  seasonal: z.array(RestAreaMenuItemSchema).default([]),
  menu_updated_on: optionalText,
  source_collected_at: Iso8601Schema,
  attribution: z.string().default('한국도로공사'),
  paired_distance_m: z.number().nullable().optional(),
});
export type RestAreaFood = z.infer<typeof RestAreaFoodSchema>;

/** `GET /transport/{fuel-stations|rest-areas|highway-incidents|airports}/{feature_id}`. */
export const TransportDetailResponseSchema = z.object({
  item: TransportItemSchema,
  freshness: TransportFreshnessSchema,
  fuel_price_freshness: TransportFreshnessSchema.nullable().optional(),
  food: RestAreaFoodSchema.nullable().optional(),
});
export type TransportDetailResponse = z.infer<typeof TransportDetailResponseSchema>;

export const FuelPriceHistoryPointSchema = z.object({
  product_key: z.string(),
  product_name: z.string().nullable().optional(),
  price: z.number().nullable(),
  observed_at: Iso8601Schema,
});
export type FuelPriceHistoryPoint = z.infer<typeof FuelPriceHistoryPointSchema>;

/** `GET /transport/fuel-stations/{feature_id}/price-history`. `unavailable`은 오류가 아니다. */
export const FuelPriceHistoryResponseSchema = z.object({
  feature_id: z.string(),
  status: z.enum(['available', 'unavailable']),
  reason: z.string().nullable().optional(),
  truncated: z.boolean(),
  items: z.array(FuelPriceHistoryPointSchema),
  current_prices: z.array(FuelPriceSchema),
  freshness: TransportFreshnessSchema,
});
export type FuelPriceHistoryResponse = z.infer<typeof FuelPriceHistoryResponseSchema>;
