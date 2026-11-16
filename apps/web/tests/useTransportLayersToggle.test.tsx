import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// #686 NEAR-024(mobile): 칩을 켜면 교통 패널이 자라 여행 지도가 다시 맞춰진다. 켠 순간의 bounds로 바로
// 조회하면 요청 bbox가 맞춘 뒤의 실제 지도와 다르다 — 켠 뒤 지도가 멈출 때까지 기다렸다가 조회한다.

const h = vi.hoisted(() => ({
  markersInBounds: vi.fn(),
  markersNear: vi.fn(),
}));

vi.mock('@pinvi/api-client', () => ({
  transportApi: () => ({
    status: () => Promise.resolve({ enabled: true }),
    markersInBounds: h.markersInBounds,
    markersNear: h.markersNear,
  }),
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));

import { useTransportLayers } from '@/lib/useTransportLayers';
import { toBboxParam } from '@/lib/featureBounds';
import type { MapLibreMap } from '@/components/map/vworldPrimitives';

function fakeMap(initial: [number, number, number, number]) {
  let box = initial;
  const map = {
    isMoving: () => false,
    getZoom: () => 9,
    getBounds: () => ({
      getWest: () => box[0],
      getSouth: () => box[1],
      getEast: () => box[2],
      getNorth: () => box[3],
    }),
    moveTo(next: [number, number, number, number]) {
      box = next;
    },
  };
  return map;
}

beforeEach(() => {
  vi.useFakeTimers();
  h.markersInBounds.mockReset();
  h.markersInBounds.mockResolvedValue({ zoom: 9, layers: [] });
  h.markersNear.mockReset();
  h.markersNear.mockResolvedValue({
    radius_m: { fuel_station: 10000 },
    layers: [{ layer: 'fuel_station', status: 'ok', truncated: false, items: [] }],
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useTransportLayers 칩 토글 조회 시점', () => {
  it('켠 직후 지도가 다시 맞춰지면 맞춘 뒤의 bounds로 한 번만 조회한다', async () => {
    const { result } = renderHook(() => useTransportLayers({ active: true }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.visible).toBe(true);
    const map = fakeMap([128.0, 36.0, 129.0, 37.0]);
    act(() => {
      result.current.onViewportChange(map as unknown as MapLibreMap);
      vi.advanceTimersByTime(300);
    });
    h.markersInBounds.mockClear();

    act(() => {
      result.current.toggle('highway_incident');
    });
    // 패널이 자라 맞춤이 다시 돌았다(moveend → onViewportChange).
    act(() => {
      map.moveTo([128.2, 36.1, 129.2, 37.3]);
      result.current.onViewportChange(map as unknown as MapLibreMap);
    });
    await act(async () => {
      vi.advanceTimersByTime(300);
      await Promise.resolve();
    });

    expect(h.markersInBounds).toHaveBeenCalledTimes(1);
    expect(h.markersInBounds.mock.calls[0]?.[0].bbox).toBe(toBboxParam(128.2, 36.1, 129.2, 37.3, 3));
    expect(h.markersInBounds.mock.calls[0]?.[0].layers).toEqual(['highway_incident']);
  });

  it('켠 뒤 지도가 움직이지 않으면 잠시 뒤 지금 bounds로 조회한다', async () => {
    const { result } = renderHook(() => useTransportLayers({ active: true }));
    await act(async () => {
      await Promise.resolve();
    });
    const map = fakeMap([128.0, 36.0, 129.0, 37.0]);
    act(() => {
      result.current.onViewportChange(map as unknown as MapLibreMap);
      vi.advanceTimersByTime(300);
    });
    h.markersInBounds.mockClear();
    act(() => {
      result.current.toggle('highway_incident');
    });
    await act(async () => {
      vi.advanceTimersByTime(300);
      await Promise.resolve();
    });
    expect(h.markersInBounds).toHaveBeenCalledTimes(1);
    expect(h.markersInBounds.mock.calls[0]?.[0].bbox).toBe(toBboxParam(128.0, 36.0, 129.0, 37.0, 3));
  });
});

describe('useTransportLayers 여행 장소 반경 모드', () => {
  const TRIP = [
    { lon: 128.5, lat: 37.1 },
    { lon: 128.6, lat: 37.2 },
  ];

  it('켠 레이어를 여행 장소 반경으로 조회하고 지도 이동으로는 다시 조회하지 않는다', async () => {
    const { result } = renderHook(() => useTransportLayers({ active: true, nearPoints: TRIP }));
    await act(async () => {
      await Promise.resolve();
    });
    const map = fakeMap([128.0, 36.0, 129.0, 37.0]);
    act(() => {
      result.current.onViewportChange(map as unknown as MapLibreMap);
      vi.advanceTimersByTime(300);
    });
    expect(h.markersNear).not.toHaveBeenCalled();

    act(() => {
      result.current.toggle('fuel_station');
    });
    await act(async () => {
      vi.advanceTimersByTime(300);
      await Promise.resolve();
    });
    expect(h.markersNear).toHaveBeenCalledTimes(1);
    expect(h.markersNear.mock.calls[0]?.[0]).toMatchObject({
      points: TRIP,
      layers: ['fuel_station'],
    });
    expect(h.markersInBounds).not.toHaveBeenCalled();
    expect(result.current.nearMode).toBe(true);
    expect(result.current.radiusM).toEqual({ fuel_station: 10000 });

    // 지도를 옮겨도(맞춤·팬) 반경 결과는 그대로다.
    act(() => {
      map.moveTo([127.0, 35.0, 128.0, 36.0]);
      result.current.onViewportChange(map as unknown as MapLibreMap);
      vi.advanceTimersByTime(300);
    });
    expect(h.markersNear).toHaveBeenCalledTimes(1);
  });

  it('여행 장소가 바뀌면(값) 다시 조회하고, 같은 값의 새 배열이면 조회하지 않는다', async () => {
    const { result, rerender } = renderHook(
      ({ points }) => useTransportLayers({ active: true, nearPoints: points }),
      { initialProps: { points: TRIP } },
    );
    await act(async () => {
      await Promise.resolve();
    });
    act(() => {
      result.current.toggle('fuel_station');
    });
    await act(async () => {
      vi.advanceTimersByTime(300);
      await Promise.resolve();
    });
    expect(h.markersNear).toHaveBeenCalledTimes(1);
    rerender({ points: TRIP.map((p) => ({ ...p })) });
    await act(async () => {
      await Promise.resolve();
    });
    expect(h.markersNear).toHaveBeenCalledTimes(1);
    rerender({ points: [...TRIP, { lon: 129.0, lat: 35.1 }] });
    await act(async () => {
      await Promise.resolve();
    });
    expect(h.markersNear).toHaveBeenCalledTimes(2);
    expect(h.markersNear.mock.calls[1]?.[0].points).toHaveLength(3);
  });
});
