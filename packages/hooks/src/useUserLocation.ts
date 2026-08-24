import { useCallback, useRef, useState } from 'react';

/** 사용자 위치 — `docs/architecture/user-location.md` 참고. */
export interface UserLocation {
  coord: { lon: number; lat: number };
  accuracy_m: number;
  /** epoch ms */
  timestamp: number;
  source: 'gps' | 'wifi' | 'network' | 'ip';
}

export interface LocationOptions {
  high_accuracy?: boolean;
  timeout_ms?: number;
  max_age_ms?: number;
}

export type LocationErrorCode =
  | 'PERMISSION_DENIED'
  | 'POSITION_UNAVAILABLE'
  | 'TIMEOUT'
  | 'UNSUPPORTED'
  | 'UNKNOWN';

export class LocationError extends Error {
  constructor(
    public code: LocationErrorCode,
    message: string,
  ) {
    super(message);
    this.name = 'LocationError';
  }
}

/** 플랫폼 어댑터 — 웹은 `navigator.geolocation`, 모바일은 `expo-location`. */
export interface LocationAdapter {
  getCurrentPosition(opts?: LocationOptions): Promise<UserLocation>;
  /**
   * **프롬프트를 띄우지 않고** 현재 권한 상태만 읽는다(T-325 자동 센터링 게이트).
   * 웹은 Permissions API, 모바일은 `getForegroundPermissionsAsync`. 조회 수단이 없으면
   * `'prompt'`로 답해야 한다 — 낙관적으로 `'granted'`를 돌려주면 진입만으로 권한 프롬프트가 뜬다.
   *
   * optional인 이유는 기존 어댑터 호환이며, 자동 센터링을 쓰는 표면은 반드시 구현해야 한다.
   * 반환 타입을 `@pinvi/domain`의 `LocationPermissionState`와 인라인 union으로 맞춘 것은
   * `@pinvi/hooks`에 domain 의존을 늘리지 않기 위해서다(구조적 타이핑으로 호환).
   */
  getPermissionState?(): Promise<'granted' | 'prompt' | 'denied' | 'unsupported'>;
}

export interface UseUserLocationOptions extends LocationOptions {
  /** 사용자 동의 + 권한이 있을 때만 true. */
  enabled?: boolean;
  on_success?: (loc: UserLocation) => void;
  on_error?: (err: LocationError) => void;
}

/**
 * 공용 위치 hook — `docs/architecture/user-location.md` §3.3.
 * 어댑터를 인자로 받아 web/mobile 분기 회피.
 */
export function useUserLocation(adapter: LocationAdapter, opts: UseUserLocationOptions = {}) {
  const [location, setLocation] = useState<UserLocation | null>(null);
  const [error, setError] = useState<LocationError | null>(null);
  const [loading, setLoading] = useState(false);

  // 호출부는 opts를 객체 리터럴로 넘긴다. deps에 그대로 두면 `refresh`가 매 렌더 새 identity가 되고,
  // effect에서 자동으로 부르는 순간 무한 루프가 된다(T-325). 최신 값만 ref로 읽는다.
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const fetchLocation = useCallback(async () => {
    const current = optsRef.current;
    if (current.enabled === false) return;
    setLoading(true);
    setError(null);
    let acquired: UserLocation | null = null;
    try {
      acquired = await adapter.getCurrentPosition(current);
      setLocation(acquired);
    } catch (rawError) {
      const err =
        rawError instanceof LocationError
          ? rawError
          : new LocationError('UNKNOWN', String(rawError));
      setError(err);
      current.on_error?.(err);
      return;
    } finally {
      setLoading(false);
    }
    // 성공 콜백은 try 밖에서 부른다 — 콜백이 던지는 예외(예: 지도 카메라 API)가
    // `LocationError('UNKNOWN')`으로 둔갑해 "위치를 가져오지 못했습니다"라는 거짓 실패가 되면 안 된다.
    current.on_success?.(acquired);
  }, [adapter]);

  return { location, error, loading, refresh: fetchLocation } as const;
}
