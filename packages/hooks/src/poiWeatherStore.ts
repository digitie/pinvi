/**
 * 장소별 현재 날씨 카드(`GET /trips/{id}/pois/{poi}/weather`) 공유 캐시 — 웹·모바일 공용.
 *
 * 장소 목록의 배지, 날씨 팝업, 장소 정보 패널이 같은 장소의 카드를 한 번만 받아 나눠 쓴다.
 * - 동시 요청은 `MAX_CONCURRENT`개로 제한한다 — 날씨 한 건이 수십 초 걸리는 일이 있어(2026-11-02 prod
 *   점검) 장소 수만큼 한꺼번에 보내면 연결 슬롯을 다 잡아 다른 요청이 줄을 선다.
 * - 아직 보내지 않은 요청은 구독자가 모두 사라지면(행이 화면에서 빠지면) 큐에서 뺀다.
 * - 성공은 `FRESH_MS`, 실패는 `RETRY_MS` 동안 다시 묻지 않는다. 실패는 조용히 빈 상태로 둔다.
 * - 지도 마커 라벨은 요청을 만들지 않는 구독(`usePoiWeatherPeek`)으로 이미 받은 카드만 읽는다.
 *
 * 카드 타입·요청 함수는 앱이 넣는다(`createPoiWeatherStore(loader)`) — 이 패키지는 API 클라이언트를 모른다.
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';

export const POI_WEATHER_MAX_CONCURRENT = 2;
const FRESH_MS = 10 * 60_000;
const RETRY_MS = 60_000;

export type PoiWeatherState<Card> =
  | { status: 'idle' }
  | { status: 'loading'; card: Card | null }
  | { status: 'ready'; card: Card; fetchedAt: number }
  | { status: 'error'; card: Card | null; fetchedAt: number };

export type PoiWeatherLoader<Card> = (tripId: string, poiId: string) => Promise<Card>;

const IDLE = { status: 'idle' } as const;

export function createPoiWeatherStore<Card>(initialLoader: PoiWeatherLoader<Card>) {
  const states = new Map<string, PoiWeatherState<Card>>();
  const listeners = new Map<string, Set<() => void>>();
  // 요청을 붙잡지 않는 구독(지도 마커 라벨). 큐 정리·새로고침이 "보고 있는 장소"를 셀 때 세지 않는다.
  const peekListeners = new Map<string, Set<() => void>>();
  // 어느 장소든 바뀌면 알린다(여러 마커의 날씨를 한 번에 읽는 지도).
  const anyListeners = new Set<() => void>();
  let version = 0;
  const queue: string[] = [];
  let running = 0;
  let loader = initialLoader;

  const cacheKey = (tripId: string, poiId: string) => `${tripId}/${poiId}`;

  function setState(key: string, state: PoiWeatherState<Card>) {
    states.set(key, state);
    version += 1;
    listeners.get(key)?.forEach((listener) => listener());
    peekListeners.get(key)?.forEach((listener) => listener());
    anyListeners.forEach((listener) => listener());
  }

  function addTo(map: Map<string, Set<() => void>>, key: string, listener: () => void) {
    let set = map.get(key);
    if (!set) {
      set = new Set();
      map.set(key, set);
    }
    set.add(listener);
    return () => {
      set.delete(listener);
      if (set.size === 0) map.delete(key);
    };
  }

  function previousCard(key: string): Card | null {
    const state = states.get(key);
    return state && 'card' in state ? state.card : null;
  }

  function pump() {
    while (running < POI_WEATHER_MAX_CONCURRENT && queue.length > 0) {
      const key = queue.shift()!;
      if (!listeners.get(key)?.size) {
        // 구독자가 없는 대기 요청은 보내지 않는다(다음 구독 때 다시 큐에 들어온다).
        if (states.get(key)?.status === 'loading') states.delete(key);
        continue;
      }
      const [tripId, poiId] = key.split('/') as [string, string];
      running += 1;
      loader(tripId, poiId)
        .then(
          (card) => setState(key, { status: 'ready', card, fetchedAt: Date.now() }),
          () => setState(key, { status: 'error', card: previousCard(key), fetchedAt: Date.now() }),
        )
        .finally(() => {
          running -= 1;
          pump();
        });
    }
  }

  function ensure(key: string, force = false) {
    const state = states.get(key);
    if (state?.status === 'loading') return;
    if (!force && state?.status === 'ready' && Date.now() - state.fetchedAt < FRESH_MS) return;
    if (!force && state?.status === 'error' && Date.now() - state.fetchedAt < RETRY_MS) return;
    setState(key, { status: 'loading', card: previousCard(key) });
    queue.push(key);
    pump();
  }

  /** 장소 하나의 날씨 카드. `tripId`·`poiId` 중 하나라도 없으면 아무것도 요청하지 않는다. */
  function usePoiWeather(
    tripId: string | null | undefined,
    poiId: string | null | undefined,
  ): PoiWeatherState<Card> & { refresh: () => void } {
    const key = tripId && poiId ? cacheKey(tripId, poiId) : null;
    const state = useSyncExternalStore(
      useCallback(
        (listener: () => void) => (key ? addTo(listeners, key, listener) : () => {}),
        [key],
      ),
      () => (key ? (states.get(key) ?? IDLE) : IDLE),
      () => IDLE,
    );
    useEffect(() => {
      if (key) ensure(key);
    }, [key]);
    const refresh = useCallback(() => {
      if (key) ensure(key, true);
    }, [key]);
    return { ...state, refresh };
  }

  /** 요청을 만들지 않고 이미 받은 카드만 읽는다. 없으면 null. */
  function usePoiWeatherPeek(
    tripId: string | null | undefined,
    poiId: string | null | undefined,
  ): Card | null {
    const key = tripId && poiId ? cacheKey(tripId, poiId) : null;
    const state = useSyncExternalStore(
      useCallback(
        (listener: () => void) => (key ? addTo(peekListeners, key, listener) : () => {}),
        [key],
      ),
      () => (key ? (states.get(key) ?? IDLE) : IDLE),
      () => IDLE,
    );
    return 'card' in state ? state.card : null;
  }

  /**
   * 요청 없이 여러 장소의 카드를 읽는다(지도 마커들). 어느 장소든 바뀌면 다시 그린다 — 돌려주는 함수는
   * 렌더 중에 불러 쓴다.
   */
  function usePoiWeatherPeekAll(): (tripId: string, poiId: string) => Card | null {
    const current = useSyncExternalStore(
      useCallback((listener: () => void) => {
        anyListeners.add(listener);
        return () => {
          anyListeners.delete(listener);
        };
      }, []),
      () => version,
      () => 0,
    );
    return useCallback(
      (tripId: string, poiId: string) => {
        void current;
        return previousCard(cacheKey(tripId, poiId));
      },
      [current],
    );
  }

  /** 여행(또는 그 한 장소)의 캐시를 비우고, 화면에 있는 장소는 다시 받는다(날씨 새로고침 버튼용). */
  function refreshPoiWeather(tripId: string, poiId?: string): void {
    const prefix = poiId ? cacheKey(tripId, poiId) : `${tripId}/`;
    for (const key of [...states.keys()]) {
      if (poiId ? key === prefix : key.startsWith(prefix)) {
        if (listeners.get(key)?.size) ensure(key, true);
        else states.delete(key);
      }
    }
  }

  /** 테스트 전용 — 캐시를 비우고 loader를 바꾼다. */
  function reset(next?: PoiWeatherLoader<Card>): void {
    states.clear();
    listeners.clear();
    peekListeners.clear();
    anyListeners.clear();
    queue.length = 0;
    running = 0;
    version = 0;
    loader = next ?? initialLoader;
  }

  return {
    usePoiWeather,
    usePoiWeatherPeek,
    usePoiWeatherPeekAll,
    refreshPoiWeather,
    reset,
  };
}

