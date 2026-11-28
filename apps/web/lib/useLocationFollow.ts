'use client';

/**
 * 지도 "내 위치" 버튼 — 구글·네이버 지도 방식의 따라가기(follow) 모드.
 *
 * - 처음 누르면 위치 동의(LBS 제15·16조)를 서버에서 확인하고, 동의가 있으면 `watchPosition`을 시작한다.
 *   첫 위치에서 지도를 가까운 줌으로 옮기고 **따라가기**를 켠다.
 * - 따라가는 동안 위치가 바뀌면 지도 중심이 그 위치로 부드럽게 옮겨진다(줌은 그대로).
 * - 사용자가 지도를 손으로 끌면(`dragstart`) 따라가기만 끈다 — 파란 점은 계속 갱신된다.
 *   다시 누르면 현재 위치로 돌아가 따라가기를 다시 켠다.
 * - 사용자가 **고른** 이동(검색 결과 선택, 목록에서 장소 선택, 묶음 펼치기, "여기서 주변 보기")도 따라가기를
 *   끈다. 호출부가 카메라를 옮기기 직전에 `notifyUserMove()`로 알린다(라이브러리 묶음 거품 클릭은 이 훅이 지도
 *   DOM에서 직접 알아챈다). 그러지 않으면 다음 위치 갱신이 지도를 내 위치로 되돌려 방금 고른 장소가 화면 밖으로
 *   사라진다(2026-11-28 소유자 보고 "dmz 자생" 검색 → 선택 → 지도가 리셋되는 듯 검색 결과가 사라짐).
 * - 화면이 **알아서** 하는 이동(여행 장소 재맞춤, popup 비키기, resize, 자동 센터링)은 따라가기를 끄지 않는다.
 *   그런 이동도 사용자 선택 이동도 원본 이벤트가 없어 `movestart`로는 가를 수 없으므로 추론하지 않고, 의도는
 *   호출부가 명시한다. 여행 지도는 따라가는 동안 자동 재맞춤을 하지 않는다(`isFollowing()`).
 * - 화면을 떠나면 측위를 멈춘다. 좌표는 화면 상태로만 들고 저장하거나 보내지 않는다.
 */

import type { LocationErrorCode } from '@pinvi/hooks';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { MapLibreMap } from '@/components/map/vworldPrimitives';

export type LocationFollowMode = 'off' | 'locating' | 'follow' | 'tracking';

/** 처음 위치로 옮길 때의 줌 — 탐색 지도 "내 위치"와 같은 거리감(동네 단위). */
export const FOLLOW_INITIAL_ZOOM = 15;

/** vworld-map-web `ClusterMarker`가 마커 루트에 다는 표시 — 기본 묶음 거품은 라이브러리가 직접 flyTo한다. */
export const CLUSTER_MARKER_SELECTOR = '[data-is-cluster="true"]';

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

