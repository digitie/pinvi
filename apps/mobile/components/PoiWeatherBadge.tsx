import { useMemo } from 'react';
import { Text, View } from 'react-native';
import { useMinuteNow } from '@pinvi/hooks';
import { conditionLabel, currentWeather, formatTemp, todayRange } from '@pinvi/domain';
import type { FeatureWeatherCard } from '@pinvi/schemas';
import { usePoiWeather } from '../lib/poiWeather';
import { WeatherIcon } from './WeatherIcon';

/** 아이콘 + 현재 기온 + 오늘 최고/최저(웹 `WeatherBadge` 대응). 보일 값이 없으면 아무것도 그리지 않는다. */
export function WeatherBadge({ card }: { card: FeatureWeatherCard | null }) {
  const now = useMinuteNow();
  const current = useMemo(() => (now ? currentWeather(card, now) : null), [card, now]);
  const range = useMemo(() => (now ? todayRange(card, now) : null), [card, now]);
  if (!current) return null;
  const label = [
    `현재 ${conditionLabel(current.condition)}`,
    current.temp != null ? `${Math.round(current.temp)}도` : null,
    range ? `최고 ${Math.round(range.max)}도 최저 ${Math.round(range.min)}도` : null,
  ]
    .filter(Boolean)
    .join(', ');
  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel={label}
      testID="weather-badge"
      className="flex-row items-center gap-1 self-start"
    >
      <WeatherIcon condition={current.condition} night={current.night} size={14} />
      <Text className="text-xs font-semibold text-ink">{formatTemp(current.temp)}</Text>
      {range ? (
        <Text className="text-xs text-muted">
          {formatTemp(range.max)}/{formatTemp(range.min)}
        </Text>
      ) : null}
    </View>
  );
}

/**
 * 여행 장소 하나의 현재 날씨 배지 — `GET /trips/{id}/pois/{poi}/weather`를 공유 캐시로(동시 2건) 받는다.
 * 좌표를 모르는 장소는 부르지 않는다(`poiId=null`).
 */
export function PoiWeatherBadge({ tripId, poiId }: { tripId: string; poiId: string | null }) {
  const weather = usePoiWeather(tripId, poiId);
  return <WeatherBadge card={'card' in weather ? weather.card : null} />;
}
