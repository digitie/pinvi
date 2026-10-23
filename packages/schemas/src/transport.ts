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
  brand_name: optionalText,
  phone: optionalText,
  is_self: optionalBool,
  is_24h: optionalBool,
  has_carwash: optionalBool,
  has_cvs: optionalBool,
  has_maintenance: optionalBool,
  lpg_available: optionalBool,
  prices: z.array(FuelPriceSchema),
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

/** `GET /transport/{fuel-stations|rest-areas|highway-incidents|airports}/{feature_id}`. */
export const TransportDetailResponseSchema = z.object({
  item: TransportItemSchema,
  freshness: TransportFreshnessSchema,
  fuel_price_freshness: TransportFreshnessSchema.nullable().optional(),
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
