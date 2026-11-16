'use client';

import { apiClient } from '@/lib/api';
import { ApiError, poiApi } from '@pinvi/api-client';
import type { ExternalEnrichment, PoiPlaceDetails } from '@pinvi/schemas';
import { useCallback, useEffect, useState } from 'react';

export type PlaceDetailsState =
  | { status: 'loading'; data: PoiPlaceDetails | null }
  | { status: 'ready'; data: PoiPlaceDetails }
  | { status: 'error'; data: null };

export type PlaceDetailsRefreshState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'done' }
  | { status: 'error'; message: string };

function refreshErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    const wait = error.retryAfterSeconds ?? null;
    return wait ? `${wait}초 뒤에 다시 읽어올 수 있습니다.` : '잠시 뒤에 다시 읽어올 수 있습니다.';
  }
  if (error instanceof ApiError && error.status === 403) {
    return '이 여행을 편집할 수 있는 사람만 다시 읽어올 수 있습니다.';
  }
  return '장소 정보를 다시 읽어오지 못했습니다. 잠시 뒤 다시 시도해 주세요.';
}

/**
 * 장소 영업 정보(`GET …/place-details`) — 처음 쓸 때 한 번 받는다. 실패는 조용히 빈 상태다.
 * 장소가 바뀌면 호출부가 key로 컴포넌트를 새로 만든다(초기 상태가 곧 loading).
 * `refresh`는 "다시 읽어오기"(`POST …/refresh`) — 성공하면 값을 바꾸고, 실패해도 기존 값을 둔다.
 */
export function usePlaceDetails(tripId: string, poiId: string) {
  const [state, setState] = useState<PlaceDetailsState>({ status: 'loading', data: null });
  const [refreshState, setRefreshState] = useState<PlaceDetailsRefreshState>({ status: 'idle' });
  useEffect(() => {
    const controller = new AbortController();
    poiApi(apiClient)
      .placeDetails(tripId, poiId, { signal: controller.signal })
      .then(
        (data) => {
          if (!controller.signal.aborted) setState({ status: 'ready', data });
        },
        () => {
          if (!controller.signal.aborted) setState({ status: 'error', data: null });
        },
      );
    return () => controller.abort();
  }, [tripId, poiId]);

  const refresh = useCallback(() => {
    setRefreshState({ status: 'loading' });
    poiApi(apiClient)
      .refreshPlaceDetails(tripId, poiId)
      .then(
        (data) => {
          setState({ status: 'ready', data });
          setRefreshState({ status: 'done' });
        },
        (error: unknown) =>
          setRefreshState({ status: 'error', message: refreshErrorMessage(error) }),
      );
  }, [tripId, poiId]);

  return { state, refreshState, refresh };
}

// 세션 메모리 캐시 — 같은 장소의 영업 정보를 다시 펼칠 때 Kakao를 또 부르지 않는다(저장하지 않음).
const kakaoPhoneCache = new Map<string, ExternalEnrichment>();

/** 테스트 전용. */
export function __clearKakaoPhoneCacheForTest(): void {
  kakaoPhoneCache.clear();
}

/**
 * 저장된 전화가 없을 때만(`enabled`) Kakao Local 라이브 전화를 받는다(ADR-054 — 표시 전용, 미저장).
 * 못 찾거나 실패하면 null이다(조용히).
 */
export function useKakaoPhone(
  tripId: string,
  poiId: string,
  enabled: boolean,
): ExternalEnrichment | null {
  const key = `${tripId}/${poiId}`;
  const [result, setResult] = useState<{ key: string; value: ExternalEnrichment } | null>(null);
  useEffect(() => {
    if (!enabled || kakaoPhoneCache.has(key)) return;
    const controller = new AbortController();
    poiApi(apiClient)
      .kakaoPhone(tripId, poiId, { signal: controller.signal })
      .then(
        (value) => {
          if (controller.signal.aborted) return;
          kakaoPhoneCache.set(key, value);
          setResult({ key, value });
        },
        () => {
          // 선택 정보 — 실패는 표시하지 않는다.
        },
      );
    return () => controller.abort();
  }, [enabled, key, tripId, poiId]);
  if (!enabled) return null;
  const value = kakaoPhoneCache.get(key) ?? (result?.key === key ? result.value : null);
  return value?.matched && value.phone ? value : null;
}
