import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { FeatureWeatherCard } from '@pinvi/schemas';
import {
  __resetPoiWeatherForTest,
  refreshPoiWeather,
  usePoiWeather,
  usePoiWeatherPeek,
} from '@/lib/usePoiWeather';

const card: FeatureWeatherCard = {
  feature_id: 'poi:p1',
  asof: null,
  latest_at: null,
  is_stale: false,
  source_styles: [],
  metrics: [],
};

afterEach(() => __resetPoiWeatherForTest());

describe('usePoiWeatherPeek(지도 마커 라벨용 — 요청을 만들지 않는다)', () => {
  it('혼자서는 아무것도 요청하지 않고, 목록 배지가 받은 카드를 나눠 쓴다', async () => {
    const loader = vi.fn(async () => card);
    __resetPoiWeatherForTest(loader);
    const peek = renderHook(() => usePoiWeatherPeek('t1', 'p1'));
    expect(peek.result.current).toBeNull();
    expect(loader).not.toHaveBeenCalled();

    // 목록 배지(usePoiWeather)가 같은 장소를 받으면 마커도 그 카드를 본다.
    const badge = renderHook(() => usePoiWeather('t1', 'p1'));
    await waitFor(() => expect(peek.result.current).toEqual(card));
    expect(loader).toHaveBeenCalledTimes(1);
    badge.unmount();
  });

  it('새로고침은 마커만 보고 있는 장소를 다시 받지 않는다', async () => {
    const loader = vi.fn(async () => card);
    __resetPoiWeatherForTest(loader);
    renderHook(() => usePoiWeatherPeek('t1', 'p2'));
    act(() => refreshPoiWeather('t1'));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(loader).not.toHaveBeenCalled();
  });
});
