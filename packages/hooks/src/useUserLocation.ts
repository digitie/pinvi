import { useCallback, useState } from 'react';

/** 사용자 위치 — `docs/architecture/user-location.md` 참고. */
export interface UserLocation {
  coord: { longitude: number; latitude: number };
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
export function useUserLocation(
  adapter: LocationAdapter,
  opts: UseUserLocationOptions = {},
) {
  const [location, setLocation] = useState<UserLocation | null>(null);
  const [error, setError] = useState<LocationError | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchLocation = useCallback(async () => {
    if (opts.enabled === false) return;
    setLoading(true);
    setError(null);
    try {
      const loc = await adapter.getCurrentPosition(opts);
      setLocation(loc);
      opts.on_success?.(loc);
    } catch (rawError) {
      const err = rawError instanceof LocationError
        ? rawError
        : new LocationError('UNKNOWN', String(rawError));
      setError(err);
      opts.on_error?.(err);
    } finally {
      setLoading(false);
    }
  }, [adapter, opts]);

  return { location, error, loading, refresh: fetchLocation } as const;
}
