import { z } from 'zod';

/** `GET /users/me/home` — 개인 홈(내 여행·다녀온 장소·여행 통계). 정의는 API `services/user_home.py`. */
export const HomeTripPhaseSchema = z.enum(['ongoing', 'upcoming', 'undated', 'completed']);
export type HomeTripPhase = z.infer<typeof HomeTripPhaseSchema>;

export const HomeTripCardSchema = z.object({
  trip_id: z.string().uuid(),
  title: z.string(),
  region_hint: z.string().nullable(),
  region_name: z.string().nullable(),
  start_date: z.string().date().nullable(),
  end_date: z.string().date().nullable(),
  phase: HomeTripPhaseSchema,
  days_until: z.number().int().nullable(),
  place_count: z.number().int().nonnegative(),
  // 동행으로 참여한 여행(소유자가 아님). 이전 API 응답에는 없어 기본 false.
  joined: z.boolean().default(false),
});
export type HomeTripCard = z.infer<typeof HomeTripCardSchema>;

export const HomeVisitedPlaceSchema = z.object({
  poi_id: z.string().uuid(),
  trip_id: z.string().uuid(),
  trip_title: z.string(),
  name: z.string(),
  category: z.string().nullable(),
  visited_on: z.string().date(),
  region_name: z.string().nullable(),
});
export type HomeVisitedPlace = z.infer<typeof HomeVisitedPlaceSchema>;

export const HomeRegionStatSchema = z.object({
  code: z.string(),
  name: z.string(),
  place_count: z.number().int().nonnegative(),
  trip_count: z.number().int().nonnegative(),
});
export type HomeRegionStat = z.infer<typeof HomeRegionStatSchema>;

export const HomeStatsSchema = z.object({
  trip_count: z.number().int().nonnegative(),
  upcoming_trip_count: z.number().int().nonnegative(),
  ongoing_trip_count: z.number().int().nonnegative(),
  completed_trip_count: z.number().int().nonnegative(),
  undated_trip_count: z.number().int().nonnegative(),
  travel_day_count: z.number().int().nonnegative(),
  visited_place_count: z.number().int().nonnegative(),
  region_count: z.number().int().nonnegative(),
});
export type HomeStats = z.infer<typeof HomeStatsSchema>;

export const UserHomeSchema = z.object({
  today: z.string().date(),
  stats: HomeStatsSchema,
  next_trip: HomeTripCardSchema.nullable(),
  upcoming_trips: z.array(HomeTripCardSchema),
  recent_trips: z.array(HomeTripCardSchema),
  recent_places: z.array(HomeVisitedPlaceSchema),
  regions: z.array(HomeRegionStatSchema),
});
export type UserHome = z.infer<typeof UserHomeSchema>;