// 분 단위 공유 시계 — 렌더 중 Date.now()를 직접 부르지 않고(순수성) 모든 배지가 같은 시각을 본다.
let minuteNow = 0;
const clockListeners = new Set<() => void>();
let clockTimer: ReturnType<typeof setInterval> | null = null;

function readClock(): number {
  if (minuteNow === 0) minuteNow = Math.floor(Date.now() / 60_000) * 60_000;
  return minuteNow;
}

function subscribeClock(listener: () => void): () => void {
  clockListeners.add(listener);
  if (!clockTimer) {
    clockTimer = setInterval(() => {
      minuteNow = Math.floor(Date.now() / 60_000) * 60_000;
      clockListeners.forEach((notify) => notify());
    }, 60_000);
  }
  return () => {
    clockListeners.delete(listener);
    if (clockListeners.size === 0 && clockTimer) {
      clearInterval(clockTimer);
      clockTimer = null;
      minuteNow = 0;
    }
  };
}

/** 분 단위로 갱신되는 현재 시각(epoch ms). 서버 렌더에서는 0이다. */
export function useMinuteNow(): number {
  return useSyncExternalStore(subscribeClock, readClock, () => 0);
}

/** 테스트 전용 — 분 시계를 처음 상태로. */
export function __resetMinuteNowForTest(): void {
  minuteNow = 0;
}
