import { describe, expect, it } from 'vitest';
import { TripViewDaySchema } from './trip';

const weatherCard = {
  asof: '2026-07-30T00:00:00+09:00',
  latest_at: null,
  is_stale: false,
  source_styles: ['short'],
  metrics: [],
};

function dayWeather(
  weatherCards: Record<string, typeof weatherCard>,
  weatherByFeatureId: Record<string, { state: 'found'; card_key: string }>,
) {
  return {
    day_index: 1,
    date: '2026-07-30',
    title: null,
    version: 1,
    weather_cards: weatherCards,
    weather_by_feature_id: weatherByFeatureId,
    pois: [],
  };
}

describe('TripViewDaySchema weather partition', () => {
  it('여러 feature가 같은 일자 card를 공유한다', () => {
    const parsed = TripViewDaySchema.parse(
      dayWeather(
        { 'card:seoul': weatherCard },
        {
          'weather:a': { state: 'found', card_key: 'card:seoul' },
          'weather:b': { state: 'found', card_key: 'card:seoul' },
        },
      ),
    );

    expect(Object.keys(parsed.weather_cards)).toEqual(['card:seoul']);
  });

  it.each([
    dayWeather({}, { 'weather:a': { state: 'found', card_key: 'card:missing' } }),
    dayWeather({ 'card:orphan': weatherCard }, {}),
  ])('누락되거나 고아인 card를 거부한다', (value) => {
    expect(() => TripViewDaySchema.parse(value)).toThrow(/weather card 참조 집합 불일치/);
  });
});
