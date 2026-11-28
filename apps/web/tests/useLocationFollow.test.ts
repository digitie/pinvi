import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { LocationErrorCode } from '@pinvi/hooks';
import type { MapLibreMap } from '@/components/map/vworldPrimitives';
import {
  CLUSTER_MARKER_SELECTOR,
  FOLLOW_INITIAL_ZOOM,
  useLocationFollow,
  type WatchPositionSource,
} from '@/lib/useLocationFollow';

function fakeSource() {
  const state = {
    onPosition: null as ((coord: [number, number]) => void) | null,
    onError: null as ((code: LocationErrorCode) => void) | null,
    stopped: 0,
    started: 0,
  };
  const source: WatchPositionSource = {
    watch(onPosition, onError) {
      state.started += 1;
      state.onPosition = onPosition;
      state.onError = onError;
      return () => {
        state.stopped += 1;
      };
    },
  };
  return { state, source };
}

type Handler = (event?: { originalEvent?: Event }) => void;

/**
 * MapLibre 6.17 카메라를 흉내 낸 가짜 지도: 카메라 호출은 그 안에서 `movestart`를 동기로 내고, 진행 중인 이동을
 * 끊으면 끊긴 이동의 `moveend`를 먼저 낸 뒤 새 `movestart`를 낸다(`_stop` → `_afterEase` → `_prepareEase`).
 */
function fakeMap(zoom = 10) {
  const handlers = new Map<string, Handler>();
  const container = document.createElement('div');
  let moving = false;
  let center: [number, number] = [127, 37.5];
  let target: [number, number] | null = null;
  const fire = (type: string) => handlers.get(type)?.({});
  const startCamera = (options: { center?: [number, number] }) => {
    if (moving) {
      moving = false;
      fire('moveend');
    }
    target = options.center ?? null;
    moving = true;
    fire('movestart');
  };
  const map = {
    getZoom: vi.fn(() => zoom),
    flyTo: vi.fn(startCamera),
    easeTo: vi.fn(startCamera),
    panBy: vi.fn(() => startCamera({ center: [center[0] + 0.001, center[1]] })),
    fitBounds: vi.fn(() => startCamera({ center: [129, 35] })),
    isMoving: vi.fn(() => moving),
    getCenter: vi.fn(() => ({ lng: center[0], lat: center[1] })),
    getContainer: vi.fn(() => container),
    on: vi.fn((type: string, fn: Handler) => handlers.set(type, fn)),
    off: vi.fn((type: string) => handlers.delete(type)),
  };
  return {
    map,
    container,
    drag: () => handlers.get('dragstart')?.(),
    move: (originalEvent?: Event) => handlers.get('move')?.({ originalEvent }),
    moveEnd: () => {
      moving = false;
      if (target) center = target;
      target = null;
      fire('moveend');
    },
  };
}

function setup({ consent = true } = {}) {
  const { state, source } = fakeSource();
  const { map, container, drag, move, moveEnd } = fakeMap();
  const ensureConsent = vi.fn(async () => consent);
  const hook = renderHook(() =>
    useLocationFollow({
      getMap: () => map as unknown as MapLibreMap,
      ensureConsent,
      source,
    }),
  );
  return { hook, state, map, container, drag, move, moveEnd, ensureConsent };
}

describe('useLocationFollow(내 위치 따라가기)', () => {
  it('누르면 동의 확인 → 측위 → 첫 위치로 가까운 줌 이동, 따라가기 켜짐', async () => {
    const { hook, state, map, ensureConsent } = setup();
    await act(() => hook.result.current.activate());
    expect(ensureConsent).toHaveBeenCalledTimes(1);
    expect(hook.result.current.mode).toBe('locating');
    act(() => state.onPosition?.([127.1, 37.5]));
    expect(hook.result.current.mode).toBe('follow');
    expect(hook.result.current.position).toEqual([127.1, 37.5]);
    expect(map.flyTo).toHaveBeenCalledWith({ center: [127.1, 37.5], zoom: FOLLOW_INITIAL_ZOOM });
  });

  it('따라가는 동안 위치가 바뀌면 지도 중심이 따라간다(줌은 그대로)', async () => {
    const { hook, state, map } = setup();
    await act(() => hook.result.current.activate());
    act(() => state.onPosition?.([127.1, 37.5]));
    act(() => state.onPosition?.([127.2, 37.6]));
    expect(map.easeTo).toHaveBeenLastCalledWith({ center: [127.2, 37.6], duration: 600 });
    expect(map.easeTo.mock.calls[0]?.[0]).not.toHaveProperty('zoom');
  });

  it('손으로 지도를 끌면 따라가기만 끄고(점은 계속 갱신), 다시 누르면 돌아와 따라간다', async () => {
    const { hook, state, map, drag, ensureConsent } = setup();
    await act(() => hook.result.current.activate());
    act(() => state.onPosition?.([127.1, 37.5]));
    act(() => drag());
    expect(hook.result.current.mode).toBe('tracking');
    map.easeTo.mockClear();
    act(() => state.onPosition?.([127.3, 37.7]));
    expect(hook.result.current.position).toEqual([127.3, 37.7]);
    expect(map.easeTo).not.toHaveBeenCalled();

    await act(() => hook.result.current.activate());
    expect(hook.result.current.mode).toBe('follow');
    expect(map.easeTo).toHaveBeenCalledWith({ center: [127.3, 37.7], duration: 500 });
    // 돌아올 때는 동의를 다시 묻지도, 측위를 새로 시작하지도 않는다.
    expect(ensureConsent).toHaveBeenCalledTimes(1);
    expect(state.started).toBe(1);
  });

  it('동의가 없으면 측위를 시작하지 않는다(호출부가 동의 다이얼로그를 띄운다)', async () => {
    const { hook, state } = setup({ consent: false });
    await act(() => hook.result.current.activate());
    expect(state.started).toBe(0);
    expect(hook.result.current.mode).toBe('off');
  });

  it('권한 거부면 안내를 보이고 꺼진다, 화면을 떠나면 측위를 멈춘다', async () => {
    const { hook, state } = setup();
    await act(() => hook.result.current.activate());
    act(() => state.onError?.('PERMISSION_DENIED'));
    expect(hook.result.current.mode).toBe('off');
    expect(hook.result.current.error).toContain('위치 권한');
    expect(state.stopped).toBe(1);

    await act(() => hook.result.current.activate());
    act(() => state.onPosition?.([127.1, 37.5]));
    hook.unmount();
    expect(state.stopped).toBe(2);
  });
});

