import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import type { MapLibreMap } from 'vworld-map-web';
import type { FeaturesInBoundsResponse } from '@pinvi/schemas';
import type { GeometryFeature } from '@/lib/featureGeometry';
import { useFeatureGeometry } from '@/lib/useFeatureGeometry';

const { inBounds } = vi.hoisted(() => ({ inBounds: vi.fn() }));
vi.mock('@pinvi/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@pinvi/api-client')>()),
  featureApi: () => ({ inBounds }),
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));

function route(id = 'route:a'): GeometryFeature {
  return {
    feature_id: id,
    kind: 'route',
    name: id,
    coord: null,
    marker_color: 'P-06',
    marker_icon: 'walking',
    geometry: {
      type: 'LineString',
      coordinates: [
        [126, 35],
        [129, 38],
      ],
    },
  };
}
function response(id = 'route:a', truncated = false): FeaturesInBoundsResponse {
  return {
    items: [route(id)],
    clusters: [],
    truncated,
    zoom: 14,
    bbox: { lng_min: 126, lat_min: 35, lng_max: 129, lat_max: 38 },
  };
}
function map(zoom = 14, west = 126) {
  return {
    getZoom: () => zoom,
    getBounds: () => ({
      getWest: () => west,
      getSouth: () => 35,
      getEast: () => west + 0.1,
      getNorth: () => 35.1,
    }),
    cameraForBounds: vi.fn(() => ({ center: [127.5, 36.5], zoom: 9 })),
    easeTo: vi.fn(),
  } as unknown as MapLibreMap;
}
function deferred() {
  let resolve!: (value: FeaturesInBoundsResponse) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<FeaturesInBoundsResponse>((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
}
async function tick() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(250);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  inBounds.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('useFeatureGeometry', () => {
  it('기본 OFF와 공유 비활성 화면은 조회하지 않는다', async () => {
    const { result, rerender } = renderHook(({ active }) => useFeatureGeometry({ active }), {
      initialProps: { active: true },
    });
    act(() => result.current.onViewportChange(map()));
    await tick();
    expect(inBounds).not.toHaveBeenCalled();
    rerender({ active: false });
    act(() => result.current.toggle('route', true));
    await tick();
    expect(result.current.features).toEqual([]);
    expect(inBounds).not.toHaveBeenCalled();
  });
  it.each([13.49, 13.5, 13.999])(
    'zoom %s에서 반올림한 shape 요청도 보내지 않는다',
    async (zoom) => {
      const { result } = renderHook(() => useFeatureGeometry({ active: true }));
      act(() => {
        result.current.onViewportChange(map(zoom));
        result.current.toggle('route', true);
      });
      await tick();
      expect(inBounds).not.toHaveBeenCalled();
      expect(result.current.eligible).toBe(false);
    },
  );
  it('shape 요청을 분리하고 fetch나 pan으로 자동 fit하지 않는다', async () => {
    inBounds.mockResolvedValue(response());
    const viewport = map();
    const { result } = renderHook(() => useFeatureGeometry({ active: true }));
    act(() => {
      result.current.onViewportChange(viewport);
      result.current.toggle('route', true);
    });
    await tick();
    expect(inBounds).toHaveBeenCalledWith(
      expect.objectContaining({
        kinds: ['route'],
        zoom: 14,
        includeGeometry: true,
        limit: 100,
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(result.current.features[0]?.coord).toBeNull();
    expect(viewport.easeTo).not.toHaveBeenCalled();
  });
  it('abort를 무시하는 느린 pan 응답을 버리고 캐시도 오염시키지 않는다', async () => {
    const old = deferred(),
      fresh = deferred();
    inBounds
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(fresh.promise)
      .mockResolvedValue(response('route:again'));
    const { result } = renderHook(() => useFeatureGeometry({ active: true }));
    act(() => {
      result.current.onViewportChange(map());
      result.current.toggle('route', true);
    });
    await tick();
    const oldSignal = inBounds.mock.calls[0]?.[1].signal as AbortSignal;
    act(() => result.current.onViewportChange(map(14, 127)));
    expect(oldSignal.aborted).toBe(true);
    await tick();
    await act(async () => fresh.resolve(response('route:fresh')));
    await act(async () => old.resolve(response('route:old')));
    expect(result.current.features[0]?.feature_id).toBe('route:fresh');
    act(() => result.current.onViewportChange(map()));
    await tick();
    expect(inBounds).toHaveBeenCalledTimes(3);
    expect(result.current.features[0]?.feature_id).toBe('route:again');
  });
  it('캐시 hit 전에 기존 요청을 취소하고 같은 bbox 재이동도 다시 표시한다', async () => {
    const pending = deferred();
    inBounds.mockResolvedValueOnce(response('route:cached')).mockReturnValueOnce(pending.promise);
    const { result } = renderHook(() => useFeatureGeometry({ active: true }));
    act(() => {
      result.current.onViewportChange(map());
      result.current.toggle('route', true);
    });
    await tick();
    act(() => result.current.onViewportChange(map(14, 127)));
    await tick();
    act(() => result.current.onViewportChange(map()));
    await tick();
    await act(async () => pending.resolve(response('route:stale')));
    expect(result.current.features[0]?.feature_id).toBe('route:cached');
    act(() => result.current.onViewportChange(map()));
    await tick();
    expect(result.current.features[0]?.feature_id).toBe('route:cached');
    expect(inBounds).toHaveBeenCalledTimes(2);
  });
  it('OFF/축소/화면 비활성화에서 요청·선택·도형을 무효화한다', async () => {
    const pending = deferred();
    inBounds.mockResolvedValueOnce(response()).mockReturnValueOnce(pending.promise);
    const { result, rerender } = renderHook(({ active }) => useFeatureGeometry({ active }), {
      initialProps: { active: true },
    });
    act(() => {
      result.current.onViewportChange(map());
      result.current.toggle('route', true);
    });
    await tick();
    act(() => result.current.select(route()));
    expect(result.current.selection).not.toBeNull();
    act(() => result.current.toggle('route', false));
    expect(result.current.selection).toBeNull();
    expect(result.current.features).toEqual([]);
    act(() => {
      result.current.toggle('route', true);
      result.current.onViewportChange(map(14, 127));
    });
    await tick();
    act(() => result.current.onViewportChange(map(13.999)));
    expect((inBounds.mock.calls[1]?.[1].signal as AbortSignal).aborted).toBe(true);
    await act(async () => pending.resolve(response('route:stale')));
    expect(result.current.features).toEqual([]);
    rerender({ active: false });
    act(() => result.current.onViewportChange(map()));
    await tick();
    expect(result.current.features).toEqual([]);
    expect(inBounds).toHaveBeenCalledTimes(2);
  });
  it('category 변경은 이전 응답을 버리고 다른 캐시를 쓴다', async () => {
    const pending = deferred();
    inBounds
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce(response('route:new-category'));
    const { result, rerender } = renderHook(
      ({ category }) => useFeatureGeometry({ active: true, category }),
      { initialProps: { category: 'first' } },
    );
    act(() => {
      result.current.onViewportChange(map());
      result.current.toggle('route', true);
    });
    await tick();
    rerender({ category: 'second' });
    await tick();
    await act(async () => pending.resolve(response('route:old-category')));
    expect(result.current.features[0]?.feature_id).toBe('route:new-category');
    expect(inBounds.mock.calls[1]?.[0].category).toBe('second');
  });
  it('숨긴 feature는 목록·도형·기존 선택에서 제외한다', async () => {
    inBounds.mockResolvedValue(response());
    const { result, rerender } = renderHook(
      ({ hiddenFeatureIds }) => useFeatureGeometry({ active: true, hiddenFeatureIds }),
      { initialProps: { hiddenFeatureIds: new Set<string>() } },
    );
    act(() => {
      result.current.onViewportChange(map());
      result.current.toggle('route', true);
    });
    await tick();
    act(() => result.current.select(route()));
    rerender({ hiddenFeatureIds: new Set(['route:a']) });
    expect(result.current.features).toEqual([]);
    expect(result.current.selection).toBeNull();
    act(() => result.current.select(route()));
    expect(result.current.selection).toBeNull();
    expect(inBounds).toHaveBeenCalledTimes(1);
  });
  it('목록 focus는 전체 bounds를 사용하되 큰 도형도 14 미만으로 축소하지 않는다', async () => {
    inBounds.mockResolvedValue(response());
    const viewport = map(),
      onSelect = vi.fn(),
      feature = route();
    const { result } = renderHook(() => useFeatureGeometry({ active: true, onSelect }));
    act(() => {
      result.current.onViewportChange(viewport);
      result.current.toggle('route', true);
    });
    await tick();
    act(() => result.current.select(feature, undefined, true));
    expect(viewport.cameraForBounds).toHaveBeenCalledWith(
      [
        [126, 35],
        [129, 38],
      ],
      { padding: 48, maxZoom: 16 },
    );
    expect(viewport.easeTo).toHaveBeenCalledWith(expect.objectContaining({ zoom: 14 }));
    expect(result.current.selection?.anchor).toEqual([127.5, 36.5]);
    expect(feature.coord).toBeNull();
    expect(onSelect).toHaveBeenCalledWith(feature);
  });
  it('오류 후 재시도와 truncated 표시를 보존한다', async () => {
    inBounds
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(response('route:retry', true));
    const { result } = renderHook(() => useFeatureGeometry({ active: true }));
    act(() => {
      result.current.onViewportChange(map());
      result.current.toggle('route', true);
    });
    await tick();
    expect(result.current.error).toBeTruthy();
    act(() => result.current.retry());
    await tick();
    expect(result.current.error).toBeNull();
    expect(result.current.truncated).toBe(true);
    expect(result.current.features[0]?.feature_id).toBe('route:retry');
  });
});

it('이전 native popup의 늦은 닫기가 같은 도형의 새 선택을 지우지 않는다', async () => {
  inBounds.mockResolvedValue(response());
  const { result } = renderHook(() => useFeatureGeometry({ active: true }));
  act(() => {
    result.current.onViewportChange(map());
    result.current.toggle('route', true);
  });
  await tick();
  act(() => result.current.select(route(), [127, 36]));
  const old = result.current.selection!.revision;
  act(() => result.current.select(route(), [127, 36]));
  const current = result.current.selection!.revision;
  act(() => result.current.clearSelection(old));
  expect(result.current.selection?.revision).toBe(current);
  act(() => result.current.clearSelection(current));
  expect(result.current.selection).toBeNull();
});
