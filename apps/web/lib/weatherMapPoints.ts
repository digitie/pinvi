import type { WeatherMarkersInBoundsResponse } from '@pinvi/schemas';
import type { ClusterPoint, WeatherCondition } from '@/components/map/vworldPrimitives';
export type WeatherMapPoint = ClusterPoint & {
  kind: 'weather';
  locationId: string;
  title: string;
  temperatureC: number;
  condition: WeatherCondition;
  provider: string | null;
};

export function toWeatherPoints(data: WeatherMarkersInBoundsResponse): WeatherMapPoint[] {
  return data.items.map((m) => ({
    id: `weather:${m.location_id}`,
    lngLat: [m.coord.lon, m.coord.lat] as [number, number],
    kind: 'weather' as const,
    locationId: m.location_id,
    title: m.name,
    temperatureC: m.temperature_c,
    condition: m.condition,
    provider: m.provider ?? null,
  }));
}
