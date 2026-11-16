'use client';

/**
 * 지도 "내 위치" 버튼 — 구글·네이버 지도 방식의 따라가기(follow) 모드.
 *
 * - 처음 누르면 위치 동의(LBS 제15·16조)를 서버에서 확인하고, 동의가 있으면 `watchPosition`을 시작한다.
 *   첫 위치에서 지도를 가까운 줌으로 옮기고 **따라가기**를 켠다.
 * - 따라가는 동안 위치가 바뀌면 지도 중심이 그 위치로 부드럽게 옮겨진다(줌은 그대로).
 * - 사용자가 지도를 손으로 끌면(`dragstart`) 따라가기만 끈다 — 파란 점은 계속 갱신된다.
 *   다시 누르면 현재 위치로 돌아가 따라가기를 다시 켠다.
 * - 화면을 떠나면 측위를 멈춘다. 좌표는 화면 상태로만 들고 저장하거나 보내지 않는다.
 */

import type { LocationErrorCode } from '@pinvi/hooks';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { MapLibreMap } from '@/components/map/vworldPrimitives';

export type LocationFollowMode = 'off' | 'locating' | 'follow' | 'tracking';

/** 처음 위치로 옮길 때의 줌 — 탐색 지도 "내 위치"와 같은 거리감(동네 단위). */
export const FOLLOW_INITIAL_ZOOM = 15;

export interface WatchPositionSource {
  watch(
    onPosition: (coord: [number, number]) => void,
    onError: (code: LocationErrorCode) => void,
  ): () => void;
}

function errorCode(code: number): LocationErrorCode {
  if (code === 1) return 'PERMISSION_DENIED';
  if (code === 2) return 'POSITION_UNAVAILABLE';
  if (code === 3) return 'TIMEOUT';
  return 'UNKNOWN';
}

/** `navigator.geolocation.watchPosition` 감싸기. 지원하지 않으면 바로 UNSUPPORTED. */
export const browserWatchSource: WatchPositionSource = {
  watch(onPosition, onError) {
    if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
      onError('UNSUPPORTED');
      return () => {};
    }
    const id = navigator.geolocation.watchPosition(
      (position) => onPosition([position.coords.longitude, position.coords.latitude]),
      (err) => onError(errorCode(err.code)),
      { enableHighAccuracy: true, maximumAge: 5_000, timeout: 15_000 },
    );
    return () => navigator.geolocation.clearWatch(id);
  },
};

export function locationErrorMessage(code: LocationErrorCode): string {
  if (code === 'PERMISSION_DENIED') {
    return '위치 권한이 거부되어 있습니다. 브라우저 설정에서 이 사이트의 위치 권한을 허용해 주세요.';
  }
  if (code === 'UNSUPPORTED') return '이 브라우저는 위치를 지원하지 않습니다.';
  return '위치를 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.';
}

export interface UseLocationFollowOptions {
  getMap: () => MapLibreMap | null;
  /** 위치 동의 확인. true면 바로 측위, false면 호출부가 동의 다이얼로그를 띄운다. */
  ensureConsent: () => Promise<boolean>;
  source?: WatchPositionSource;
}

export function useLocationFollow({
  getMap,
  ensureConsent,
  source = browserWatchSource,
}: UseLocationFollowOptions) {
  const [mode, setMode] = useState<LocationFollowMode>('off');
  const [position, setPosition] = useState<[number, number] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 측위 세션 — 켜면 아래 effect가 watch를 시작하고, 끄거나 화면을 떠나면 effect 정리가 멈춘다.
  const [watching, setWatching] = useState(false);
  // 끌기 감지를 붙일 지도(첫 위치 때 정해진다). 붙이고 떼는 일은 effect가 맡는다.
  const [followMap, setFollowMap] = useState<MapLibreMap | null>(null);
  const modeRef = useRef<LocationFollowMode>('off');
  const getMapRef = useRef(getMap);
  useEffect(() => {
    getMapRef.current = getMap;
  }, [getMap]);

  const changeMode = useCallback((next: LocationFollowMode) => {
    modeRef.current = next;
    setMode(next);
  }, []);

  const stop = useCallback(() => {
    setWatching(false);
    changeMode('off');
  }, [changeMode]);

  useEffect(() => {
    if (!watching) return undefined;
    let first = true;
    const unwatch = source.watch(
      (coord) => {
        setPosition(coord);
        const map = getMapRef.current();
        setFollowMap(map);
        if (first) {
          first = false;
          changeMode('follow');
          map?.flyTo({ center: coord, zoom: Math.max(map.getZoom(), FOLLOW_INITIAL_ZOOM) });
          return;
        }
        if (modeRef.current === 'follow') map?.easeTo({ center: coord, duration: 600 });
      },
      (code) => {
        // 일시적 timeout은 watch가 계속 재시도한다 — 아직 위치를 못 받았을 때만 알린다.
        if (code === 'TIMEOUT' && !first) return;
        setError(locationErrorMessage(code));
        setWatching(false);
        changeMode('off');
      },
    );
    return () => {
      unwatch();
    };
  }, [watching, source, changeMode]);

  // 첫 위치가 지도 로드보다 먼저 오면(버튼을 일찍 누름) 지도를 기다렸다가 붙이고, 따라가는 중이면 그때
  // 위치로 옮긴다 — 그러지 않으면 끌기 감지가 붙지 않아 따라가기가 풀리지 않는다.
  const positionRef = useRef<[number, number] | null>(null);
  useEffect(() => {
    positionRef.current = position;
  }, [position]);
  useEffect(() => {
    if (followMap || (mode !== 'follow' && mode !== 'tracking')) return undefined;
    const timer = setInterval(() => {
      const map = getMapRef.current();
      if (!map) return;
      clearInterval(timer);
      setFollowMap(map);
      const at = positionRef.current;
      if (modeRef.current === 'follow' && at) {
        map.flyTo({ center: at, zoom: Math.max(map.getZoom(), FOLLOW_INITIAL_ZOOM) });
      }
    }, 250);
    return () => {
      clearInterval(timer);
    };
  }, [mode, followMap]);

  // 손으로 끈 이동만 따라가기를 끈다. 우리가 부른 easeTo/flyTo는 dragstart를 내지 않는다.
  useEffect(() => {
    if (!followMap) return undefined;
    const handleDragStart = () => {
      if (modeRef.current === 'follow') changeMode('tracking');
    };
    followMap.on('dragstart', handleDragStart);
    return () => {
      followMap.off('dragstart', handleDragStart);
    };
  }, [followMap, changeMode]);

  const startWatch = useCallback(() => {
    if (modeRef.current !== 'off') return;
    changeMode('locating');
    setError(null);
    setWatching(true);
  }, [changeMode]);

  /** 버튼 동작: 꺼짐 → 동의 확인 후 시작 / 따라가기 꺼짐 → 현재 위치로 돌아가 다시 따라가기. */
  const activate = useCallback(async () => {
    if (modeRef.current === 'tracking' && position) {
      changeMode('follow');
      getMapRef.current()?.easeTo({ center: position, duration: 500 });
      return;
    }
    if (modeRef.current !== 'off') return;
    if (!(await ensureConsent())) return;
    startWatch();
  }, [changeMode, ensureConsent, position, startWatch]);

  return { mode, position, error, activate, startWatch, stop, clearError: () => setError(null) };
}
