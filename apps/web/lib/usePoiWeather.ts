'use client';

/**
 * 장소별 현재 날씨 카드(`GET /trips/{id}/pois/{poi}/weather`) 공유 캐시.
 *
 * 장소 목록의 배지, 날씨 팝업, 장소 정보 패널이 같은 장소의 카드를 한 번만 받아 나눠 쓴다.
 * - 동시 요청은 `MAX_CONCURRENT`개로 제한한다 — 날씨 한 건이 수십 초 걸리는 일이 있어(2026-11-02 prod
 *   점검) 목록의 장소 수만큼 한꺼번에 보내면 브라우저 연결 슬롯을 다 잡아 다른 요청이 줄을 선다.
 * - 아직 보내지 않은 요청은 구독자가 모두 사라지면(행이 화면에서 빠지면) 큐에서 뺀다.
 * - 성공은 `FRESH_MS`, 실패는 `RETRY_MS` 동안 다시 묻지 않는다. 실패는 조용히 빈 상태로 둔다.
 */
import { poiApi } from '@pinvi/api-client';
import type { FeatureWeatherCard } from '@pinvi/schemas';
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { apiClient } from '@/lib/api';

const MAX_CONCURRENT = 2;
const FRESH_MS = 10 * 60_000;
const RETRY_MS = 60_000;

export type PoiWeatherState =
  | { status: 'idle' }
  | { status: 'loading'; card: FeatureWeatherCard | null }
  | { status: 'ready'; card: FeatureWeatherCard; fetchedAt: number }
  | { status: 'error'; card: FeatureWeatherCard | null; fetchedAt: number };

type Loader = (tripId: string, poiId: string) => Promise<FeatureWeatherCard>;

const IDLE: PoiWeatherState = { status: 'idle' };
const states = new Map<string, PoiWeatherState>();
const listeners = new Map<string, Set<() => void>>();
const queue: string[] = [];
let running = 0;
let loader: Loader = (tripId, poiId) => poiApi(apiClient).weather(tripId, poiId);

function cacheKey(tripId: string, poiId: string): string {
  return `${tripId}/${poiId}`;
}

function setState(key: string, state: PoiWeatherState) {
  states.set(key, state);
  listeners.get(key)?.forEach((listener) => listener());
}

function previousCard(key: string): FeatureWeatherCard | null {
  const state = states.get(key);
  return state && 'card' in state ? state.card : null;
}

function pump() {
  while (running < MAX_CONCURRENT && queue.length > 0) {
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

function subscribe(key: string, listener: () => void): () => void {
  let set = listeners.get(key);
  if (!set) {
    set = new Set();
    listeners.set(key, set);
  }
  set.add(listener);
  return () => {
    set.delete(listener);
    if (set.size === 0) listeners.delete(key);
  };
}

/** 장소 하나의 날씨 카드. `poiId`가 없으면 아무것도 요청하지 않는다. */
export function usePoiWeather(
  tripId: string | null | undefined,
  poiId: string | null | undefined,
): PoiWeatherState & { refresh: () => void } {
  const key = tripId && poiId ? cacheKey(tripId, poiId) : null;
  const state = useSyncExternalStore(
    useCallback((listener: () => void) => (key ? subscribe(key, listener) : () => {}), [key]),
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

/** 여행(또는 그 한 장소)의 캐시를 비우고, 화면에 있는 장소는 다시 받는다(날씨 새로고침 버튼용). */
export function refreshPoiWeather(tripId: string, poiId?: string): void {
  const prefix = poiId ? cacheKey(tripId, poiId) : `${tripId}/`;
  for (const key of [...states.keys()]) {
    if (poiId ? key === prefix : key.startsWith(prefix)) {
      if (listeners.get(key)?.size) ensure(key, true);
      else states.delete(key);
    }
  }
}

/** 테스트 전용 — 캐시를 비우고 loader를 바꾼다. */
export function __resetPoiWeatherForTest(next?: Loader): void {
  states.clear();
  listeners.clear();
  queue.length = 0;
  running = 0;
  minuteNow = 0;
  loader = next ?? ((tripId, poiId) => poiApi(apiClient).weather(tripId, poiId));
}