describe('useLocationFollow — 첫 위치가 지도 로드보다 먼저 올 때', () => {
  it('지도가 준비되면 붙여 그 위치로 옮기고, 그 뒤 끌기로 따라가기가 풀린다', async () => {
    vi.useFakeTimers();
    try {
      const { state, source } = fakeSource();
      const { map, drag } = fakeMap();
      let ready: typeof map | null = null;
      const hook = renderHook(() =>
        useLocationFollow({
          getMap: () => ready as unknown as MapLibreMap | null,
          ensureConsent: async () => true,
          source,
        }),
      );
      await act(() => hook.result.current.activate());
      act(() => state.onPosition?.([127.1, 37.5]));
      expect(hook.result.current.mode).toBe('follow');
      expect(map.flyTo).not.toHaveBeenCalled();

      ready = map;
      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(map.flyTo).toHaveBeenCalledWith({ center: [127.1, 37.5], zoom: FOLLOW_INITIAL_ZOOM });
      act(() => drag());
      expect(hook.result.current.mode).toBe('tracking');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('useLocationFollow — 카메라 애니메이션 중 끌기·준비 상태(#759 CI 경합)', () => {
  it('따라가기 카메라가 움직이는 동안에도 손으로 옮기면(마우스·터치 move) 따라가기가 풀린다', async () => {
    const { hook, state, move } = setup();
    await act(() => hook.result.current.activate());
    act(() => state.onPosition?.([127.1, 37.5]));
    expect(hook.result.current.mode).toBe('follow');
    // 우리가 부른 이동(originalEvent 없음)·휠 확대는 풀지 않는다.
    act(() => move());
    act(() => move(new WheelEvent('wheel')));
    expect(hook.result.current.mode).toBe('follow');
    act(() => move(new MouseEvent('mousemove')));
    expect(hook.result.current.mode).toBe('tracking');
  });

  it('ready는 지도에 붙고 따라가기 카메라 이동이 끝난 뒤에만 true', async () => {
    const { hook, state, moveEnd } = setup();
    expect(hook.result.current.ready).toBe(false);
    await act(() => hook.result.current.activate());
    act(() => state.onPosition?.([127.1, 37.5]));
    // flyTo가 진행 중 — 아직 준비 아님(다음 프레임에도 isMoving이 true).
    await act(() => new Promise((resolve) => requestAnimationFrame(() => resolve(undefined))));
    expect(hook.result.current.ready).toBe(false);
    act(() => moveEnd());
    expect(hook.result.current.ready).toBe(true);
  });
});

describe('useLocationFollow — 사용자가 고른 이동과 화면이 알아서 하는 이동(2026-11-28 "dmz 자생" 보고)', () => {
  // 보고: 따라가기 중 "dmz 자생" 검색 → DMZ 자생식물원 선택 → 다음 위치 갱신이 지도를 내 위치로 되돌려 지도가
  // 리셋되는 듯 검색한 장소가 사라졌다.
  async function following() {
    const ctx = setup();
    await act(() => ctx.hook.result.current.activate());
    act(() => ctx.state.onPosition?.([127.1, 37.5]));
    act(() => ctx.moveEnd()); // 첫 flyTo가 내 위치에 선다.
    expect(ctx.hook.result.current.mode).toBe('follow');
    ctx.map.easeTo.mockClear();
    ctx.map.flyTo.mockClear();
    return ctx;
  }

  it('따라가기 이동 중 검색 선택 flyTo가 끼어들면 따라가기를 끄고, 이후 위치 갱신이 지도를 되돌리지 않는다', async () => {
    const { hook, state, map, moveEnd } = await following();
    // 따라가기 easeTo가 진행 중이다.
    act(() => state.onPosition?.([127.1001, 37.5001]));
    expect(map.easeTo).toHaveBeenCalledTimes(1);
    expect(map.isMoving()).toBe(true);
    // FeatureMapView.handleSearchSelect: 알린 뒤 flyTo — 가짜 지도는 진행 중 ease의 moveend를 먼저 낸다.
    act(() => {
      hook.result.current.notifyUserMove();
      map.flyTo({ center: [128.12, 38.28] });
    });
    expect(hook.result.current.mode).toBe('tracking');
    act(() => state.onPosition?.([127.1002, 37.5002]));
    act(() => state.onPosition?.([127.1003, 37.5003]));
    expect(map.easeTo).toHaveBeenCalledTimes(1);
    expect(hook.result.current.position).toEqual([127.1003, 37.5003]);
    act(() => moveEnd());
    expect(map.getCenter()).toEqual({ lng: 128.12, lat: 38.28 });
    expect(hook.result.current.ready).toBe(true);
    // 다시 누르면 내 위치로 돌아와 따라간다.
    await act(() => hook.result.current.activate());
    expect(hook.result.current.mode).toBe('follow');
    expect(map.easeTo).toHaveBeenLastCalledWith({ center: [127.1003, 37.5003], duration: 500 });
  });

  it('화면이 알아서 하는 이동(여행 재맞춤 fitBounds·popup 비키기 panBy·resize)은 따라가기를 끄지 않는다', async () => {
    const { hook, state, map, moveEnd } = await following();
    act(() => {
      map.fitBounds();
    });
    act(() => moveEnd());
    act(() => {
      map.panBy();
    });
    act(() => moveEnd());
    expect(hook.result.current.mode).toBe('follow');
    act(() => state.onPosition?.([127.11, 37.51]));
    expect(map.easeTo).toHaveBeenCalledWith({ center: [127.11, 37.51], duration: 600 });
  });

  it('기본 묶음 거품 클릭(라이브러리가 직접 flyTo)도 고른 이동으로 보고 따라가기를 끈다', async () => {
    const { hook, container } = await following();
    const bubble = document.createElement('div');
    bubble.dataset.isCluster = 'true';
    const label = document.createElement('span');
    bubble.append(label);
    container.append(bubble);
    // 거품의 click 핸들러는 전파를 막는다 — 캡처 단계에서 본다.
    bubble.addEventListener('click', (event) => event.stopPropagation());
    expect(bubble.matches(CLUSTER_MARKER_SELECTOR)).toBe(true);
    act(() => label.click());
    expect(hook.result.current.mode).toBe('tracking');
  });

  it('첫 위치를 기다리는 동안 장소를 고르면 첫 위치가 그 이동을 끊지 않고 점만 찍는다', async () => {
    const { hook, state, map } = setup();
    await act(() => hook.result.current.activate());
    expect(hook.result.current.mode).toBe('locating');
    act(() => {
      hook.result.current.notifyUserMove();
      map.flyTo({ center: [128.12, 38.28] });
    });
    map.flyTo.mockClear();
    act(() => state.onPosition?.([127.1, 37.5]));
    expect(map.flyTo).not.toHaveBeenCalled();
    expect(map.easeTo).not.toHaveBeenCalled();
    expect(hook.result.current.mode).toBe('tracking');
    expect(hook.result.current.position).toEqual([127.1, 37.5]);
  });

  it('지도가 늦게 붙는 경로에서도 그 사이 고른 이동이 있었으면 카메라를 옮기지 않는다', async () => {
    vi.useFakeTimers();
    try {
      const { state, source } = fakeSource();
      const { map } = fakeMap();
      let ready: typeof map | null = null;
      const hook = renderHook(() =>
        useLocationFollow({
          getMap: () => ready as unknown as MapLibreMap | null,
          ensureConsent: async () => true,
          source,
        }),
      );
      await act(() => hook.result.current.activate());
      act(() => state.onPosition?.([127.1, 37.5]));
      expect(hook.result.current.mode).toBe('follow');
      act(() => hook.result.current.notifyUserMove());
      ready = map;
      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(map.flyTo).not.toHaveBeenCalled();
      expect(hook.result.current.mode).toBe('tracking');
    } finally {
      vi.useRealTimers();
    }
  });

  it('따라가는 중에 버튼을 다시 누르면 카메라를 다시 잡는다(어떤 이동이 남아 있어도 복구)', async () => {
    const { hook, state, map } = await following();
    act(() => state.onPosition?.([127.2, 37.6]));
    map.easeTo.mockClear();
    await act(() => hook.result.current.activate());
    expect(hook.result.current.mode).toBe('follow');
    expect(map.easeTo).toHaveBeenCalledWith({ center: [127.2, 37.6], duration: 500 });
  });
});