/** 손으로 지도를 옮기는 원본 이벤트(마우스·터치·포인터 이동). 휠 확대 등은 따라가기를 풀지 않는다. */
export function isUserPanEvent(event: Event): boolean {
  return /^(mouse|touch|pointer)move$/.test(event.type);
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
  // 우리가 부른 카메라 이동(flyTo/easeTo)이 진행 중인가 — 끝나면(moveend) false. 화면·검사가 "따라가기 시점이
  // 자리 잡았다"를 알 수 있게 `ready`로 내보낸다.
  const [cameraMoving, setCameraMoving] = useState(false);
  // 첫 위치를 기다리는 동안(`locating`) 사용자가 장소를 골라 지도를 옮겼는가 — 그러면 첫 위치에서 카메라를
  // 빼앗지 않고 점만 찍는다(`tracking`).
  const movedWhileLocatingRef = useRef(false);
  const modeRef = useRef<LocationFollowMode>('off');
  const getMapRef = useRef(getMap);
  useEffect(() => {
    getMapRef.current = getMap;
  }, [getMap]);

  const changeMode = useCallback((next: LocationFollowMode) => {
    modeRef.current = next;
    setMode(next);
  }, []);

  /**
   * 사용자가 고른 카메라 이동(검색 결과 선택·목록 선택·묶음 펼치기·"여기서 주변 보기")을 **옮기기 직전에** 알린다.
   * 따라가는 중이면 따라가기를 끄고(점은 계속 갱신), 첫 위치를 기다리는 중이면 첫 위치에서 카메라를 옮기지 않게
   * 한다. 화면이 알아서 하는 이동(재맞춤·popup 비키기)에는 부르지 않는다.
   */
  const notifyUserMove = useCallback(() => {
    if (modeRef.current === 'follow') changeMode('tracking');
    else if (modeRef.current === 'locating') movedWhileLocatingRef.current = true;
  }, [changeMode]);

  const moveCamera = useCallback(
    (map: MapLibreMap | null, kind: 'fly' | 'ease', center: [number, number], duration?: number) => {
      if (!map) return;
      setCameraMoving(true);
      if (kind === 'fly') {
        map.flyTo({ center, zoom: Math.max(map.getZoom(), FOLLOW_INITIAL_ZOOM) });
      } else {
        map.easeTo({ center, duration });
      }
      // maplibre-gl 6.17은 제자리 이동에도 moveend를 낸다. 이 다음 프레임 확인은 moveend를 놓쳐도(다른 moveend
      // 리스너의 예외 등) `ready`가 묶이지 않게 하는 무해한 중복 안전장치다.
      requestAnimationFrame(() => {
        if (typeof map.isMoving !== 'function' || !map.isMoving()) setCameraMoving(false);
      });
    },
    [],
  );

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
          // 기다리는 동안 사용자가 장소를 골라 지도를 옮겼으면 그 이동(검색 flyTo 등)을 끊지 않는다.
          if (movedWhileLocatingRef.current) {
            changeMode('tracking');
            return;
          }
          changeMode('follow');
          moveCamera(map, 'fly', coord);
          return;
        }
        if (modeRef.current === 'follow') moveCamera(map, 'ease', coord, 600);
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
  }, [watching, source, changeMode, moveCamera]);

  // 첫 위치가 지도 로드보다 먼저 오면(버튼을 일찍 누름) 지도를 기다렸다가 붙이고, 따라가는 중이면 그때
  // 위치로 옮긴다 — 그러지 않으면 끌기 감지가 붙지 않아 따라가기가 풀리지 않는다. 그 사이 사용자가 장소를
  // 골랐으면 `notifyUserMove`가 이미 `tracking`으로 바꿔 두었으므로 옮기지 않는다.
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
      if (modeRef.current === 'follow' && at) moveCamera(map, 'fly', at);
    }, 250);
    return () => {
      clearInterval(timer);
    };
  }, [mode, followMap, moveCamera]);

  // 손으로 끈 이동만 따라가기를 끈다(구글·네이버). 우리가 부른 easeTo/flyTo는 originalEvent가 없다.
  // 따라가기 카메라 애니메이션 도중에 끌어도 사용자 의도다 — dragstart만 보면 애니메이션 중 끌기가 놓일 수
  // 있어(CI #759 canvas 1회) 마우스·터치·포인터 원본 이벤트가 있는 move도 함께 본다.
  useEffect(() => {
    if (!followMap) return undefined;
    // 손으로 옮긴 것도 고른 이동이다 — 따라가는 중이면 끄고, (지도가 이미 붙은) 첫 위치 대기 중이면 첫 위치가
    // 카메라를 뺏지 않게 표시한다.
    const release = notifyUserMove;
    const handleMove = (event: { originalEvent?: Event }) => {
      if (event.originalEvent && isUserPanEvent(event.originalEvent)) release();
    };
    const handleMoveEnd = () => setCameraMoving(false);
    followMap.on('dragstart', release);
    followMap.on('move', handleMove);
    followMap.on('moveend', handleMoveEnd);
    return () => {
      followMap.off('dragstart', release);
      followMap.off('move', handleMove);
      followMap.off('moveend', handleMoveEnd);
    };
  }, [followMap, notifyUserMove]);

  // 기본 묶음 거품(`ClusterLayer`에 renderCluster가 없을 때)은 라이브러리가 직접 flyTo해 호출부가 알릴 틈이 없다.
  // 거품의 click 핸들러는 전파를 막으므로 지도 컨테이너에서 캡처 단계로 본다(사용자 클릭 = 고른 이동). 첫 위치를
  // 기다리는 동안(`locating`)의 클릭도 잡아야 첫 위치가 카메라를 뺏지 않으므로, 측위를 시작하면 지도가 있는 즉시
  // 붙인다(없으면 생길 때까지 250ms마다 확인).
  useEffect(() => {
    if (!watching) return undefined;
    let container: HTMLElement | null = null;
    const handleClusterClick = (event: Event) => {
      const target = event.target;
      if (target instanceof Element && target.closest(CLUSTER_MARKER_SELECTOR)) notifyUserMove();
    };
    const attach = () => {
      const map = getMapRef.current();
      if (!map) return false;
      container = map.getContainer();
      container.addEventListener('click', handleClusterClick, true);
      return true;
    };
    const timer = attach()
      ? null
      : setInterval(() => {
          if (attach() && timer) clearInterval(timer);
        }, 250);
    return () => {
      if (timer) clearInterval(timer);
      container?.removeEventListener('click', handleClusterClick, true);
    };
  }, [watching, notifyUserMove]);

  const startWatch = useCallback(() => {
    if (modeRef.current !== 'off') return;
    movedWhileLocatingRef.current = false;
    changeMode('locating');
    setError(null);
    setWatching(true);
  }, [changeMode]);

  /** 따라가는 중인가 — 화면이 자동 맞춤을 건너뛸지 콜백·effect 안에서 읽는다(렌더 중에는 `mode`를 쓴다). */
  const isFollowing = useCallback(() => modeRef.current === 'follow', []);

  /**
   * 버튼 동작: 꺼짐 → 동의 확인 후 시작 / 따라가기 꺼짐·따라가는 중 → 현재 위치로 돌아가 (다시) 따라가기.
   * 따라가는 중에 눌러도 카메라를 다시 잡는다 — 무엇이 지도를 옮겨 두었든 버튼 한 번으로 복구된다.
   */
  const activate = useCallback(async () => {
    if ((modeRef.current === 'tracking' || modeRef.current === 'follow') && position) {
      changeMode('follow');
      moveCamera(getMapRef.current(), 'ease', position, 500);
      return;
    }
    if (modeRef.current !== 'off') return;
    if (!(await ensureConsent())) return;
    startWatch();
  }, [changeMode, ensureConsent, moveCamera, position, startWatch]);

  // 따라가기(또는 해제) 중 지도에 붙었고 우리가 부른 카메라 이동이 끝났다 — 이 뒤의 끌기는 확실히 사용자 이동이다.
  const ready = mode !== 'off' && mode !== 'locating' && followMap != null && !cameraMoving;

  return {
    mode,
    position,
    error,
    ready,
    activate,
    notifyUserMove,
    isFollowing,
    startWatch,
    stop,
    clearError: () => setError(null),
  };
}
