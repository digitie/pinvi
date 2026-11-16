import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { LocationErrorCode } from '@pinvi/hooks';
import type { MapLibreMap } from '@/components/map/vworldPrimitives';
import {
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

function fakeMap(zoom = 10) {
  const handlers = new Map<string, Handler>();
  let moving = false;
  const map = {
    getZoom: vi.fn(() => zoom),
    flyTo: vi.fn(() => {
      moving = true;
    }),
    easeTo: vi.fn(() => {
      moving = true;
    }),
    isMoving: vi.fn(() => moving),
    on: vi.fn((type: string, fn: Handler) => handlers.set(type, fn)),
    off: vi.fn((type: string) => handlers.delete(type)),
  };
  return {
    map,
    drag: () => handlers.get('dragstart')?.(),
    move: (originalEvent?: Event) => handlers.get('move')?.({ originalEvent }),
    moveEnd: () => {
      moving = false;
      handlers.get('moveend')?.();
    },
  };
}

function setup({ consent = true } = {}) {
  const { state, source } = fakeSource();
  const { map, drag, move, moveEnd } = fakeMap();
  const ensureConsent = vi.fn(async () => consent);
  const hook = renderHook(() =>
    useLocationFollow({
      getMap: () => map as unknown as MapLibreMap,
      ensureConsent,
      source,
    }),
  );
  return { hook, state, map, drag, move, moveEnd, ensureConsent };
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
