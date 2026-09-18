import { z } from 'zod';
import { BBoxSchema } from './feature';
import { CoordSchema } from './common';

/**
 * 지도 weather marker — `kor-travel-weather` 직접 노출 (ADR-068, T-368).
 *
 * feature가 아니다. `FeatureKindSchema`/`FeatureSummarySchema`와는 완전히 분리된
 * 스키마다 — T-363 trip view가 확립한 "완전 분리" 원칙을 지도 marker 표면에
 * 적용한 결과다.
 */
export const WeatherConditionSchema = z.enum(['sunny', 'cloudy', 'rainy', 'snowy']);
export type WeatherCondition = z.infer<typeof WeatherConditionSchema>;

export const WeatherMapMarkerSchema = z.object({
  location_id: z.string().min(1).max(200),
  name: z.string(),
  coord: CoordSchema,
  temperature_c: z.number(),
  condition: WeatherConditionSchema,
  provider: z.string().nullable().optional(),
});
export type WeatherMapMarker = z.infer<typeof WeatherMapMarkerSchema>;

/** viewport 응답 — `GET /weather/markers-in-bounds`. */
export const WeatherMarkersInBoundsResponseSchema = z.object({
  items: z.array(WeatherMapMarkerSchema),
  zoom: z.number().int().min(5).max(19),
  bbox: BBoxSchema,
});
export type WeatherMarkersInBoundsResponse = z.infer<typeof WeatherMarkersInBoundsResponseSchema>;
