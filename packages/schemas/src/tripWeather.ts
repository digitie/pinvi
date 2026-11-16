import { z } from 'zod';

// 일정 화면 날씨 새로고침(2026-11-16 소유자 요청 15) — `POST /trips/{id}/days/{n}/weather/refresh`.
// 백엔드 정본: apps/api/app/schemas/trip_weather.py.
export const TripWeatherRefreshRequestSchema = z.object({
  poi_id: z.string().uuid().nullable().optional(),
});
export type TripWeatherRefreshRequest = z.infer<typeof TripWeatherRefreshRequestSchema>;

export const TripWeatherRefreshResponseSchema = z.object({
  trip_id: z.string().uuid(),
  day_index: z.number().int(),
  refreshed: z.number().int().nonnegative(),
  cooldown: z.number().int().nonnegative(),
  no_data: z.number().int().nonnegative(),
  failed: z.number().int().nonnegative(),
  skipped: z.number().int().nonnegative(),
  retry_after_seconds: z.number().int().positive().nullable().default(null),
});
export type TripWeatherRefreshResponse = z.infer<typeof TripWeatherRefreshResponseSchema>;
