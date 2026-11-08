import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// #686 NEAR-024(mobile): 칩을 켜면 교통 패널이 자라 여행 지도가 다시 맞춰진다. 켠 순간의 bounds로 바로
// 조회하면 요청 bbox가 맞춘 뒤의 실제 지도와 다르다 — 켠 뒤 지도가 멈출 때까지 기다렸다가 조회한다.

const h = vi.hoisted(() => ({
  markersInBounds: vi.fn(),
}));

vi.mock('@pinvi/api-client', () => ({
  transportApi: () => ({
    status: () => Promise.resolve({ enabled: true }),
    markersInBounds: h.markersInBounds,
  }),
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));

import { useTransportLayers } from '@/lib/useTransportLayers';
import { toBboxParam } from '@/lib/featureBounds';
import type { MapLibreMap } from '@/components/map/vworldPrimitives';

function fakeMap(initial: [number, number, number, number]) {
  let box = initial;
  const map = {
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
