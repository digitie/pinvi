import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { POI_WEATHER_MAX_CONCURRENT, createPoiWeatherStore } from '@pinvi/hooks';

/** 장소별 날씨 공유 캐시(웹·모바일 공용 `createPoiWeatherStore`) — 요청을 묶는 규칙. */
function deferredLoader() {
  const calls: { key: string; resolve: (card: string) => void }[] = [];
  const loader = vi.fn(
    (tripId: string, poiId: string) =>
      new Promise<string>((resolve) => calls.push({ key: `${tripId}/${poiId}`, resolve })),
  );
  return { calls, loader };
}

describe('createPoiWeatherStore', () => {
  it('동시 요청은 2건까지, 끝나면 다음 장소를 보낸다', async () => {
    const { calls, loader } = deferredLoader();
    const store = createPoiWeatherStore(loader);
    const pois = ['a', 'b', 'c', 'd'];
    const hooks = pois.map((poi) => renderHook(() => store.usePoiWeather('t', poi)));
    expect(POI_WEATHER_MAX_CONCURRENT).toBe(2);
    expect(calls.map((c) => c.key)).toEqual(['t/a', 't/b']);
    await act(async () => calls[0]!.resolve('card-a'));
    await waitFor(() => expect(calls.map((c) => c.key)).toEqual(['t/a', 't/b', 't/c']));
    expect(hooks[0]!.result.current).toMatchObject({ status: 'ready', card: 'card-a' });
  });

  it('같은 장소는 한 번만 받아 나눠 쓰고, 장소를 모르면 요청하지 않는다', async () => {
    const { calls, loader } = deferredLoader();
    const store = createPoiWeatherStore(loader);
    const first = renderHook(() => store.usePoiWeather('t', 'a'));
    const second = renderHook(() => store.usePoiWeather('t', 'a'));
    renderHook(() => store.usePoiWeather('t', null));
    expect(loader).toHaveBeenCalledTimes(1);
    await act(async () => calls[0]!.resolve('card-a'));
    await waitFor(() => expect(second.result.current).toMatchObject({ card: 'card-a' }));
    expect(first.result.current).toMatchObject({ card: 'card-a' });
  });

  it('지도 마커의 읽기(peek)는 요청을 만들지 않고, 받은 카드가 오면 다시 그린다', async () => {
    const { calls, loader } = deferredLoader();
    const store = createPoiWeatherStore(loader);
    const peek = renderHook(() => store.usePoiWeatherPeekAll());
    expect(peek.result.current('t', 'a')).toBeNull();
    expect(loader).not.toHaveBeenCalled();

    renderHook(() => store.usePoiWeather('t', 'a'));
    await act(async () => calls[0]!.resolve('card-a'));
    await waitFor(() => expect(peek.result.current('t', 'a')).toBe('card-a'));
    expect(loader).toHaveBeenCalledTimes(1);
  });
});
